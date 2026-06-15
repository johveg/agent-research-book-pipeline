#!/usr/bin/env python3
"""Report-only scheduler wrapper contract for safe daily-worker orchestration.

Run 38 models how a future scheduler should wrap daily_book_worker.py with
protected mutation-guard snapshots and fail-closed commit/push policy. In
--run-mutation-guard mode, the wrapper performs its own before/after/compare
guard subprocess flow while still not executing the daily worker.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
HARD_FLAGS = [
    "author_allowed",
    "publication_approved",
    "eligible_for_claim_insertion",
    "eligible_for_authoring",
    "eligible_for_publication",
    "chapter_update_allowed",
]

PROFILE_MATRIX: dict[tuple[str, str], dict[str, Any]] = {
    ("report_only_daily", "safe_reports_only"): {"ok": True, "profile": "report_only", "future_disabled": False},
    ("config_update", "config_only"): {"ok": True, "profile": "config_only", "future_disabled": False},
    ("control_plane_code", "control_plane_code_only"): {"ok": True, "profile": "control_plane_code_only", "future_disabled": False},
    ("source_note_write", "caveat_only"): {
        "ok": False,
        "profile": "db_write_source_notes_only",
        "future_disabled": True,
        "fail_closed": True,
        "reason": "future_source_note_write_gate_not_enabled",
    },
}
FAIL_CLOSED_MODES = {"claim_write", "docs_book_write", "publication"}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def resolve(path: str | Path) -> Path:
    p = Path(path)
    return p if p.is_absolute() else ROOT / p


def rel(path: str | Path) -> str:
    p = resolve(path)
    try:
        return str(p.resolve().relative_to(ROOT))
    except ValueError:
        return str(p)


def load_json(path: str | Path) -> dict[str, Any]:
    p = resolve(path)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def select_verification_profile(mode: str, disposition: str) -> dict[str, Any]:
    if (mode, disposition) in PROFILE_MATRIX:
        result = dict(PROFILE_MATRIX[(mode, disposition)])
        result.setdefault("fail_closed", not result.get("ok", False))
        result.setdefault("reason", "mapped")
        result["mode"] = mode
        result["disposition"] = disposition
        return result
    if mode in FAIL_CLOSED_MODES:
        return {
            "ok": False,
            "profile": None,
            "future_disabled": True,
            "fail_closed": True,
            "mode": mode,
            "disposition": disposition,
            "reason": f"{mode}_requires_future_explicit_machine_gate",
        }
    valid_modes = {m for m, _ in PROFILE_MATRIX} | FAIL_CLOSED_MODES
    valid_dispositions = {d for _, d in PROFILE_MATRIX}
    if mode not in valid_modes:
        reason = "unknown_mode"
    elif disposition not in valid_dispositions:
        reason = "unknown_disposition"
    else:
        reason = "unsupported_mode_disposition_pair"
    return {
        "ok": False,
        "profile": None,
        "future_disabled": False,
        "fail_closed": True,
        "mode": mode,
        "disposition": disposition,
        "reason": reason,
    }


def build_daily_worker_command_contract(
    run_id: str,
    daily_worker: str | Path,
    execute_safe_command: bool = False,
) -> dict[str, Any]:
    # The safest existing daily-worker argv still lacks explicit flags to disable
    # entity/claim extraction, docs/entities updates, claims page updates,
    # source-registry export, and the runs-table write. Therefore Run 38 models
    # the later command but refuses execution even if --execute-safe-command is
    # requested. Future Run 39+ work should add or wrap those missing controls
    # before any live scheduler invocation is allowed.
    argv = [
        "python3",
        rel(daily_worker),
        run_id,
        "--skip-capture",
        "--no-commit",
        "--skip-vector",
    ]
    execution_requested = bool(execute_safe_command)
    execution_refusal_reasons = [
        "current_daily_worker_lacks_no_entity_claim_extraction_flag",
        "current_daily_worker_lacks_no_docs_entities_claims_page_flag",
        "current_daily_worker_lacks_no_source_registry_export_flag",
        "current_daily_worker_writes_runs_table_metadata",
        "run38_is_report_only_contract",
    ]
    return {
        "argv": argv,
        "command_string": " ".join(argv),
        "execution_requested": execution_requested,
        "would_execute": False,
        "execution_enabled": False,
        "execution_refusal_reasons": execution_refusal_reasons,
        "blocks_capture": True,
        "blocks_entity_claim_extraction": True,
        "blocks_docs_entities_claims_mutation": True,
        "blocks_source_registry_mutation": True,
        "blocks_docs_book_mutation": True,
        "blocks_commit": True,
        "blocks_push": True,
        "blocks_schema_change": True,
        "notes": [
            "Run 38 does not execute this command.",
            "--skip-capture prevents raw capture; --no-commit prevents commit/push; omission of --allow-chapter-updates blocks docs/book chapter updates.",
            "Execution remains refused because the current daily worker has no flags to disable extraction, docs/entities or claims page updates, source-registry export, and runs-table metadata writes.",
        ],
    }


def default_guard_report() -> dict[str, Any]:
    return {
        "ok": True,
        "unexpected_changed_paths": [],
        "db_delta": {},
        "status_hash_delta": {},
        "protected_path_delta": {},
        "docs_book_changed": False,
        "source_registry_changed": False,
        "raw_changed": False,
        "schema_changed": False,
        "daily_worker_changed": False,
        "human_in_loop_dependency_added": False,
        "hard_flags_changed": {flag: False for flag in HARD_FLAGS},
        "failed_checks": [],
        "recommendation": "dry_run_no_compare_performed_inside_wrapper",
    }


def build_mutation_guard_snapshot_command(mutation_guard: str | Path, output: str | Path) -> list[str]:
    return [sys.executable, rel(mutation_guard), "snapshot", "--output", str(output)]


def build_mutation_guard_compare_command(
    mutation_guard: str | Path,
    before_snapshot: str | Path,
    after_snapshot: str | Path,
    selected_profile: str,
    output: str | Path,
) -> list[str]:
    return [
        sys.executable,
        rel(mutation_guard),
        "compare",
        "--before",
        str(before_snapshot),
        "--after",
        str(after_snapshot),
        "--profile",
        selected_profile,
        "--output",
        str(output),
    ]


def _fail_closed_guard_result(
    profile: str | None,
    before_snapshot: str | Path,
    after_snapshot: str | Path,
    report_path: str | Path,
    failed_check: str,
    completed: subprocess.CompletedProcess | None = None,
) -> dict[str, Any]:
    failed_checks = [failed_check]
    if completed is not None and completed.returncode != 0:
        failed_checks.append("mutation_guard_subprocess_failed")
    guard_report = default_guard_report()
    guard_report.update(
        {
            "ok": False,
            "profile": profile,
            "failed_checks": failed_checks,
            "unexpected_changed_paths": [],
            "recommendation": "fail_closed_scheduler_wrapper_mutation_guard_flow",
        }
    )
    return {
        "executed": True,
        "ok": False,
        "profile_used": profile,
        "before_snapshot": str(before_snapshot),
        "after_snapshot": str(after_snapshot),
        "report_path": str(report_path),
        "failed_checks": failed_checks,
        "unexpected_changed_paths": [],
        "report": guard_report,
        "subprocess_returncode": completed.returncode if completed is not None else None,
        "subprocess_stdout": completed.stdout if completed is not None else None,
        "subprocess_stderr": completed.stderr if completed is not None else None,
    }


def run_mutation_guard_flow(
    mutation_guard: str | Path,
    selected_profile: str | None,
    before_snapshot: str | Path,
    after_snapshot: str | Path,
    mutation_guard_report: str | Path,
    runner=subprocess.run,
) -> dict[str, Any]:
    if not selected_profile:
        return _fail_closed_guard_result(
            selected_profile,
            before_snapshot,
            after_snapshot,
            mutation_guard_report,
            "selected_verification_profile_missing",
        )

    before = Path(before_snapshot)
    after = Path(after_snapshot)
    report_path = Path(mutation_guard_report)
    for path in [before, after, report_path]:
        if path.exists():
            path.unlink()

    before_cmd = build_mutation_guard_snapshot_command(mutation_guard, before)
    before_proc = runner(before_cmd, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=180)
    if before_proc.returncode != 0:
        return _fail_closed_guard_result(selected_profile, before, after, report_path, "before_snapshot_subprocess_failed", before_proc)
    if not before.exists():
        return _fail_closed_guard_result(selected_profile, before, after, report_path, "before_snapshot_missing", before_proc)

    after_cmd = build_mutation_guard_snapshot_command(mutation_guard, after)
    after_proc = runner(after_cmd, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=180)
    if after_proc.returncode != 0:
        return _fail_closed_guard_result(selected_profile, before, after, report_path, "after_snapshot_subprocess_failed", after_proc)
    if not after.exists():
        return _fail_closed_guard_result(selected_profile, before, after, report_path, "after_snapshot_missing", after_proc)

    compare_cmd = build_mutation_guard_compare_command(mutation_guard, before, after, selected_profile, report_path)
    compare_proc = runner(compare_cmd, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=180)
    if compare_proc.returncode not in (0, 2):
        return _fail_closed_guard_result(selected_profile, before, after, report_path, "mutation_guard_compare_subprocess_failed", compare_proc)
    if not report_path.exists():
        return _fail_closed_guard_result(selected_profile, before, after, report_path, "mutation_guard_report_missing", compare_proc)

    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except Exception as exc:
        result = _fail_closed_guard_result(selected_profile, before, after, report_path, "mutation_guard_report_unreadable", compare_proc)
        result["exception"] = str(exc)
        return result

    return {
        "executed": True,
        "ok": bool(report.get("ok")),
        "profile_used": report.get("profile", selected_profile),
        "before_snapshot": str(before),
        "after_snapshot": str(after),
        "report_path": str(report_path),
        "failed_checks": report.get("failed_checks", []),
        "unexpected_changed_paths": report.get("unexpected_changed_paths", []),
        "report": report,
        "subprocess_returncode": compare_proc.returncode,
        "subprocess_stdout": compare_proc.stdout,
        "subprocess_stderr": compare_proc.stderr,
    }


def evaluate_commit_push_policy(
    mutation_guard_report: dict[str, Any],
    selected_profile: str | None,
    git_diff_check_ok: bool = True,
    secrets_detected: bool = False,
    report_only_contract: bool = True,
) -> dict[str, Any]:
    reasons: list[str] = []
    if not mutation_guard_report.get("ok", False):
        reasons.append("mutation_guard_failed")
    if not git_diff_check_ok:
        reasons.append("git_diff_check_failed")
    if secrets_detected:
        reasons.append("secrets_detected")
    if mutation_guard_report.get("unexpected_changed_paths"):
        reasons.append("unexpected_protected_or_scope_changes")
    if mutation_guard_report.get("db_delta"):
        reasons.append("db_delta_outside_selected_profile")
    if mutation_guard_report.get("status_hash_delta"):
        reasons.append("status_hash_delta_outside_selected_profile")
    if selected_profile in {"report_only", "config_only", "control_plane_code_only"} and mutation_guard_report.get("docs_book_changed"):
        reasons.append("docs_book_changed_under_non_publication_profile")
    if mutation_guard_report.get("human_in_loop_dependency_added"):
        reasons.append("human_in_loop_dependency_added")
    hard = mutation_guard_report.get("hard_flags_changed", {}) or {}
    if any(bool(v) for v in hard.values()):
        reasons.append("hard_flag_true")
    if report_only_contract:
        reasons.append("report_only_contract_blocks_commit")
        reasons.append("report_only_contract_blocks_push")
    commit_reasons = sorted(set(r.replace("report_only_contract_blocks_push", "report_only_contract_blocks_commit") for r in reasons))
    push_reasons = sorted(set(r.replace("report_only_contract_blocks_commit", "report_only_contract_blocks_push") for r in reasons))
    return {
        "commit_allowed": False if commit_reasons else True,
        "push_allowed": False if push_reasons else True,
        "commit_block_reasons": commit_reasons,
        "push_block_reasons": push_reasons,
    }


def inspect_paths(paths: list[str | Path]) -> dict[str, dict[str, Any]]:
    out = {}
    for path in paths:
        p = resolve(path)
        out[rel(p)] = {"exists": p.exists(), "bytes": p.stat().st_size if p.exists() else 0}
    return out


def build_report(
    run_id: str,
    daily_worker: str | Path,
    state_machine_config: str | Path,
    transition_engine: str | Path,
    mutation_guard: str | Path,
    daily_worker_preflight: str | Path,
    mode: str,
    disposition: str,
    output_dir: str | Path,
    report_suffix: str,
    dry_run: bool = True,
    execute_safe_command: bool = False,
    before_snapshot_path: str | Path | None = None,
    after_snapshot_path: str | Path | None = None,
    mutation_guard_report_path: str | Path | None = None,
    mutation_guard_report: dict[str, Any] | None = None,
    mutation_guard_execution: dict[str, Any] | None = None,
) -> dict[str, Any]:
    profile = select_verification_profile(mode, disposition)
    selected = profile.get("profile")
    command = build_daily_worker_command_contract(run_id, daily_worker, execute_safe_command=execute_safe_command)
    if dry_run:
        command["would_execute"] = False
        command["execution_enabled"] = False
    preflight = load_json(daily_worker_preflight)
    guard_execution = mutation_guard_execution or {
        "executed": False,
        "ok": True,
        "profile_used": selected,
        "before_snapshot": str(before_snapshot_path or "/tmp/run38-before.json"),
        "after_snapshot": str(after_snapshot_path or "/tmp/run38-after.json"),
        "report_path": rel(mutation_guard_report_path or resolve(output_dir) / f"{run_id}-mutation-guard-{report_suffix}.json"),
        "failed_checks": [],
        "unexpected_changed_paths": [],
        "report": mutation_guard_report or default_guard_report(),
    }
    guard = guard_execution.get("report") or mutation_guard_report or default_guard_report()
    if guard_execution.get("executed") and not guard_execution.get("ok", False):
        guard = dict(guard)
        guard["ok"] = False
        guard.setdefault("failed_checks", guard_execution.get("failed_checks", []))
    policy = evaluate_commit_push_policy(guard, selected_profile=selected)
    safety_flags = {flag: False for flag in HARD_FLAGS}
    safety_flags.update(
        {
            "report_only": True,
            "dry_run": bool(dry_run),
            "no_author_prose": True,
            "no_chapter_prose": True,
            "no_unattended_production_writes_enabled": True,
            "gpt55_advisory_is_machine_reasoning_not_human_approval": True,
        }
    )
    report = {
        "run_id": run_id,
        "generated_at": utc_now(),
        "report_only": True,
        "dry_run": bool(dry_run),
        "llm_used": False,
        "provider": None,
        "model": None,
        "bridge": None,
        "model_profile": None,
        "mode": mode,
        "disposition": disposition,
        "profile_mapping": profile,
        "selected_verification_profile": selected,
        "daily_worker_command_contract": command,
        "daily_worker_command_would_execute": bool(command["would_execute"]),
        "execution_enabled": bool(command["execution_enabled"]),
        "execution_performed": False,
        "mutation_guard_executed": bool(guard_execution.get("executed")),
        "mutation_guard_ok": bool(guard_execution.get("ok", guard.get("ok", False))),
        "mutation_guard_profile_used": guard_execution.get("profile_used") or guard.get("profile") or selected,
        "mutation_guard_before_snapshot": str(guard_execution.get("before_snapshot") or before_snapshot_path or "/tmp/run38-before.json"),
        "mutation_guard_after_snapshot": str(guard_execution.get("after_snapshot") or after_snapshot_path or "/tmp/run38-after.json"),
        "mutation_guard_report_path": rel(guard_execution.get("report_path") or mutation_guard_report_path or resolve(output_dir) / f"{run_id}-mutation-guard-{report_suffix}.json"),
        "mutation_guard_failed_checks": guard_execution.get("failed_checks") or guard.get("failed_checks", []),
        "mutation_guard_unexpected_changed_paths": guard_execution.get("unexpected_changed_paths") or guard.get("unexpected_changed_paths", []),
        "mutation_guard_result": guard,
        "preflight_report_path": rel(daily_worker_preflight),
        "state_machine_config_path": rel(state_machine_config),
        "transition_engine_path": rel(transition_engine),
        "mutation_guard_path": rel(mutation_guard),
        "before_snapshot_path": str(guard_execution.get("before_snapshot") or before_snapshot_path or "/tmp/run38-before.json"),
        "after_snapshot_path": str(guard_execution.get("after_snapshot") or after_snapshot_path or "/tmp/run38-after.json"),
        "mutation_guard_report_path": rel(guard_execution.get("report_path") or mutation_guard_report_path or resolve(output_dir) / f"{run_id}-mutation-guard-{report_suffix}.json"),
        "commit_allowed": policy["commit_allowed"],
        "push_allowed": policy["push_allowed"],
        "commit_block_reasons": policy["commit_block_reasons"],
        "push_block_reasons": policy["push_block_reasons"],
        "protected_write_surfaces_blocked": True,
        "db_write_surfaces_blocked": True,
        "docs_book_write_blocked": True,
        "source_registry_write_blocked": True,
        "raw_capture_write_blocked": True,
        "schema_change_blocked": True,
        "daily_worker_change_blocked": True,
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
        "inspected_paths": inspect_paths([daily_worker, mutation_guard, transition_engine, state_machine_config, daily_worker_preflight]),
        "preflight_write_surfaces": preflight.get("daily_worker_write_surfaces", []),
        "daily_worker_write_surfaces_still_blocked": [
            "capture_scripts",
            "entity_and_claim_extraction",
            "docs_entities_and_claims_pages",
            "source_registry_export",
            "chapter_publication_path",
            "git_commit_push",
            "runs_table_update",
        ],
        "mutation_guard_strategy": [
            "take before snapshot at scheduler wrapper start",
            "execute only a profile-approved safe command after future gates exist",
            "take after snapshot after worker exits",
            "compare before/after using selected verification profile",
            "block commit/push on guard failure, unexpected protected paths, DB/status deltas, hard flags, human-in-loop dependency, diff-check failure, or secrets",
        ],
        "missing_before_unattended_execution": [
            "daily worker mode split or flags that can disable extraction/entity/docs/source-registry side effects",
            "transition-engine evaluation wired before any mutation path",
            "mutation-guard compare wired before commit/push",
            "future explicit gates for source-note, claim, docs/book, and publication profiles",
            "machine-only safety reports proving no human-review production dependency",
        ],
        "recommendation_for_run38": "Add a report-only scheduler wrapper dry-run that invokes the protected mutation guard snapshot/compare subprocesses itself while still not executing daily_book_worker.py.",
        "recommendation_for_run39": "Add the next machine-only scheduler gate: require explicit daily-worker no-write flags or a wrapper-enforced no-op worker mode before any unattended execution path can be enabled.",
    }
    return report


def render_markdown(report: dict[str, Any]) -> str:
    cmd = report["daily_worker_command_contract"]
    lines = [
        "# Scheduler wrapper contract — Run 38",
        "",
        f"Generated: {report['generated_at']}",
        "",
        "## Summary",
        "",
        "Run 38 upgrades the deterministic, report-only scheduler wrapper contract so the wrapper itself runs the protected mutation guard before snapshot, after snapshot, and compare subprocesses. It builds the safe daily-worker command contract but does not execute `scripts/daily_book_worker.py`, does not enable unattended production writes, and keeps wrapper-level commit/push authorization blocked.",
        "",
        "## Selected scheduler mode",
        "",
        f"- mode: `{report['mode']}`",
        f"- disposition: `{report['disposition']}`",
        f"- selected verification profile: `{report['selected_verification_profile']}`",
        "",
        "## Command that would be run later",
        "",
        f"```bash\n{cmd['command_string']}\n```",
        "",
        "Why it was not executed: Run 38 is dry-run/report-only, and future daily-worker execution still needs narrower mode controls plus mutation-guard enforcement before commit/push.",
        "",
        "## Mutation guard before/after/compare flow",
        "",
        f"- mutation_guard_executed: `{report['mutation_guard_executed']}`",
        f"- mutation_guard_ok: `{report['mutation_guard_ok']}`",
        f"- profile used: `{report['mutation_guard_profile_used']}`",
        f"- before snapshot: `{report['mutation_guard_before_snapshot']}`",
        f"- after snapshot: `{report['mutation_guard_after_snapshot']}`",
        f"- report path: `{report['mutation_guard_report_path']}`",
        f"- failed checks: `{report['mutation_guard_failed_checks']}`",
        f"- unexpected changed paths: `{report['mutation_guard_unexpected_changed_paths']}`",
        "",
        "## Mutation guard strategy",
        "",
    ]
    for item in report["mutation_guard_strategy"]:
        lines.append(f"- {item}")
    lines += ["", "## Commit/push block strategy", ""]
    lines.append(f"- commit_allowed: `{report['commit_allowed']}`")
    lines.append(f"- push_allowed: `{report['push_allowed']}`")
    lines.append(f"- commit block reasons: `{report['commit_block_reasons']}`")
    lines.append(f"- push block reasons: `{report['push_block_reasons']}`")
    lines += ["", "## Daily-worker write surfaces still blocked", ""]
    for item in report["daily_worker_write_surfaces_still_blocked"]:
        lines.append(f"- `{item}`")
    lines += ["", "## What remains missing before unattended execution", ""]
    for item in report["missing_before_unattended_execution"]:
        lines.append(f"- {item}")
    lines += ["", "## Safety confirmations", ""]
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
        "execution_performed",
    ]:
        lines.append(f"- {key}: `{report[key]}`")
    lines += ["", "## Recommendation for Run 39", "", report["recommendation_for_run39"], ""]
    return "\n".join(lines)


def write_reports(report: dict[str, Any], output_dir: str | Path, suffix: str) -> dict[str, str]:
    out = resolve(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    base = f"{report['run_id']}-scheduler-wrapper-contract-{suffix}"
    json_path = out / f"{base}.json"
    md_path = out / f"{base}.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    return {"json": rel(json_path), "markdown": rel(md_path)}


def maybe_execute(command: dict[str, Any]) -> None:
    if not command.get("execution_enabled"):
        return
    # This branch is intentionally conservative and unused in Run 38.
    subprocess.run(command["argv"], cwd=ROOT, check=True, timeout=600)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build report-only scheduler wrapper contract")
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--daily-worker", required=True)
    ap.add_argument("--state-machine-config", required=True)
    ap.add_argument("--transition-engine", required=True)
    ap.add_argument("--mutation-guard", required=True)
    ap.add_argument("--daily-worker-preflight", required=True)
    ap.add_argument("--mode", required=True)
    ap.add_argument("--disposition", required=True)
    ap.add_argument("--output-dir", default="reports/editorial")
    ap.add_argument("--report-suffix", default="run38")
    ap.add_argument("--dry-run", action="store_true", default=False)
    ap.add_argument("--execute-safe-command", action="store_true", default=False)
    ap.add_argument("--run-mutation-guard", action="store_true", default=False)
    ap.add_argument("--before-snapshot", default=None)
    ap.add_argument("--after-snapshot", default=None)
    ap.add_argument("--mutation-guard-report", default=None)
    args = ap.parse_args(argv)
    profile = select_verification_profile(args.mode, args.disposition)
    selected = profile.get("profile")
    mutation_guard_report_path = args.mutation_guard_report or str(resolve(args.output_dir) / f"{args.run_id}-mutation-guard-{args.report_suffix}.json")
    before_snapshot = args.before_snapshot or f"/tmp/{args.run_id}-{args.report_suffix}-before.json"
    after_snapshot = args.after_snapshot or f"/tmp/{args.run_id}-{args.report_suffix}-after.json"
    guard_execution = None
    if args.run_mutation_guard:
        guard_execution = run_mutation_guard_flow(
            mutation_guard=args.mutation_guard,
            selected_profile=selected,
            before_snapshot=before_snapshot,
            after_snapshot=after_snapshot,
            mutation_guard_report=mutation_guard_report_path,
        )
    report = build_report(
        run_id=args.run_id,
        daily_worker=args.daily_worker,
        state_machine_config=args.state_machine_config,
        transition_engine=args.transition_engine,
        mutation_guard=args.mutation_guard,
        daily_worker_preflight=args.daily_worker_preflight,
        mode=args.mode,
        disposition=args.disposition,
        output_dir=args.output_dir,
        report_suffix=args.report_suffix,
        dry_run=args.dry_run or not args.execute_safe_command,
        execute_safe_command=args.execute_safe_command,
        before_snapshot_path=before_snapshot,
        after_snapshot_path=after_snapshot,
        mutation_guard_report_path=mutation_guard_report_path,
        mutation_guard_execution=guard_execution,
    )
    maybe_execute(report["daily_worker_command_contract"])
    paths = write_reports(report, args.output_dir, args.report_suffix)
    ok = not (args.run_mutation_guard and not report["mutation_guard_ok"])
    print(json.dumps({"ok": ok, "report_only": True, "dry_run": report["dry_run"], "execution_performed": False, "mutation_guard_executed": report["mutation_guard_executed"], "mutation_guard_ok": report["mutation_guard_ok"], "outputs": paths}, sort_keys=True))
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
