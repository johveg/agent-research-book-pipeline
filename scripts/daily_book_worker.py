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




def docs_book_dirty_files() -> list[str]:
    p = subprocess.run(["git", "status", "--short", "--", "docs/book"], cwd=ROOT, text=True, capture_output=True)
    dirty = []
    for line in p.stdout.splitlines():
        if line.strip():
            dirty.append(line[3:] if len(line) > 3 else line.strip())
    return dirty


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
    ap.add_argument("--allow-chapter-updates", action="store_true", help="Allow Author chapter synthesis. Default daily behavior is collection/preparation only; use after weekly curation or explicit Editor approval.")
    args = ap.parse_args()

    if args.print_capabilities_json:
        print(json.dumps(no_write_capabilities(), sort_keys=True))
        return 0

    run_id = args.run_id or (("manual-" + run_id_now()) if args.manual else run_id_now())
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
