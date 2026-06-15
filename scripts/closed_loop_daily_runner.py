#!/usr/bin/env python3
"""Closed-loop daily runner shell for guarded preflight execution.

Run 41 introduces orchestration and event-ledger wiring only. It can execute the
wrapped daily worker in preflight-only/no-op mode, but it never authorizes book
publication, docs/book updates, raw collection, metadata writes, internal commits,
or internal pushes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shlex
import sqlite3
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import closed_loop_event_ledger as event_ledger

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable

REQUIRED_CAPABILITIES = [
    "supports_skip_capture",
    "supports_skip_entity_extraction",
    "supports_skip_claim_extraction",
    "supports_skip_docs_entities_update",
    "supports_skip_docs_claims_update",
    "supports_skip_source_registry_export",
    "supports_skip_run_table_update",
    "supports_skip_vector",
    "supports_no_commit",
    "supports_no_push",
    "supports_no_docs_book_update_without_gate",
    "supports_preflight_only",
    "preflight_only_no_write",
    "capability_probe_no_write",
]

SAFE_FLAGS = [
    "--preflight-only",
    "--skip-capture",
    "--skip-entity-extraction",
    "--skip-claim-extraction",
    "--skip-docs-entities-update",
    "--skip-docs-claims-update",
    "--skip-source-registry-export",
    "--skip-run-table-update",
    "--skip-vector",
    "--no-commit",
]

PROTECTED_PATHS = [
    ".var/book.sqlite",
    "data/source_registry.json",
    "raw",
    "docs/book",
    "docs/entities",
    "docs/research/claims.md",
    "data/schema.sql",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def resolve(path: str | Path) -> Path:
    p = Path(path)
    return p if p.is_absolute() else ROOT / p


def run_subprocess(cmd: list[str]) -> dict[str, Any]:
    proc = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)
    return {
        "cmd": cmd,
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "stdout_tail": proc.stdout[-4000:],
        "stderr_tail": proc.stderr[-4000:],
    }


def stable_hash(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest()


def select_verification_profile(mode: str, disposition: str) -> str:
    if mode == "preflight_only" and disposition == "safe_reports_only":
        return "preflight_only_daily_runner"
    if mode == "report_only" and disposition == "safe_reports_only":
        return "report_only"
    return "blocked_unsupported_mode"


def build_daily_worker_command(daily_worker: str, run_id: str) -> list[str]:
    return [PY, daily_worker, run_id, *SAFE_FLAGS]


def command_contract_hash(command: list[str], mode: str, disposition: str) -> str:
    return stable_hash({"command": command, "mode": mode, "disposition": disposition})


def probe_daily_worker(daily_worker: str) -> dict[str, Any]:
    result = run_subprocess([PY, daily_worker, "--print-capabilities-json"])
    parsed: dict[str, Any] | None = None
    ok = result["returncode"] == 0
    error = ""
    if ok:
        try:
            parsed = json.loads(result["stdout"])
        except Exception as exc:
            ok = False
            error = f"invalid_json:{type(exc).__name__}:{exc}"
    else:
        error = f"nonzero_exit:{result['returncode']}"
    return {"ok": ok, "capabilities": parsed or {}, "error": error, "subprocess": result}


def missing_capabilities(capabilities: dict[str, Any]) -> list[str]:
    return [key for key in REQUIRED_CAPABILITIES if capabilities.get(key) is not True]


def current_db_counts(db_path: str | Path = ".var/book.sqlite") -> dict[str, int | None]:
    path = resolve(db_path)
    if not path.exists():
        return {"source_notes": None, "claims": None, "editorial_reviews": None}
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        return {
            table: int(con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in ["source_notes", "claims", "editorial_reviews"]
        }
    finally:
        con.close()


def run_guard_snapshot(mutation_guard: str, output: str) -> dict[str, Any]:
    return run_subprocess([PY, mutation_guard, "snapshot", "--output", output])


def run_guard_compare(mutation_guard: str, before: str, after: str, profile: str, output: str) -> dict[str, Any]:
    return run_subprocess([PY, mutation_guard, "compare", "--before", before, "--after", after, "--profile", profile, "--output", output])


def load_json_file(path: str | Path, default: Any) -> Any:
    try:
        return json.loads(resolve(path).read_text(encoding="utf-8"))
    except Exception:
        return default


def summarize_guard_report(report: dict[str, Any]) -> dict[str, Any]:
    protected_delta = report.get("protected_path_delta") or {}
    return {
        "mutation_guard_ok": bool(report.get("ok")),
        "mutation_guard_profile_used": report.get("profile"),
        "mutation_guard_failed_checks": report.get("failed_checks", []),
        "mutation_guard_unexpected_changed_paths": report.get("unexpected_changed_paths", []),
        "db_delta": report.get("db_delta", {}),
        "status_hash_delta": report.get("status_hash_delta", {}),
        "protected_path_delta": protected_delta,
        "docs_book_changed": bool(report.get("docs_book_changed") or protected_delta.get("docs/book")),
        "docs_entities_changed": bool(report.get("docs_entities_changed") or protected_delta.get("docs/entities")),
        "docs_claims_changed": bool(report.get("docs_claims_changed") or protected_delta.get("docs/research/claims.md")),
        "source_registry_changed": bool(report.get("source_registry_changed") or protected_delta.get("data/source_registry.json")),
        "raw_changed": bool(report.get("raw_changed") or protected_delta.get("raw")),
        "schema_changed": bool(report.get("schema_changed") or protected_delta.get("data/schema.sql")),
        "daily_worker_changed_during_execution": bool(report.get("daily_worker_changed") or protected_delta.get("scripts/daily_book_worker.py")),
    }


def format_status(report: dict[str, Any]) -> str:
    command = " ".join(shlex.quote(x) for x in report.get("daily_worker_command", []))
    lines = [
        "# Run 41 status — Full closed-loop daily runner shell with event ledger and guarded preflight execution",
        "",
        f"- Success/failure: `{'success' if report.get('final_disposition') == 'attempt_completed' else 'failure'}`",
        f"- Run ID: `{report.get('run_id')}`",
        f"- Attempt ID: `{report.get('attempt_id')}`",
        f"- GPT-5.5 used: `false`",
        "- Model/provider/profile: `not used`",
        f"- execution_allowed: `{report.get('execution_allowed')}`",
        f"- execution_performed: `{report.get('execution_performed')}`",
        f"- execution_type: `{report.get('execution_type')}`",
        f"- Daily-worker command executed: `{command}`",
        f"- Capability probe ok: `{report.get('daily_worker_capability_probe', {}).get('ok')}`",
        f"- Missing capabilities: `{report.get('missing_capabilities')}`",
        f"- Supported capabilities: `{report.get('supported_capabilities')}`",
        f"- Event ledger path: `{report.get('event_ledger_path')}`",
        f"- Event count delta: `{report.get('event_count_delta')}`",
        f"- Idempotency key: `{report.get('idempotency_key')}`",
        f"- Mutation guard result: `ok={report.get('mutation_guard_ok')}`",
        f"- Mutation guard profile: `{report.get('mutation_guard_profile_used')}`",
        f"- Mutation guard failed checks: `{report.get('mutation_guard_failed_checks')}`",
        f"- Unexpected changed paths: `{report.get('mutation_guard_unexpected_changed_paths')}`",
        f"- DB deltas: `{report.get('db_delta')}`",
        f"- Current DB counts: `{report.get('current_db_counts')}`",
        f"- Status hash delta: `{report.get('status_hash_delta')}`",
        f"- Protected path delta: `{report.get('protected_path_delta')}`",
        f"- docs/book delta: `{report.get('docs_book_changed')}`",
        f"- docs/entities delta: `{report.get('docs_entities_changed')}`",
        f"- docs/research/claims.md delta: `{report.get('docs_claims_changed')}`",
        f"- source_registry delta: `{report.get('source_registry_changed')}`",
        f"- raw delta: `{report.get('raw_changed')}`",
        f"- schema delta: `{report.get('schema_changed')}`",
        f"- daily-worker delta during execution: `{report.get('daily_worker_changed_during_execution')}`",
        f"- production_publish_enabled: `{report.get('production_publish_enabled')}`",
        f"- docs_book_update_enabled: `{report.get('docs_book_update_enabled')}`",
        f"- raw_collection_enabled: `{report.get('raw_collection_enabled')}`",
        f"- metadata_write_enabled: `{report.get('metadata_write_enabled')}`",
        f"- authoring_enabled: `{report.get('authoring_enabled')}`",
        f"- publication_approved: `{report.get('publication_approved')}`",
        f"- chapter_update_allowed: `{report.get('chapter_update_allowed')}`",
        f"- human_in_loop_dependency_added: `{report.get('human_in_loop_dependency_added')}`",
        f"- Runner commit allowed: `{report.get('runner_commit_allowed')}`",
        f"- Runner push allowed: `{report.get('runner_push_allowed')}`",
        f"- Runner commit block reasons: `{report.get('runner_commit_block_reasons')}`",
        f"- Runner push block reasons: `{report.get('runner_push_block_reasons')}`",
        f"- Reports created: `{report.get('reports_created')}`",
        "- Tests run and results: `pending external verification`",
        "- Mutation guard result: `pending external repository guard unless this is final status after commit`",
        "- Commit hash: `pending external repository checkpoint`",
        "- Push result: `pending external repository checkpoint`",
        "- Final git status: `pending external repository checkpoint`",
        "- Recommended next run: `Run 42 — build automated evidence-to-authoring promotion lane with machine dispositions only; produce authoring packets but do not publish docs/book yet.`",
        f"- Blockers: `{report.get('blockers')}`",
        "",
    ]
    return "\n".join(lines)


def write_reports(report: dict[str, Any], output_json: str, output_md: str, telegram_status: str) -> None:
    out_json = resolve(output_json)
    out_md = resolve(output_md)
    telegram = resolve(telegram_status)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    telegram.parent.mkdir(parents=True, exist_ok=True)
    report["reports_created"] = [str(out_json), str(out_md), str(resolve(report.get("mutation_guard_report_path", ""))), str(telegram)]
    status = format_status(report)
    report["telegram_status_path"] = str(telegram)
    report["telegram_delivery_attempted"] = False
    report["telegram_delivery_ok"] = False
    report["telegram_fallback_written"] = True
    report["telegram_delivery_note"] = "No configured in-repo Telegram sender was invoked by Run 41 runner shell; fallback status file written."
    out_json.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    md = [
        "# Run 41 closed-loop daily runner report",
        "",
        "## What the daily runner did",
        "",
        "The runner probed daily-worker no-write capabilities, recorded a JSONL event ledger attempt, selected the preflight-only verification profile, took mutation-guard snapshots, executed only the daily worker preflight/no-op command, compared the guard result, and wrote reports/status files. It did not enable production publication.",
        "",
        "## Capability probe result",
        "",
        f"- ok: `{report.get('daily_worker_capability_probe', {}).get('ok')}`",
        f"- missing_capabilities: `{report.get('missing_capabilities')}`",
        "",
        "## Preflight-only command executed",
        "",
        f"`{' '.join(shlex.quote(x) for x in report.get('daily_worker_command', []))}`",
        "",
        "## Event ledger events written",
        "",
        f"- Ledger: `{report.get('event_ledger_path')}`",
        f"- Event count delta: `{report.get('event_count_delta')}`",
        "",
        "## Mutation guard result",
        "",
        f"- ok: `{report.get('mutation_guard_ok')}`",
        f"- profile: `{report.get('mutation_guard_profile_used')}`",
        f"- failed_checks: `{report.get('mutation_guard_failed_checks')}`",
        "",
        "## DB/protected/docs/source-registry/raw/schema deltas",
        "",
        "```json",
        json.dumps({k: report.get(k) for k in ["db_delta", "status_hash_delta", "protected_path_delta", "docs_book_changed", "docs_entities_changed", "docs_claims_changed", "source_registry_changed", "raw_changed", "schema_changed"]}, indent=2, sort_keys=True),
        "```",
        "",
        "## Why publication is still disabled in Run 41",
        "",
        "Run 41 is a runner-shell/preflight-only run. Production publication, docs/book updates, raw collection, metadata writes, authoring, approval, and chapter updates all remain false by construction.",
        "",
        "## What must happen in Run 42",
        "",
        "Build the automated evidence-to-authoring promotion lane with machine dispositions only, GPT-5.5 evidence evaluation if needed, authoring packets only, and no docs/book publication.",
        "",
        "## Telegram status and repository checkpoint",
        "",
        f"- Telegram status written: `{report.get('telegram_fallback_written')}` at `{report.get('telegram_status_path')}`",
        "- Final repo commit/push: handled by external Run 41 repository verification, not by the internal runner.",
        "",
    ]
    out_md.write_text("\n".join(md), encoding="utf-8")
    telegram.write_text(status, encoding="utf-8")
    out_json.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Closed-loop daily runner shell")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--mode", required=True)
    parser.add_argument("--disposition", required=True)
    parser.add_argument("--daily-worker", required=True)
    parser.add_argument("--state-machine-config", required=True)
    parser.add_argument("--transition-engine", required=True)
    parser.add_argument("--mutation-guard", required=True)
    parser.add_argument("--event-ledger", required=True)
    parser.add_argument("--before-snapshot", required=True)
    parser.add_argument("--after-snapshot", required=True)
    parser.add_argument("--mutation-guard-report", required=True)
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--output-md", required=True)
    parser.add_argument("--telegram-status", required=True)
    parser.add_argument("--execute-preflight-only", action="store_true")
    args = parser.parse_args(argv)

    command = build_daily_worker_command(args.daily_worker, args.run_id)
    contract_hash = command_contract_hash(command, args.mode, args.disposition)
    idempotency_key = event_ledger.compute_idempotency_key(args.run_id, args.mode, args.disposition, "attempt_completed", contract_hash)
    attempt_id = f"run41-{idempotency_key[:12]}"
    selected_profile = select_verification_profile(args.mode, args.disposition)
    ledger_before = len(event_ledger.load_events(args.event_ledger))
    duplicate = event_ledger.detect_duplicate_event(
        event_ledger.load_events(args.event_ledger),
        run_id=args.run_id,
        attempt_id=attempt_id,
        idempotency_key=idempotency_key,
        completed_only=True,
    )

    report: dict[str, Any] = {
        "run_id": args.run_id,
        "attempt_id": attempt_id,
        "generated_at": utc_now(),
        "mode": args.mode,
        "disposition": args.disposition,
        "selected_verification_profile": selected_profile,
        "execution_allowed": False,
        "execution_performed": False,
        "execution_type": "preflight_only",
        "daily_worker_command": command,
        "daily_worker_capability_probe": {"ok": False},
        "missing_capabilities": REQUIRED_CAPABILITIES[:],
        "supported_capabilities": [],
        "event_ledger_path": str(resolve(args.event_ledger)),
        "event_count_delta": 0,
        "idempotency_key": idempotency_key,
        "duplicate_detected": duplicate is not None,
        "duplicate_suppressed": False,
        "mutation_guard_executed": False,
        "mutation_guard_ok": False,
        "mutation_guard_profile_used": selected_profile,
        "mutation_guard_failed_checks": [],
        "mutation_guard_unexpected_changed_paths": [],
        "mutation_guard_before_snapshot": str(resolve(args.before_snapshot)),
        "mutation_guard_after_snapshot": str(resolve(args.after_snapshot)),
        "mutation_guard_report_path": str(resolve(args.mutation_guard_report)),
        "db_delta": {},
        "status_hash_delta": {},
        "protected_path_delta": {},
        "docs_book_changed": False,
        "docs_entities_changed": False,
        "docs_claims_changed": False,
        "source_registry_changed": False,
        "raw_changed": False,
        "schema_changed": False,
        "daily_worker_changed_during_execution": False,
        "production_publish_enabled": False,
        "docs_book_update_enabled": False,
        "raw_collection_enabled": False,
        "metadata_write_enabled": False,
        "authoring_enabled": False,
        "publication_approved": False,
        "chapter_update_allowed": False,
        "human_in_loop_dependency_added": False,
        "runner_commit_allowed": False,
        "runner_push_allowed": False,
        "runner_commit_block_reasons": ["run41_internal_runner_commit_disabled"],
        "runner_push_block_reasons": ["run41_internal_runner_push_disabled"],
        "telegram_status_path": str(resolve(args.telegram_status)),
        "telegram_delivery_attempted": False,
        "telegram_delivery_ok": False,
        "telegram_fallback_written": False,
        "final_disposition": "attempt_failed",
        "current_db_counts": current_db_counts(),
        "blockers": [],
        "worker_preflight_result": None,
    }

    common_event = dict(
        ledger_path=args.event_ledger,
        run_id=args.run_id,
        attempt_id=attempt_id,
        mode=args.mode,
        disposition=args.disposition,
        command_contract_hash=contract_hash,
    )

    try:
        if duplicate:
            report["duplicate_suppressed"] = True
            report["blockers"].append("duplicate_completed_attempt_detected")
            event_ledger.append_event(
                args.event_ledger,
                run_id=args.run_id,
                attempt_id=attempt_id,
                event_type="duplicate_suppressed",
                mode=args.mode,
                disposition=args.disposition,
                status="failed",
                payload={"duplicate_event_id": duplicate.get("event_id")},
                idempotency_key=idempotency_key,
            )
            return_code = 2
        else:
            event_ledger.record_attempt_started(**common_event, payload={"selected_verification_profile": selected_profile})
            probe = probe_daily_worker(args.daily_worker)
            caps = probe.get("capabilities", {})
            missing = missing_capabilities(caps)
            report["daily_worker_capability_probe"] = {"ok": probe["ok"], "error": probe.get("error"), "capabilities": caps, "returncode": probe["subprocess"]["returncode"]}
            report["missing_capabilities"] = missing
            report["supported_capabilities"] = sorted(k for k, v in caps.items() if v is True)
            event_ledger.record_capability_probe(**common_event, ok=probe["ok"] and not missing, payload={"missing_capabilities": missing})

            execution_allowed = bool(
                args.execute_preflight_only
                and args.mode == "preflight_only"
                and args.disposition == "safe_reports_only"
                and selected_profile == "preflight_only_daily_runner"
                and probe["ok"]
                and not missing
            )
            report["execution_allowed"] = execution_allowed
            if not execution_allowed:
                if not args.execute_preflight_only:
                    report["blockers"].append("execute_preflight_only_flag_absent")
                if args.mode != "preflight_only":
                    report["blockers"].append("mode_not_preflight_only")
                if args.disposition != "safe_reports_only":
                    report["blockers"].append("disposition_not_safe_reports_only")
                if selected_profile != "preflight_only_daily_runner":
                    report["blockers"].append("unsupported_verification_profile")
                if not probe["ok"]:
                    report["blockers"].append("capability_probe_failed")
                if missing:
                    report["blockers"].append("missing_required_capabilities")
                event_ledger.record_attempt_failed(**common_event, payload={"blockers": report["blockers"]})
                return_code = 2
            else:
                before = run_guard_snapshot(args.mutation_guard, args.before_snapshot)
                if before["returncode"] != 0:
                    raise RuntimeError(f"mutation guard before snapshot failed: {before['stderr_tail']}")
                event_ledger.record_mutation_guard_before(**common_event, payload={"snapshot": args.before_snapshot})
                event_ledger.record_worker_preflight_execution(**common_event, status="started", payload={"command": command})
                worker_result = run_subprocess(command)
                report["worker_preflight_result"] = {k: worker_result[k] for k in ["returncode", "stdout_tail", "stderr_tail"]}
                report["execution_performed"] = True
                if worker_result["returncode"] == 0:
                    event_ledger.record_worker_preflight_execution(**common_event, status="completed", payload=report["worker_preflight_result"])
                else:
                    event_ledger.record_worker_preflight_execution(**common_event, status="failed", payload=report["worker_preflight_result"])
                after = run_guard_snapshot(args.mutation_guard, args.after_snapshot)
                if after["returncode"] != 0:
                    raise RuntimeError(f"mutation guard after snapshot failed: {after['stderr_tail']}")
                event_ledger.record_mutation_guard_after(**common_event, payload={"snapshot": args.after_snapshot})
                compare = run_guard_compare(args.mutation_guard, args.before_snapshot, args.after_snapshot, selected_profile, args.mutation_guard_report)
                report["mutation_guard_executed"] = True
                guard_report = load_json_file(args.mutation_guard_report, {})
                report.update(summarize_guard_report(guard_report))
                event_ledger.record_mutation_guard_result(**common_event, ok=bool(report["mutation_guard_ok"]), payload={"returncode": compare["returncode"], "failed_checks": report["mutation_guard_failed_checks"]})
                if worker_result["returncode"] == 0 and report["mutation_guard_ok"]:
                    report["final_disposition"] = "attempt_completed"
                    event_ledger.record_attempt_completed(**common_event, payload={"mutation_guard_ok": True})
                    return_code = 0
                else:
                    if worker_result["returncode"] != 0:
                        report["blockers"].append("worker_preflight_failed")
                    if not report["mutation_guard_ok"]:
                        report["blockers"].append("mutation_guard_failed")
                    event_ledger.record_attempt_failed(**common_event, payload={"blockers": report["blockers"]})
                    return_code = 2
    except Exception as exc:
        report["blockers"].append(f"runner_exception:{type(exc).__name__}:{exc}")
        try:
            event_ledger.record_attempt_failed(**common_event, payload={"blockers": report["blockers"]})
        except Exception:
            pass
        return_code = 2

    ledger_after = len(event_ledger.load_events(args.event_ledger))
    report["event_count_delta"] = ledger_after - ledger_before
    report["current_db_counts"] = current_db_counts()
    write_reports(report, args.output_json, args.output_md, args.telegram_status)
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
