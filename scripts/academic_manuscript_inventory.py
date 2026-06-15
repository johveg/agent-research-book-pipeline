#!/usr/bin/env python3
"""Report-only academic manuscript inventory for docs/book.

Run 49: classify existing public book pages against the academic book quality
contract without mutating docs/book, DB, source registry, raw captures, schema,
or production workers.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections import Counter
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

APPARENT_ROLES = {
    "preface_or_reader_guide",
    "academic_chapter_candidate",
    "research_note",
    "evidence_stub",
    "claim_ledger_or_source_mapping",
    "methodology_or_process_note",
    "tool_profile",
    "case_study_material",
    "appendix_candidate",
    "open_questions_or_research_agenda",
    "glossary_or_reference_material",
    "unknown",
}
RECOMMENDED_ROLES = {
    "front_matter",
    "introduction",
    "literature_and_context",
    "conceptual_framework",
    "methodology",
    "core_concept_chapter",
    "tool_case_chapter",
    "local_case_study",
    "production_operations_chapter",
    "governance_safety_chapter",
    "research_agenda",
    "appendix",
    "glossary",
    "bibliography",
    "reports_only",
}
UPDATE_TYPES = {
    "academic_chapter_update",
    "methodology_update",
    "literature_context_update",
    "conceptual_framework_update",
    "case_study_update",
    "glossary_or_bibliography_update",
    "appendix_evidence_update",
    "evidence_stub",
    "claim_ledger_dump",
    "source_status_summary",
    "editor_workflow_note",
    "changelog_only_update",
    "social_signal_without_corroboration",
    "unsupported_field_claim",
}
MATURITY_LABELS = {
    0: "not book material / operational artifact",
    1: "evidence stub or claim/status page",
    2: "research note / scaffold",
    3: "practitioner guide draft",
    4: "academic/professional chapter draft",
    5: "publication-quality academic chapter",
}
FORBIDDEN_FALLBACK_ENV = [
    "TEREFO_ALLOW_WEAK_LOCAL_FALLBACK",
    "ALLOW_WEAK_LOCAL_FALLBACK",
    "HERMES_ALLOW_LOCAL_FALLBACK",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def resolve(path: str | Path) -> Path:
    p = Path(path)
    return p if p.is_absolute() else ROOT / p


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def fail_report(run_id: str, errors: list[str]) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "title": "Academic manuscript inventory and chapter conversion plan",
        "generated_at": utc_now(),
        "disposition": "academic_inventory_failed_closed",
        "errors": errors,
        "page_count": 0,
        "pages": [],
        "summary_counts": {},
        "safety_flags": dict(SAFETY_FLAGS),
        "docs_book_modified": False,
        "db_modified": False,
        "source_registry_modified": False,
        "raw_modified": False,
        "schema_modified": False,
        "daily_worker_modified": False,
        "gpt55_review_status": "not_run",
        "gpt55_used": False,
        "weak_local_fallback_used": False,
    }


def words(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9][A-Za-z0-9_\-']*", text)


def first_heading(text: str, fallback: str) -> str:
    for line in text.splitlines():
        m = re.match(r"^#\s+(.+?)\s*$", line)
        if m:
            return m.group(1).strip()
    return Path(fallback).stem.replace("-", " ").title()


def paragraph_count(text: str) -> int:
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    return sum(1 for p in paras if not p.lstrip().startswith(("#", "- ", "* ", ">", "```")))


def has_any(text: str, terms: list[str]) -> bool:
    low = text.lower()
    return any(t in low for t in terms)


def classify_page(path: Path, book_dir: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    low = text.lower()
    rel = str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)
    wc = len(words(text))
    headings = len(re.findall(r"^#{1,6}\s+", text, flags=re.M))
    bullets = len(re.findall(r"^\s*[-*+]\s+", text, flags=re.M))
    citations = len(re.findall(r"\[[^\]]+\]\([^)]+\)|\[[A-Za-z0-9_:\-]+\]|`src_[a-f0-9]+`|src_[a-f0-9]+", text))
    ref_present = bool(re.search(r"^#{2,6}\s+(references|bibliography|sources|further reading)\b", text, re.I | re.M))

    evidence_stub_risk = bool(re.search(r"\bsrc_[a-f0-9]+\b|support_status|claim_id|\bclaim[_ -]?ledger\b", low)) and (wc < 900 or bullets > paragraph_count(text))
    claim_ledger_risk = has_any(low, ["claim_id", "claim ledger", "claims ledger", "source mapping", "support_status", "validated_support"])
    source_status_summary_risk = has_any(low, ["support_status", "source status", "pending support", "validated support", "unresolved source"])
    internal_workflow_language_risk = has_any(low, ["publication pipeline", "machine disposition", "workflow note", "safe_reports_only", "editorial run", "run 4", "run 5", "run 6"])
    social_signal_risk = has_any(low, ["linkedin", "tweet", "social signal", "feed post", "followers", "3rd+"])
    unsupported_field_claim_risk = has_any(low, ["field claim", "unsupported", "uncorroborated", "needs corroboration"])

    missing_thesis = not has_any(low, ["argue", "argument", "thesis", "purpose", "this chapter"])
    missing_definitions = not has_any(low, ["define", "definition", "means", "refers to", "the term"])
    missing_literature = not has_any(low, ["literature", "prior work", "scholar", "research", "context"])
    missing_methodology = not has_any(low, ["method", "methodology", "approach", "we compare", "analysis"])
    missing_conceptual = not has_any(low, ["conceptual", "framework", "model", "taxonomy", "architecture"])
    missing_examples = not has_any(low, ["example", "case", "illustrat", "for instance"])
    missing_limitations = not has_any(low, ["limitation", "caveat", "risk", "constraint"])
    missing_summary = not bool(re.search(r"^#{2,6}\s+(summary|conclusion|takeaways)\b", text, re.I | re.M))
    missing_further = not bool(re.search(r"^#{2,6}\s+(further reading|references|bibliography)\b", text, re.I | re.M))

    name = path.name.lower()
    title = first_heading(text, path.name)
    if name == "preface.md":
        apparent = "preface_or_reader_guide"
        recommended = "front_matter"
        update_type = "literature_context_update"
    elif "open-question" in name:
        apparent = "open_questions_or_research_agenda"
        recommended = "research_agenda"
        update_type = "appendix_evidence_update"
    elif evidence_stub_risk:
        apparent = "evidence_stub"
        recommended = "reports_only" if claim_ledger_risk else "appendix"
        update_type = "claim_ledger_dump" if claim_ledger_risk else "evidence_stub"
    elif claim_ledger_risk or source_status_summary_risk:
        apparent = "claim_ledger_or_source_mapping"
        recommended = "reports_only"
        update_type = "claim_ledger_dump" if claim_ledger_risk else "source_status_summary"
    elif has_any(low, ["hermes", "openclaw"]):
        apparent = "tool_profile" if wc < 1600 or missing_literature else "academic_chapter_candidate"
        recommended = "tool_case_chapter"
        update_type = "case_study_update"
    elif has_any(low, ["method", "operating loop", "production", "pipeline"]):
        apparent = "methodology_or_process_note" if missing_literature else "academic_chapter_candidate"
        recommended = "methodology" if "method" in low else "production_operations_chapter"
        update_type = "methodology_update"
    else:
        apparent = "academic_chapter_candidate" if wc >= 250 and not missing_thesis else "research_note"
        recommended = "core_concept_chapter"
        update_type = "academic_chapter_update"

    blockers = sum([missing_thesis, missing_definitions, missing_literature, missing_methodology, missing_conceptual, missing_limitations])
    if apparent in {"evidence_stub", "claim_ledger_or_source_mapping"}:
        maturity = 1
    elif apparent in {"research_note", "open_questions_or_research_agenda", "methodology_or_process_note", "tool_profile"}:
        maturity = 2 if blockers >= 3 else 3
    elif wc > 1000 and blockers <= 1 and ref_present:
        maturity = 5
    elif wc > 55 and blockers <= 2:
        maturity = 4
    elif wc > 250:
        maturity = 3
    else:
        maturity = 2

    reports_only = recommended == "reports_only" or apparent in {"evidence_stub", "claim_ledger_or_source_mapping"} or internal_workflow_language_risk
    appendix_only = (recommended in {"appendix", "research_agenda", "glossary", "bibliography"} or apparent == "appendix_candidate") and not reports_only
    main_allowed = maturity >= 4 and not reports_only and not appendix_only and not any([
        evidence_stub_risk,
        claim_ledger_risk,
        source_status_summary_risk,
        internal_workflow_language_risk,
        unsupported_field_claim_risk,
    ])
    if reports_only:
        safe = "safe_reports_only"
    elif appendix_only:
        safe = "appendix_candidate"
    elif main_allowed:
        safe = "manuscript_page_classified"
    else:
        safe = "rewrite_plan_created"

    priority = 1
    if recommended in {"introduction", "literature_and_context", "conceptual_framework", "methodology"}:
        priority = 1
    elif main_allowed:
        priority = 3
    elif reports_only:
        priority = 5
    elif blockers >= 4:
        priority = 2
    else:
        priority = 4

    action_parts = []
    if reports_only:
        action_parts.append("keep out of main chapters; use as report/source planning input")
    if appendix_only:
        action_parts.append("route to appendix/back matter before any public chapter use")
    if missing_literature:
        action_parts.append("add literature/context support")
    if missing_methodology:
        action_parts.append("add methodology support")
    if missing_conceptual:
        action_parts.append("define conceptual framework and terms")
    if missing_limitations:
        action_parts.append("add limitations/caveats")
    if not action_parts:
        action_parts.append("retain as academic chapter candidate and polish structure")

    return {
        "path": rel,
        "title": title,
        "word_count": wc,
        "heading_count": headings,
        "paragraph_count": paragraph_count(text),
        "bullet_count": bullets,
        "citation_count": citations,
        "reference_section_present": ref_present,
        "apparent_current_role": apparent,
        "recommended_academic_role": recommended,
        "academic_maturity_level": maturity,
        "academic_maturity_label": MATURITY_LABELS[maturity],
        "contract_update_type": update_type,
        "main_chapter_allowed": main_allowed,
        "appendix_only_recommended": appendix_only,
        "reports_only_recommended": reports_only,
        "evidence_stub_risk": evidence_stub_risk,
        "claim_ledger_risk": claim_ledger_risk,
        "source_status_summary_risk": source_status_summary_risk,
        "internal_workflow_language_risk": internal_workflow_language_risk,
        "social_signal_risk": social_signal_risk,
        "unsupported_field_claim_risk": unsupported_field_claim_risk,
        "missing_thesis_or_argument": missing_thesis,
        "missing_definitions": missing_definitions,
        "missing_literature_support": missing_literature,
        "missing_methodology_support": missing_methodology,
        "missing_conceptual_framework": missing_conceptual,
        "missing_examples_or_case_material": missing_examples,
        "missing_limitations": missing_limitations,
        "missing_chapter_summary": missing_summary,
        "missing_further_reading": missing_further,
        "rewrite_priority": priority,
        "recommended_next_action": "; ".join(action_parts),
        "safe_handling": safe,
        "gpt55_review_status": "not_run",
    }


def bounded_page_summary(page: dict[str, Any], path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    excerpt = re.sub(r"\s+", " ", text).strip()[:3500]
    return {"deterministic_classification": page, "bounded_excerpt": excerpt}


def call_gpt55_review(page_summary: dict[str, Any], reasoning_profile: str = "closed_loop_editorial", timeout_seconds: int = 300) -> str:
    prompt = {
        "task": "Classify this manuscript page for academic/professional book conversion. Return strict JSON only.",
        "provider": "copilot",
        "model": "gpt-5.5",
        "bridge": "hermes_cli",
        "reasoning_profile": reasoning_profile,
        "weak_local_fallback": False,
        "required_safety_flags": SAFETY_FLAGS,
        "allowed_dispositions": ["manuscript_page_classified", "evidence_stub_detected", "appendix_candidate", "safe_reports_only"],
        "page": page_summary,
    }
    bridge = ROOT / "scripts" / "hermes_high_reasoning_json.py"
    if not bridge.exists():
        raise RuntimeError("hermes_cli bridge unavailable")
    proc = subprocess.run(
        [
            sys.executable,
            str(bridge),
            "--prompt",
            json.dumps(prompt, sort_keys=True),
            "--schema-name",
            "academic_manuscript_page_review",
            "--provider",
            "copilot",
            "--model",
            "gpt-5.5",
            "--reasoning-profile",
            reasoning_profile,
            "--timeout-seconds",
            str(timeout_seconds),
        ],
        text=True,
        capture_output=True,
        timeout=timeout_seconds + 20,
        cwd=ROOT,
    )
    if proc.returncode != 0:
        raise RuntimeError("gpt55 bridge failed closed")
    return proc.stdout


def validate_gpt55_json(raw: str) -> dict[str, Any]:
    data = json.loads(raw)
    if isinstance(data, dict) and isinstance(data.get("parsed_json"), dict):
        data = data["parsed_json"]
    for k, v in SAFETY_FLAGS.items():
        if data.get(k) is not v:
            raise ValueError(f"missing_or_invalid_safety_flag:{k}")
    if "academic_maturity_level" not in data or not isinstance(data["academic_maturity_level"], int):
        raise ValueError("missing_academic_maturity_level")
    if data.get("recommended_academic_role") not in RECOMMENDED_ROLES:
        raise ValueError("invalid_recommended_academic_role")
    return data


def apply_gpt55(page: dict[str, Any], page_path: Path, reasoning_profile: str, timeout_seconds: int) -> dict[str, Any]:
    try:
        raw = call_gpt55_review(bounded_page_summary(page, page_path), reasoning_profile, timeout_seconds)
        review = validate_gpt55_json(raw)
    except Exception as exc:
        page["gpt55_review_status"] = "failed_closed"
        page["gpt55_error"] = str(exc)
        return page
    page["gpt55_review_status"] = "completed"
    page["gpt55_review"] = review
    # Advisory only: do not replace deterministic safety decisions or flags.
    return page


def summarize(pages: list[dict[str, Any]]) -> dict[str, Any]:
    c = Counter()
    for p in pages:
        c[f"maturity_{p['academic_maturity_level']}"] += 1
        c[p["apparent_current_role"]] += 1
        c[f"recommended_{p['recommended_academic_role']}"] += 1
        for key in [
            "evidence_stub_risk", "claim_ledger_risk", "appendix_only_recommended", "reports_only_recommended",
            "missing_literature_support", "missing_methodology_support", "missing_conceptual_framework",
        ]:
            if p.get(key):
                c[key] += 1
    return dict(sorted(c.items()))


def validate_report(report: dict[str, Any]) -> None:
    if report.get("safety_flags") != SAFETY_FLAGS:
        raise ValueError("hard_safety_flags_not_preserved")
    for page in report.get("pages", []):
        if page.get("apparent_current_role") not in APPARENT_ROLES:
            raise ValueError("invalid_apparent_current_role")
        if page.get("recommended_academic_role") not in RECOMMENDED_ROLES:
            raise ValueError("invalid_recommended_academic_role")
        if page.get("contract_update_type") not in UPDATE_TYPES:
            raise ValueError("invalid_contract_update_type")
        json.dumps(page)


def build_inventory(
    book_dir: str | Path,
    quality_contract: str | Path,
    structure_plan: str | Path | None,
    run_id: str = "run49",
    use_gpt55_review: bool = False,
    reasoning_profile: str = "closed_loop_editorial",
    timeout_seconds: int = 300,
) -> dict[str, Any]:
    book = resolve(book_dir)
    contract = resolve(quality_contract)
    structure = resolve(structure_plan) if structure_plan else None
    errors: list[str] = []
    if not book.exists() or not book.is_dir():
        errors.append("docs/book does not exist")
    if not contract.exists():
        errors.append("academic quality contract missing")
    if errors:
        return fail_report(run_id, errors)
    try:
        read_json(contract)
    except Exception as exc:
        return fail_report(run_id, [f"academic quality contract invalid:{exc}"])
    if structure and not structure.exists():
        errors.append("academic structure plan missing")
    if errors:
        return fail_report(run_id, errors)

    weak_requested = any(os.environ.get(k) for k in FORBIDDEN_FALLBACK_ENV)
    if use_gpt55_review and weak_requested:
        report = fail_report(run_id, ["weak/local fallback requested and refused"])
        report["gpt55_review_status"] = "failed_closed"
        return report

    pages = []
    try:
        md_pages = sorted(book.glob("*.md"))
        for page_path in md_pages:
            page = classify_page(page_path, book)
            if use_gpt55_review:
                page = apply_gpt55(page, page_path, reasoning_profile, timeout_seconds)
            pages.append(page)
    except Exception as exc:
        return fail_report(run_id, [f"markdown parsing/classification failed:{exc}"])

    gpt_statuses = Counter(p.get("gpt55_review_status", "not_run") for p in pages)
    report = {
        "run_id": run_id,
        "title": "Academic manuscript inventory and chapter conversion plan",
        "generated_at": utc_now(),
        "disposition": "academic_inventory_completed",
        "machine_dispositions": ["academic_inventory_completed", "manuscript_page_classified", "rewrite_plan_created", "safe_reports_only"],
        "page_count": len(pages),
        "book_dir": str(book),
        "quality_contract": str(contract),
        "structure_plan": str(structure) if structure else None,
        "pages": pages,
        "summary_counts": summarize(pages),
        "academic_maturity_counts": dict(Counter(str(p["academic_maturity_level"]) for p in pages)),
        "rewrite_priority_sequence": [p["path"] for p in sorted(pages, key=lambda x: (x["rewrite_priority"], x["path"]))],
        "safety_flags": dict(SAFETY_FLAGS),
        "docs_book_modified": False,
        "db_modified": False,
        "source_registry_modified": False,
        "raw_modified": False,
        "schema_modified": False,
        "daily_worker_modified": False,
        "gpt55_used": use_gpt55_review and bool(pages) and any(p.get("gpt55_review_status") == "completed" for p in pages),
        "gpt55_review_status": "completed" if gpt_statuses.get("completed") else ("failed_closed" if use_gpt55_review else "not_run"),
        "gpt55_review_status_counts": dict(gpt_statuses),
        "weak_local_fallback_used": False,
    }
    validate_report(report)
    return report


def write_reports(report: dict[str, Any], output_json: str | Path, output_md: str | Path) -> None:
    outj = resolve(output_json)
    outm = resolve(output_md)
    outj.parent.mkdir(parents=True, exist_ok=True)
    outm.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(report, indent=2, sort_keys=True)
    json.loads(text)
    outj.write_text(text + "\n", encoding="utf-8")
    lines = [
        f"# Run {report.get('run_id', 'unknown')} academic manuscript inventory",
        "",
        f"- disposition: `{report.get('disposition')}`",
        f"- page_count: `{report.get('page_count')}`",
        f"- GPT-5.5 used: `{report.get('gpt55_used')}`",
        f"- GPT-5.5 review status: `{report.get('gpt55_review_status')}`",
        f"- docs/book modified: `{report.get('docs_book_modified')}`",
        "",
        "## Summary counts",
        "",
        "```json",
        json.dumps(report.get("summary_counts", {}), indent=2, sort_keys=True),
        "```",
        "",
        "## Pages",
        "",
    ]
    for p in report.get("pages", []):
        lines.extend([
            f"### {p['title']}",
            f"- path: `{p['path']}`",
            f"- apparent_current_role: `{p['apparent_current_role']}`",
            f"- recommended_academic_role: `{p['recommended_academic_role']}`",
            f"- academic_maturity: `{p['academic_maturity_level']} — {p['academic_maturity_label']}`",
            f"- safe_handling: `{p['safe_handling']}`",
            f"- rewrite_priority: `{p['rewrite_priority']}`",
            f"- recommended_next_action: {p['recommended_next_action']}",
            "",
        ])
    outm.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Report-only academic manuscript inventory")
    ap.add_argument("--book-dir", required=True)
    ap.add_argument("--quality-contract", required=True)
    ap.add_argument("--structure-plan")
    ap.add_argument("--output-json", required=True)
    ap.add_argument("--output-md", required=True)
    ap.add_argument("--run-id", default="run49")
    ap.add_argument("--use-gpt55-review", action="store_true")
    ap.add_argument("--reasoning-profile", default="closed_loop_editorial")
    ap.add_argument("--timeout-seconds", type=int, default=300)
    args = ap.parse_args(argv)
    report = build_inventory(args.book_dir, args.quality_contract, args.structure_plan, args.run_id, args.use_gpt55_review, args.reasoning_profile, args.timeout_seconds)
    write_reports(report, args.output_json, args.output_md)
    print(json.dumps({"ok": report["disposition"] == "academic_inventory_completed", "output_json": str(resolve(args.output_json)), "page_count": report.get("page_count"), "gpt55_review_status": report.get("gpt55_review_status")}, sort_keys=True))
    return 0 if report["disposition"] == "academic_inventory_completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
