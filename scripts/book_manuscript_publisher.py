#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, re
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

FALSE_FLAGS = {
    "author_allowed": False,
    "publication_approved": False,
    "eligible_for_claim_insertion": False,
    "eligible_for_authoring": False,
    "eligible_for_publication": False,
    "chapter_update_allowed": False,
}
DEFAULT_CONFIGURED_TARGETS = {"docs/book/introduction.md", "docs/book/06-operating-loops.md"}
FORBIDDEN = ["Current evidence status", "Source/claim mapping", "Bullet 1 maps", "Editor notes", "Changelog", "Editorial policy", "status supported", "status weakly_supported", "quality A", "quality B", "claim record", "source tokens"]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def fail(checks: list[str], **extra) -> dict[str, Any]:
    return {"ok": False, "published": False, "run_id": "run58", "failed_checks": sorted(set(checks)), "generated_at_utc": utc_now(), "fallback_channel_used": False, **extra}


def _normal(path: str) -> str:
    return str(Path(path)).replace("\\", "/")


def _configured_targets(contract: dict[str, Any] | None) -> set[str]:
    if not contract:
        return set(DEFAULT_CONFIGURED_TARGETS)
    chapters = contract.get("chapters") if isinstance(contract.get("chapters"), dict) else {}
    targets = {
        _normal(str(spec.get("target_path")))
        for spec in chapters.values()
        if isinstance(spec, dict) and spec.get("target_path")
    }
    return targets | set(DEFAULT_CONFIGURED_TARGETS)


def _target_under_docs_book(target_path: str) -> bool:
    normalized = _normal(target_path)
    p = Path(normalized)
    return normalized.startswith("docs/book/") and normalized.endswith(".md") and ".." not in p.parts


def target_safe(target_path: str, packet: dict[str, Any] | None = None, contract: dict[str, Any] | None = None) -> bool:
    p = Path(target_path)
    normalized = _normal(target_path)
    if ".." in p.parts or not _target_under_docs_book(normalized):
        return False
    if packet and packet.get("queue_mode") == "automatic_guarded_new_chapter":
        return True
    return normalized in _configured_targets(contract)


def content_safe(text: str) -> list[str]:
    failed=[]
    body = text.split("## References", 1)[0]
    if any(x.lower() in body.lower() for x in FORBIDDEN):
        failed.append("forbidden_reader_facing_evidence_machinery")
    if re.search(r"\b(?:claim|source|src|raw_capture|evidence)[_:][A-Za-z0-9_.:-]+\b", text, re.I):
        failed.append("internal_id_exposed")
    if not re.search(r"\[\d+\]", text):
        failed.append("missing_integrated_citations")
    if "## References" not in text:
        failed.append("missing_references")
    if not re.search(r"limited|limitation|cautious|does not claim|not settled|not sufficient", text, re.I):
        failed.append("missing_limitations")
    bullets=[l for l in body.splitlines() if l.startswith("- ")]
    if len(bullets)>4:
        failed.append("bullet_heavy_public_body")
    return failed


def publish(*, root: Path, packet: dict[str, Any], draft_md: Path, quality_gate: dict[str, Any], evidence_gate: dict[str, Any], contract: dict[str, Any] | None = None) -> dict[str, Any]:
    failed=[]
    if packet.get("publication_safety_flags") != FALSE_FLAGS or packet.get("safety_flags") != FALSE_FLAGS:
        failed.append("invalid_packet_safety_flags")
    target = str(packet.get("target_path") or "")
    if not target_safe(target, packet=packet, contract=contract):
        failed.append("target_not_allowed_for_guarded_manuscript_workflow")
    if quality_gate.get("manuscript_quality_passed") is not True or quality_gate.get("publication_candidate") is not True or quality_gate.get("docs_book_update_allowed") is not True:
        failed.append("manuscript_quality_gate_failed")
    if evidence_gate.get("evidence_safety_passed") is not True or evidence_gate.get("publication_candidate") is not True:
        failed.append("evidence_safety_gate_failed")
    if not draft_md.exists():
        failed.append("draft_missing")
        text=""
    else:
        text=draft_md.read_text(encoding="utf-8")
        failed.extend(content_safe(text))
    if failed:
        return fail(failed, target_path=target)
    out = root / target
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text.rstrip()+"\n", encoding="utf-8")
    return {
        "ok": True,
        "published": True,
        "run_id": "run58",
        "chapter_id": packet.get("chapter_id"),
        "published_path": target,
        "docs_book_changed": True,
        "changed_paths": [target],
        "manuscript_quality_passed": True,
        "evidence_safety_passed": True,
        "publication_candidate": True,
        "chapter_canary_published": True,
        "fallback_channel_used": False,
        "weak_local_fallback_used": False,
        "generated_at_utc": utc_now(),
    }


def write_report(report: dict[str, Any], output_json: Path, output_md: Path) -> None:
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    lines=["# Run 58 guarded manuscript publisher", "", f"- ok: `{report.get('ok')}`", f"- published: `{report.get('published')}`", f"- path: `{report.get('published_path') or report.get('target_path')}`", f"- failed_checks: `{json.dumps(report.get('failed_checks', []))}`", ""]
    output_md.write_text("\n".join(lines), encoding="utf-8")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv=None) -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--packet-json", required=True)
    ap.add_argument("--draft-md", required=True)
    ap.add_argument("--quality-gate", required=True)
    ap.add_argument("--evidence-gate", required=True)
    ap.add_argument("--output-json", default="reports/editorial/run58-book-manuscript-publisher.json")
    ap.add_argument("--output-md", default="reports/editorial/run58-book-manuscript-publisher.md")
    ap.add_argument("--contract-json", default=None)
    args=ap.parse_args(argv)
    root=Path(args.root).resolve()
    contract = load_json(Path(args.contract_json)) if args.contract_json else None
    report=publish(root=root, packet=load_json(Path(args.packet_json)), draft_md=Path(args.draft_md), quality_gate=load_json(Path(args.quality_gate)), evidence_gate=load_json(Path(args.evidence_gate)), contract=contract)
    write_report(report, Path(args.output_json), Path(args.output_md))
    print(json.dumps({"ok": report.get("ok"), "published": report.get("published"), "path": report.get("published_path"), "failed_checks": report.get("failed_checks", [])}, sort_keys=True))
    return 0 if report.get("ok") else 2

if __name__ == "__main__":
    raise SystemExit(main())
