#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
FALSE_FLAGS = {
    "author_allowed": False,
    "publication_approved": False,
    "eligible_for_claim_insertion": False,
    "eligible_for_authoring": False,
    "eligible_for_publication": False,
    "chapter_update_allowed": False,
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def resolve(path: str | Path, root: Path = ROOT) -> Path:
    p = Path(path)
    return p if p.is_absolute() else root / p


def strip_internal_ids(text: str) -> str:
    text = re.sub(r"\b(?:claim|source|src|raw_capture|evidence)[_:][A-Za-z0-9_.:-]+\b", "", text, flags=re.I)
    return text


def build_packet(chapter_id: str, contract: dict[str, Any], inventory: dict[str, Any], structure_plan: str) -> dict[str, Any]:
    chapters = contract.get("chapters") if isinstance(contract, dict) else None
    if not isinstance(chapters, dict) or chapter_id not in chapters:
        return {"ok": False, "chapter_id": chapter_id, "disposition": "manuscript_packet_failed_closed", "failed_checks": ["unknown_chapter_id"], "publication_safety_flags": dict(FALSE_FLAGS), "safety_flags": dict(FALSE_FLAGS)}
    chapter = chapters[chapter_id]
    pages = inventory.get("pages", []) if isinstance(inventory, dict) else []
    context_pages = []
    for page in pages[:12]:
        if not isinstance(page, dict):
            continue
        context_pages.append({
            "path": page.get("path"),
            "title": page.get("title"),
            "recommended_role": page.get("recommended_academic_role"),
            "missing_methodology_support": bool(page.get("missing_methodology_support")),
            "missing_conceptual_framework": bool(page.get("missing_conceptual_framework")),
            "missing_literature_support": bool(page.get("missing_literature_support")),
        })
    packet = {
        "ok": True,
        "run_id": "run58",
        "chapter_id": chapter_id,
        "chapter_title": chapter.get("title", chapter_id.replace("_", " ").title()),
        "target_path": chapter.get("target_path"),
        "chapter_role": chapter.get("role"),
        "required_sections": chapter.get("required_sections", []),
        "created_at_utc": utc_now(),
        "disposition": "manuscript_input_packet_created",
        "draft_mode": "report_only_then_guarded_publish_canary",
        "central_thesis": "This book treats agent loops as governable engineering systems: not merely prompts, not autonomous magic, but bounded operational arrangements that require evidence, verification, memory, escalation, and publication discipline.",
        "audience": ["software engineers", "technical leaders", "AI governance practitioners", "researchers of agentic software practice"],
        "scope": "Introduce the book's argument, define why closed-loop agent production matters, describe the manuscript's evidence boundaries, and preview the chapter structure without claiming settled consensus.",
        "contribution": "A cautious academic/professional framing for turning practitioner evidence and local production loops into reader-facing prose through explicit quality gates.",
        "required_caveats": ["loop engineering remains emerging practitioner vocabulary", "local case material does not establish industry-wide adoption", "social or discovery signals are not confirmation", "the book separates evidence ledgers from public chapter prose"],
        "claims_not_made": ["prompt engineering is dead", "loop engineering is a settled discipline", "Hermes or OpenClaw has broad adoption", "the evidence proves industry consensus"],
        "forbidden_reader_facing_phrases": contract.get("forbidden_reader_facing_phrases", []),
        "structure_plan_excerpt": strip_internal_ids(structure_plan[:3500]),
        "inventory_context_pages": context_pages,
        "citation_policy": ["Use bracketed references only when references are supplied in the draft packet", "Do not invent external bibliographic claims", "Do not expose raw claim/source IDs"],
        "references": [
            {"token": "[1]", "reference": "Terefo Heal Reboa manuscript inventory and academic structure plan, internal reports, 2026."},
            {"token": "[2]", "reference": "Run 56 Agent Loop manuscript conversion canary and manuscript quality contract, internal reports, 2026."},
            {"token": "[3]", "reference": "Terefo closed-loop production, OPS routing, and publication-gate reports, internal evidence base, 2026."},
        ],
        "report_only": True,
        "publication_safety_flags": dict(FALSE_FLAGS),
        "safety_flags": dict(FALSE_FLAGS),
    }
    reader_text = json.dumps({
        "central_thesis": packet["central_thesis"],
        "scope": packet["scope"],
        "contribution": packet["contribution"],
        "structure_plan_excerpt": packet["structure_plan_excerpt"],
        "references": packet["references"],
    }, ensure_ascii=False).lower()
    for forbidden in ["claim_", "source_", "current evidence status", "source/claim mapping"]:
        if forbidden in reader_text:
            return {"ok": False, "chapter_id": chapter_id, "disposition": "manuscript_packet_failed_closed", "failed_checks": ["forbidden_internal_material:" + forbidden], "publication_safety_flags": dict(FALSE_FLAGS), "safety_flags": dict(FALSE_FLAGS)}
    return packet


def write_reports(packet: dict[str, Any], output_json: Path, output_md: Path) -> None:
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(packet, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    lines = ["# Run 58 manuscript input packet", "", f"- ok: `{packet.get('ok')}`", f"- chapter_id: `{packet.get('chapter_id')}`", f"- target_path: `{packet.get('target_path')}`", f"- disposition: `{packet.get('disposition')}`", "", "## Thesis", "", str(packet.get("central_thesis") or ""), "", "## Safety", "", "All publication and authoring flags remain false until publisher gates pass.", ""]
    output_md.write_text("\n".join(lines), encoding="utf-8")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--chapter-id", default="introduction")
    ap.add_argument("--contract", default="config/book_manuscript_production_contract.json")
    ap.add_argument("--inventory", default="reports/editorial/run49-academic-manuscript-inventory.json")
    ap.add_argument("--structure-plan", default="book/academic_structure_plan.md")
    ap.add_argument("--output-json", default="reports/manuscript/run58-introduction-input-packet.json")
    ap.add_argument("--output-md", default="reports/manuscript/run58-introduction-input-packet.md")
    args = ap.parse_args(argv)
    try:
        contract = json.loads(resolve(args.contract).read_text(encoding="utf-8"))
        inventory = json.loads(resolve(args.inventory).read_text(encoding="utf-8"))
        structure = resolve(args.structure_plan).read_text(encoding="utf-8")
        packet = build_packet(args.chapter_id, contract, inventory, structure)
    except Exception as exc:
        packet = {"ok": False, "chapter_id": args.chapter_id, "disposition": "manuscript_packet_failed_closed", "failed_checks": [type(exc).__name__], "error": str(exc), "publication_safety_flags": dict(FALSE_FLAGS), "safety_flags": dict(FALSE_FLAGS)}
    write_reports(packet, resolve(args.output_json), resolve(args.output_md))
    print(json.dumps({"ok": packet.get("ok"), "chapter_id": packet.get("chapter_id"), "target_path": packet.get("target_path"), "output_json": str(resolve(args.output_json))}, sort_keys=True))
    return 0 if packet.get("ok") else 2

if __name__ == "__main__":
    raise SystemExit(main())
