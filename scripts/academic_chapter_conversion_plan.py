#!/usr/bin/env python3
"""Report-only academic chapter conversion plan from Run 49 inventory."""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SAFETY_FLAGS = {
    "author_allowed": False,
    "publication_approved": False,
    "eligible_for_claim_insertion": False,
    "eligible_for_authoring": False,
    "eligible_for_publication": False,
    "chapter_update_allowed": False,
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def resolve(path: str | Path) -> Path:
    p = Path(path)
    return p if p.is_absolute() else ROOT / p


def fail_plan(run_id: str, errors: list[str]) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "title": "Academic manuscript inventory and chapter conversion plan",
        "generated_at": utc_now(),
        "disposition": "academic_inventory_failed_closed",
        "errors": errors,
        "safety_flags": dict(SAFETY_FLAGS),
        "docs_book_modified": False,
        "do_not_rewrite_yet": True,
    }


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def build_conversion_plan(
    inventory: str | Path,
    quality_contract: str | Path,
    structure_plan: str | Path,
    run_id: str = "run49",
) -> dict[str, Any]:
    inv_path = resolve(inventory)
    contract_path = resolve(quality_contract)
    structure_path = resolve(structure_plan)
    errors = []
    for label, path in [("inventory", inv_path), ("academic quality contract", contract_path), ("academic structure plan", structure_path)]:
        if not path.exists():
            errors.append(f"{label} missing")
    if errors:
        return fail_plan(run_id, errors)
    try:
        inv = load_json(inv_path)
        load_json(contract_path)
        structure_text = structure_path.read_text(encoding="utf-8")
    except Exception as exc:
        return fail_plan(run_id, [f"input invalid:{exc}"])
    pages = inv.get("pages", [])
    if not isinstance(pages, list):
        return fail_plan(run_id, ["inventory pages invalid"])

    by_role: dict[str, list[str]] = defaultdict(list)
    pages_to_keep: list[str] = []
    pages_to_split: list[str] = []
    pages_to_merge: list[str] = []
    pages_to_appendix: list[str] = []
    pages_to_reports: list[str] = []
    mapping: list[dict[str, Any]] = []
    priority = []

    for p in pages:
        path = p.get("path", "unknown")
        role = p.get("recommended_academic_role", "reports_only")
        by_role[role].append(path)
        if p.get("reports_only_recommended"):
            pages_to_reports.append(path)
        elif p.get("appendix_only_recommended") or role in {"appendix", "research_agenda", "glossary", "bibliography"}:
            pages_to_appendix.append(path)
        else:
            pages_to_keep.append(path)
        if p.get("academic_maturity_level", 0) <= 2 and not p.get("reports_only_recommended"):
            pages_to_split.append(path)
        if role in {"core_concept_chapter", "conceptual_framework"}:
            pages_to_merge.append(path)
        priority.append({
            "path": path,
            "priority": p.get("rewrite_priority", 5),
            "title": p.get("title"),
            "recommended_academic_role": role,
            "recommended_next_action": p.get("recommended_next_action"),
        })
        mapping.append({
            "source_page": path,
            "current_role": p.get("apparent_current_role"),
            "future_role": role,
            "future_location": "reports_only" if p.get("reports_only_recommended") else ("appendix" if p.get("appendix_only_recommended") else "main_manuscript_candidate"),
            "rewrite_priority": p.get("rewrite_priority"),
            "safe_handling": p.get("safe_handling"),
        })

    roles_present = set(by_role)
    missing_front_matter = [x for x in ["introduction"] if x not in roles_present]
    missing_methodology = [] if "methodology" in roles_present else ["methodology"]
    missing_literature = [] if "literature_and_context" in roles_present else ["literature_and_context"]
    missing_conceptual = [] if "conceptual_framework" in roles_present else ["conceptual_framework"]
    missing_glossary = [] if ("glossary" in roles_present or "bibliography" in roles_present) else ["glossary", "bibliography"]
    missing_chapters = missing_front_matter + missing_methodology + missing_literature + missing_conceptual + missing_glossary

    future_structure = [
        "Front matter: Preface and reader guide",
        "Introduction: thesis, scope, contribution, limitations",
        "Literature and context: agent-loop and tool-ecosystem background",
        "Conceptual framework: definitions, taxonomy, and model of closed-loop agents",
        "Methodology: evidence collection, source quality, and validation approach",
        "Core chapters: agent loop, Hermes, OpenClaw, Loop Engineering, memory/context architecture, operating loops",
        "Governance and safety chapter: publication gates, mutation guards, and no-fallback controls",
        "Appendices: evidence/source inventories, open questions, glossary, bibliography",
    ]
    priority_sorted = sorted(priority, key=lambda x: (x["priority"], x["path"]))
    plan = {
        "run_id": run_id,
        "title": "Academic manuscript inventory and chapter conversion plan",
        "generated_at": utc_now(),
        "disposition": "rewrite_plan_created",
        "machine_dispositions": ["rewrite_plan_created", "safe_reports_only"],
        "inventory": str(inv_path),
        "quality_contract": str(contract_path),
        "structure_plan": str(structure_path),
        "structure_plan_loaded": bool(structure_text.strip()),
        "recommended_future_book_structure": future_structure,
        "page_to_future_mapping": mapping,
        "pages_to_keep": sorted(set(pages_to_keep)),
        "pages_to_split": sorted(set(pages_to_split)),
        "pages_to_merge": sorted(set(pages_to_merge)),
        "pages_to_move_to_appendix": sorted(set(pages_to_appendix)),
        "pages_to_keep_as_reports_only": sorted(set(pages_to_reports)),
        "missing_chapters": missing_chapters,
        "missing_front_matter": missing_front_matter,
        "missing_methodology_section": missing_methodology,
        "missing_literature_context_section": missing_literature,
        "missing_conceptual_framework": missing_conceptual,
        "missing_glossary_bibliography": missing_glossary,
        "rewrite_priority_sequence": priority_sorted,
        "candidate_run50_scope": "Draft Introduction, thesis, scope, contribution, and limitations as report-only manuscript prose.",
        "candidate_run51_scope": "Draft literature/context and conceptual framework as report-only manuscript prose.",
        "candidate_run52_scope": "Draft methodology and source-quality appendix as report-only manuscript prose.",
        "recommended_next_run": "Run 50 — Draft Introduction, thesis, scope, contribution, and limitations as report-only manuscript prose.",
        "do_not_rewrite_yet": True,
        "safety_note": "Do not rewrite docs/book in Run 49; this plan is report-only and not publication approval.",
        "safety_flags": dict(SAFETY_FLAGS),
        "docs_book_modified": False,
        "db_modified": False,
        "source_registry_modified": False,
        "raw_modified": False,
        "schema_modified": False,
        "daily_worker_modified": False,
    }
    return plan


