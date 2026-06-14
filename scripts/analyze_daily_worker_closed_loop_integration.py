#!/usr/bin/env python3
"""Report-only daily-worker closed-loop integration preflight.

Run 36 maps current scheduler/daily-worker write surfaces against the closed-loop
state machine, transition engine, and protected mutation guard. It does not
modify the daily worker, SQLite, source registry, raw captures, docs/book,
schema, statuses, claims, source_notes, editorial_reviews, or production gates.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INSPECT = [
    "scripts/daily_book_worker.py",
    "scripts/closed_loop_transition_engine.py",
    "scripts/protected_mutation_guard.py",
    "config/closed_loop_state_machine.json",
    "config/reasoning_models.json",
    "scripts/update_closed_loop_promotion_contract.py",
    "scripts/verify_book_workspace.py",
    "scripts/verify_editorial_roles.py",
    "scripts/verify_book_citations.py",
]

HARD_FALSE_FLAGS = [
    "author_allowed",
    "publication_approved",
    "eligible_for_claim_insertion",
    "eligible_for_authoring",
    "eligible_for_publication",
    "chapter_update_allowed",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def resolve(path: str | Path) -> Path:
    p = Path(path)
    return p if p.is_absolute() else ROOT / p


def sha_file(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def inspect_files(extra: list[str] | None = None) -> dict[str, dict[str, Any]]:
    files = list(DEFAULT_INSPECT)
    for item in extra or []:
        r = rel(resolve(item))
        if r not in files:
            files.append(r)
    out: dict[str, dict[str, Any]] = {}
    for item in files:
        path = resolve(item)
        out[item] = {"exists": path.exists(), "sha256": sha_file(path), "bytes": path.stat().st_size if path.exists() else 0}
    return out


def call_names_from_daily_worker(path: Path) -> list[str]:
    text = read_text(path)
    calls: list[str] = []
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return calls
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            # Detect run([PY, "scripts/foo.py", ...]) script calls.
            if isinstance(node.func, ast.Name) and node.func.id == "run" and node.args and isinstance(node.args[0], ast.List):
                for elt in node.args[0].elts:
                    if isinstance(elt, ast.Constant) and isinstance(elt.value, str) and elt.value.startswith("scripts/"):
                        calls.append(elt.value)
            if isinstance(node.func, ast.Name) and node.func.id == "git_commit_push":
                calls.append("git_commit_push")
            if isinstance(node.func, ast.Attribute) and node.func.attr in {"write_text", "mkdir", "open"}:
                calls.append(node.func.attr)
            if isinstance(node.func, ast.Attribute) and node.func.attr in {"execute", "commit"}:
                calls.append(node.func.attr)
    return sorted(set(calls))


def find_daily_worker_flags(text: str) -> dict[str, str]:
    flags: dict[str, str] = {}
    for match in re.finditer(r'ap\.add_argument\("([^"]+)"[^\n]*(?:help="([^"]*)")?', text):
        flags[match.group(1)] = match.group(2) or ""
    return flags


def daily_worker_write_surfaces(path: Path) -> list[dict[str, Any]]:
    text = read_text(path)
    calls = call_names_from_daily_worker(path)
    surfaces = [
        {
            "surface": "run_state_files",
            "location": "logs/runs/state/*.state and logs/runs/*.log",
            "evidence": ["state_path.write_text", "latest.write_text", "full_log.open"],
            "risk": "operational_state_only",
            "verification_profile": "report_only",
        },
        {
            "surface": "daily_summary_report",
            "location": "reports/daily/{run_id}.md",
            "evidence": ["build_daily_summary", "summary_md.write_text"],
            "risk": "report_artifact",
            "verification_profile": "report_only",
        },
        {
            "surface": "step_and_commit_json_reports",
            "location": "logs/runs/{run_id}-steps.json, logs/runs/{run_id}-commit.json",
            "evidence": ["write_steps", "write_json(commit_json, commit)"],
            "risk": "operational_report_artifact",
            "verification_profile": "report_only",
        },
        {
            "surface": "capture_scripts",
            "location": "capture_web_daily.py and capture_linkedin_daily.py outputs",
            "evidence": [c for c in calls if c in {"scripts/capture_web_daily.py", "scripts/capture_linkedin_daily.py"}],
            "risk": "may_write_raw_or_logs_and_update_source_metadata_depending_on_called_scripts",
            "verification_profile": "report_only_until_safe_collection_profile_exists",
        },
        {
            "surface": "entity_and_claim_extraction",
            "location": ".var/book.sqlite and derived docs",
            "evidence": [c for c in calls if c in {"scripts/extract_entities.py", "scripts/extract_claims.py"}],
            "risk": "may_insert_or_update entities, claims, source-derived records, or statuses depending on called scripts",
            "verification_profile": "future_db_write_profile_required_before_unattended",
        },
        {
            "surface": "docs_entities_and_claims_pages",
            "location": "docs/entities/ and docs/research/claims.md",
            "evidence": [c for c in calls if c in {"scripts/update_entity_pages.py", "scripts/update_claims_page.py"}],
            "risk": "protected_docs_mutation_not_book_chapter_prose_but still protected path in guard",
            "verification_profile": "future_docs_entities_claims_profile_needed",
        },
        {
            "surface": "source_registry_export",
            "location": "data/source_registry.json",
            "evidence": [c for c in calls if c == "scripts/export_source_registry.py"],
            "risk": "source_registry protected path mutation",
            "verification_profile": "future_source_registry_write_profile_needed",
        },
        {
            "surface": "editorial_pipeline_reports",
            "location": "logs/runs/{run_id}-editorial-pipeline.json and reports",
            "evidence": [c for c in calls if c == "scripts/editorial_pipeline_report.py"],
            "risk": "gate/report generation; must not insert editorial_reviews in unattended mode without future profile",
            "verification_profile": "report_only",
        },
        {
            "surface": "chapter_publication_path",
            "location": "docs/book via synthesize_chapters, resolve_book_citations, update_book_pages",
            "evidence": [c for c in calls if c in {"scripts/synthesize_chapters.py", "scripts/resolve_book_citations.py", "scripts/update_book_pages.py"}],
            "risk": "docs_book chapter mutation when --allow-chapter-updates and editorial gate allow",
            "verification_profile": "docs_book_write_disabled_until_future_gates",
        },
        {
            "surface": "book_role_and_vector_build",
            "location": "site/build reports and vector_db/chroma artifacts",
            "evidence": [c for c in calls if c in {"scripts/book_role_report.py", "scripts/build_vector_db.py"}],
            "risk": "generated verification/index artifacts; must be excluded from protected publication writes unless explicitly scoped",
            "verification_profile": "report_only_or_future_index_profile",
        },
        {
            "surface": "git_commit_push",
            "location": "git index, commits, remote push",
            "evidence": ["git_commit_push", "safe_paths" if "safe_paths" in text else ""],
            "risk": "commits/pushes broad safe_paths; docs/book included when status is not blocked",
            "verification_profile": "full_publication_gate_disabled_until_future_gates_for_publication_commits",
        },
        {
            "surface": "runs_table_update",
            "location": ".var/book.sqlite:runs",
            "evidence": ["INSERT OR REPLACE INTO runs", "connect_db", "con.commit"],
            "risk": "DB mutation even for daily operational metadata",
            "verification_profile": "future_runs_metadata_profile_or_report_only_wrapper_needed",
        },
    ]
    return surfaces


def db_mutation_risk_map() -> dict[str, Any]:
    return {
        "source_notes": {"risk": "called pipeline scripts may insert future advisory notes; Run 36 does not", "current_run_changed": False, "future_profile": "db_write_source_notes_only"},
        "claims": {"risk": "extract_claims.py and future claim filing can insert/update claims; unattended claims writes blocked", "current_run_inserted": 0, "future_profile": "db_write_claims_only_or_stricter_future_claim_profile"},
        "editorial_reviews": {"risk": "editorial reports must remain report-only unless a future editorial persistence gate exists", "current_run_inserted": 0, "future_profile": "future_editorial_review_write_profile_required"},
        "source_statuses": {"risk": "capture/extraction/curation may alter source quality/privacy/duplicate statuses", "current_run_changed": False, "future_profile": "future_status_change_profile_required"},
        "claim_statuses": {"risk": "curation/editorial stages may promote/reject/alter publication decisions", "current_run_changed": False, "future_profile": "future_status_change_profile_required"},
        "editorial_statuses": {"risk": "editorial review/status persistence must not be routine dependency", "current_run_changed": False, "future_profile": "future_editorial_status_profile_required"},
        "runs": {"risk": "daily worker currently writes operational run row at end", "current_run_changed": False, "future_profile": "future_runs_metadata_profile_or_scheduler_wrapper"},
    }


def protected_paths_risk_map() -> dict[str, Any]:
    return {
        "data/source_registry.json": {"risk": "export_source_registry.py writes protected registry", "run36_changed": False, "must_block_unexpected": True},
        "raw/": {"risk": "capture scripts may write raw captures", "run36_changed": False, "must_block_unexpected": True},
        "docs/book/": {"risk": "chapter synthesis/citation resolution/update pages write publication files", "run36_changed": False, "future_profile": "docs_book_write disabled"},
        "docs/entities/": {"risk": "update_entity_pages.py writes entity docs", "run36_changed": False, "future_profile": "future docs/entities profile needed"},
        "docs/research/claims.md": {"risk": "update_claims_page.py writes claims page", "run36_changed": False, "future_profile": "future docs/research profile needed"},
        "data/schema.sql": {"risk": "schema must never drift under daily worker", "run36_changed": False, "future_profile": "schema_change disabled"},
        "scripts/daily_book_worker.py": {"risk": "integration code itself; Run 36 must not modify", "run36_changed": False, "future_profile": "control_plane_code_only for later edits"},
        ".var/book.sqlite": {"risk": "pipeline scripts and runs table can mutate DB", "run36_changed": False, "future_profile": "table-specific DB profiles required"},
        "git_state": {"risk": "git_commit_push can stage/commit/push broad paths", "run36_changed": False, "future_profile": "mutation guard + explicit commit allowlist gate"},
    }


def integration_points() -> tuple[list[dict[str, str]], list[dict[str, str]], list[dict[str, str]]]:
    state_machine = [
        {"point": "after editorial_pipeline_report pre-authoring gate", "reason": "normalize editorial blocked/allowed output into configured closed-loop states before chapter path"},
        {"point": "before synthesize_chapters/resolve_book_citations/update_book_pages", "reason": "require transition decision and hard invariants before any docs/book mutation"},
        {"point": "before commit/push decision", "reason": "derive allowed write scope from state/disposition, not only worker status"},
    ]
    transition_engine = [
        {"point": "after final editorial report is loaded", "later_call": "closed_loop_transition_engine evaluate", "reason": "evaluate current_state/proposed_next_state and automated disposition"},
        {"point": "before source_notes/claims/editorial_reviews persistence stages", "later_call": "closed_loop_transition_engine evaluate", "reason": "allow only table-specific future transitions with false author/publication flags"},
        {"point": "before --allow-chapter-updates can take effect", "later_call": "closed_loop_transition_engine evaluate", "reason": "--allow-chapter-updates must become necessary but not sufficient"},
    ]
    mutation_guard = [
        {"point": "scheduler wrapper start", "later_call": "protected_mutation_guard.py snapshot --output before", "reason": "baseline existing dirty files before daily worker"},
        {"point": "after daily worker and before commit/push", "later_call": "protected_mutation_guard.py snapshot/compare", "reason": "block unexpected DB/protected/status deltas before git state changes"},
        {"point": "after verification and before publishing alerts", "later_call": "protected_mutation_guard.py compare", "reason": "deliver machine-readable safety report for autonomous run"},
    ]
    return state_machine, transition_engine, mutation_guard


def recommended_profiles() -> dict[str, str]:
    return {
        "report_only_daily_runs": "report_only",
        "config_only_contract_updates": "config_only",
        "control_plane_code_changes": "control_plane_code_only",
        "future_source_note_writes": "db_write_source_notes_only",
        "future_claim_writes": "db_write_claims_only_or_future_stricter_claim_profile",
        "future_docs_book_updates": "docs_book_write",
        "future_schema_changes": "schema_change",
        "future_daily_worker_changes": "daily_worker_change_or_control_plane_code_only_until_enabled",
        "future_publication": "full_publication_gate",
    }


def build_report(
    run_id: str,
    daily_worker: str | Path,
    state_machine_config: str | Path,
    transition_engine: str | Path,
    mutation_guard: str | Path,
) -> dict[str, Any]:
    daily_worker_path = resolve(daily_worker)
    text = read_text(daily_worker_path)
    state_points, transition_points, guard_points = integration_points()
    inspected = inspect_files([str(daily_worker), str(state_machine_config), str(transition_engine), str(mutation_guard)])
    safety_flags = {flag: False for flag in HARD_FALSE_FLAGS}
    safety_flags.update({
        "advisory_only": True,
        "report_only": True,
        "no_author_prose": True,
        "no_chapter_prose": True,
        "no_daily_worker_mutation": True,
        "no_unattended_production_writes_enabled": True,
        "gpt55_advisory_is_machine_reasoning_not_human_approval": True,
    })
    report = {
        "run_id": run_id,
        "generated_at": utc_now(),
        "report_only": True,
        "llm_used": False,
        "inspected_files": sorted(inspected.keys()),
        "inspected_file_details": inspected,
        "daily_worker_flags": find_daily_worker_flags(text),
        "daily_worker_write_surfaces": daily_worker_write_surfaces(daily_worker_path),
        "daily_worker_mutation_paths": call_names_from_daily_worker(daily_worker_path),
        "protected_paths_risk_map": protected_paths_risk_map(),
        "db_mutation_risk_map": db_mutation_risk_map(),
        "state_machine_integration_points": state_points,
        "transition_engine_integration_points": transition_points,
        "mutation_guard_integration_points": guard_points,
        "recommended_verification_profiles": recommended_profiles(),
        "blocked_until_future_gate": [
            "unattended DB writes beyond report/log artifacts",
            "source_notes persistence without db_write_source_notes_only guard",
            "claim insertion or claim status promotion",
            "editorial_reviews insertion or editorial status mutation",
            "source status mutation without explicit status-change profile",
            "docs/book updates without docs_book_write and explicit machine gates",
            "full publication gate and publication commit/push",
            "daily-worker integration code changes",
            "schema changes",
            "raw/source_registry writes without explicit safe collection/export profile",
        ],
        "required_future_changes": [
            "add scheduler wrapper snapshots before and after daily worker execution",
            "insert transition-engine evaluation after editorial report and before chapter path",
            "make --allow-chapter-updates necessary but still insufficient without transition approval",
            "derive allowed write scope from verification profile and state-machine disposition",
            "run mutation guard before any commit/push and fail closed on unexpected deltas",
            "split daily-worker modes into report-only, DB-write, docs-write, and publication-gate profiles",
            "narrow git commit allowlists based on profile instead of broad safe_paths",
        ],
        "safe_current_state": {
            "daily_worker_not_modified_by_run36": True,
            "preflight_only": True,
            "unattended_production_not_enabled": True,
            "chapter_update_paths_remain_disabled_in_run36": True,
        },
        "production_readiness_assessment": {
            "status": "not_ready_for_unattended_mutation",
            "reason": "daily worker has multiple DB/protected/git mutation surfaces that are not yet guarded by transition-engine decisions and before/after mutation guard comparisons",
            "safe_next_step": "report_only_scheduler_wrapper_contract_or_daily_worker_integration_design_tests",
        },
        "human_in_loop_dependency_added": False,
        "changed_db": False,
        "changed_source_notes": False,
        "changed_source_registry": False,
        "changed_raw_captures": False,
        "changed_docs_book": False,
        "changed_schema": False,
        "changed_daily_worker": False,
        "claims_inserted": 0,
        "editorial_reviews_inserted": 0,
        "source_status_changed": False,
        "claim_status_changed": False,
        "editorial_status_changed": False,
        "safety_flags": safety_flags,
    }
    return report


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Daily-worker closed-loop integration preflight — Run 36",
        "",
        f"Generated: {report['generated_at']}",
        "",
        "## Scope",
        "",
        "This is a deterministic report-only preflight. It does not modify `scripts/daily_book_worker.py`, SQLite, source registry, raw captures, docs/book, schema, statuses, claims, source notes, or editorial reviews. GPT-5.5 was not used.",
        "",
        "## Daily-worker write surfaces",
        "",
    ]
    for item in report["daily_worker_write_surfaces"]:
        lines += [f"- {item['surface']}: {item['location']}", f"  - risk: {item['risk']}", f"  - profile: `{item['verification_profile']}`"]
    lines += ["", "## Scheduler/daily-worker risks", ""]
    for path, info in report["protected_paths_risk_map"].items():
        lines.append(f"- `{path}`: {info['risk']} (Run 36 changed: `{info['run36_changed']}`)")
    lines += ["", "## Current blockers for unattended operation", ""]
    for item in report["blocked_until_future_gate"]:
        lines.append(f"- {item}")
    lines += ["", "## Transition-engine insertion points", ""]
    for item in report["transition_engine_integration_points"]:
        lines.append(f"- {item['point']}: {item['reason']}")
    lines += ["", "## Mutation-guard insertion points", ""]
    for item in report["mutation_guard_integration_points"]:
        lines.append(f"- {item['point']}: {item['reason']}")
    lines += ["", "## Recommended verification profiles", ""]
    for key, value in report["recommended_verification_profiles"].items():
        lines.append(f"- {key}: `{value}`")
    lines += [
        "",
        "## What must remain disabled",
        "",
        "- unattended production writes",
        "- docs/book updates",
        "- publication approval and full publication gate",
        "- claim insertion and editorial review insertion",
        "- source/claim/editorial status mutation",
        "- daily-worker mutation paths without before/after guard comparison",
        "",
        "## Why Run 36 does not modify daily worker",
        "",
        "The daily worker currently has broad orchestration, DB, protected-doc, raw/source-registry, and git state surfaces. Editing it before a report-only integration contract would risk enabling mutation paths before the transition engine and mutation guard are wired as fail-closed gates.",
        "",
        "## Recommended Run 37",
        "",
        "Create a report-only scheduler wrapper contract and tests for before/after mutation-guard snapshots around `daily_book_worker.py --no-commit --skip-capture`, still without editing the daily worker or enabling unattended writes. The wrapper should compute the verification profile from mode/disposition and refuse commit/push on any unexpected protected or DB/status delta.",
        "",
        "## Safety confirmations",
        "",
    ]
    for key in [
        "human_in_loop_dependency_added",
        "changed_db",
        "changed_source_notes",
        "changed_source_registry",
        "changed_raw_captures",
        "changed_docs_book",
        "changed_schema",
        "changed_daily_worker",
        "claims_inserted",
        "editorial_reviews_inserted",
        "source_status_changed",
        "claim_status_changed",
        "editorial_status_changed",
    ]:
        lines.append(f"- {key}: `{report[key]}`")
    return "\n".join(lines) + "\n"


def write_reports(report: dict[str, Any], output_dir: str | Path, suffix: str) -> dict[str, str]:
    out = resolve(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    base = f"{report['run_id']}-daily-worker-closed-loop-preflight-{suffix}"
    json_path = out / f"{base}.json"
    md_path = out / f"{base}.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    return {"json": rel(json_path), "markdown": rel(md_path)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Analyze daily-worker closed-loop integration preflight")
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--daily-worker", required=True)
    ap.add_argument("--state-machine-config", required=True)
    ap.add_argument("--transition-engine", required=True)
    ap.add_argument("--mutation-guard", required=True)
    ap.add_argument("--output-dir", default="reports/editorial")
    ap.add_argument("--report-suffix", default="run36")
    args = ap.parse_args(argv)
    report = build_report(args.run_id, args.daily_worker, args.state_machine_config, args.transition_engine, args.mutation_guard)
    paths = write_reports(report, args.output_dir, args.report_suffix)
    print(json.dumps({"ok": True, "report_only": True, "llm_used": False, "outputs": paths}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
