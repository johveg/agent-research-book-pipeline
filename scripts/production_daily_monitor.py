#!/usr/bin/env python3
"""Run 46 production-daily health monitor.

Deterministic status monitor for production-daily-YYYYMMDD runs. It does not
run authoring, capture, extraction, GPT, publication, git commit, or git push.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from datetime import datetime, time, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
RUN_RE = re.compile(r"^(production-daily-\d{8}|production-daily-manual-\d{8}T\d{6}Z)$")
FIXED_RUN_ID = "citation-pipeline-test-20260612"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_crontab() -> str:
    proc = subprocess.run(["bash", "-lc", "crontab -l 2>/dev/null || true"], text=True, capture_output=True)
    return proc.stdout or ""


def expected_run_id_for_date(date: str) -> str:
    return "production-daily-" + date.replace("-", "")


def parse_local_time(value: str) -> time:
    hour, minute = value.split(":", 1)
    return time(int(hour), int(minute))


def load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"_load_error": str(exc)}


def write_json(path: Path, obj: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def write_md(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Production daily monitor",
        "",
        f"Generated: `{report.get('generated_at')}`",
        "",
        f"- status: `{report.get('status')}`",
        f"- ok: `{report.get('ok')}`",
        f"- expected_run_id: `{report.get('expected_run_id')}`",
        f"- schedule due: `{report.get('schedule_due')}`",
        f"- crontab production command found: `{report.get('crontab_production_daily_command_found')}`",
        f"- production report JSON: `{report.get('production_report_json')}` exists `{report.get('production_report_json_exists')}`",
        f"- production report MD: `{report.get('production_report_md')}` exists `{report.get('production_report_md_exists')}`",
        f"- telegram status path: `{report.get('telegram_daily_status_path')}` exists `{report.get('telegram_daily_status_exists')}`",
        f"- log path: `{report.get('log_path')}` exists `{report.get('log_exists')}`",
        f"- disposition: `{report.get('latest_disposition')}`",
    ]
    if report.get("warnings"):
        lines += ["", "## Warnings", ""] + [f"- `{w}`" for w in report.get("warnings", [])]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")



def future_recorded_next_run(repo: Path, local_now: datetime) -> str | None:
    for path in sorted((repo / "reports" / "editorial").glob("*run45.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        value = payload.get("next_expected_run_time")
        if not value:
            continue
        try:
            # Run45 stored a dual-offset display; compare the ISO prefix.
            iso = str(value).split("/+", 1)[0]
            dt = datetime.fromisoformat(iso)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=local_now.tzinfo)
            if dt > local_now:
                return str(value)
        except Exception:
            continue
    return None

def monitor(
    repo: str | Path = ROOT,
    date: str | None = None,
    run_id: str | None = None,
    timezone_name: str = "Europe/Oslo",
    expect_schedule_time: str = "05:30",
    max_age_minutes: int = 180,
    telegram_status: str | Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    repo = Path(repo)
    tz = ZoneInfo(timezone_name)
    local_now = now.astimezone(tz) if now else datetime.now(tz)
    date = date or local_now.date().isoformat()
    expected_run_id = run_id or expected_run_id_for_date(date)
    warnings: list[str] = []
    if expected_run_id == FIXED_RUN_ID or not RUN_RE.match(expected_run_id):
        warnings.append("fixed_run_id_not_allowed")
        status = "production_monitor_failed_closed"
        report = {
            "ok": False,
            "status": status,
            "final_disposition": status,
            "generated_at": utc_now(),
            "repo": str(repo),
            "expected_run_id": expected_run_id,
            "timezone": timezone_name,
            "expected_schedule_time": expect_schedule_time,
            "warnings": warnings,
            "old_fixed_run_id_ignored": True,
        }
        if telegram_status:
            write_md(Path(telegram_status), report)
        return report

    scheduled = datetime.combine(datetime.fromisoformat(date).date(), parse_local_time(expect_schedule_time), tzinfo=tz)
    due = local_now >= scheduled
    recorded_next_run = future_recorded_next_run(repo, local_now)
    if due and recorded_next_run:
        due = False
    json_path = repo / "reports" / "editorial" / f"{expected_run_id}-production-execute-once.json"
    md_path = repo / "reports" / "editorial" / f"{expected_run_id}-production-execute-once.md"
    telegram_daily = repo / "reports" / "telegram" / "production-daily-latest.md"
    log_path = repo / "logs" / "runs" / f"{expected_run_id}.log"
    event_log = repo / "logs" / "closed_loop" / "events.jsonl"
    crontab = read_crontab()
    schedule_found = "closed_loop_production_scheduler.py" in crontab and "production-daily-%Y%m%d" in crontab

    payload = load_json(json_path) if json_path.exists() else {}
    disposition = payload.get("final_disposition") or payload.get("status")
    status = "production_daily_missing_not_due_yet"
    ok = True
    if json_path.exists():
        if disposition == "production_daily_completed" or payload.get("production_daily_completed") is True:
            status = "production_daily_completed"
            ok = True
        elif disposition == "production_daily_failed_closed" or payload.get("production_daily_failed_closed") is True:
            status = "production_daily_failed_closed"
            ok = False
        else:
            status = "production_monitor_warning"
            ok = False
            warnings.append("unknown_production_report_disposition")
    elif log_path.exists():
        age_minutes = max(0.0, (local_now.timestamp() - log_path.stat().st_mtime) / 60.0)
        if age_minutes > max_age_minutes:
            status = "production_daily_stale"
            ok = False
        else:
            status = "production_daily_running"
            ok = True
    elif due:
        status = "production_daily_missing_after_due"
        ok = False
    else:
        status = "production_daily_missing_not_due_yet"
        ok = True

    if not schedule_found:
        warnings.append("crontab_production_daily_command_missing")
        if status == "production_daily_completed":
            status = "production_monitor_warning"
            ok = False

    report = {
        "ok": ok,
        "status": status,
        "final_disposition": status,
        "generated_at": utc_now(),
        "repo": str(repo),
        "timezone": timezone_name,
        "local_now": local_now.isoformat(),
        "expected_schedule_time": expect_schedule_time,
        "schedule_due": due,
        "recorded_next_expected_run_time": recorded_next_run,
        "expected_run_id": expected_run_id,
        "old_fixed_run_id_ignored": True,
        "old_fixed_run_id": FIXED_RUN_ID,
        "production_report_json": str(json_path),
        "production_report_json_exists": json_path.exists(),
        "production_report_md": str(md_path),
        "production_report_md_exists": md_path.exists(),
        "telegram_daily_status_path": str(telegram_daily),
        "telegram_daily_status_exists": telegram_daily.exists(),
        "log_path": str(log_path),
        "log_exists": log_path.exists(),
        "events_log_path": str(event_log),
        "events_log_exists": event_log.exists(),
        "latest_disposition": disposition,
        "max_age_minutes": max_age_minutes,
        "crontab_production_daily_command_found": schedule_found,
        "schedule_command": next((line for line in crontab.splitlines() if "closed_loop_production_scheduler.py" in line), ""),
        "warnings": warnings,
    }
    if telegram_status:
        write_md(Path(telegram_status), report)
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Monitor production-daily run health")
    ap.add_argument("--date")
    ap.add_argument("--run-id")
    ap.add_argument("--repo", default=str(ROOT))
    ap.add_argument("--status-only", action="store_true")
    ap.add_argument("--telegram-status")
    ap.add_argument("--max-age-minutes", type=int, default=180)
    ap.add_argument("--expect-schedule-time", default="05:30")
    ap.add_argument("--timezone", default="Europe/Oslo")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--output-md")
    args = ap.parse_args(argv)
    report = monitor(args.repo, args.date, args.run_id, args.timezone, args.expect_schedule_time, args.max_age_minutes, args.telegram_status)
    if args.output_md:
        write_md(Path(args.output_md), report)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False))
    else:
        print(f"{report['status']} {report['expected_run_id']}")
    return 0 if report.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
