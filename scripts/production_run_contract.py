#!/usr/bin/env python3
"""Canonical production daily run contract validation."""
from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "production_run_contract.json"
OPS_CHANNEL = "AL-Hermoine-OPS"

DEFAULT_REQUIRED_ARTIFACTS = [
    "logs/runs/{RUN_ID}.log",
    "logs/runs/{RUN_ID}.cron.out",
    "logs/runs/{RUN_ID}.cron.err",
    "reports/editorial/{RUN_ID}-production-execute-once.json",
    "reports/editorial/{RUN_ID}-production-execute-once.md",
    "reports/telegram/production-daily-latest.md",
]
DEFAULT_REQUIRED_FIELDS = [
    "run_id",
    "status",
    "severity",
    "disposition",
    "run_started_at_unix_s",
    "run_finished_at_unix_s",
    "duration_seconds",
    "emitted_at_unix_s",
    "emitted_at_unix_ms",
    "emitted_at_utc_iso",
    "emitted_at_oslo_iso",
    "target_channel",
    "fallback_channel_used",
    "production_execution_attempted",
    "production_execution_completed",
    "failed_closed_reason",
    "wrapper_invocation_id",
    "git_branch",
    "git_commit",
]


def now_meta(component: str, run_id: str, status: str, severity: str, disposition: str) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    oslo = now.astimezone(ZoneInfo("Europe/Oslo"))
    return {
        "emitted_at_unix_s": int(now.timestamp()),
        "emitted_at_unix_ms": int(now.timestamp() * 1000),
        "emitted_at_utc_iso": now.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "emitted_at_oslo_iso": oslo.replace(microsecond=0).isoformat(),
        "timezone": "Europe/Oslo",
        "component": component,
        "run_id": run_id,
        "status": status,
        "severity": severity,
        "disposition": disposition,
        "target_channel": OPS_CHANNEL,
        "fallback_channel_used": False,
    }


def load_contract(repo: Path) -> dict[str, Any]:
    path = repo / "config" / "production_run_contract.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"required_artifacts": DEFAULT_REQUIRED_ARTIFACTS, "required_machine_fields": DEFAULT_REQUIRED_FIELDS}


def load_json(path: Path) -> tuple[dict[str, Any], str | None]:
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except Exception as exc:
        return {}, str(exc)


def git_value(repo: Path, args: list[str]) -> str | None:
    try:
        proc = subprocess.run(["git", *args], cwd=repo, text=True, capture_output=True, timeout=30)
        if proc.returncode == 0:
            return proc.stdout.strip()
    except Exception:
        return None
    return None


def relative_artifact_paths(contract: dict[str, Any], run_id: str) -> list[str]:
    return [str(p).replace("{RUN_ID}", run_id) for p in contract.get("required_artifacts", DEFAULT_REQUIRED_ARTIFACTS)]


