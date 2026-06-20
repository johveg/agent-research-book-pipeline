#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

DEFAULT_POLICY = Path("config/global_ops_routing_policy.json")


def load_policy(path: str | Path = DEFAULT_POLICY) -> dict[str, Any]:
    return json.loads(Path(path).read_text())


def _metadata(payload: dict[str, Any]) -> dict[str, Any]:
    return payload.get("status_metadata") if isinstance(payload.get("status_metadata"), dict) else payload


def classify_delivery(payload: dict[str, Any], policy: dict[str, Any] | None = None, alias_resolvable: bool = False) -> dict[str, Any]:
    policy = policy or load_policy()
    meta = _metadata(payload)
    target = payload.get("target_channel") or meta.get("target_channel")
    fallback = payload.get("fallback_channel_used") is True or meta.get("fallback_channel_used") is True
    queued = payload.get("queued") is True or payload.get("delivery_state") in {"queued", "retry_scheduled"}
    confirmation = payload.get("delivery_confirmation") or payload.get("message_id") or payload.get("confirmed_message_id")
    reasons: list[str] = []
    if fallback and not policy.get("fallback_allowed"):
        reasons.append("fallback_channel_blocked")
        return {"classification": "blocked_fallback", "success": False, "reasons": reasons, "disposition": "fallback_channel_blocked"}
    if str(target).lower() in {"telegram:marius", "marius", "telegram", "home", "default", "origin", "all"}:
        reasons.append("blocked_dm" if "marius" in str(target).lower() else "blocked_default")
        return {"classification": "blocked_dm", "success": False, "reasons": reasons, "disposition": "fallback_channel_blocked"}
    if target != policy["required_ops_channel"]:
        reasons.append("wrong_target_channel")
    if policy.get("timestamp_metadata_required") and not any(k in meta for k in ["emitted_at_unix_s", "emitted_at_unix_ms", "emitted_at_utc_iso", "emitted_at_oslo_iso"]):
        reasons.append("missing_metadata")
    if not alias_resolvable:
        reasons.append("unresolved_target")
        if queued and policy.get("queue_if_unresolved") and not any(r in reasons for r in ["wrong_target_channel", "missing_metadata"]):
            return {"classification": "queued", "success": False, "reasons": reasons, "disposition": "ops_outbox_queued"}
    if policy.get("delivery_confirmation_required_for_success") and alias_resolvable and not confirmation:
        reasons.append("missing_delivery_confirmation")
    if reasons:
        classification = "missing_metadata" if reasons == ["missing_metadata"] else "failed_closed"
        return {"classification": classification, "success": False, "reasons": reasons, "disposition": "ops_delivery_failed_closed"}
    return {"classification": "compliant", "success": True, "reasons": [], "disposition": "ops_delivery_verified"}


def routing_fixed(alias_resolvable: bool, live_delivery_confirmed: bool) -> bool:
    return bool(alias_resolvable and live_delivery_confirmed)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--payload-json")
    ap.add_argument("--alias-resolvable", action="store_true")
    args = ap.parse_args()
    payload = json.loads(Path(args.payload_json).read_text()) if args.payload_json else {}
    print(json.dumps(classify_delivery(payload, load_policy(), args.alias_resolvable), indent=2, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
