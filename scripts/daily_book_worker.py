#!/usr/bin/env python3
"""Daily orchestrator for the Terefo Heal Reboa research book loop.

The worker follows the editorial pipeline: collect/store/sanitize, extract notes/entities/claims,
score and curate, run Editor review, let Author synthesize only from promoted claims, let Book role
publish only when gates pass, then verify and commit only safe curated artifacts.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from research_common import CONFIG_PATH, LOGS, REPORTS, ROOT, connect_db, git_commit_push, init_db, run_id_now, utc_now, write_json

PY = sys.executable
MKDOCS_PY = str(ROOT / ".venv" / "bin" / "python") if (ROOT / ".venv" / "bin" / "python").exists() else PY


def no_write_capabilities() -> dict:
    return {
        "supports_skip_capture": True,
        "supports_optional_visual_capture": True,
        "supports_skip_entity_extraction": True,
        "supports_skip_claim_extraction": True,
        "supports_skip_docs_entities_update": True,
        "supports_skip_docs_claims_update": True,
        "supports_skip_source_registry_export": True,
        "supports_skip_run_table_update": True,
        "supports_skip_vector": True,
        "supports_no_commit": True,
        "supports_no_push": True,
        "supports_no_docs_book_update_without_gate": True,
        "supports_preflight_only": True,
        "supports_all_chapter_public_proof_gate": True,
        "supports_post_processing_chapter_revision_policy": True,
        "supports_existing_chapter_fluent_refactor_rewrite": True,
        "supports_automatic_guarded_new_chapter_queue": True,
        "supports_human_approved_chapter_subject_discovery": True,
        "supports_human_approved_research_pair_creation": True,
        "all_chapter_public_proof_gate_blocks_evidence_led_pages": True,
        "supports_preflight_all_chapter_public_proof": True,
        "preflight_only_no_write": True,
        "capability_probe_no_write": True,
        "human_in_loop_dependency_added": False,
        "author_allowed": False,
        "publication_approved": False,
        "eligible_for_claim_insertion": False,
        "eligible_for_authoring": False,
        "eligible_for_publication": False,
        "chapter_update_allowed": False,
    }


def run(cmd: list[str], log) -> dict:
    log.write('\n$ ' + ' '.join(cmd) + '\n')
    p = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)
    log.write(p.stdout)
    if p.stderr:
        log.write('\n[stderr]\n' + p.stderr)
    return {"cmd": cmd, "returncode": p.returncode, "stdout_tail": p.stdout[-2000:], "stderr_tail": p.stderr[-2000:]}


def script_step(name: str, code: int = 0, msg: str = "") -> dict:
    return {"cmd": [PY, name], "returncode": code, "stdout_tail": msg, "stderr_tail": ""}


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except Exception:
        return default




def run_all_chapter_public_proof(run_id: str) -> dict:
    out = REPORTS / "editorial" / f"{run_id}-all-chapters-public-proof.json"
    cmd = [
        PY,
        "scripts/public_chapter_proof.py",
        "--all-local-book-chapters",
        "--contract-json",
        "config/book_manuscript_production_contract.json",
        "--repo-root",
        ".",
        "--output-json",
        str(out),
    ]
    proc = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)
    data = load_json(out, {})
    return {
        "cmd": cmd,
        "returncode": proc.returncode,
        "stdout_tail": proc.stdout[-2000:],
        "stderr_tail": proc.stderr[-2000:],
        "report": str(out.relative_to(ROOT)),
        "ok": bool(data.get("ok")),
        "total_chapters": data.get("total_chapters"),
        "passed_chapters": data.get("passed_chapters", []),
        "failed_chapters": data.get("failed_chapters", []),
    }


def docs_book_dirty_files() -> list[str]:
    p = subprocess.run(["git", "status", "--short", "--", "docs/book"], cwd=ROOT, text=True, capture_output=True)
    dirty = []
    for line in p.stdout.splitlines():
        if line.strip():
            dirty.append(line[3:] if len(line) > 3 else line.strip())
    return dirty


def slug_from_target(target_path: str, fallback: str) -> str:
    stem = Path(target_path or fallback).stem or fallback
    return stem.replace("_", "-").lower()


def load_approved_queue_items(queue_path: Path) -> list[dict]:
    data = load_json(queue_path, {})
    queue = data.get("queue", []) if isinstance(data, dict) else []
    has_queue_shape = bool(queue)
    subjects = queue
    if not subjects:
        topics_path = queue_path.parent / "chapter_discovery_topics.json"
        topics = load_json(topics_path, {})
        subjects = topics.get("approved_subjects", []) if isinstance(topics, dict) else []
    approved = []
    for item in subjects:
        if not isinstance(item, dict):
            continue
        if has_queue_shape:
            if item.get("mode") != "human_approved_research_pair":
                continue
            if item.get("status") not in {"approved", "approved_research_lane", "chapter_seed_created", "chapter_matured"}:
                continue
        else:
            if item.get("status") != "approved":
                continue
        target = str(item.get("target_path") or "")
        if not (target.startswith("docs/book/") and target.endswith(".md") and ".." not in Path(target).parts):
            continue
        approved.append(item)
    return approved


def update_queue_item_state(queue_path: Path, item: dict, state: str) -> None:
    data = load_json(queue_path, {})
    changed = False
    for candidate in data.get("queue", []) if isinstance(data, dict) else []:
        if candidate.get("chapter_id") == item.get("chapter_id") and candidate.get("target_path") == item.get("target_path"):
            if candidate.get("chapter_state") != state:
                candidate["chapter_state"] = state
                changed = True
            if candidate.get("status") == "approved":
                candidate["status"] = "approved_research_lane"
                changed = True
    if changed and queue_path.exists():
        write_json(queue_path, data)


def contract_with_approved_queue_chapters(contract: dict, queue_path: Path) -> dict:
    enriched = json.loads(json.dumps(contract))
    chapters = enriched.setdefault("chapters", {})
    for item in load_approved_queue_items(queue_path):
        chapter_id = str(item.get("chapter_id") or slug_from_target(str(item.get("target_path")), "chapter")).strip()
        if not chapter_id:
            continue
        chapters.setdefault(chapter_id, {
            "title": item.get("title") or chapter_id.replace("_", " ").title(),
            "target_path": item.get("target_path"),
            "role": "human_approved_research_chapter",
            "publication_mode": "human_approved_guarded_seed",
        })
    return enriched


def seed_chapter_markdown(title: str, item: dict) -> str:
    web_query = ((item.get("research_pair") or {}).get("web_query") or item.get("web_query") or title).strip()
    linkedin_query = ((item.get("research_pair") or {}).get("linkedin_query") or item.get("linkedin_query") or title).strip()
    return f"""# {title}

