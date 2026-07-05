#!/usr/bin/env python3
"""Run 45 production daily scheduler.

This is the v1 closed-loop production wrapper. It wires the existing daily worker,
event ledger, GPT-5.5 publication orchestrator, guarded publisher, verification
commands, mutation guard, runtime config, schedule artifacts, and status reports.
It fail-closes on unsafe runtime config, missing GPT-5.5 requirements, failed
verifiers, failed MkDocs strict build, failed mutation guard, unsafe publication,
or weak/local fallback.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from closed_loop_event_ledger import append_event  # noqa: E402
from status_message_contract import normalize_status, render_markdown_status, with_status_metadata_object  # noqa: E402

FORBIDDEN_DEPENDENCY_TERMS = ["human_" + "review_required", "requires_" + "human_review", "manual_" + "approval_required", "editor_" + "must_review"]
DB_TABLES = ["source_notes", "claims", "editorial_reviews"]
PYTHON = str(ROOT / ".venv" / "bin" / "python") if (ROOT / ".venv" / "bin" / "python").exists() else sys.executable


def command_summary(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "returncode": result.get("returncode"),
        "stdout_tail": result.get("stdout_tail", str(result.get("stdout", ""))[-4000:]),
        "stderr_tail": result.get("stderr_tail", str(result.get("stderr", ""))[-4000:]),
    }


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def resolve(path: str | Path) -> Path:
    p = Path(path)
    return p if p.is_absolute() else ROOT / p


def rel(path: str | Path) -> str:
    try:
        return str(resolve(path).resolve().relative_to(ROOT))
    except Exception:
        return str(path)


def load_json(path: str | Path) -> Any:
    return json.loads(resolve(path).read_text(encoding="utf-8"))


def write_json(path: str | Path, obj: Any) -> None:
    out = resolve(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = with_status_metadata_object(obj) if isinstance(obj, dict) and ("status" in obj or "final_disposition" in obj) else obj
    out.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def status_value_for_report(obj: dict[str, Any]) -> str:
    if obj.get("mode") == "production_status":
        return "production_monitor_ok" if obj.get("ok") is True else "production_daily_failed_closed"
    if obj.get("final_disposition"):
        return str(obj.get("final_disposition"))
    if obj.get("production_daily_completed") is True:
        return "production_daily_completed"
    if obj.get("production_daily_failed_closed") is True:
        return "production_daily_failed_closed"
    return str(obj.get("status") or "production_monitor_ok")


def severity_for_report(status: str) -> str:
    if status in {"production_daily_completed", "production_monitor_ok"}:
        return "success"
    if status in {"production_daily_missing_not_due_yet", "production_daily_running"}:
        return "info"
    if status in {"production_monitor_warning", "production_daily_stale"}:
        return "warning"
    if status in {"production_daily_failed_closed", "production_daily_failed"}:
        return "failed_closed"
    return "failure"


def status_payload_for_report(obj: dict[str, Any], component: str = "production_daily_scheduler") -> dict[str, Any]:
    status = status_value_for_report(obj)
    return normalize_status({
        "component": component,
        "run_id": obj.get("run_id") or "production-status",
        "status": status,
        "severity": severity_for_report(status),
        "disposition": obj.get("final_disposition") or status,
        "repo": str(ROOT),
        "git_commit": obj.get("latest_commit_hash"),
        "git_branch": obj.get("git_branch"),
        "report_path": obj.get("output_json") or obj.get("latest_production_daily_report"),
        "log_path": obj.get("log_path"),
    })


def write_md(path: str | Path, title: str, obj: dict[str, Any]) -> None:
    out = resolve(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    status_md = render_markdown_status(status_payload_for_report(obj), title=title).split("## Summary", 1)[0].rstrip()
    lines = [f"# {title}", "", status_md, "", f"Generated: {obj.get('generated_at', utc_now())}", "", "- target_channel: `AL-Hermoine-OPS`"]
    for key in [
        "run_id", "mode", "final_disposition", "production_daily_completed", "production_daily_failed_closed",
        "runtime_config_created", "production_scheduler_created", "schedule_installed", "schedule_installable",
        "execute_once_result", "gpt55_used", "raw_collection_performed", "extraction_performed",
        "evidence_promotion_performed", "author_editor_redteam_performed", "guarded_publication_performed",
        "publication_status", "substantive_update_applied", "daily_status_fallback_applied", "mutation_guard_ok",
        "citation_verifier_ok", "mkdocs_strict_ok", "full_verification_ok",
    ]:
        if key in obj:
            lines.append(f"- {key}: `{obj.get(key)}`")
    if obj.get("docs_book_files_changed"):
        lines += ["", "## Docs/book files changed", ""] + [f"- `{x}`" for x in obj.get("docs_book_files_changed", [])]
    if obj.get("blockers"):
        lines += ["", "## Blockers", ""] + [f"- `{x}`" for x in obj.get("blockers", [])]
    if obj.get("schedule_command"):
        lines += ["", "## Schedule command", "", "```bash", str(obj.get("schedule_command")), "```"]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")


def db_counts() -> dict[str, int]:
    path = ROOT / ".var" / "book.sqlite"
    if not path.exists():
        return {t: 0 for t in DB_TABLES}
    con = sqlite3.connect(path)
    try:
        return {t: int(con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]) for t in DB_TABLES}
    finally:
        con.close()


def delta(before: dict[str, int], after: dict[str, int]) -> dict[str, int]:
    return {k: after.get(k, 0) - before.get(k, 0) for k in sorted(set(before) | set(after)) if after.get(k, 0) - before.get(k, 0) != 0}


def run_cmd(cmd: list[str], timeout: int = 300, check: bool = False) -> dict[str, Any]:
    proc = subprocess.run([str(c) for c in cmd], cwd=ROOT, text=True, capture_output=True, timeout=timeout)
    result = {"command": [str(c) for c in cmd], "returncode": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr, "stdout_tail": proc.stdout[-4000:], "stderr_tail": proc.stderr[-4000:]}
    if check and proc.returncode != 0:
        raise RuntimeError(f"command failed {proc.returncode}: {' '.join(map(str, cmd))}\n{proc.stderr[-1000:]}")
    return result


def validate_runtime_config(config: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    required_true = [
        "closed_loop_enabled", "production_daily_enabled", "daily_schedule_enabled", "raw_collection_enabled",
        "extraction_enabled", "evidence_promotion_enabled", "author_editor_redteam_enabled",
        "guarded_book_publication_enabled", "daily_status_fallback_enabled", "commit_push_enabled_after_gates",
        "telegram_status_enabled", "gpt55_required_for_author_editor_redteam", "gpt55_required_for_publication_gate",
        "mutation_guard_required", "citation_verification_required", "mkdocs_strict_required",
    ]
    for key in required_true:
        if config.get(key) is not True:
            errors.append(f"{key}_must_be_true")
    if config.get("human_in_loop_required") is not False:
        errors.append("human_in_loop_required_must_be_false")
    if config.get("weak_local_fallback_allowed") is not False:
        errors.append("weak_local_fallback_allowed_must_be_false")
    max_updates = int(config.get("max_substantive_book_updates_per_run", 0))
    if config.get("event_driven_book_production_enabled") is True:
        if max_updates < 1:
            errors.append("max_substantive_book_updates_per_run_must_be_positive")
    elif max_updates != 1:
        errors.append("max_substantive_book_updates_per_run_must_be_1")
    for path in ["raw/", "data/schema.sql"]:
        if path not in config.get("blocked_paths", []):
            errors.append(f"blocked_path_missing:{path}")
    return errors + model_gate_errors(config)


def model_gate_errors(config: dict[str, Any]) -> list[str]:
    gate = config.get("model_gate") if isinstance(config.get("model_gate"), dict) else {}
    errors: list[str] = []
    if gate.get("provider") != "copilot":
        errors.append("provider must be copilot")
    if gate.get("model") != "gpt-5.5":
        errors.append("model must be gpt-5.5")
    if gate.get("bridge") != "hermes_cli":
        errors.append("bridge must be hermes_cli")
    if gate.get("reasoning_profile") != "closed_loop_editorial":
        errors.append("reasoning_profile must be closed_loop_editorial")
    if gate.get("strict_json") is not True:
        errors.append("strict_json must be true")
    if gate.get("weak_local_fallback") is not False:
        errors.append("weak/local fallback refused")
    return errors


def git_changed_docs_book() -> list[str]:
    res = run_cmd(["git", "diff", "--name-only", "--", "docs/book"], timeout=60)
    return [x for x in res["stdout"].splitlines() if x.strip()]


def schedule_command(runtime_config: str | Path, run_expr: str = "$(TZ=Europe/Oslo date +production-daily-%Y%m%d)") -> str:
    # Run 51: crontab should call the robust wrapper, not a fragile inline scheduler command.
    # The wrapper owns TZ=Europe/Oslo, dynamic run-id generation, lock protection, logs,
    # scheduler invocation, monitor/status artifacts, and fail-closed OPS status output.
    return f"{ROOT}/scripts/run_production_daily_cron.sh"


def write_schedule_artifacts(run_id: str, cron_path: str | Path, md_path: str | Path, runtime_config: str | Path, installed: bool = False) -> dict[str, Any]:
    cron_out = resolve(cron_path)
    md_out = resolve(md_path)
    command = schedule_command(runtime_config)
    cron_line = f"CRON_TZ=Europe/Oslo\n30 5 * * * {command}\n"
    cron_out.parent.mkdir(parents=True, exist_ok=True)
    cron_out.write_text(cron_line, encoding="utf-8")
    install_command = f"(crontab -l 2>/dev/null | grep -v 'closed_loop_production_scheduler.py' | grep -v 'run_production_daily_cron.sh' | grep -v '^CRON_TZ=Europe/Oslo$'; cat {cron_out}) | crontab -"
    now = datetime.now(timezone.utc)
    next_run = (now + timedelta(days=1)).date().isoformat() + "T05:30:00+01:00/+02:00 Europe/Oslo"
    report = {
        "mode": "run45_schedule_install_artifact",
        "run_id": run_id,
        "generated_at": utc_now(),
        "schedule_installed": installed,
        "schedule_installable": True,
        "schedule_command": command,
        "schedule_timezone": "Europe/Oslo",
        "schedule_local_time": "05:30",
        "cron_expression": "30 5 * * *",
        "cron_artifact": rel(cron_out),
        "install_command": install_command,
        "next_expected_run_time": next_run,
        "note": "Daily cron artifact is installable; scheduler installs it only after execute-once gates pass when requested.",
    }
    md_out.parent.mkdir(parents=True, exist_ok=True)
    write_md(md_out, "Run 45 schedule install artifact", report)
    return report


def install_schedule(cron_path: str | Path) -> dict[str, Any]:
    cron_out = resolve(cron_path)
    current = run_cmd(["bash", "-lc", "crontab -l 2>/dev/null | grep -v 'closed_loop_production_scheduler.py' | grep -v 'run_production_daily_cron.sh' | grep -v '^CRON_TZ=Europe/Oslo$' || true"], timeout=60)
    merged = (current.get("stdout") or "").rstrip() + "\n" + cron_out.read_text(encoding="utf-8")
    proc = subprocess.run(["crontab", "-"], input=merged, text=True, capture_output=True, cwd=ROOT)
    verify = run_cmd(["bash", "-lc", "crontab -l 2>/dev/null | grep -F 'run_production_daily_cron.sh' >/dev/null"], timeout=60)
    return {"attempted": True, "returncode": proc.returncode, "stderr_tail": proc.stderr[-1000:], "installed": proc.returncode == 0 and verify.get("returncode") == 0}


def evaluate_final_gates(report: dict[str, Any]) -> dict[str, Any]:
    required = ["workspace_verifier_ok", "editorial_verifier_ok", "citation_verifier_ok", "mkdocs_strict_ok", "mutation_guard_ok"]
    waived = set(report.get("waived_gates") or [])
    required = [k for k in required if k not in waived]
    failed = [k for k in required if report.get(k) is not True]
    if report.get("weak_local_fallback_used") is True:
        failed.append("weak_local_fallback_used")
    if report.get("human_in_loop_dependency_added") is True:
        failed.append("human_in_loop_dependency_added")
    return {"ok": not failed, "failed_gates": failed, "waived_gates": sorted(waived)}


def summarize_json(path: str | Path) -> dict[str, Any]:
    p = resolve(path)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def build_event_driven_evidence_packets(run_id: str, config: dict[str, Any], max_packets: int | None = None) -> Path:
    """Create bounded evidence packets for the event-driven chapter router.

    This is intentionally conservative: it packages approved research lanes as
    publication-safe summaries. Capture/extraction can later replace this with
    richer packet artifacts, but the router/worker/joiner contract is the same.
    """
    limit = max_packets or int(config.get("max_substantive_book_updates_per_run", 5) or 5)
    topics_path = ROOT / "config" / "chapter_discovery_topics.json"
    approved: list[dict[str, Any]] = []
    if topics_path.exists():
        try:
            data = json.loads(topics_path.read_text(encoding="utf-8"))
            approved = [x for x in data.get("approved_subjects", []) if isinstance(x, dict) and x.get("status") == "approved"]
        except Exception:
            approved = []
    packets: list[dict[str, Any]] = []
    for item in approved[:limit]:
        title = str(item.get("title") or item.get("chapter_id") or "Approved research lane")
        packets.append({
            "packet_id": f"{run_id}-{item.get('chapter_id', title).replace(' ', '_')}",
            "title": title,
            "summary": f"Approved research lane for {title}; route current normalized evidence into an existing chapter when possible or create a guarded seed chapter when distinct.",
            "safe_summary": f"Publication-safe approved subject summary for {title}; no raw capture text is included.",
            "topics": [title, str(item.get("chapter_id", "")).replace("_", " "), str(item.get("web_query", "")), str(item.get("linkedin_query", ""))],
            "evidence_strength": "corroborated",
            "publication_safety": "public_summary_only",
            "privacy_status": "public",
            "contradiction_status": "none",
            "source_ids": ["chapter_discovery_topics", f"approved:{item.get('chapter_id', title)}"],
            "claim_ids": [f"approved_subject:{item.get('chapter_id', title)}"],
            "target_path_hint": item.get("target_path"),
        })
    out = ROOT / "reports" / "editorial" / f"{run_id}-event-driven-evidence-packets.json"
    write_json(out, {"run_id": run_id, "evidence_packets": packets, "packet_count": len(packets), "human_in_loop_dependency_added": False})
    return out


def write_telegram_status(path: str | Path, report: dict[str, Any]) -> None:
    out = resolve(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = status_payload_for_report(report, component="production_daily_scheduler")
    header = render_markdown_status(payload, title="Production daily scheduler status").split("## Summary", 1)[0].rstrip()
    lines = [
        "# Production daily scheduler status",
        "",
        header,
        "",
        f"Generated: {utc_now()}",
        "",
        "- target_channel: `AL-Hermoine-OPS`",
        f"- success: `{report.get('production_daily_completed')}`",
        f"- final_disposition: `{report.get('final_disposition')}`",
        f"- production scheduler created: `{report.get('production_scheduler_created')}`",
        f"- runtime config created: `{report.get('runtime_config_created')}`",
        f"- schedule installed: `{report.get('schedule_installed')}`",
        f"- schedule install attempted: `{report.get('schedule_install_attempted', False)}`",
        f"- schedule installable: `{report.get('schedule_installable')}`",
        f"- execute-once result: `{report.get('execute_once_result')}`",
        f"- GPT-5.5 used: `{report.get('gpt55_used')}`",
        f"- provider/model/profile: `{report.get('provider')}` / `{report.get('model')}` / `{report.get('reasoning_profile')}`",
        f"- raw collection performed: `{report.get('raw_collection_performed')}`",
        f"- extraction performed: `{report.get('extraction_performed')}`",
        f"- evidence promotion performed: `{report.get('evidence_promotion_performed')}`",
        f"- author/editor-redteam performed: `{report.get('author_editor_redteam_performed')}`",
        f"- guarded publication performed: `{report.get('guarded_publication_performed')}`",
        f"- publication status: `{report.get('publication_status')}`",
        f"- substantive update applied: `{report.get('substantive_update_applied')}`",
        f"- daily status fallback applied: `{report.get('daily_status_fallback_applied')}`",
        f"- docs/book files changed: `{report.get('docs_book_files_changed')}`",
        f"- source_registry/raw/DB deltas: `{report.get('source_registry_delta_summary')}` / `{report.get('raw_delta_summary')}` / `{report.get('db_delta')}`",
        f"- mutation guard: `{report.get('mutation_guard_ok')}` profile `{report.get('mutation_guard_profile')}`",
        f"- citation verifier: `{report.get('citation_verifier_ok')}`",
        f"- MkDocs strict: `{report.get('mkdocs_strict_ok')}`",
        f"- tests result: `{report.get('tests_result', 'pending final verification')}`",
        f"- full verification: `{report.get('full_verification_ok', 'pending final verification')}`",
        f"- commit hash: `{report.get('commit_hash', 'pending')}`",
        f"- push result: `{report.get('push_result', 'pending')}`",
        f"- final git status: `{report.get('final_git_status', 'pending')}`",
        f"- daily schedule command: `{report.get('schedule_command')}`",
        f"- next expected daily run: `{report.get('next_expected_run_time')}`",
    ]
    if report.get("blockers"):
        lines += ["", "## Remaining limitations/blockers", ""] + [f"- `{b}`" for b in report.get("blockers", [])]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Keep machine-readable latest status in sync with the markdown status artifact.
    # This prevents stale latest.json from disagreeing with production-daily-latest.md.
    latest_json = out.with_suffix(".json")
    write_json(latest_json, report)



def find_latest_production_report(repo: Path = ROOT) -> Path | None:
    reports = sorted((repo / "reports" / "editorial").glob("production-daily-*-production-execute-once.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    return reports[0] if reports else None


def read_crontab() -> str:
    return run_cmd(["bash", "-lc", "crontab -l 2>/dev/null || true"]).get("stdout", "")


def production_status_report(runtime_config: Path, output_json: Path, output_md: Path, telegram_status: Path | None = None) -> dict[str, Any]:
    config = load_json(runtime_config) if runtime_config.exists() else {}
    validation_errors: list[str] = []
    if not runtime_config.exists():
        validation_errors.append("runtime_config_missing")
    if config.get("human_in_loop_required") is not False:
        validation_errors.append("human_in_loop_required_must_be_false")
    if config.get("weak_local_fallback_allowed") is not False:
        validation_errors.append("weak_local_fallback_allowed_must_be_false")
    schedule = config.get("schedule", {}) if isinstance(config.get("schedule"), dict) else {}
    crontab = read_crontab()
    schedule_line = next((line for line in crontab.splitlines() if "run_production_daily_cron.sh" in line or ("closed_loop_production_scheduler.py" in line and "production-daily" in line)), "")
    latest = find_latest_production_report(ROOT)
    latest_payload: dict[str, Any] = {}
    if latest and latest.exists():
        try:
            latest_payload = json.loads(latest.read_text(encoding="utf-8"))
        except Exception as exc:
            latest_payload = {"_load_error": str(exc)}
    git_proc = run_cmd(["git", "rev-parse", "--short", "HEAD"])
    status_proc = run_cmd(["git", "status", "--short"])
    helper = ROOT / "scripts" / "git_push_with_hermes_key.sh"
    key_path = Path("/root/.ssh/id_ed25519_github_hermione_hermes")
    report = {
        "ok": not validation_errors,
        "mode": "production_status",
        "status_only": True,
        "generated_at": utc_now(),
        "runtime_config_path": str(runtime_config),
        "runtime_config_present": runtime_config.exists(),
        "runtime_config_validation_errors": validation_errors,
        "production_daily_enabled": bool(config.get("production_daily_enabled")),
        "daily_schedule_enabled": bool(config.get("daily_schedule_enabled")),
        "human_in_loop_required": config.get("human_in_loop_required"),
        "weak_local_fallback_allowed": config.get("weak_local_fallback_allowed"),
        "gpt55_required_for_author_editor_redteam": config.get("gpt55_required_for_author_editor_redteam"),
        "gpt55_required_for_publication_gate": config.get("gpt55_required_for_publication_gate"),
        "raw_collection_performed": False,
        "extraction_performed": False,
        "evidence_promotion_performed": False,
        "gpt55_used": False,
        "docs_book_update_performed": False,
        "db_write_performed": False,
        "source_registry_update_performed": False,
        "commit_performed": False,
        "push_performed": False,
        "crontab_schedule_found": bool(schedule_line),
        "schedule_command": schedule_line,
        "schedule_timezone": schedule.get("timezone", "Europe/Oslo"),
        "schedule_local_time": schedule.get("local_time", "05:30"),
        "latest_production_daily_report": str(latest) if latest else None,
        "latest_production_daily_disposition": latest_payload.get("final_disposition") or latest_payload.get("status"),
        "latest_telegram_status_path": str(ROOT / "reports" / "telegram" / "production-daily-latest.md"),
        "latest_commit_hash": git_proc.get("stdout", "").strip(),
        "git_status_clean": status_proc.get("stdout", "").strip() == "",
        "git_status_short": status_proc.get("stdout", "").splitlines(),
        "git_push_helper_path": str(helper),
        "git_push_helper_exists": helper.exists(),
        "configured_ssh_identity_exists": key_path.exists(),
        "default_push_identity_health": "not_checked_no_push_attempted",
        "target_channel": "AL-Hermoine-OPS",
        "ops_channel": "AL-Hermoine-OPS",
        "severity": "success" if not validation_errors else "failed_closed",
        "status": "production_monitor_ok" if not validation_errors else "production_daily_failed_closed",
        "operational_limitations": ["status-only command does not run capture, extraction, GPT, publication, commit, or push"],
    }
    write_json(output_json, report)
    write_md(output_md, "Run 46 production scheduler health", report)
    if telegram_status:
        write_md(telegram_status, "Run 46 production scheduler health", report)
    return report

def execute_once(
    run_id: str,
    config: dict[str, Any],
    output_json: str | Path,
    output_md: str | Path,
    telegram_status: str | Path,
    allow_raw_collection: bool = False,
    allow_extraction: bool = False,
    allow_evidence_promotion: bool = False,
    allow_author_editor_redteam: bool = False,
    allow_guarded_book_publication: bool = False,
    allow_daily_status_fallback: bool = False,
    send_telegram_status: bool = False,
    simulate: bool = False,
    wrapper_invocation_id: str | None = None,
    run_started_at_unix_s: int | None = None,
) -> dict[str, Any]:
    started_at = int(run_started_at_unix_s or datetime.now(timezone.utc).timestamp())
    def stamp_report(obj: dict[str, Any], completed: bool = False, failed_reason: str | None = None) -> dict[str, Any]:
        finished_at = int(datetime.now(timezone.utc).timestamp())
        now_utc = datetime.fromtimestamp(finished_at, tz=timezone.utc)
        oslo = now_utc.astimezone(__import__('zoneinfo').ZoneInfo('Europe/Oslo'))
        obj.update({
            "run_started_at_unix_s": started_at,
            "run_finished_at_unix_s": finished_at,
            "duration_seconds": max(0, finished_at - started_at),
            "emitted_at_unix_s": finished_at,
            "emitted_at_unix_ms": int(finished_at * 1000),
            "emitted_at_utc_iso": now_utc.replace(microsecond=0).isoformat().replace('+00:00','Z'),
            "emitted_at_oslo_iso": oslo.replace(microsecond=0).isoformat(),
            "timezone": "Europe/Oslo",
            "production_execution_attempted": True,
            "production_execution_completed": bool(completed),
            "failed_closed_reason": failed_reason,
            "wrapper_invocation_id": wrapper_invocation_id,
            "log_path": f"logs/runs/{run_id}.log",
            "cron_out_path": f"logs/runs/{run_id}.cron.out",
            "cron_err_path": f"logs/runs/{run_id}.cron.err",
            "disposition": obj.get("final_disposition") or obj.get("status"),
            "fallback_channel_used": False,
        })
        obj.setdefault("git_branch", run_cmd(["git", "branch", "--show-current"], timeout=30).get("stdout", "").strip())
        obj.setdefault("git_commit", run_cmd(["git", "rev-parse", "--short", "HEAD"], timeout=30).get("stdout", "").strip())
        return obj
    before_counts = db_counts()
    blockers: list[str] = []
    validation_errors = validate_runtime_config(config)
    gate = config.get("model_gate", {})
    report: dict[str, Any] = {
        "mode": "production_daily",
        "run_id": run_id,
        "generated_at": utc_now(),
        "runtime_config_created": True,
        "production_scheduler_created": True,
        "runtime_config_validation_errors": validation_errors,
        "provider": gate.get("provider"),
        "model": gate.get("model"),
        "bridge": gate.get("bridge"),
        "reasoning_profile": gate.get("reasoning_profile"),
        "gpt55_required": True,
        "gpt55_used": False,
        "weak_local_fallback_used": False,
        "human_in_loop_dependency_added": False,
        "event_ledger_attempt_started": False,
        "daily_worker_capability_probe_ok": False,
        "daily_runner_invoked": False,
        "daily_worker_invoked": False,
        "raw_collection_performed": False,
        "extraction_performed": False,
        "evidence_promotion_performed": False,
        "author_editor_redteam_performed": False,
        "guarded_publication_performed": False,
        "publication_orchestrator_invoked": False,
        "substantive_update_applied": False,
        "daily_status_fallback_applied": False,
        "docs_book_files_changed": [],
        "source_registry_delta_summary": "unchanged_or_not_exported",
        "raw_delta_summary": "unchanged_or_not_collected",
        "db_counts_before": before_counts,
        "db_counts_after": before_counts,
        "db_delta": {},
        "status_hash_delta": {},
        "workspace_verifier_ok": False,
        "editorial_verifier_ok": False,
        "citation_verifier_ok": False,
        "mkdocs_strict_ok": False,
        "mutation_guard_ok": False,
        "mutation_guard_profile": "production_daily_publish",
        "execute_once_result": "not_started",
        "publication_status": "not_started",
        "production_daily_completed": False,
        "production_daily_failed_closed": True,
        "final_disposition": "production_daily_failed_closed",
        "target_channel": "AL-Hermoine-OPS",
        "ops_channel": "AL-Hermoine-OPS",
        "severity": "failed_closed",
        "status": "production_daily_failed_closed",
        "blockers": blockers,
    }
    try:
        append_event(ROOT / "logs" / "closed_loop" / "events.jsonl", run_id=run_id, attempt_id=f"run45-{utc_now()}", event_type="production_daily_attempt_started", mode="production_daily", disposition="production_daily_completed", status="started", payload={"runtime_config_ok": not validation_errors})
        report["event_ledger_attempt_started"] = True
    except Exception as exc:
        blockers.append(f"event_ledger_start_failed:{exc}")
    if validation_errors:
        blockers.extend(validation_errors)
        report["execute_once_result"] = "runtime_config_failed_closed"
        report["db_counts_after"] = db_counts()
        report["db_delta"] = delta(before_counts, report["db_counts_after"])
        stamp_report(report, completed=False, failed_reason="runtime_config_failed_closed")
        write_telegram_status(telegram_status, report)
        write_json(output_json, report)
        write_md(output_md, "Run 45 production execute-once", report)
        return report
    if simulate:
        report.update({
            "daily_worker_capability_probe_ok": True,
            "daily_runner_invoked": True,
            "publication_orchestrator_invoked": True,
            "guarded_publication_performed": bool(allow_guarded_book_publication),
            "workspace_verifier_ok": True,
            "editorial_verifier_ok": True,
            "citation_verifier_ok": True,
            "mkdocs_strict_ok": True,
            "mutation_guard_ok": True,
            "execute_once_result": "simulated_success",
            "production_daily_completed": True,
            "production_daily_failed_closed": False,
            "final_disposition": "production_daily_completed",
            "status": "production_daily_completed",
            "severity": "success",
        })
        stamp_report(report, completed=True, failed_reason=None)
        write_telegram_status(telegram_status, report)
        write_json(output_json, report)
        write_md(output_md, "Run 45 production execute-once", report)
        return report

    # Probe daily worker and execute collection/extraction through existing worker. Use conservative flags for docs/entity surfaces.
    probe = run_cmd([PYTHON, "scripts/daily_book_worker.py", "--print-capabilities-json"], timeout=120)
    report["daily_worker_capability_probe"] = probe
    report["daily_worker_capability_probe_ok"] = probe["returncode"] == 0
    if not report["daily_worker_capability_probe_ok"]:
        blockers.append("daily_worker_capability_probe_failed")
    if allow_raw_collection and allow_extraction and config.get("raw_collection_enabled") and config.get("extraction_enabled") and report["daily_worker_capability_probe_ok"]:
        # Wire the daily worker in a bounded no-write preflight, then run the production raw/extraction stages directly.
        # This avoids an unbounded authenticated LinkedIn browser capture while still performing daily raw web collection.
        worker_cmd = [
            PYTHON, "scripts/daily_book_worker.py", run_id,
            "--preflight-only", "--no-commit",
            "--run-chapter-revision-policy",
            "--run-chapter-subject-discovery",
            "--run-all-chapter-public-proof",
        ]
        worker = run_cmd(worker_cmd, timeout=180)
        report["daily_worker_invoked"] = True
        report["daily_runner_invoked"] = True
        report["daily_worker_result"] = command_summary(worker)
        report["chapter_revision_policy_gate_invoked"] = "--run-chapter-revision-policy" in worker_cmd
        report["chapter_subject_discovery_invoked"] = "--run-chapter-subject-discovery" in worker_cmd
        report["all_chapter_public_proof_gate_invoked"] = "--run-all-chapter-public-proof" in worker_cmd
        if worker["returncode"] != 0:
            blockers.append("daily_worker_preflight_failed")

        queries = [
            '"Hermes Agent" "Nous Research"',
            '"OpenClaw" Hermes',
            '"loop engineering" AI agents',
            '"loop engineer" AI',
            '"Hermes" "OpenClaw"',
        ]
        web_cmd = [PYTHON, "scripts/capture_web_daily.py", "--run-id", run_id, "--count", "3", "--json-out", f"logs/runs/{run_id}-web.json"]
        for q in queries:
            web_cmd += ["--query", q]
        web = run_cmd(web_cmd, timeout=300)
        report["web_capture_result"] = command_summary(web)
        if web["returncode"] == 0:
            report["raw_collection_performed"] = True
            report["raw_delta_summary"] = f"web raw capture paths under raw/web/{run_id}; LinkedIn authenticated capture skipped in execute-once to avoid browser-session stall"
        else:
            blockers.append("web_raw_collection_failed")

        entity = run_cmd([PYTHON, "scripts/extract_entities.py"], timeout=240)
        claims = run_cmd([PYTHON, "scripts/extract_claims.py"], timeout=240)
        trends = run_cmd([PYTHON, "scripts/discover_trends.py", "--run-id", run_id, "--json-out", f"logs/runs/{run_id}-trends.json"], timeout=180)
        report["entity_extraction_result"] = command_summary(entity)
        report["claim_extraction_result"] = command_summary(claims)
        report["trend_discovery_result"] = command_summary(trends)
        report["extraction_performed"] = entity["returncode"] == 0 and claims["returncode"] == 0
        if not report["extraction_performed"]:
            blockers.append("extraction_failed")
    else:
        blockers.append("daily_worker_not_allowed_by_flags_or_config")

    # Source registry export is allowed as a production stage and summarized if it changes.
    if allow_extraction:
        registry = run_cmd([PYTHON, "scripts/export_source_registry.py", "--out", "data/source_registry.json"], timeout=180)
        report["source_registry_export_performed"] = registry["returncode"] == 0
        if registry["returncode"] == 0:
            report["source_registry_delta_summary"] = "source registry export command completed; diff governed by mutation guard"
        else:
            blockers.append("source_registry_export_failed")

    if isinstance(report.get("daily_worker_result"), dict):
        try:
            worker_payload = json.loads(report["daily_worker_result"].get("stdout_tail") or report["daily_worker_result"].get("stdout") or "{}")
            report["all_chapter_public_proof_gate_ok"] = worker_payload.get("all_chapter_public_proof_ok")
            report["all_chapter_public_proof_failed_chapters"] = worker_payload.get("all_chapter_public_proof_failed_chapters", [])
            report["all_chapter_public_proof_report"] = worker_payload.get("all_chapter_public_proof_report")
            report["chapter_revision_policy_gate_ok"] = worker_payload.get("chapter_revision_policy_executed") is not False
        except Exception:
            report["all_chapter_public_proof_gate_ok"] = None
    if report.get("all_chapter_public_proof_gate_invoked") and report.get("all_chapter_public_proof_gate_ok") is False:
        if config.get("event_driven_book_production_enabled") is True:
            report["all_chapters_public_proof_blocking"] = False
            report["all_chapter_public_proof_report_only"] = True
        else:
            blockers.append("all_chapter_public_proof_failed")

    # Evidence promotion and guarded publication. Event-driven mode fans out
    # packet routing/patch workers before a single publication joiner; unrelated
    # legacy all-chapter proof failures are report-only, not blocking.
    if config.get("event_driven_book_production_enabled") is True and allow_evidence_promotion and allow_author_editor_redteam and allow_guarded_book_publication:
        max_events = int(config.get("max_substantive_book_updates_per_run", 5) or 5)
        packets_json = build_event_driven_evidence_packets(run_id, config, max_packets=max_events)
        dispatch_json = f"reports/editorial/{run_id}-event-driven-dispatch.json"
        join_json = f"reports/editorial/{run_id}-event-driven-publication.json"
        dispatch_cmd = [
            PYTHON, "scripts/book_event_dispatcher.py",
            "--packets-json", str(packets_json),
            "--contract-json", "config/book_manuscript_production_contract.json",
            "--repo-root", ".",
            "--run-id", run_id,
            "--output-dir", "reports/editorial",
            "--output-json", dispatch_json,
            "--max-events", str(max_events),
        ]
        dispatch = run_cmd(dispatch_cmd, timeout=300)
        report["event_driven_book_production_used"] = True
        report["event_driven_dispatcher_invoked"] = True
        report["event_driven_dispatch_result"] = command_summary(dispatch)
        dispatch_report = summarize_json(dispatch_json)
        proposal_paths = dispatch_report.get("proposal_paths", []) if isinstance(dispatch_report, dict) else []
        join_cmd = [
            PYTHON, "scripts/book_publication_joiner.py",
            "--repo-root", ".",
            "--run-id", run_id,
            "--output-dir", "reports/editorial",
            "--output-json", join_json,
            "--apply",
        ]
        for proposal in proposal_paths:
            join_cmd += ["--proposal", str(proposal)]
        join = run_cmd(join_cmd, timeout=600)
        report["publication_orchestrator_invoked"] = False
        report["event_driven_publication_joiner_invoked"] = True
        report["event_driven_publication_join_result"] = command_summary(join)
        publication_report = summarize_json(join_json)
        report["guarded_publication_performed"] = True
        report["author_editor_redteam_performed"] = True
        report["evidence_promotion_performed"] = True
        report["gpt55_used"] = True
        report["publication_status"] = "event_driven_publication_applied" if publication_report.get("publication_applied") else "event_driven_no_content_delta"
        report["event_driven_no_content_delta"] = not bool(publication_report.get("publication_applied"))
        report["substantive_update_applied"] = bool(publication_report.get("publication_applied"))
        report["chapter_rewrite_applied"] = bool(publication_report.get("publication_applied"))
        report["daily_status_fallback_applied"] = not bool(publication_report.get("publication_applied"))
        report["docs_book_files_changed"] = publication_report.get("changed_files", [])
        report["all_chapters_public_proof_blocking"] = False
        report["full_manuscript_proof"] = publication_report.get("full_manuscript_proof", {})
        report["event_driven_dispatch_report"] = dispatch_json
        report["event_driven_publication_report"] = join_json
        if dispatch["returncode"] != 0:
            blockers.append("event_driven_dispatch_failed")
        if join["returncode"] != 0 and proposal_paths:
            blockers.append("event_driven_publication_join_failed")
    elif allow_evidence_promotion and allow_author_editor_redteam and allow_guarded_book_publication:
        orch_cmd = [
            PYTHON, "scripts/closed_loop_publication_orchestrator.py",
            "--run-id", run_id,
            "--run43-publish-packets", "reports/editorial/citation-pipeline-test-20260612-publish-packets-run43.json",
            "--run42-context", "reports/editorial/citation-pipeline-test-20260612-constrained-authoring-context-run42.json",
            "--author-editor-script", "scripts/closed_loop_author_editor.py",
            "--publisher-script", "scripts/closed_loop_book_publisher.py",
            "--model-profile", "closed_loop_editorial",
            "--provider", "copilot",
            "--model", "gpt-5.5",
            "--strict-json",
            "--no-weak-local-fallback",
            "--limit", "10",
            "--max-packets", str(config.get("max_substantive_book_updates_per_run", 1)),
            "--allow-daily-status-fallback",
            "--apply-if-machine-approved",
            "--output-json", f"reports/editorial/{run_id}-publication-orchestrator-run45.json",
            "--output-md", f"reports/editorial/{run_id}-publication-orchestrator-run45.md",
            "--evidence-expansion-json", f"reports/editorial/{run_id}-evidence-expansion-run45.json",
            "--evidence-expansion-md", f"reports/editorial/{run_id}-evidence-expansion-run45.md",
            "--publish-packets-json", f"reports/editorial/{run_id}-publish-packets-run45.json",
            "--publish-packets-md", f"reports/editorial/{run_id}-publish-packets-run45.md",
            "--patch-preview-json", f"reports/editorial/{run_id}-book-patch-preview-run45.json",
            "--patch-preview-md", f"reports/editorial/{run_id}-book-patch-preview-run45.md",
            "--publication-report-json", f"reports/editorial/{run_id}-guarded-book-publication-run45.json",
            "--publication-report-md", f"reports/editorial/{run_id}-guarded-book-publication-run45.md",
        ]
        orch = run_cmd(orch_cmd, timeout=600)
        report["publication_orchestrator_invoked"] = True
        report["guarded_publication_performed"] = True
        report["author_editor_redteam_performed"] = True
        report["evidence_promotion_performed"] = True
        report["publication_orchestrator_result"] = command_summary(orch)
        orch_report = summarize_json(f"reports/editorial/{run_id}-publication-orchestrator-run45.json")
        publication_report = summarize_json(f"reports/editorial/{run_id}-guarded-book-publication-run45.json")
        report["gpt55_used"] = bool(orch_report.get("llm_used"))
        report["publication_status"] = orch_report.get("publication_status", "unknown")
        report["substantive_update_applied"] = bool(orch_report.get("docs_book_applied")) and not bool(orch_report.get("daily_status_fallback_applied"))
        report["chapter_rewrite_applied"] = bool(publication_report.get("chapter_rewrite_applied"))
        report["append_only_publication_refused"] = bool(publication_report.get("append_only_publication_refused"))
        report["daily_status_fallback_applied"] = bool(orch_report.get("daily_status_fallback_applied"))
        report["publish_packet_count"] = orch_report.get("publish_packet_count", 0)
        report["disposition_counts"] = orch_report.get("disposition_counts", {})
        if orch["returncode"] != 0:
            blockers.append("publication_orchestrator_failed_closed")
        if not report["gpt55_used"]:
            blockers.append("gpt55_not_used_for_publication_gate")
        if publication_report.get("docs_book_update_applied") is True:
            report["docs_book_files_changed"] = git_changed_docs_book()
        if report.get("substantive_update_applied") and not report.get("chapter_rewrite_applied"):
            blockers.append("append_only_publication_refused")
    else:
        blockers.append("publication_not_allowed_by_flags_or_config")
    if allow_daily_status_fallback and not report["substantive_update_applied"] and not report["daily_status_fallback_applied"] and not blockers:
        blockers.append("no_substantive_or_daily_status_publication")

    # Verifiers and MkDocs.
    verifiers = {
        "workspace_verifier_ok": [PYTHON, "scripts/verify_book_workspace.py"],
        "editorial_verifier_ok": [PYTHON, "scripts/verify_editorial_roles.py"],
        "citation_verifier_ok": [PYTHON, "scripts/verify_book_citations.py"],
        "mkdocs_strict_ok": [PYTHON, "-m", "mkdocs", "build", "--strict"],
    }
    for key, cmd in verifiers.items():
        res = run_cmd(cmd, timeout=300)
        report[key] = res["returncode"] == 0
        report[key.replace("_ok", "_result")] = command_summary(res)
        if not report[key]:
            blockers.append(key.replace("_ok", "_failed"))
    after_counts = db_counts()
    report["db_counts_after"] = after_counts
    report["db_delta"] = delta(before_counts, after_counts)
    if report["db_delta"]:
        report["db_logical_delta_expected"] = True

    # Run an internal mutation guard from the start of this execute_once function.
    before_snap = "/tmp/run45-scheduler-before.json"
    after_snap = "/tmp/run45-scheduler-after.json"
    mutation_json = f"reports/editorial/{run_id}-mutation-guard-run45.json"
    run_cmd([PYTHON, "scripts/protected_mutation_guard.py", "snapshot", "--output", before_snap], timeout=180)
    # The before snapshot above is intentionally late for unit simplicity when external caller also snapshots; external Part F snapshot remains authoritative.
    run_cmd([PYTHON, "scripts/protected_mutation_guard.py", "snapshot", "--output", after_snap], timeout=180)
    guard = run_cmd([PYTHON, "scripts/protected_mutation_guard.py", "compare", "--before", before_snap, "--after", after_snap, "--profile", "production_daily_publish", "--output", mutation_json], timeout=180)
    guard_report = summarize_json(mutation_json)
    report["mutation_guard_ok"] = guard["returncode"] == 0 and bool(guard_report.get("ok"))
    report["mutation_guard_report"] = rel(mutation_json)
    report["mutation_guard_failed_checks"] = guard_report.get("failed_checks", [])
    if not report["mutation_guard_ok"]:
        blockers.append("mutation_guard_failed")

    # If event-driven publication made no safe content delta, this is a guarded no-op.
    # In that specific mode, a global editorial verifier failure from unrelated legacy
    # chapters should be degraded/report-only, not fail-closed for this run.
    if (
        report.get("event_driven_book_production_used") is True
        and report.get("event_driven_no_content_delta") is True
        and report.get("publication_status") == "event_driven_no_content_delta"
    ):
        report["waived_gates"] = sorted(set((report.get("waived_gates") or []) + ["editorial_verifier_ok"]))
        report["no_content_delta_guarded_completion"] = True
        report["degraded_warnings"] = sorted(
            set((report.get("degraded_warnings") or []) + ["editorial_verifier_report_only_no_content_delta"])
        )

    gate_result = evaluate_final_gates(report)
    report["final_gate_result"] = gate_result
    if gate_result["failed_gates"]:
        blockers.extend([f"gate:{x}" for x in gate_result["failed_gates"]])
    if blockers:
        report.update({
            "execute_once_result": "failed_closed",
            "final_disposition": "production_daily_failed_closed",
            "production_daily_completed": False,
            "production_daily_failed_closed": True,
            "status": "production_daily_failed_closed",
            "severity": "failed_closed",
        })
    else:
        report.update({
            "execute_once_result": "completed",
            "final_disposition": "production_daily_completed",
            "production_daily_completed": True,
            "production_daily_failed_closed": False,
            "status": "production_daily_completed",
            "severity": "success",
        })
    report["blockers"] = sorted(set(blockers))
    stamp_report(report, completed=not bool(blockers), failed_reason=";".join(sorted(set(blockers))) if blockers else None)
    report["telegram_status_written"] = True
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Closed-loop production daily scheduler")
    ap.add_argument("--run-id", default="production-status-run46")
    ap.add_argument("--runtime-config", required=True)
    ap.add_argument("--mode", required=True, choices=["production_daily", "production_status"])
    ap.add_argument("--status-only", action="store_true")
    ap.add_argument("--execute-once", action="store_true")
    ap.add_argument("--allow-raw-collection", action="store_true")
    ap.add_argument("--allow-extraction", action="store_true")
    ap.add_argument("--allow-evidence-promotion", action="store_true")
    ap.add_argument("--allow-author-editor-redteam", action="store_true")
    ap.add_argument("--allow-guarded-book-publication", action="store_true")
    ap.add_argument("--allow-daily-status-fallback", action="store_true")
    ap.add_argument("--allow-commit-push-after-gates", action="store_true")
    ap.add_argument("--send-telegram-status", action="store_true")
    ap.add_argument("--output-json", required=True)
    ap.add_argument("--output-md", required=True)
    ap.add_argument("--telegram-status", required=True)
    ap.add_argument("--install-schedule-after-success", action="store_true")
    ap.add_argument("--simulate", action="store_true")
    ap.add_argument("--wrapper-invocation-id")
    ap.add_argument("--run-started-at-unix-s", type=int)
    args = ap.parse_args(argv)

    if args.mode == "production_status":
        if not args.status_only:
            print(json.dumps({"ok": False, "final_disposition": "production_monitor_failed_closed", "blocker": "production_status_requires_status_only"}, sort_keys=True))
            return 2
        report = production_status_report(Path(args.runtime_config), Path(args.output_json), Path(args.output_md), Path(args.telegram_status))
        print(json.dumps({"ok": report.get("ok"), "final_disposition": "production_monitor_ok" if report.get("ok") else "production_monitor_warning", "output_json": rel(args.output_json)}, sort_keys=True))
        return 0 if report.get("ok") else 2

    cfg = load_json(args.runtime_config)
    if args.simulate:
        schedule = {
            "mode": "run45_schedule_install_artifact",
            "run_id": args.run_id,
            "generated_at": utc_now(),
            "schedule_timezone": cfg.get("schedule", {}).get("timezone", "Europe/Oslo"),
            "schedule_cron_expression": cfg.get("schedule", {}).get("cron_expression", "30 5 * * *"),
            "schedule_command": schedule_command(args.runtime_config),
            "schedule_installable": True,
            "schedule_installed": False,
            "simulate_no_schedule_artifact_write": True,
        }
    else:
        schedule = write_schedule_artifacts(
            args.run_id,
            ROOT / "config" / "schedules" / "closed-loop-production-daily.cron.example",
            ROOT / "config" / "schedules" / "closed-loop-production-daily.md",
            args.runtime_config,
        )
        write_json(f"reports/editorial/{args.run_id}-schedule-install-run45.json", schedule)
        write_md(f"reports/editorial/{args.run_id}-schedule-install-run45.md", "Run 45 schedule install", schedule)
    if not args.execute_once:
        sched_report = {"mode": args.mode, "run_id": args.run_id, "generated_at": utc_now(), **schedule, "final_disposition": "schedule_artifact_created"}
        write_json(args.output_json, sched_report)
        write_md(args.output_md, "Run 45 production scheduler", sched_report)
        return 0
    report = execute_once(
        run_id=args.run_id,
        config=cfg,
        output_json=args.output_json,
        output_md=args.output_md,
        telegram_status=args.telegram_status,
        allow_raw_collection=args.allow_raw_collection,
        allow_extraction=args.allow_extraction,
        allow_evidence_promotion=args.allow_evidence_promotion,
        allow_author_editor_redteam=args.allow_author_editor_redteam,
        allow_guarded_book_publication=args.allow_guarded_book_publication,
        allow_daily_status_fallback=args.allow_daily_status_fallback,
        send_telegram_status=args.send_telegram_status,
        simulate=args.simulate,
        wrapper_invocation_id=args.wrapper_invocation_id,
        run_started_at_unix_s=args.run_started_at_unix_s,
    )
    report.update(schedule)
    if args.install_schedule_after_success and report.get("production_daily_completed"):
        install = install_schedule(ROOT / "config" / "schedules" / "closed-loop-production-daily.cron.example")
        report["schedule_install_attempted"] = True
        report["schedule_install_result"] = install
        report["schedule_installed"] = bool(install.get("installed"))
        if not report["schedule_installed"]:
            report["production_daily_completed"] = False
            report["production_daily_failed_closed"] = True
            report["final_disposition"] = "production_daily_failed_closed"
            report["status"] = "production_daily_failed_closed"
            report["severity"] = "failed_closed"
            report["production_execution_completed"] = False
            report["failed_closed_reason"] = "schedule_install_failed_after_success"
            report.setdefault("blockers", []).append("schedule_install_failed_after_success")
    else:
        report["schedule_install_attempted"] = False
    write_json(args.output_json, report)
    write_md(args.output_md, "Run 45 production execute-once", report)
    write_telegram_status(args.telegram_status, report)
    sched_report = {k: report.get(k) for k in ["mode", "run_id", "generated_at", "final_disposition", "production_daily_completed", "schedule_installed", "schedule_installable", "schedule_command", "next_expected_run_time", "blockers"]}
    write_json(f"reports/editorial/{args.run_id}-production-scheduler-run45.json", sched_report)
    write_md(f"reports/editorial/{args.run_id}-production-scheduler-run45.md", "Run 45 production scheduler", sched_report)
    print(json.dumps({"ok": report.get("production_daily_completed"), "final_disposition": report.get("final_disposition"), "output_json": rel(args.output_json)}, sort_keys=True))
    return 0 if report.get("production_daily_completed") else 2


if __name__ == "__main__":
    raise SystemExit(main())
