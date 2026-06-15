#!/usr/bin/env python3
"""Run 43 publish-packet validator.

Validates machine-generated publish packets for dry-run preview only. This module
keeps Run 43 publication disabled by default and rejects unsafe dependencies,
unsupported dispositions, missing evidence/citation linkage, and any indication
that docs/book or deployment already happened.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

ALLOWED_DISPOSITIONS = {
    "publish_packet_candidate",
    "publish_packet_machine_approved",
    "caveat_only_publish_packet",
    "publish_packet_blocked",
    "needs_more_sources",
    "contradiction_review_required",
    "quarantine",
    "safe_reports_only",
    "publish_daily_no_safe_promotions",
}
ALLOWED_UPDATE_TYPES = {
    "existing_chapter_delta",
    "new_chapter_candidate",
    "caveated_note",
    "guarded_substantive_canary",
    "caveated_substantive_canary",
    "daily_status_only",
    "no_publication",
}
REQUIRED_FIELDS = [
    "publish_packet_id",
    "source_packet_ids",
    "input_context_ids",
    "target_book_area",
    "target_file_suggestion",
    "update_type",
    "title",
    "summary",
    "proposed_markdown_delta",
    "claim_map",
    "citation_map",
    "evidence_refs",
    "source_quality_summary",
    "required_caveats",
    "forbidden_claims_checked",
    "redteam_findings",
    "machine_editor_findings",
    "disposition",
    "publication_readiness",
    "idempotency_key",
    "human_in_loop_dependency_added",
]
HUMAN_DEPENDENCY_TOKENS = [
    "human_" + "review_required",
    "requires_" + "human_review",
    "manual_" + "approval_required",
    "editor_" + "must_review",
]
FORBIDDEN_POSITIVE_CLAIMS = [
    "hermes is the runtime dependency of openclaw",
    "hermes is a runtime dependency of openclaw",
    "hermes is the general operating environment for openclaw",
    "openclaw requires hermes for web or phone access",
]
NEGATION_HINTS = ["do not", "does not", "not establish", "not state", "must not", "without additional"]


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def compact(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str)


def _is_nonempty_list(value: Any) -> bool:
    return isinstance(value, list) and len(value) > 0


def _is_nonempty_dict(value: Any) -> bool:
    return isinstance(value, dict) and len(value) > 0


def _has_human_dependency(obj: Any) -> bool:
    text = compact(obj).lower()
    return any(token in text for token in HUMAN_DEPENDENCY_TOKENS)


def _positive_forbidden_claim(text: str) -> str:
    lower = " ".join(str(text or "").lower().split())
    for phrase in FORBIDDEN_POSITIVE_CLAIMS:
        idx = lower.find(phrase)
        if idx == -1:
            continue
        window = lower[max(0, idx - 60): idx + len(phrase) + 20]
        if any(hint in window for hint in NEGATION_HINTS):
            continue
        return phrase
    return ""


def validate_publish_packet(packet: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(packet, dict):
        return ["packet must be object"]
    for field in REQUIRED_FIELDS:
        if field not in packet:
            errors.append(f"missing required field: {field}")
    if errors:
        return errors

    for field in ["publish_packet_id", "target_book_area", "target_file_suggestion", "title", "summary", "proposed_markdown_delta", "source_quality_summary", "idempotency_key"]:
        if not isinstance(packet.get(field), str) or not packet[field].strip():
            errors.append(f"{field} must be non-empty string")
    for field in ["source_packet_ids", "input_context_ids", "evidence_refs", "required_caveats", "forbidden_claims_checked"]:
        if not _is_nonempty_list(packet.get(field)):
            errors.append(f"{field} must be non-empty list")
    if not _is_nonempty_list(packet.get("claim_map")):
        errors.append("claim_map must be non-empty list")
    if not _is_nonempty_dict(packet.get("citation_map")):
        errors.append("citation_map must be non-empty object")
    if packet.get("update_type") not in ALLOWED_UPDATE_TYPES:
        errors.append(f"unsupported update_type: {packet.get('update_type')}")
    if packet.get("disposition") not in ALLOWED_DISPOSITIONS:
        errors.append(f"unsupported disposition: {packet.get('disposition')}")

    readiness = packet.get("publication_readiness")
    if not isinstance(readiness, dict):
        errors.append("publication_readiness must be object")
        readiness = {}
    for key in ["ready_for_dry_run_patch", "ready_for_guarded_publication", "blocked"]:
        if not isinstance(readiness.get(key), bool):
            errors.append(f"publication_readiness.{key} must be boolean")
    if readiness.get("ready_for_guarded_publication") is True:
        editor_ok = isinstance(packet.get("machine_editor_findings"), dict) and packet["machine_editor_findings"].get("approved") is True
        redteam_ok = isinstance(packet.get("redteam_findings"), dict) and packet["redteam_findings"].get("approved") is True
        if not (editor_ok and redteam_ok and packet.get("disposition") in {"publish_packet_machine_approved", "caveat_only_publish_packet"}):
            errors.append("guarded publication requires machine editor/red-team approval and machine-approved or caveat-only disposition")
    if readiness.get("ready_for_dry_run_patch") is True:
        editor_ok = isinstance(packet.get("machine_editor_findings"), dict) and packet["machine_editor_findings"].get("approved") is True
        redteam_ok = isinstance(packet.get("redteam_findings"), dict) and packet["redteam_findings"].get("approved") is True
        if not (editor_ok and redteam_ok):
            errors.append("ready_for_dry_run_patch requires machine editor/red-team approval fields")

    if packet.get("human_in_loop_dependency_added") is not False:
        errors.append("human_in_loop_dependency_added must be false")
    if _has_human_dependency(packet):
        errors.append("human-review dependency terms are forbidden in Run 43 packets")
    if packet.get("docs_book_update_applied") is True:
        errors.append("docs_book_update_applied must not be true in Run 43")
    if packet.get("publication_deployed") is True:
        errors.append("publication_deployed must not be true in Run 43")
    if packet.get("raw_text_publication_allowed") is not False:
        errors.append("raw_text_publication_allowed must be false")

    evidence_refs = set(str(x) for x in packet.get("evidence_refs") or [])
    citation_map = packet.get("citation_map") if isinstance(packet.get("citation_map"), dict) else {}
    missing_citations = sorted(ref for ref in evidence_refs if ref not in citation_map)
    if missing_citations:
        errors.append(f"evidence_refs missing citation_map entries: {missing_citations}")
    for idx, claim in enumerate(packet.get("claim_map") if isinstance(packet.get("claim_map"), list) else []):
        if not isinstance(claim, dict):
            errors.append(f"claim_map[{idx}] must be object")
            continue
        refs = claim.get("evidence_refs")
        if not _is_nonempty_list(refs):
            errors.append(f"claim_map[{idx}] missing evidence_refs")
        elif not set(str(x) for x in refs).issubset(evidence_refs):
            errors.append(f"claim_map[{idx}] references evidence outside evidence_refs")
        bad = _positive_forbidden_claim(str(claim.get("claim") or ""))
        if bad:
            errors.append(f"unsupported forbidden positive claim in claim_map[{idx}]: {bad}")
    bad_delta = _positive_forbidden_claim(str(packet.get("proposed_markdown_delta") or ""))
    if bad_delta:
        errors.append(f"unsupported forbidden positive claim in proposed_markdown_delta: {bad_delta}")
    return errors


def validate_packet_document(data: Any) -> list[str]:
    packets = data.get("publish_packets") if isinstance(data, dict) else data
    if not isinstance(packets, list):
        return ["publish packet document must contain publish_packets list or be a list"]
    errors: list[str] = []
    for idx, packet in enumerate(packets):
        for err in validate_publish_packet(packet):
            errors.append(f"publish_packets[{idx}]: {err}")
    return errors


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Validate Run 43 publish packets")
    ap.add_argument("path")
    args = ap.parse_args(argv)
    errors = validate_packet_document(load_json(Path(args.path)))
    if errors:
        print(json.dumps({"ok": False, "errors": errors}, indent=2), file=sys.stderr)
        return 2
    print(json.dumps({"ok": True, "errors": []}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