The central argument of this chapter is that {title.lower()} deserves a visible place in the book because it names a recurring problem in practical agent systems. The chapter is published first as a guarded seed: it gives readers the topic, its scope, and the questions the daily loop is now assigned to research, while refusing to turn early discovery signals into settled claims. [1] [2] [3]

For this seed chapter, the operational pattern is more important than volume. The daily loop will collect web, LinkedIn, and supplemental visual evidence for this subject, normalize that material into the source registry, and only later promote claims that survive the same editorial and evidence-safety gates used by the rest of the manuscript. This makes the chapter visible without bypassing the book's publication discipline. [1] [2]

The evidence limits are explicit. A search lane, a social mention, or a cluster of repeated terms is not enough to prove adoption, maturity, or industry consensus. Early material can justify continued research and a cautious conceptual frame, but the chapter should not claim more than the captured sources support. Stronger revisions should add sustained prose only when corroborated sources, citations, and editorial review make the update safe. [2] [3]

The chapter will therefore mature in stages. First, the subject appears as a seed chapter so the book shows that the approved research lane exists. Next, daily harvests accumulate candidate evidence and source-quality signals. Finally, the guarded authoring path rewrites this page into a fuller academic and professional chapter when enough support exists for definitions, examples, limitations, and practical implications. [1] [3]

## References

