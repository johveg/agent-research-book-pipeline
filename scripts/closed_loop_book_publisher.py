#!/usr/bin/env python3
"""Run 44 guarded docs/book publisher.

Applies at most one machine-gated publish packet to docs/book, or a clearly
labeled rolling daily no-safe-promotions status page. This script never commits,
pushes, writes raw captures, mutates SQLite, or changes source registry/schema.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from closed_loop_publish_packet_validator import validate_publish_packet  # noqa: E402

ALLOWED_SUBSTANTIVE_DISPOSITIONS = {"publish_packet_machine_approved", "caveat_only_publish_packet"}
BLOCKED_DISPOSITIONS = {
    "safe_reports_only",
    "publish_daily_no_safe_promotions",
    "publish_packet_blocked",
    "needs_more_sources",
    "contradiction_review_required",
    "quarantine",
}
FORBIDDEN_DEPENDENCY_TERMS = [
    "human_" + "review_required",
    "requires_" + "human_review",
    "manual_" + "approval_required",
    "editor_" + "must_review",
]
RAW_LEAKAGE_PATTERNS = [
    re.compile(r"RAW_CAPTURE", re.I),
    re.compile(r"BEGIN RAW", re.I),
    re.compile(r"raw_text_publication_allowed\s*[:=]\s*true", re.I),
    re.compile(r"-----BEGIN (?:RSA |OPENSSH |DSA |EC )?PRIVATE KEY-----"),
]
SUBSTANTIVE_UPDATE_TYPES = {"existing_chapter_delta", "substantive_chapter_delta", "caveated_note", "guarded_substantive_canary", "substantive_canary_caveated", "caveated_substantive_canary"}
DAILY_STATUS_FILE = "daily-pipeline-status.md"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def resolve_repo_path(path: str | Path) -> Path:
    p = Path(path)
    return p if p.is_absolute() else ROOT / p


def rel(path: str | Path) -> str:
    p = Path(path)
    try:
        return str(p.resolve().relative_to(ROOT))
    except Exception:
        return str(p)


def load_json(path: str | Path) -> Any:
    return json.loads(resolve_repo_path(path).read_text(encoding="utf-8"))


def write_json(path: str | Path, obj: Any) -> None:
    out = resolve_repo_path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def markdown_report(title: str, report: dict[str, Any]) -> str:
    lines = [f"# {title}", "", f"Generated: {report.get('generated_at')}", ""]
    for key in [
        "run_id",
        "publication_status",
        "publication_decision",
        "publication_applied",
        "docs_book_update_applied",
        "daily_status_fallback_applied",
        "publish_packet_count",
        "selected_packet_count",
        "target_file",
    ]:
        if key in report:
            lines.append(f"- {key}: `{report.get(key)}`")
    if report.get("changed_files"):
        lines += ["", "## Changed files", ""] + [f"- `{x}`" for x in report["changed_files"]]
    if report.get("failed_checks"):
        lines += ["", "## Failed checks", ""] + [f"- `{x}`" for x in report["failed_checks"]]
    if report.get("rejected_packets"):
        lines += ["", "## Rejected packets", ""]
        for item in report["rejected_packets"]:
            lines.append(f"- `{item.get('publish_packet_id')}`: {item.get('reason')}")
    return "\n".join(lines) + "\n"


def write_markdown(path: str | Path, title: str, report: dict[str, Any]) -> None:
    out = resolve_repo_path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(markdown_report(title, report), encoding="utf-8")


def extract_packets(doc: Any) -> list[dict[str, Any]]:
    if isinstance(doc, list):
        return [x for x in doc if isinstance(x, dict)]
    if isinstance(doc, dict):
        packets = doc.get("publish_packets") or doc.get("packets") or []
        return [x for x in packets if isinstance(x, dict)]
    return []


def text_blob(packet: dict[str, Any]) -> str:
    return json.dumps(packet, sort_keys=True, default=str, ensure_ascii=False)


def target_path_for(packet: dict[str, Any], docs_root: Path) -> Path | None:
    suggestion = str(packet.get("target_file_suggestion") or packet.get("target_file") or "")
    if not suggestion:
        return None
    suggestion = suggestion.strip()
    if suggestion.startswith("docs/book/"):
        rel_part = suggestion[len("docs/book/"):]
    elif suggestion.startswith("book/"):
        rel_part = suggestion[len("book/"):]
    elif suggestion.endswith(".md") and "/" not in suggestion:
        rel_part = suggestion
    else:
        return None
    if ".." in Path(rel_part).parts:
        return None
    target = docs_root / rel_part
    try:
        target.resolve().relative_to(docs_root.resolve())
    except Exception:
        return None
    return target


def packet_rejection_reason(packet: dict[str, Any], docs_root: Path) -> str:
    validator_errors = validate_publish_packet(packet)
    if validator_errors:
        return "validator:" + "; ".join(validator_errors[:3])
    blob = text_blob(packet).lower()
    if any(term in blob for term in FORBIDDEN_DEPENDENCY_TERMS):
        return "human-review dependency"
    if any(p.search(text_blob(packet)) for p in RAW_LEAKAGE_PATTERNS):
        return "raw_text_leakage_marker"
    if not packet.get("evidence_refs"):
        return "missing_evidence_refs"
    if not packet.get("citation_map"):
        return "missing_citation_map"
    if not packet.get("claim_map"):
        return "unsupported_claims"
    disposition = str(packet.get("disposition") or "")
    if disposition in BLOCKED_DISPOSITIONS:
        return "blocked_disposition"
    if disposition not in ALLOWED_SUBSTANTIVE_DISPOSITIONS:
        return "unsupported_disposition"
    if str(packet.get("update_type") or "") in {"no_publication", "safe_reports_only"}:
        return "no_publication_update"
    readiness = packet.get("publication_readiness") if isinstance(packet.get("publication_readiness"), dict) else {}
    if not (readiness.get("ready_for_guarded_publication") is True or readiness.get("ready_for_dry_run_patch") is True):
        return "not_ready_for_publication"
    if readiness.get("blocked") is True:
        return "readiness_blocked"
    if not isinstance(packet.get("redteam_findings"), dict) or packet["redteam_findings"].get("approved") is not True:
        return "redteam_not_approved"
    if not isinstance(packet.get("machine_editor_findings"), dict) or packet["machine_editor_findings"].get("approved") is not True:
        return "machine_editor_not_approved"
    target = target_path_for(packet, docs_root)
    if target is None:
        return "invalid_target_file"
    return ""


def select_publishable_packets(packets: list[dict[str, Any]], max_packets: int, docs_root: str | Path | None = None) -> dict[str, Any]:
    root = Path(docs_root) if docs_root is not None else ROOT / "docs" / "book"
    selected: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for packet in packets:
        reason = packet_rejection_reason(packet, root)
        if reason:
            rejected.append({"publish_packet_id": packet.get("publish_packet_id", ""), "reason": reason})
            continue
        if len(selected) < max_packets:
            selected.append(packet)
        else:
            rejected.append({"publish_packet_id": packet.get("publish_packet_id", ""), "reason": "max_packets_exceeded"})
    return {"selected": selected, "rejected": rejected}


def append_delta(target: Path, packet: dict[str, Any], run_id: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    existing = target.read_text(encoding="utf-8") if target.exists() else ""
    marker = f"<!-- run44-packet:{packet.get('idempotency_key') or packet.get('publish_packet_id')} -->"
    if marker in existing:
        return
    delta = str(packet.get("proposed_markdown_delta") or "").strip()
    citations = packet.get("citation_map") or {}
    caveats = packet.get("required_caveats") or []
    block = ["", marker, "", delta, "", f"*Run: `{run_id}`. Machine disposition: `{packet.get('disposition')}`.*"]
    if caveats:
        block += ["", "Caveats:"] + [f"- {c}" for c in caveats]
    if citations:
        block += ["", "Evidence references:"]
        block.append("- Safe internal packet report: `reports/editorial/citation-pipeline-test-20260612-publish-packets-run44.json`")
        block.append("- Guarded publication report: `reports/editorial/citation-pipeline-test-20260612-guarded-book-publication-run44.json`")
        block.append("- Citation details are retained in internal reports; raw claim/source identifiers are not published on this page.")
    block.append("")
    target.write_text(existing.rstrip() + "\n" + "\n".join(block), encoding="utf-8")


def publish_packets(packets: list[dict[str, Any]], docs_root: str | Path, apply: bool, max_packets: int, run_id: str) -> dict[str, Any]:
    docs = Path(docs_root)
    selection = select_publishable_packets(packets, max_packets=max_packets, docs_root=docs)
    failed_checks: list[str] = []
    if len(selection["selected"]) > max_packets:
        failed_checks.append("max_packets_exceeded")
    if sum(1 for p in packets if not packet_rejection_reason(p, docs)) > max_packets:
        failed_checks.append("max_packets_exceeded")
    changed: list[str] = []
    applied = False
    if not failed_checks and apply and selection["selected"]:
        for packet in selection["selected"]:
            target = target_path_for(packet, docs)
            if target is None:
                failed_checks.append("invalid_target_file")
                continue
            before = target.read_bytes() if target.exists() else b""
            append_delta(target, packet, run_id)
            after = target.read_bytes() if target.exists() else b""
            if before != after:
                changed.append("docs/book/" + str(target.relative_to(docs)))
                applied = True
    elif selection["selected"] and not apply:
        changed = []
    return {
        "mode": "closed_loop_book_publisher",
        "run_id": run_id,
        "generated_at": utc_now(),
        "publication_status": "substantive_publication_applied" if applied else ("substantive_publication_ready" if selection["selected"] else "no_substantive_publication"),
        "publication_decision": "substantive_canary_applied" if applied else ("substantive_canary_ready" if selection["selected"] else "no_safe_substantive_packet"),
        "publication_applied": applied,
        "docs_book_update_applied": applied,
        "publication_deployed": False,
        "daily_status_fallback_applied": False,
        "publish_packet_count": len(packets),
        "selected_packet_count": len(selection["selected"]),
        "selected_packets": [p.get("publish_packet_id") for p in selection["selected"]],
        "rejected_packets": selection["rejected"],
        "target_file": changed[0] if changed else (str(selection["selected"][0].get("target_file_suggestion")) if selection["selected"] else ""),
        "changed_files": changed,
        "failed_checks": sorted(set(failed_checks)),
        "safety_flags": {"raw_text_publication_allowed": False, "human_in_loop_dependency_added": False, "publication_deployed": False},
    }


def apply_daily_status(docs_root: str | Path, run_id: str, packets_considered: int, reason: str, apply: bool, disposition: str = "publish_daily_no_safe_promotions") -> dict[str, Any]:
    docs = Path(docs_root)
    target = docs / DAILY_STATUS_FILE
    timestamp = utc_now()
    entry = [
        "# Daily pipeline status",
        "",
        "This rolling page records machine-gated daily publication outcomes. It is pipeline status, not narrative evidence.",
        "",
        "## Latest status",
        "",
        f"- Date/time: `{timestamp}`",
        f"- Run id: `{run_id}`",
        f"- Machine disposition: `{disposition}`",
        f"- Packets considered: `{packets_considered}`",
        f"- Reason: {reason}",
        "- Unsupported or caveated material was blocked by machine gates.",
        "- No raw material is published on this page.",
        "- Safe internal reports: `reports/editorial/` and `reports/telegram/run44-status.md`.",
        "",
    ]
    before = target.read_bytes() if target.exists() else b""
    if apply:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("\n".join(entry), encoding="utf-8")
    after = target.read_bytes() if target.exists() else b""
    changed = apply and before != after
    return {
        "mode": "closed_loop_book_publisher",
        "run_id": run_id,
        "generated_at": timestamp,
        "publication_status": "daily_no_safe_promotions_status_applied" if changed else "daily_no_safe_promotions_status_ready",
        "publication_decision": "daily_no_safe_promotions_applied" if changed else "daily_no_safe_promotions_ready",
        "publication_applied": bool(changed),
        "docs_book_update_applied": bool(changed),
        "publication_deployed": False,
        "daily_status_fallback_applied": bool(changed),
        "publish_packet_count": packets_considered,
        "selected_packet_count": 0,
        "target_file": "docs/book/" + DAILY_STATUS_FILE,
        "changed_files": ["docs/book/" + DAILY_STATUS_FILE] if changed else [],
        "failed_checks": [],
        "reason": reason,
        "safety_flags": {"raw_text_publication_allowed": False, "human_in_loop_dependency_added": False, "publication_deployed": False},
    }


def run(args: argparse.Namespace) -> int:
    packets = extract_packets(load_json(args.publish_packets))
    if args.daily_status_fallback:
        report = apply_daily_status(args.docs_root, args.run_id, len(packets), args.daily_status_reason, args.apply)
    else:
        report = publish_packets(packets, args.docs_root, args.apply, args.max_packets, args.run_id)
    if args.output_json:
        write_json(args.output_json, report)
    if args.output_md:
        write_markdown(args.output_md, "Run 44 guarded book publication", report)
    print(json.dumps({"ok": not report.get("failed_checks"), "publication_applied": report.get("publication_applied"), "publication_decision": report.get("publication_decision")}, sort_keys=True))
    return 0 if not report.get("failed_checks") else 2


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Run 44 guarded docs/book publisher")
    ap.add_argument("--publish-packets", required=True)
    ap.add_argument("--docs-root", default=str(ROOT / "docs" / "book"))
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    ap.add_argument("--daily-status-fallback", action="store_true")
    ap.add_argument("--daily-status-reason", default="No substantive packet passed machine gates.")
    ap.add_argument("--max-packets", type=int, default=1)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--output-json")
    ap.add_argument("--output-md")
    try:
        return run(ap.parse_args(argv))
    except Exception as exc:
        print(f"failed_closed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
