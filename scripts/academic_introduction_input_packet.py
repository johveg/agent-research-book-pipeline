#!/usr/bin/env python3
"""Build a report-only input packet for Run 50 introduction drafting."""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
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
PROTECTED_WRITES = ["docs/book", ".var/book.sqlite", "data/source_registry.json", "raw", "docs/entities", "docs/research/claims.md", "data/schema.sql", "scripts/daily_book_worker.py"]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def resolve(path: str | Path) -> Path:
    p = Path(path)
    return p if p.is_absolute() else ROOT / p


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def fail_report(errors: list[str]) -> dict[str, Any]:
    return {
        "ok": False,
        "run_id": "run50",
        "title": "Introduction input packet",
        "generated_at": utc_now(),
        "disposition": "introduction_draft_failed_closed",
        "errors": errors,
        "report_only": True,
        "protected_writes_allowed": False,
        "protected_write_targets_forbidden": PROTECTED_WRITES,
        "publication_safety_flags": dict(FALSE_FLAGS),
        "safety_flags": dict(FALSE_FLAGS),
    }


def page_excerpt(path: Path, limit: int = 1200) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    title = path.stem
    for line in text.splitlines():
        if line.startswith("#"):
            title = line.lstrip("# ").strip() or title
            break
    cleaned = re.sub(r"\s+", " ", text).strip()
    return {"path": str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path), "title": title, "word_count": len(re.findall(r"\b\w+\b", text)), "bounded_excerpt": cleaned[:limit]}


def build_packet(quality_contract: str | Path, structure_plan: str | Path, inventory: str | Path, conversion_plan: str | Path, book_dir: str | Path) -> dict[str, Any]:
    paths = {
        "quality_contract": resolve(quality_contract),
        "structure_plan": resolve(structure_plan),
        "inventory": resolve(inventory),
        "conversion_plan": resolve(conversion_plan),
        "book_dir": resolve(book_dir),
    }
    missing = [name for name, path in paths.items() if not path.exists()]
    if missing:
        return fail_report([f"missing_input:{name}" for name in missing])
    if not paths["book_dir"].is_dir():
        return fail_report(["book_dir_not_directory"])
    try:
        contract = read_json(paths["quality_contract"])
        inv = read_json(paths["inventory"])
        plan = read_json(paths["conversion_plan"])
        structure = paths["structure_plan"].read_text(encoding="utf-8")
    except Exception as exc:
        return fail_report([f"input_parse_failed:{type(exc).__name__}:{exc}"])

    pages = inv.get("pages", []) if isinstance(inv, dict) else []
    page_counts = Counter(str(p.get("recommended_academic_role") or "unknown") for p in pages if isinstance(p, dict))
    gaps = {
        "literature_gaps_that_must_be_acknowledged": [p.get("path") for p in pages if isinstance(p, dict) and p.get("missing_literature_support")],
        "methodology_gaps_that_must_be_acknowledged": [p.get("path") for p in pages if isinstance(p, dict) and p.get("missing_methodology_support")],
        "conceptual_framework_gaps_that_must_be_acknowledged": [p.get("path") for p in pages if isinstance(p, dict) and p.get("missing_conceptual_framework")],
    }
    book_pages = [page_excerpt(p) for p in sorted(paths["book_dir"].glob("*.md"))]
    priority = plan.get("rewrite_priority_sequence", []) if isinstance(plan, dict) else []
    priority_paths = [x.get("path") for x in priority if isinstance(x, dict) and x.get("path")]

    packet = {
        "ok": True,
        "run_id": "run50",
        "title": "Introduction input packet",
        "generated_at": utc_now(),
        "disposition": "report_only_manuscript_draft",
        "proposed_working_title": "Engineering Governable Agent Loops: A Professional and Academic Inquiry",
        "proposed_audience": ["software and platform engineers", "technical leaders", "AI governance practitioners", "researchers studying agentic software practice"],
        "proposed_thesis_candidates": [
            "Agent loops should be treated as governable engineering systems rather than as isolated prompts or informal automation tricks.",
            "Loop engineering is best handled as an emerging practitioner label for a set of observable design, operations, and governance problems, not as a settled field.",
        ],
        "proposed_contribution_candidates": [
            "A cautious vocabulary for discussing agent loops across engineering, operations, governance, and case-study evidence.",
            "A structured path for separating practitioner observations, local case material, open questions, and supported claims before public chapter publication.",
        ],
        "scope_statement_candidates": [
            "The introduction should frame agent loops, loop engineering, and related tool cases as a bounded professional inquiry based on the current manuscript inventory.",
            "The scope includes conceptual framing, methodology needs, case material, governance concerns, and limitations; it excludes unsupported field-wide adoption claims.",
        ],
        "exclusion_candidates": [
            "Loop engineering should be described as an emerging practitioner label or working concept rather than as a settled field.",
            "Do not claim that Hermes, OpenClaw, or any named tool has broad adoption, maturity, or strategic importance beyond the available evidence.",
            "Do not convert social or discovery signals into factual support.",
            "Do not invent citations, sources, survey findings, or field consensus.",
        ],
        "limitation_candidates": [
            "The current manuscript is stronger as practitioner observation and local case material than as literature-supported academic synthesis.",
            "Methodology, literature context, conceptual definitions, and bibliography support remain incomplete.",
            "Claims should remain bounded until evidence quality and source status are separately validated.",
        ],
        "evidence_use_policy_summary": "Use current docs/book pages, Run 49 inventory, and conversion plan as source context only. Distinguish established concepts, practitioner observations, local case material, open questions, and unsupported or emerging terminology. Do not invent citations or settle unsupported claims.",
        "terminology_needing_definition": ["agent loop", "loop engineering", "governable engineering system", "practitioner observation", "local case material", "supported claim"],
        "key_chapters_referenced_by_introduction": priority_paths[:8],
        "source_evidence_limitations_from_current_manuscript": gaps,
        **gaps,
        "do_not_say_list": ["conclusive proof language", "loop engineering as a settled discipline", "broad industry adoption language", "Hermes/OpenClaw maturity overclaims", "social posts as factual support"],
        "citation_evidence_constraints": ["No invented citation markers", "No claim IDs/source IDs in main prose", "No evidence-status labels in main prose", "No field-consensus claims without literature support"],
        "academic_quality_requirements": contract.get("minimum_requirements_for_academic_chapter_prose", []),
        "required_academic_apparatus": contract.get("required_academic_apparatus", []),
        "structure_plan_excerpt": structure[:4000],
        "run49_page_role_counts": dict(sorted(page_counts.items())),
        "book_context_pages": book_pages,
        "report_only": True,
        "protected_writes_allowed": False,
        "protected_write_targets_forbidden": PROTECTED_WRITES,
        "publication_safety_flags": dict(FALSE_FLAGS),
        "safety_flags": dict(FALSE_FLAGS),
    }
    return packet


