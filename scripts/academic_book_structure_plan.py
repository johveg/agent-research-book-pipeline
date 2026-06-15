#!/usr/bin/env python3
"""Report-only academic book structure plan for Run 48."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_JSON = ROOT / "reports" / "editorial" / "run48-academic-book-structure-plan-run48.json"
DEFAULT_MD = ROOT / "reports" / "editorial" / "run48-academic-book-structure-plan-run48.md"
DEFAULT_STRUCTURE_PLAN_MD = ROOT / "book" / "academic_structure_plan.md"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def resolve(path: str | Path) -> Path:
    p = Path(path)
    return p if p.is_absolute() else ROOT / p


def build_plan(run_id: str) -> dict[str, Any]:
    sections = [
        {"part": "Front matter", "chapters": ["Title page", "Preface", "Reader guide", "Contribution summary"]},
        {"part": "Part I Foundations", "chapters": ["Introduction", "Literature and Context", "Conceptual Framework", "Methodology"]},
        {"part": "Part II Core Concepts", "chapters": ["Closed-loop production", "Evidence boundaries", "Machine review and safety gates", "Academic prose quality contract"]},
        {"part": "Part III Tools and Case Material", "chapters": ["Hermes as automation infrastructure", "OpenClaw case material", "Terefo Heal Reboa pipeline case", "Tooling patterns and limits"]},
        {"part": "Part IV Production Operations", "chapters": ["Daily operation model", "Publication validation", "Monitoring and rollback", "Operational caveats"]},
        {"part": "Back Matter", "chapters": ["Glossary", "Source-quality schema", "Claim-status schema", "Bibliography", "Appendix: evidence ledger and internal reports"]},
    ]
    return {
        "mode": "academic_book_structure_plan",
        "run_id": run_id,
        "generated_at": utc_now(),
        "report_only": True,
        "docs_book_restructured": False,
        "docs_book_modified": False,
        "db_modified": False,
        "source_registry_modified": False,
        "raw_modified": False,
        "schema_modified": False,
        "daily_worker_modified": False,
        "gpt55_used": False,
        "reasoning_status": "deterministic_structure_plan",
        "strategic_goal": "Separate public academic/professional prose from operational evidence ledgers and workflow/status pages.",
        "recommended_structure": sections,
        "migration_principles": [
            "Move claim/source ledger material out of chapter prose and into appendices or internal reports.",
            "Give the book a clear thesis, contribution, methodology, literature/context chapter, and conceptual framework before expanding case chapters.",
            "Use evidence as cited support for sustained paragraphs, not as raw status bullets.",
            "Keep machine/editor workflow notes out of reader-facing pages.",
            "Do not restructure docs/book until a later explicitly tested restructuring run.",
        ],
        "recommended_next_run": "Run a report-only manuscript inventory that classifies existing docs/book pages against this structure before any rewrite.",
    }


def write_json(path: str | Path, obj: Any) -> None:
    out = resolve(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def markdown(plan: dict[str, Any]) -> str:
    lines = ["# Academic book structure plan", "", f"Generated: {plan['generated_at']}", "", f"- run_id: `{plan['run_id']}`", "- report_only: `True`", "- docs_book_restructured: `False`", ""]
    lines += ["## Recommended future structure", ""]
    for part in plan["recommended_structure"]:
        lines.append(f"### {part['part']}")
        lines.append("")
        for chapter in part["chapters"]:
            lines.append(f"- {chapter}")
        lines.append("")
    lines += ["## Migration principles", ""] + [f"- {x}" for x in plan["migration_principles"]]
    lines += ["", "## Recommendation", "", plan["recommended_next_run"], ""]
    return "\n".join(lines)


def write_md(path: str | Path, plan: dict[str, Any]) -> None:
    out = resolve(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(markdown(plan), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Write report-only academic book structure plan")
    ap.add_argument("--run-id", default="run48")
    ap.add_argument("--output-json", default=str(DEFAULT_JSON))
    ap.add_argument("--output-md", default=str(DEFAULT_MD))
    ap.add_argument("--structure-plan-md", default=str(DEFAULT_STRUCTURE_PLAN_MD))
    args = ap.parse_args(argv)
    plan = build_plan(args.run_id)
    write_json(args.output_json, plan)
    write_md(args.output_md, plan)
    write_md(args.structure_plan_md, plan)
    print(json.dumps({"ok": True, "output_json": str(resolve(args.output_json)), "docs_book_restructured": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
