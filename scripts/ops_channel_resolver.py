#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
from pathlib import Path
from typing import Any

OPS_ALIAS = "AL-Hermoine-OPS"
DEFAULT_DIRS = [Path("/root/.hermes/channel_directory.json"), Path("/root/.hermes/profiles/ops-bot/channel_directory.json")]
SECRET_KEY_RE = re.compile(r"(token|secret|password|cookie|authorization|api[_-]?key|chat_id|id)$", re.I)
CHAT_ID_RE = re.compile(r"^-?\d{5,}(?::\d+)?$")
BOT_TOKEN_RE = re.compile(r"\b\d{8,12}:[A-Za-z0-9_-]{20,}\b")


def _redact_value(key: str, value: Any) -> Any:
    if isinstance(value, str):
        if SECRET_KEY_RE.search(key) or CHAT_ID_RE.match(value) or BOT_TOKEN_RE.search(value):
            return "[REDACTED]"
        return BOT_TOKEN_RE.sub("[REDACTED_BOT_TOKEN]", value)
    if isinstance(value, (int, float)) and SECRET_KEY_RE.search(key):
        return "[REDACTED]"
    return value


def sanitize_directory(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: sanitize_directory(_redact_value(k, v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize_directory(v) for v in obj]
    return obj


def reject_ops_substitute(target: str | None) -> str | None:
    t = (target or "").lower()
    if "marius" in t or t in {"telegram", "home", "default", "origin", "all"}:
        return "rejected_non_ops_dm" if "marius" in t else "rejected_default_or_fallback"
    return None


def _iter_entries(directory: Any):
    if isinstance(directory, dict):
        if isinstance(directory.get("channels"), list):
            for x in directory["channels"]:
                if isinstance(x, dict):
                    yield x
        for k, v in directory.items():
            if isinstance(v, dict):
                entry = {"name": k, **v}
                yield entry
                yield from _iter_entries(v)
            elif isinstance(v, list):
                yield from _iter_entries(v)
    elif isinstance(directory, list):
        for v in directory:
            yield from _iter_entries(v)


def _entry_name(entry: dict[str, Any]) -> str:
    return str(entry.get("name") or entry.get("alias") or entry.get("display_name") or entry.get("title") or entry.get("label") or "")


def _is_ops_bot_home(entry: dict[str, Any]) -> bool:
    return (
        _entry_name(entry) == OPS_ALIAS
        and str(entry.get("platform", "telegram")).lower() == "telegram"
        and entry.get("kind") == "ops_bot_home"
        and entry.get("delivery_profile") == "ops-bot"
        and entry.get("delivery_target") == "telegram"
    )


def _is_dm(entry: dict[str, Any]) -> bool:
    if _is_ops_bot_home(entry):
        return False
    blob = json.dumps(entry, ensure_ascii=False).lower()
    name = _entry_name(entry).lower()
    return "marius" in name or entry.get("kind") == "dm" or entry.get("type") == "dm" or "private" in blob


def resolve_alias(directory: Any, alias: str = OPS_ALIAS) -> dict[str, Any]:
    reject = reject_ops_substitute(alias)
    if reject:
        return {"status": "ops_alias_unresolved", "reason": reject, "fallback_accepted": False, "fallback_channel_used": False}
    matches = [e for e in _iter_entries(directory) if _entry_name(e) == alias or str(e.get("target") or "") == alias]
    if not matches:
        # equivalent spelling check without accepting non-OPS aliases
        equiv = [e for e in _iter_entries(directory) if _entry_name(e).lower().replace("_", "-") == alias.lower().replace("_", "-")]
        matches = equiv
    if not matches:
        return {"status": "ops_alias_unresolved", "alias": alias, "fallback_accepted": False, "fallback_channel_used": False, "equivalent_alias_found": False}
    safe = [e for e in matches if not _is_dm(e) and str(e.get("platform", "telegram")).lower() == "telegram"]
    if not safe:
        return {"status": "ops_alias_unresolved", "alias": alias, "reason": "matched_alias_is_dm_or_non_telegram", "fallback_accepted": False, "fallback_channel_used": False}
    return {"status": "ops_alias_resolved", "alias": alias, "is_dm": False, "fallback_accepted": False, "fallback_channel_used": False, "target_redacted": "[REDACTED]", "delivery_profile": safe[0].get("delivery_profile"), "delivery_target": safe[0].get("delivery_target"), "entry_redacted": sanitize_directory(safe[0])}


def load_directory(path: Path) -> Any:
    try:
        return json.loads(path.read_text())
    except Exception:
        return {"channels": []}


def safe_add_alias(path: Path, alias: str, target: dict[str, Any] | None) -> dict[str, Any]:
    if not target:
        return {"status": "failed_closed_no_resolvable_ops_target", "missing_input": {"active_channel_directory_path": str(path), "expected_alias_name": alias, "required_value_type": "known non-DM Telegram channel entry", "reload_restart_requirement": "restart Hermes gateway or active profile after directory update"}}
    if _is_dm({"name": alias, **target}) or reject_ops_substitute(alias):
        return {"status": "ops_delivery_failed_closed", "reason": "refused_dm_or_fallback"}
    data = load_directory(path)
    if resolve_alias(data, alias).get("status") == "ops_alias_resolved":
        return {"status": "ops_alias_resolved", "changed": False}
    if not isinstance(data, dict):
        return {"status": "failed_closed_no_resolvable_ops_target", "reason": "unknown_channel_directory_schema"}
    channels = data.setdefault("channels", [])
    if not isinstance(channels, list):
        return {"status": "failed_closed_no_resolvable_ops_target", "reason": "unknown_channel_directory_schema"}
    channels.append({"name": alias, **target})
    path.write_text(json.dumps(data, indent=2, sort_keys=True))
    return {"status": "ops_alias_resolved", "changed": True, "path": str(path)}


def sanitize_send_list(text: str) -> str:
    """Redact live send target IDs without leaving bracketed pseudo-targets."""
    text = BOT_TOKEN_RE.sub("[REDACTED_BOT_TOKEN]", text)
    text = re.sub(r"(telegram:Marius)\s*\[[^\]]+\]", r"\1 (rejected_non_ops_dm)", text)
    text = re.sub(r"\[[0-9:-]+\]", "", text)
    return text


def hermes_send_list() -> str:
    p = subprocess.run(["bash", "-lc", "hermes send --list telegram 2>/dev/null || true"], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return sanitize_send_list(p.stdout)


def resolve_from_paths(paths: list[Path] = DEFAULT_DIRS) -> dict[str, Any]:
    send_list = hermes_send_list()
    dirs = []
    resolved = None
    for p in paths:
        data = load_directory(p)
        r = resolve_alias(data, OPS_ALIAS)
        dirs.append({"path": str(p), "exists": p.exists(), "resolution": r, "directory_redacted": sanitize_directory(data) if p.exists() else None})
        if r.get("status") == "ops_alias_resolved":
            resolved = r
    if OPS_ALIAS in send_list and not resolved:
        resolved = {"status": "ops_alias_resolved", "alias": OPS_ALIAS, "source": "hermes_send_list", "target_redacted": "[REDACTED]", "fallback_channel_used": False}
    status = "ops_alias_resolved" if resolved else "ops_alias_unresolved"
    return {"run_id": "run57", "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(), "status": status, "alias": OPS_ALIAS, "fallback_channel_used": False, "fallback_accepted": False, "telegram_Marius_rejected_as_substitute": True, "send_list_redacted": send_list.splitlines(), "directories": dirs, "missing_input": None if resolved else {"active_channel_directory_path": str(paths[0]), "expected_alias_name": OPS_ALIAS, "required_value_type": "known non-DM Telegram channel/topic target entry", "reload_restart_requirement": "restart Hermes gateway/profile or rerun resolver after target appears"}}


def write_reports(report: dict[str, Any], json_path: Path, md_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True))
    md_path.write_text("# Run 57 OPS channel resolution\n\n```json\n" + json.dumps(report, indent=2, sort_keys=True) + "\n```\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output-json", default="reports/editorial/run57-ops-channel-resolution.json")
    ap.add_argument("--output-md", default="reports/editorial/run57-ops-channel-resolution.md")
    args = ap.parse_args()
    report = resolve_from_paths()
    write_reports(report, Path(args.output_json), Path(args.output_md))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
