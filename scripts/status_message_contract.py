#!/usr/bin/env python3
"""Run 51 OPS status routing and timestamp contract utilities."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "config"
DEFAULT_ROUTING = CONFIG_DIR / "status_routing.json"
DEFAULT_TIMESTAMP_CONTRACT = CONFIG_DIR / "status_timestamp_contract.json"
OPS_CHANNEL = "AL-Hermoine-OPS"
ALLOWED_SEVERITIES = {"info", "success", "warning", "failure", "blocked", "failed_closed"}
REQUIRED_BASE_FIELDS = ["component", "run_id", "status", "severity"]
SENSITIVE_PATTERNS = [
    re.compile(r"(Authorization\s*:\s*Bearer\s+)[^\s`]+", re.I),
    re.compile(r"(Bearer\s+)[A-Za-z0-9._~+\-/]+=*", re.I),
    re.compile(r"(TELEGRAM[_-]?BOT[_-]?TOKEN\s*[=:]\s*)[^\s`]+", re.I),
    re.compile(r"(token\s*[=:]\s*)[^\s`]+", re.I),
    re.compile(r"(api[_-]?key\s*[=:]\s*)[^\s`]+", re.I),
    re.compile(r"(password\s*[=:]\s*)[^\s`]+", re.I),
    re.compile(r"(cookie\s*[=:]\s*)[^\n`]+", re.I),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.I | re.S),
]


class StatusContractError(ValueError):
    """Fail-closed status contract violation."""


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise StatusContractError(f"missing_config:{path}")
    return json.loads(path.read_text(encoding="utf-8"))


def load_routing_config(path: str | Path = DEFAULT_ROUTING) -> dict[str, Any]:
    cfg = load_json(Path(path))
    if cfg.get("default_status_channel") != OPS_CHANNEL or cfg.get("ops_channel") != OPS_CHANNEL:
        raise StatusContractError("ops_channel_missing_or_not_default")
    if OPS_CHANNEL not in cfg.get("allowed_channels", []):
        raise StatusContractError("ops_channel_not_allowed")
    if cfg.get("fallback_channel_policy") != "fail_closed":
        raise StatusContractError("fallback_channel_policy_must_fail_closed")
    return cfg


def load_timestamp_contract(path: str | Path = DEFAULT_TIMESTAMP_CONTRACT) -> dict[str, Any]:
    cfg = load_json(Path(path))
    if "emitted_at_unix_s" not in cfg.get("required_machine_timestamp_fields", []):
        raise StatusContractError("timestamp_contract_missing_epoch_seconds")
    return cfg


def timestamp_metadata(now: datetime | None = None, timezone_name: str = "Europe/Oslo") -> dict[str, Any]:
    if now is None:
        unix_ms = int(time.time() * 1000)
        utc = datetime.fromtimestamp(unix_ms / 1000, tz=timezone.utc)
    else:
        utc = now.astimezone(timezone.utc)
        unix_ms = int(utc.timestamp() * 1000)
    oslo = utc.astimezone(ZoneInfo(timezone_name))
    return {
        "emitted_at_unix_s": int(unix_ms // 1000),
        "emitted_at_unix_ms": int(unix_ms),
        "emitted_at_utc_iso": utc.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "emitted_at_oslo_iso": oslo.replace(microsecond=0).isoformat(),
        "timezone": timezone_name,
    }


def redact_sensitive(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: ("[REDACTED]" if re.search(r"token|secret|password|cookie|private_key|api_key", str(k), re.I) else redact_sensitive(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_sensitive(v) for v in value]
    if not isinstance(value, str):
        return value
    text = value
    for pattern in SENSITIVE_PATTERNS:
        text = pattern.sub(lambda m: (m.group(1) if m.groups() else "") + "[REDACTED]", text)
    return text


def _git_value(args: list[str]) -> str | None:
    try:
        return subprocess.check_output(args, cwd=ROOT, text=True, stderr=subprocess.DEVNULL).strip() or None
    except Exception:
        return None


def normalize_status(payload: dict[str, Any], routing_config: str | Path = DEFAULT_ROUTING, timestamp_contract: str | Path = DEFAULT_TIMESTAMP_CONTRACT) -> dict[str, Any]:
    routing = load_routing_config(routing_config)
    load_timestamp_contract(timestamp_contract)
    missing = [field for field in REQUIRED_BASE_FIELDS if not payload.get(field)]
    if missing:
        raise StatusContractError("missing_required_fields:" + ",".join(missing))
    severity = str(payload.get("severity"))
    if severity not in ALLOWED_SEVERITIES:
        raise StatusContractError(f"invalid_severity:{severity}")
    target = payload.get("target_channel") or payload.get("ops_channel") or routing["default_status_channel"]
    allowed = set(routing.get("allowed_channels", []))
    if target not in allowed:
        raise StatusContractError(f"target_channel_not_allowed:{target}")
    meta = timestamp_metadata(timezone_name=payload.get("timezone") or "Europe/Oslo")
    normalized = {**meta, **redact_sensitive(dict(payload))}
    normalized["target_channel"] = target
    normalized.setdefault("ops_channel", routing["ops_channel"])
    normalized.setdefault("disposition", normalized["status"])
    normalized.setdefault("repo", str(ROOT))
    normalized.setdefault("git_commit", _git_value(["git", "rev-parse", "--short", "HEAD"]))
    normalized.setdefault("git_branch", _git_value(["git", "branch", "--show-current"]))
    normalized.setdefault("report_path", None)
    normalized.setdefault("log_path", None)
    normalized.setdefault("run_started_at_unix_s", None)
    normalized.setdefault("run_finished_at_unix_s", None)
    normalized.setdefault("duration_seconds", None)
    return normalized


def _yaml_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value).replace('"', '\\"')
    if re.search(r"[:#\n]|^$|\s", text):
        return f'"{text}"'
    return text


def render_metadata_block(status: dict[str, Any]) -> str:
    ordered = [
        "emitted_at_unix_s", "emitted_at_unix_ms", "emitted_at_utc_iso", "emitted_at_oslo_iso", "timezone",
        "component", "run_id", "status", "severity", "disposition", "target_channel", "repo", "git_commit", "git_branch",
        "report_path", "log_path", "run_started_at_unix_s", "run_finished_at_unix_s", "duration_seconds",
    ]
    lines = ["```yaml", "status_metadata:"]
    for key in ordered:
        if key in status:
            lines.append(f"  {key}: {_yaml_scalar(status.get(key))}")
    lines.append("```")
    return "\n".join(lines)


def render_markdown_status(status: dict[str, Any], title: str = "OPS status") -> str:
    normalized = normalize_status(status) if not all(k in status for k in REQUIRED_BASE_FIELDS + ["emitted_at_unix_s"]) else status
    lines = [f"# {redact_sensitive(title)}", "", render_metadata_block(normalized), "", "## Summary", ""]
    for key in ["component", "run_id", "status", "severity", "disposition", "target_channel", "repo", "report_path", "log_path"]:
        lines.append(f"- {key}: `{redact_sensitive(normalized.get(key))}`")
    if normalized.get("summary"):
        lines += ["", str(redact_sensitive(normalized.get("summary")))]
    return "\n".join(lines) + "\n"


def with_status_metadata_object(status: dict[str, Any]) -> dict[str, Any]:
    metadata_keys = [
        "emitted_at_unix_s", "emitted_at_unix_ms", "emitted_at_utc_iso", "emitted_at_oslo_iso", "timezone",
        "component", "run_id", "status", "severity", "disposition", "target_channel", "repo", "git_commit", "git_branch",
        "report_path", "log_path", "run_started_at_unix_s", "run_finished_at_unix_s", "duration_seconds",
    ]
    enriched = dict(status)
    enriched["status_metadata"] = {key: enriched.get(key) for key in metadata_keys if key in enriched}
    return enriched


def render_json_status(status: dict[str, Any]) -> str:
    normalized = normalize_status(status) if not all(k in status for k in REQUIRED_BASE_FIELDS + ["emitted_at_unix_s"]) else status
    return json.dumps(redact_sensitive(with_status_metadata_object(normalized)), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Normalize OPS status payloads")
    ap.add_argument("--input-json")
    ap.add_argument("--output-json")
    ap.add_argument("--output-md")
    ap.add_argument("--title", default="OPS status")
    args = ap.parse_args(argv)
    payload = json.loads(Path(args.input_json).read_text(encoding="utf-8")) if args.input_json else json.load(__import__("sys").stdin)
    try:
        normalized = normalize_status(payload)
    except StatusContractError as exc:
        print(json.dumps({"ok": False, "status": "ops_status_failed_closed", "error": str(exc)}, sort_keys=True))
        return 2
    if args.output_json:
        Path(args.output_json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output_json).write_text(render_json_status(normalized), encoding="utf-8")
    if args.output_md:
        Path(args.output_md).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output_md).write_text(render_markdown_status(normalized, args.title), encoding="utf-8")
    print(json.dumps({"ok": True, "status": normalized["status"], "target_channel": normalized["target_channel"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