def write_reports(plan: dict[str, Any], output_json: str | Path, output_md: str | Path) -> None:
    outj = resolve(output_json)
    outm = resolve(output_md)
    outj.parent.mkdir(parents=True, exist_ok=True)
    outm.parent.mkdir(parents=True, exist_ok=True)
    outj.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = [
        "# Run 49 chapter conversion plan",
        "",
        f"- disposition: `{plan.get('disposition')}`",
        f"- do_not_rewrite_yet: `{plan.get('do_not_rewrite_yet')}`",
        f"- docs/book modified: `{plan.get('docs_book_modified')}`",
        f"- recommended next run: {plan.get('recommended_next_run')}",
        "",
        "## Recommended future book structure",
        "",
        *[f"- {x}" for x in plan.get("recommended_future_book_structure", [])],
        "",
        "## Page mapping",
        "",
    ]
    for m in plan.get("page_to_future_mapping", []):
        lines.extend([
            f"- `{m['source_page']}` → `{m['future_role']}` / `{m['future_location']}` / priority `{m['rewrite_priority']}`",
        ])
    lines.extend([
        "",
        "## Rewrite priority sequence",
        "",
    ])
    for item in plan.get("rewrite_priority_sequence", []):
        lines.append(f"- priority `{item['priority']}` — `{item['path']}`: {item.get('recommended_next_action')}")
    lines.extend([
        "",
        "## Missing sections",
        "",
        f"- missing front matter: `{plan.get('missing_front_matter')}`",
        f"- missing methodology: `{plan.get('missing_methodology_section')}`",
        f"- missing literature/context: `{plan.get('missing_literature_context_section')}`",
        f"- missing conceptual framework: `{plan.get('missing_conceptual_framework')}`",
        f"- missing glossary/bibliography: `{plan.get('missing_glossary_bibliography')}`",
        "",
        "## Safety note",
        "",
        str(plan.get("safety_note")),
    ])
    outm.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Report-only academic chapter conversion plan")
    ap.add_argument("--inventory", required=True)
    ap.add_argument("--quality-contract", required=True)
    ap.add_argument("--structure-plan", required=True)
    ap.add_argument("--output-json", required=True)
    ap.add_argument("--output-md", required=True)
    ap.add_argument("--run-id", default="run49")
    args = ap.parse_args(argv)
    plan = build_conversion_plan(args.inventory, args.quality_contract, args.structure_plan, args.run_id)
    write_reports(plan, args.output_json, args.output_md)
    print(json.dumps({"ok": plan["disposition"] == "rewrite_plan_created", "output_json": str(resolve(args.output_json))}, sort_keys=True))
    return 0 if plan["disposition"] == "rewrite_plan_created" else 2


if __name__ == "__main__":
    raise SystemExit(main())