def validate_packet(packet: dict[str, Any]) -> None:
    if packet.get("publication_safety_flags") != FALSE_FLAGS or packet.get("safety_flags") != FALSE_FLAGS:
        raise ValueError("hard safety flags not preserved")
    if packet.get("protected_writes_allowed") is not False:
        raise ValueError("protected writes must remain forbidden")
    text = json.dumps(packet).lower()
    for phrase in ["this book proves", "established discipline", "broad industry adoption is clear"]:
        if phrase in text and phrase not in " ".join(packet.get("do_not_say_list", [])).lower():
            raise ValueError(f"unsupported_high_confidence_language:{phrase}")


def write_reports(packet: dict[str, Any], output_json: str | Path, output_md: str | Path) -> None:
    outj, outm = resolve(output_json), resolve(output_md)
    outj.parent.mkdir(parents=True, exist_ok=True)
    outm.parent.mkdir(parents=True, exist_ok=True)
    outj.write_text(json.dumps(packet, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    lines = ["# Run 50 introduction input packet", "", f"- ok: `{packet.get('ok')}`", f"- disposition: `{packet.get('disposition')}`", f"- working title: `{packet.get('proposed_working_title', '')}`", f"- report only: `{packet.get('report_only')}`", "", "## Thesis candidates", ""]
    for item in packet.get("proposed_thesis_candidates", []):
        lines.append(f"- {item}")
    lines += ["", "## Contribution candidates", ""]
    for item in packet.get("proposed_contribution_candidates", []):
        lines.append(f"- {item}")
    lines += ["", "## Safety", "", "All authoring/publication/claim insertion/chapter update flags remain false. Protected paths are not write targets.", ""]
    outm.write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quality-contract", default="config/academic_book_quality_contract.json")
    ap.add_argument("--structure-plan", default="book/academic_structure_plan.md")
    ap.add_argument("--inventory", default="reports/editorial/run49-academic-manuscript-inventory.json")
    ap.add_argument("--conversion-plan", default="reports/editorial/run49-chapter-conversion-plan.json")
    ap.add_argument("--book-dir", default="docs/book")
    ap.add_argument("--output-json", default="reports/editorial/run50-introduction-input-packet.json")
    ap.add_argument("--output-md", default="reports/editorial/run50-introduction-input-packet.md")
    args = ap.parse_args(argv)
    packet = build_packet(args.quality_contract, args.structure_plan, args.inventory, args.conversion_plan, args.book_dir)
    code = 0 if packet.get("ok") else 2
    try:
        if packet.get("ok"):
            validate_packet(packet)
    except Exception as exc:
        packet = fail_report([str(exc)])
        code = 2
    write_reports(packet, args.output_json, args.output_md)
    print(json.dumps({"ok": packet.get("ok"), "output_json": str(resolve(args.output_json)), "disposition": packet.get("disposition")}, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
