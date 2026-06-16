#!/usr/bin/env python3
"""Normalize and fail-closed route Terefo OPS status messages.

Live Telegram sending is performed by Hermes tooling, not by this repository
script. This script produces normalized JSON/Markdown messages and fails closed
unless the target alias is AL-Hermoine-OPS.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from status_message_contract import (  # noqa: E402
    OPS_CHANNEL,
    StatusContractError,
    normalize_status,
    redact_sensitive,
    render_json_status,
    render_markdown_status,
)


def read_status_file(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if p.suffix.lower() == ".json":
        return json.loads(text)
    # Markdown is accepted as an opaque summary when no JSON front matter exists.
    return {"summary": text}


def send_ops_status(
    status_file: str | Path,
    component: str | None = None,
    run_id: str | None = None,
    status: str | None = None,
    severity: str | None = None,
    ops_channel: str | None = OPS_CHANNEL,
    dry_run: bool = False,
    write_normalized_json: str | Path | None = None,
    write_normalized_md: str | Path | None = None,
    sender: Callable[[str, str], Any] | None = None,
) -> dict[str, Any]:
    if ops_channel != OPS_CHANNEL:
        raise StatusContractError(f"target_channel_not_allowed:{ops_channel}")
    payload = read_status_file(status_file)
    if component is not None:
        payload["component"] = component
    if run_id is not None:
        payload["run_id"] = run_id
    if status is not None:
        payload["status"] = status
    if severity is not None:
        payload["severity"] = severity
    payload.setdefault("target_channel", ops_channel)
    normalized = normalize_status(payload)
    json_text = render_json_status(normalized)
    md_text = render_markdown_status(normalized, title=f"OPS status — {normalized.get('component')}")
    if write_normalized_json:
        out = Path(write_normalized_json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json_text, encoding="utf-8")
    if write_normalized_md:
        out = Path(write_normalized_md)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(md_text, encoding="utf-8")
    live_send_performed = False
    live_send_error = None
    if not dry_run:
        if sender is None:
            live_send_error = "live_send_requires_hermes_send_message_tool_with_alias_AL-Hermoine-OPS"
            raise StatusContractError(live_send_error)
        sender(OPS_CHANNEL, md_text)
        live_send_performed = True
    return {
        "ok": True,
        "dry_run": dry_run,
        "live_send_performed": live_send_performed,
        "live_send_error": live_send_error,
        "target_channel": normalized["target_channel"],
        "normalized_status": redact_sensitive(normalized),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Normalize and route OPS status")
    ap.add_argument("--status-file", required=True)
    ap.add_argument("--component")
    ap.add_argument("--run-id")
    ap.add_argument("--status")
    ap.add_argument("--severity")
    ap.add_argument("--ops-channel", default=OPS_CHANNEL)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--write-normalized-json")
    ap.add_argument("--write-normalized-md")
    args = ap.parse_args(argv)
    try:
        result = send_ops_status(
            args.status_file,
            component=args.component,
            run_id=args.run_id,
            status=args.status,
            severity=args.severity,
            ops_channel=args.ops_channel,
            dry_run=args.dry_run,
            write_normalized_json=args.write_normalized_json,
            write_normalized_md=args.write_normalized_md,
        )
    except StatusContractError as exc:
        print(json.dumps({"ok": False, "status": "ops_status_failed_closed", "error": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps({"ok": True, "target_channel": result["target_channel"], "dry_run": result["dry_run"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