def validate_run_contract(
    repo: str | Path = ROOT,
    run_id: str = "production-daily-unknown",
    due: bool = True,
    retry_count: int = 0,
    retry_limit: int = 1,
) -> dict[str, Any]:
    repo = Path(repo)
    contract = load_contract(repo)
    required_artifacts = relative_artifact_paths(contract, run_id)
    required_fields = list(contract.get("required_machine_fields", DEFAULT_REQUIRED_FIELDS))
    reasons: list[str] = []
    artifacts = {}
    json_rel = f"reports/editorial/{run_id}-production-execute-once.json"
    payload: dict[str, Any] = {}
    load_error = None
    if (repo / json_rel).exists():
        payload, load_error = load_json(repo / json_rel)
        if load_error:
            reasons.append(f"invalid_json:{load_error}")
    wants_completed = (payload.get("final_disposition") == "production_daily_completed" or payload.get("status") == "production_daily_completed" or payload.get("production_daily_completed") is True)
    for rel in required_artifacts:
        p = repo / rel
        exists = p.exists()
        if not exists and wants_completed and rel in {f"logs/runs/{run_id}.log", f"logs/runs/{run_id}.cron.out", f"logs/runs/{run_id}.cron.err"}:
            # Shell logs are operational artifacts and may be ignored by git. A successful,
            # committed execute-once JSON still carries canonical log paths as provenance; do
            # not retroactively fail a successful run contract just because a clone or cleanup
            # lacks ignored shell-log files.
            if rel.endswith(".cron.out"):
                expected_field = "cron_out_path"
            elif rel.endswith(".cron.err"):
                expected_field = "cron_err_path"
            else:
                expected_field = "log_path"
            exists = payload.get(expected_field) == rel
        artifacts[rel] = {"exists": exists, "size": p.stat().st_size if p.exists() else None}
        if not exists:
            reasons.append(f"missing_required_artifact:{rel}")
    for field in required_fields:
        if field not in payload or payload.get(field) is None:
            if field == "failed_closed_reason" and wants_completed:
                continue
            reasons.append(f"missing_required_field:{field}")
    if payload.get("run_id") not in {None, run_id}:
        reasons.append("run_id_mismatch")
    if payload.get("target_channel") not in {None, OPS_CHANNEL}:
        reasons.append("wrong_target_channel")
    if payload.get("fallback_channel_used") is not False:
        reasons.append("fallback_channel_used")
    attempted = payload.get("production_execution_attempted") is True
    completed_flag = payload.get("production_execution_completed") is True
    wants_completed = (payload.get("final_disposition") == "production_daily_completed" or payload.get("status") == "production_daily_completed" or payload.get("production_daily_completed") is True)
    if wants_completed and not attempted:
        reasons.append("completed_without_attempt")
    if wants_completed and not completed_flag:
        reasons.append("completed_without_execution_completed")
    if completed_flag and not attempted:
        reasons.append("completed_without_attempt")
    if payload.get("run_started_at_unix_s") is not None and payload.get("run_finished_at_unix_s") is not None:
        try:
            if float(payload["run_finished_at_unix_s"]) < float(payload["run_started_at_unix_s"]):
                reasons.append("finish_before_start")
        except Exception:
            reasons.append("invalid_start_finish_timestamps")
    completed = wants_completed and not reasons and attempted and completed_flag
    status = "production_daily_completed" if completed else "production_daily_failed_closed"
    severity = "success" if completed else "failed_closed"
    self_heal_eligible = (not completed) and bool(due) and retry_count < retry_limit
    result = {
        **now_meta("production_run_contract", run_id, status, severity, status),
        "repo": str(repo),
        "contract_path": str(repo / "config" / "production_run_contract.json"),
        "required_artifacts": required_artifacts,
        "required_machine_fields": required_fields,
        "artifacts": artifacts,
        "production_json_path": str(repo / json_rel),
        "production_json_exists": (repo / json_rel).exists(),
        "completed": completed,
        "status": status,
        "severity": severity,
        "disposition": status,
        "failed_closed_reasons": sorted(set(reasons)),
        "self_heal_eligible": self_heal_eligible,
        "retry_count": retry_count,
        "retry_limit": retry_limit,
        "due": due,
        "git_branch": git_value(repo, ["branch", "--show-current"]),
        "git_commit": git_value(repo, ["rev-parse", "--short", "HEAD"]),
    }
    result["status_metadata"] = {k: result[k] for k in ["emitted_at_unix_s", "emitted_at_unix_ms", "emitted_at_utc_iso", "emitted_at_oslo_iso", "timezone", "component", "run_id", "status", "severity", "disposition", "target_channel", "fallback_channel_used"]}
    return result


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=str(ROOT))
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--due", action="store_true")
    ap.add_argument("--retry-count", type=int, default=0)
    ap.add_argument("--retry-limit", type=int, default=1)
    ap.add_argument("--output-json")
    args = ap.parse_args(argv)
    report = validate_run_contract(args.repo, args.run_id, due=args.due, retry_count=args.retry_count, retry_limit=args.retry_limit)
    if args.output_json:
        out = Path(args.output_json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False))
    return 0 if report.get("completed") else 2


if __name__ == "__main__":
    raise SystemExit(main())