[1] [Approved research lane](book/open-questions.md).
[2] [Research loop evidence process](book/source-registry.md).
[3] [Guarded publication policy](book/methodology.md).
"""


def mkdocs_book_nav_line(title: str, target_path: str) -> str:
    rel = target_path[len("docs/"):] if target_path.startswith("docs/") else target_path
    return f"      - {title}: {rel}"


def ensure_book_nav_entry(mkdocs_path: Path, title: str, target_path: str, *, public_nav_allowed: bool = False) -> bool:
    """Add a chapter to public nav only after it is explicitly approved for readers.

    Approved research lanes may create local seed files, but they should not be
    promoted into the published Book nav until they have matured into real
    narrative chapters. This keeps the public site from drifting back into a
    mixture of manuscript and internal research apparatus.
    """
    if not public_nav_allowed or not mkdocs_path.exists():
        return False
    text = mkdocs_path.read_text(encoding="utf-8")
    rel = target_path[len("docs/"):] if target_path.startswith("docs/") else target_path
    if rel in text:
        return False
    line = mkdocs_book_nav_line(title, target_path)
    lines = text.splitlines()
    insert_at = None
    for i, existing in enumerate(lines):
        if "Open Questions: book/open-questions.md" in existing:
            insert_at = i
            break
    if insert_at is None:
        insert_at = len(lines)
    lines.insert(insert_at, line)
    mkdocs_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return True


def ensure_visible_approved_seed_chapters(*, queue_path: Path, docs_root: Path, mkdocs_path: Path, max_new_chapters: int = 3) -> dict:
    approved = load_approved_queue_items(queue_path)
    docs_root.mkdir(parents=True, exist_ok=True)
    seed_chapters = []
    nav_added = []
    visible = []
    for item in approved:
        title = str(item.get("title") or str(item.get("chapter_id", "chapter")).replace("_", " ").title())
        target_path = str(item.get("target_path"))
        target = docs_root / Path(target_path).name
        exists = target.exists()
        if exists:
            visible.append(target_path)
        elif len(seed_chapters) < max_new_chapters:
            target.write_text(seed_chapter_markdown(title, item), encoding="utf-8")
            seed_chapters.append({
                "chapter_id": item.get("chapter_id"),
                "title": title,
                "target_path": target_path,
                "chapter_state": "chapter_seed_created",
            })
            visible.append(target_path)
        public_nav_allowed = item.get("status") == "chapter_matured" or bool(item.get("public_nav_allowed"))
        if target.exists() and ensure_book_nav_entry(mkdocs_path, title, target_path, public_nav_allowed=public_nav_allowed):
            nav_added.append(target_path)
        update_queue_item_state(queue_path, item, "chapter_seed_created" if any(s["target_path"] == target_path for s in seed_chapters) else "chapter_seed_visible")
    return {
        "ok": True,
        "approved_research_lane_count": len(approved),
        "visible_approved_chapter_count": len(set(visible)),
        "seed_chapter_count": len(seed_chapters),
        "nav_added_count": len(nav_added),
        "seed_chapters": seed_chapters,
        "nav_added": nav_added,
        "chapter_states": {p: "chapter_seed_created" if any(s["target_path"] == p for s in seed_chapters) else "chapter_seed_visible" for p in visible},
    }


def chapter_publication_allowed(editorial: dict, allow_chapter_updates: bool) -> tuple[bool, str]:
    bso = editorial.get("blocked_state_output", {})
    if not allow_chapter_updates:
        return False, "allow_chapter_updates_flag_absent"
    if editorial.get("final_status") == "blocked" or bso.get("chapter_update_allowed") is False or bso.get("block_reasons"):
        return False, bso.get("chapter_update_skipped_reason") or "blocked_for_publication_by_policy"
    return True, "allowed"

def write_steps(run_id: str, steps: list[dict]) -> Path:
    path = LOGS / "runs" / f"{run_id}-steps.json"
    write_json(path, {"run_id": run_id, "steps": steps, "updated_at": utc_now()})
    return path


def build_daily_summary(run_id: str, start: str, status: str, steps: list[dict], editorial: dict, commit: dict, build_status: str) -> Path:
    summary_md = REPORTS / "daily" / f"{run_id}.md"
    counts = editorial.get("counts", {})
    source_counts = counts.get("source_counts", {})
    claim_counts = counts.get("claim_counts", {})
    quality = counts.get("source_quality_distribution", editorial.get("source_quality_distribution", {}))
    commit_hash = commit.get("commit_sha") or commit.get("commit") or commit.get("sha") or "not committed"
    final_status = editorial.get("final_status", status)
    bso = editorial.get("blocked_state_output", {})
    chapter_update_allowed = bool(bso.get("chapter_update_allowed", False))
    chapter_sections_updated = editorial.get("chapter_sections_updated", []) if chapter_update_allowed else []
    chapter_update_status = "updated" if chapter_sections_updated else "skipped"
    skipped_reason = bso.get("chapter_update_skipped_reason") or ("blocked_for_publication_by_policy" if final_status == "blocked" else "allow_chapter_updates_flag_absent")
    md = [
        "# Daily research book run",
        "",
        f"- Run ID: `{run_id}`",
        f"- Started: {start}",
        f"- Finished: {utc_now()}",
        f"- Final status: `{final_status}`",
        f"- Book build status: `{build_status}`",
        f"- Git commit hash: `{commit_hash}`",
        "",
        "## Required run output",
        "",
        f"1. Run ID: `{run_id}`",
        f"2. Source counts: `{source_counts}`",
        f"3. Entity counts: `{counts.get('entity_count', 0)}`",
        f"4. Claim counts: `{claim_counts}`",
        f"5. Source quality distribution: `{quality}`",
        f"6. New candidate trends: `{len(editorial.get('new_candidate_trends', []))}`",
        f"7. Claims promoted: `{len(editorial.get('claims_promoted', []))}`",
        f"8. Claims rejected: `{len(editorial.get('claims_rejected', []))}`",
        f"9. Chapter sections updated: `{chapter_sections_updated}`",
        f"10. Editor warnings: `{editorial.get('editor_warnings', [])}`",
        f"11. Book build status: `{build_status}`",
        f"12. Git commit hash, if committed: `{commit_hash}`",
        f"13. Final status: `{final_status}`",
    ]
    md += [
        "",
        "## Publication decision model",
        "",
        f"- data_collected: `{bso.get('data_collected', bool(source_counts))}`",
        f"- data_usable_for_reports: `{bso.get('data_usable_for_reports', bso.get('data_usable', False))}`",
        f"- data_usable_for_chapter_update: `{bso.get('data_usable_for_chapter_update', False)}`",
        f"- chapter_update_allowed: `{chapter_update_allowed}`",
        f"- chapter_update_status: `{chapter_update_status}`",
        f"- chapter_sections_updated: `{chapter_sections_updated}`",
        f"- chapter_update_skipped_reason: `{skipped_reason if not chapter_sections_updated else ''}`",
        f"- automated_disposition: `{bso.get('automated_disposition', 'unknown')}`",
        f"- publication_recommendation: `{editorial.get('publication_recommendation', bso.get('publication_recommendation', 'unknown'))}`",
        "",
        "## Steps",
        "",
    ]
    for s in steps:
        name = Path(s["cmd"][1] if len(s["cmd"]) > 1 else s["cmd"][0]).name
        md.append(f"- `{name}`: exit {s['returncode']}")
    md += ["", "## Publication recommendation", "", f"- `{editorial.get('publication_recommendation', bso.get('publication_recommendation', 'unknown'))}`"]
    if final_status == "blocked" or bso.get("block_reasons"):
        md += [
            "",
            "## Blocked-state output",
            "",
            f"1. Block reason: `{bso.get('block_reasons', editorial.get('blocked_reasons', []))}`",
            f"2. Affected files: `{bso.get('affected_files', [])}`",
            f"3. Failed checks: `{bso.get('failed_checks', editorial.get('blocked_reasons', []))}`",
            f"4. Data collected: `{bso.get('data_collected', bool(source_counts))}`",
            f"5. Data usable: `{bso.get('data_usable', False)}`",
            f"6. Safely updated: `{bso.get('safe_updates_allowed', [])}`",
            f"7. Required next action: `{bso.get('required_next_action', 'safe_reports_only')}`",
            f"8. Automated disposition: `{bso.get('automated_disposition', 'safe_reports_only')}`",
            f"9. Optional escalation: `{bso.get('optional_escalation', False)}`",
        ]
        if bso.get("optional_escalation_reasons"):
            md.append(f"10. Optional escalation reasons: `{bso.get('optional_escalation_reasons')}`")
    if editorial.get("blocked_reasons"):
        md.append("- Blocked reasons:")
        for r in editorial.get("blocked_reasons", []):
            md.append(f"  - {r}")
    md += ["", "## Notes", "", "LinkedIn/social media is treated as a discovery signal, not independent confirmation. The Author may write only from Editor-promoted or clearly caveated claim records, never directly from raw captures."]
    summary_md.parent.mkdir(parents=True, exist_ok=True)
    summary_md.write_text("\n".join(md) + "\n", encoding="utf-8")
    return summary_md


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_id", nargs="?", help="Optional explicit run ID")
    ap.add_argument("--print-capabilities-json", action="store_true", help="Print supported no-write controls and exit without side effects")
    ap.add_argument("--manual", action="store_true", help="Run immediately with a manual run ID prefix")
    ap.add_argument("--skip-capture", action="store_true", help="Only run editorial ingestion/update steps on existing sources")
    ap.add_argument("--skip-entity-extraction", action="store_true", help="Do not call scripts/extract_entities.py")
    ap.add_argument("--skip-claim-extraction", action="store_true", help="Do not call scripts/extract_claims.py")
    ap.add_argument("--skip-docs-entities-update", action="store_true", help="Do not call scripts/update_entity_pages.py")
    ap.add_argument("--skip-docs-claims-update", action="store_true", help="Do not call scripts/update_claims_page.py")
    ap.add_argument("--skip-source-registry-export", action="store_true", help="Do not call scripts/export_source_registry.py")
    ap.add_argument("--skip-run-table-update", action="store_true", help="Do not write the runs table or final run state files")
    ap.add_argument("--skip-vector", action="store_true", help="Skip local vector-index refresh")
    ap.add_argument("--vector-limit", type=int, default=200, help="Maximum Markdown files to vector-index in this run; 0 means no limit")
    ap.add_argument("--no-commit", action="store_true", help="Do not commit or push; useful for verification runs")
    ap.add_argument("--preflight-only", action="store_true", help="Validate arguments and emit a no-write preflight result without running pipeline steps")
    ap.add_argument("--allow-chapter-updates", action="store_true", help="Allow Author chapter synthesis. Default daily behavior is collection/preparation only; use after weekly curation or explicit Editor approval.")
    ap.add_argument("--run-all-chapter-public-proof", action="store_true", help="Run the closed-loop manuscript public proof gate across every configured book chapter.")
    ap.add_argument("--run-chapter-revision-policy", action="store_true", help="After automatic collection and processing, plan fluent existing-chapter rewrites and guarded new chapter queue items from processed information.")
    ap.add_argument("--run-chapter-subject-discovery", action="store_true", help="After trend discovery, create human-approval proposals for possible new chapter subjects and research pairs without docs/book mutation.")
    args = ap.parse_args()

    if args.print_capabilities_json:
        print(json.dumps(no_write_capabilities(), sort_keys=True))
        return 0

    run_id = args.run_id or (("manual-" + run_id_now()) if args.manual else run_id_now())
    if args.preflight_only:
        seed = {"ok": True, "seed_chapter_count": 0, "nav_added_count": 0, "approved_research_lane_count": 0, "visible_approved_chapter_count": 0}
        if args.run_chapter_revision_policy:
            seed = ensure_visible_approved_seed_chapters(
                queue_path=ROOT / "config" / "book_manuscript_queue.json",
                docs_root=ROOT / "docs" / "book",
                mkdocs_path=ROOT / "mkdocs.yml",
                max_new_chapters=3,
            )
            seed_report_json = REPORTS / "editorial" / f"{run_id}-approved-seed-chapters.json"
            write_json(seed_report_json, {"run_id": run_id, **seed})
        proof = run_all_chapter_public_proof(run_id) if args.run_all_chapter_public_proof else {"ok": None, "report": None, "failed_chapters": []}
        print(json.dumps({
            "ok": True,
            "preflight_only": True,
            "run_id": run_id,
            "capability_probe_no_write": not args.run_chapter_revision_policy,
            "preflight_only_no_write": not args.run_chapter_revision_policy,
            "validated_arguments": True,
            "execution_performed": False,
            "writes_performed": bool(seed.get("seed_chapter_count") or seed.get("nav_added_count")),
            "capture_executed": False,
            "visual_capture_executed": False,
            "entity_extraction_executed": False,
            "claim_extraction_executed": False,
            "docs_book_update_executed": False,
            "docs_entities_update_executed": False,
            "docs_claims_update_executed": False,
            "source_registry_export_executed": False,
            "run_table_update_executed": False,
            "vector_index_build_executed": False,
            "commit_executed": False,
            "push_executed": False,
            "all_chapter_public_proof_executed": bool(args.run_all_chapter_public_proof),
            "all_chapter_public_proof_ok": proof.get("ok"),
            "all_chapter_public_proof_report": proof.get("report"),
            "all_chapter_public_proof_failed_chapters": proof.get("failed_chapters", []),
            "chapter_revision_policy_wired": True,
            "chapter_revision_policy_executed": bool(args.run_chapter_revision_policy),
            "approved_seed_chapter_count": seed.get("seed_chapter_count", 0),
            "approved_seed_nav_added_count": seed.get("nav_added_count", 0),
            "approved_research_lane_count": seed.get("approved_research_lane_count", 0),
            "visible_approved_chapter_count": seed.get("visible_approved_chapter_count", 0),
            "chapter_subject_discovery_wired": True,
            "chapter_subject_discovery_executed": False,
            "post_processing_chapter_revision_trigger": "after_automatic_collection_and_processing",
            "human_in_loop_dependency_added": False,
        }, sort_keys=True))
        return 0

    init_db()
    cfg = json.loads(CONFIG_PATH.read_text())
    state_dir = LOGS / "runs" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    state_path = state_dir / f"{run_id}.state"
    latest = state_dir / "latest.state"
    full_log = LOGS / "runs" / f"{run_id}.log"
    full_log.parent.mkdir(parents=True, exist_ok=True)
    start = utc_now()
    state = f"RUN_ID={run_id}\nSTATUS=running\nSTARTED_AT={start}\nUPDATED_AT={start}\nFULL_LOG={full_log}\nDELIVERED=0\n"
    state_path.write_text(state)
    latest.write_text(state)

    steps: list[dict] = []
    status = "success"
    error = ""
    editorial_json = LOGS / "runs" / f"{run_id}-editorial-pipeline.json"
    commit_json = LOGS / "runs" / f"{run_id}-commit.json"
    build_status = "unknown"
    commit: dict = {"status": "not_attempted"}
    editorial: dict = {}

    with full_log.open("a", encoding="utf-8") as log:
        try:
            web_json = LOGS / "runs" / f"{run_id}-web.json"
            li_json = LOGS / "runs" / f"{run_id}-linkedin.json"
            trends_json = LOGS / "runs" / f"{run_id}-trends.json"

            if not args.skip_capture:
                steps.append(run([PY, "scripts/capture_web_daily.py", "--run-id", run_id, "--json-out", str(web_json), *sum([["--query", q] for q in cfg["web_queries"]], [])], log))
                visual_cfg = cfg.get("visual_capture", {}) if isinstance(cfg.get("visual_capture", {}), dict) else {}
                if visual_cfg.get("enabled"):
                    visual_json = LOGS / "runs" / f"{run_id}-visual.json"
                    max_urls = str(int(visual_cfg.get("max_urls_per_run", 5)))
                    steps.append(run([PY, "scripts/capture_visual_daily.py", "--run-id", run_id, "--from-web-capture-json", str(web_json), "--max-urls", max_urls, "--enabled", "--json-out", str(visual_json)], log))
                steps.append(run([PY, "scripts/capture_linkedin_daily.py", "--run-id", run_id, "--json-out", str(li_json), *sum([["--query", q] for q in cfg["linkedin_queries"]], [])], log))
            else:
                steps.append(script_step("scripts/capture_web_daily.py", 0, "skipped by --skip-capture"))
                steps.append(script_step("scripts/capture_linkedin_daily.py", 0, "skipped by --skip-capture"))

            if args.skip_entity_extraction:
                steps.append(script_step("scripts/extract_entities.py", 0, "skipped by --skip-entity-extraction"))
            else:
                steps.append(run([PY, "scripts/extract_entities.py"], log))
            if args.skip_claim_extraction:
                steps.append(script_step("scripts/extract_claims.py", 0, "skipped by --skip-claim-extraction"))
            else:
                steps.append(run([PY, "scripts/extract_claims.py"], log))
            steps.append(run([PY, "scripts/discover_trends.py", "--run-id", run_id, "--json-out", str(trends_json)], log))
            if args.skip_docs_entities_update:
                steps.append(script_step("scripts/update_entity_pages.py", 0, "skipped by --skip-docs-entities-update"))
            else:
                steps.append(run([PY, "scripts/update_entity_pages.py", "--run-id", run_id], log))
            if args.skip_docs_claims_update:
                steps.append(script_step("scripts/update_claims_page.py", 0, "skipped by --skip-docs-claims-update"))
            else:
                steps.append(run([PY, "scripts/update_claims_page.py", "--run-id", run_id], log))
            if args.skip_source_registry_export:
                steps.append(script_step("scripts/export_source_registry.py", 0, "skipped by --skip-source-registry-export"))
            else:
                steps.append(run([PY, "scripts/export_source_registry.py"], log))
            steps_path = write_steps(run_id, steps)

            # Curator + Editor gate before Authoring. Exit 2 means blocked publication; it is handled, not fatal.
            ep_step = run([PY, "scripts/editorial_pipeline_report.py", "--run-id", run_id, "--step-results", str(steps_path), "--book-build-status", "unknown", "--json-out", str(editorial_json)], log)
            steps.append(ep_step)
            editorial = load_json(editorial_json, {})

            if args.run_chapter_revision_policy:
                seed_report = ensure_visible_approved_seed_chapters(
                    queue_path=ROOT / "config" / "book_manuscript_queue.json",
                    docs_root=ROOT / "docs" / "book",
                    mkdocs_path=ROOT / "mkdocs.yml",
                    max_new_chapters=3,
                )
                seed_report_json = REPORTS / "editorial" / f"{run_id}-approved-seed-chapters.json"
                seed_report_md = REPORTS / "editorial" / f"{run_id}-approved-seed-chapters.md"
                write_json(seed_report_json, {"run_id": run_id, **seed_report})
                seed_report_md.parent.mkdir(parents=True, exist_ok=True)
                seed_report_md.write_text(
                    "# Approved seed chapters\n\n"
                    f"- approved_research_lane_count: `{seed_report['approved_research_lane_count']}`\n"
                    f"- visible_approved_chapter_count: `{seed_report['visible_approved_chapter_count']}`\n"
                    f"- seed_chapter_count: `{seed_report['seed_chapter_count']}`\n"
                    f"- nav_added_count: `{seed_report['nav_added_count']}`\n",
                    encoding="utf-8",
                )
                steps.append(script_step("approved_seed_chapters", 0, json.dumps(seed_report, sort_keys=True)))
                editorial.setdefault("blocked_state_output", {})["approved_seed_chapters_report"] = str(seed_report_json.relative_to(ROOT))
                editorial["blocked_state_output"]["approved_seed_chapter_count"] = seed_report["seed_chapter_count"]
                editorial["blocked_state_output"]["approved_seed_nav_added_count"] = seed_report["nav_added_count"]
                processed_json = LOGS / "runs" / f"{run_id}-processed-information.json"
                processed_items = []
                trends_payload = load_json(trends_json, {})
                for trend in trends_payload.get("new_candidate_trends", trends_payload.get("trends", [])) if isinstance(trends_payload, dict) else []:
                    if isinstance(trend, dict):
                        processed_items.append({
                            "title": trend.get("term") or trend.get("title"),
                            "summary": trend.get("summary") or trend.get("reason") or trend.get("term"),
                            "topics": [trend.get("term")] if trend.get("term") else trend.get("topics", []),
                            "evidence_status": trend.get("evidence_status") or "caveat_only",
                        })
                if not processed_items:
                    for trend in editorial.get("new_candidate_trends", []):
                        if isinstance(trend, dict):
                            processed_items.append({
                                "title": trend.get("term") or trend.get("title"),
                                "summary": trend.get("summary") or trend.get("decision") or trend.get("term"),
                                "topics": [trend.get("term")] if trend.get("term") else trend.get("topics", []),
                                "evidence_status": "caveat_only",
                            })
                write_json(processed_json, {"run_id": run_id, "processed_information": processed_items})
                revision_plan_json = REPORTS / "editorial" / f"{run_id}-chapter-revision-policy.json"
                revision_plan_md = REPORTS / "editorial" / f"{run_id}-chapter-revision-policy.md"
                steps.append(run([PY, "scripts/book_chapter_revision_policy.py", "--contract", "config/book_manuscript_production_contract.json", "--processed-json", str(processed_json), "--run-id", run_id, "--output-json", str(revision_plan_json), "--output-md", str(revision_plan_md)], log))
                revision_plan = load_json(revision_plan_json, {})
                editorial.setdefault("blocked_state_output", {})["chapter_revision_policy_report"] = str(revision_plan_json.relative_to(ROOT))
                editorial["blocked_state_output"]["chapter_revision_policy_executed"] = True
                editorial["blocked_state_output"]["existing_chapter_revision_count"] = len(revision_plan.get("existing_chapter_revisions", []))
                editorial["blocked_state_output"]["new_chapter_candidate_count"] = len(revision_plan.get("new_chapter_candidates", []))
                if revision_plan.get("ok") is not True:
                    status = "blocked"
                    editorial.setdefault("blocked_reasons", []).append("chapter_revision_policy_failed")

            if args.run_chapter_subject_discovery:
                subject_report_json = REPORTS / "editorial" / f"{run_id}-chapter-subject-discovery.json"
                subject_report_md = REPORTS / "editorial" / f"{run_id}-chapter-subject-discovery.md"
                steps.append(run([PY, "scripts/chapter_subject_discovery.py", "--run-id", run_id, "--contract", "config/book_manuscript_production_contract.json", "--trends-json", str(trends_json), "--config", "config/chapter_discovery_topics.json", "--output-json", str(subject_report_json), "--output-md", str(subject_report_md)], log))
                subject_report = load_json(subject_report_json, {})
                editorial.setdefault("blocked_state_output", {})["chapter_subject_discovery_report"] = str(subject_report_json.relative_to(ROOT))
                editorial["blocked_state_output"]["chapter_subject_discovery_executed"] = True
                editorial["blocked_state_output"]["chapter_subject_proposal_count"] = subject_report.get("proposal_count", 0)
                editorial["blocked_state_output"]["human_approval_required_for_new_chapters"] = bool(subject_report.get("human_approval_required"))
                if subject_report.get("ok") is not True:
                    status = "blocked"
                    editorial.setdefault("blocked_reasons", []).append("chapter_subject_discovery_failed")

            chapter_allowed, chapter_skip_reason = chapter_publication_allowed(editorial, args.allow_chapter_updates)
            if not chapter_allowed:
                if editorial.get("final_status") == "blocked":
                    status = "blocked"
                msg = f"skipped: {chapter_skip_reason}"
                steps.append(script_step("scripts/synthesize_chapters.py", 0, msg))
                steps.append(script_step("scripts/resolve_book_citations.py", 0, msg))
                steps.append(script_step("scripts/update_book_pages.py", 0, msg))
                editorial.setdefault("blocked_state_output", {})["chapter_update_allowed"] = False
                editorial["blocked_state_output"]["chapter_update_skipped_reason"] = chapter_skip_reason
                editorial["chapter_sections_updated"] = []
            else:
                # Author writes only from approved/caveated claims after weekly curation or explicit Editor approval.
                steps.append(run([PY, "scripts/synthesize_chapters.py", "--run-id", run_id], log))
                # Publication normalization: Author output may contain structured citation tokens,
                # but public book pages must contain numbered references only.
                citation_report = LOGS / "runs" / f"{run_id}-citations.json"
                citation_step = run([PY, "scripts/resolve_book_citations.py", "--json-out", str(citation_report)], log)
                steps.append(citation_step)
                if citation_step["returncode"] != 0:
                    status = "blocked"
                steps.append(run([PY, "scripts/update_book_pages.py", "--run-id", run_id], log))
            steps.append(run([PY, "scripts/verify_editorial_ingestion.py"], log))
            steps.append(run([PY, "scripts/verify_book_citations.py"], log))
            if args.run_all_chapter_public_proof:
                public_proof = run_all_chapter_public_proof(run_id)
                steps.append(public_proof)
                editorial.setdefault("blocked_state_output", {})["all_chapter_public_proof_report"] = public_proof.get("report")
                editorial["blocked_state_output"]["all_chapter_public_proof_ok"] = public_proof.get("ok")
                editorial["blocked_state_output"]["all_chapter_public_proof_failed_chapters"] = public_proof.get("failed_chapters", [])
                if public_proof["returncode"] != 0:
                    status = "blocked"
                    editorial.setdefault("blocked_reasons", []).append("all_chapter_public_proof_failed")
                    editorial["blocked_state_output"]["chapter_update_allowed"] = False
                    editorial["blocked_state_output"]["chapter_update_skipped_reason"] = "all_chapter_public_proof_failed"

            # Book role gate builds the site and checks links/unsafe paths. Use local MkDocs venv if available.
            book_gate = run([MKDOCS_PY, "scripts/book_role_report.py"], log)
            steps.append(book_gate)
            build_status = "ok" if book_gate["returncode"] == 0 else "failed"
            if book_gate["returncode"] != 0:
                status = "blocked"

            # Final editorial report includes book build status and latest chapter gate state.
            steps_path = write_steps(run_id, steps)
            ep_final = run([PY, "scripts/editorial_pipeline_report.py", "--run-id", run_id, "--step-results", str(steps_path), "--book-build-status", build_status, "--json-out", str(editorial_json)], log)
            steps.append(ep_final)
            editorial = load_json(editorial_json, editorial)
            if editorial.get("final_status") == "blocked" or status == "blocked":
                status = "blocked"
            elif any(s["returncode"] not in (0,) for s in steps if Path(s["cmd"][1] if len(s["cmd"]) > 1 else s["cmd"][0]).name not in {"editorial_pipeline_report.py"}):
                status = "partial"
            else:
                status = editorial.get("final_status", "success")

            if not args.skip_vector:
                vector_cmd = [PY, "scripts/build_vector_db.py"]
                if args.vector_limit:
                    vector_cmd += ["--limit", str(args.vector_limit)]
                steps.append(run(vector_cmd, log))

            dirty_book = docs_book_dirty_files() if status == "blocked" else []
            if dirty_book:
                status = "blocked"
                editorial.setdefault("blocked_reasons", []).append("docs/book has uncommitted changes after blocked run")
                editorial.setdefault("blocked_state_output", {})["chapter_update_allowed"] = False
                editorial["blocked_state_output"]["chapter_update_skipped_reason"] = "blocked_for_publication_by_policy"
                editorial["blocked_state_output"]["docs_book_dirty_files"] = dirty_book
                commit = {"status": "blocked", "committed": False, "reason": "docs/book has uncommitted changes after blocked run", "docs_book_dirty_files": dirty_book}
            elif args.no_commit:
                commit = {"status": "skipped", "reason": "--no-commit"}
            else:
                # If blocked, commit only safe status/research/report/tooling updates.
                # Never stage docs/book chapter prose while the Editor gate is blocked.
                safe_paths = ["reports", "data/search_config.json", "data/chroma_manifest.json", "data/source_registry.json", ".github", "mkdocs.yml", "README.md", ".gitignore", ".env.example", "scripts", "tests", "docs/research", "docs/entities", "docs/reports", "docs/operations"]
                if status != "blocked":
                    safe_paths.append("docs/book")
                commit = git_commit_push(
                    f"research: daily book pipeline update {run_id}",
                    safe_paths,
                )
            write_json(commit_json, commit)
            # Regenerate summary after commit so the run output contains the commit hash when available.
            summary_md = build_daily_summary(run_id, start, status, steps, editorial, commit, build_status)
        except Exception as e:
            status = "failed"
            error = type(e).__name__ + ": " + str(e)
            log.write("\nERROR " + error + "\n")
            summary_md = REPORTS / "daily" / f"{run_id}.md"
            summary_md.parent.mkdir(parents=True, exist_ok=True)
            summary_md.write_text(f"# Daily research book run\n\n- Run ID: `{run_id}`\n- Final status: `failed`\n- Error: `{error}`\n", encoding="utf-8")

    end = utc_now()
    if not args.skip_run_table_update:
        with connect_db() as con:
            con.execute(
                "INSERT OR REPLACE INTO runs (id, started_at, ended_at, status, mode, summary_path, error) VALUES (?,?,?,?,?,?,?)",
                (run_id, start, end, status, "daily", str(REPORTS / "daily" / f"{run_id}.md"), error),
            )
            con.commit()
    final = f"RUN_ID={run_id}\nSTATUS={status}\nSTARTED_AT={start}\nUPDATED_AT={end}\nENDED_AT={end}\nFULL_LOG={full_log}\nSUMMARY_MD={REPORTS/'daily'/f'{run_id}.md'}\nEXIT_CODE={0 if status in ('success','partial','blocked') else 1}\nDELIVERED=0\nERROR={json.dumps(error)}\n"
    if not args.skip_run_table_update:
        state_path.write_text(final)
        latest.write_text(final)
    print(f"Terefo Heal Reboa book loop finished: {status}\nRun ID: {run_id}\nSummary: {REPORTS/'daily'/f'{run_id}.md'}\nLog: {full_log}")
    return 0 if status in ("success", "partial", "blocked") else 1


if __name__ == "__main__":
    raise SystemExit(main())
