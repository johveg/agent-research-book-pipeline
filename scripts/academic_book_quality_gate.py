#!/usr/bin/env python3
"""Academic book quality gate for guarded publication packets.

This gate classifies proposed book updates against a hard academic/professional
book contract. It is report-only and never grants authoring/publication/chapter
mutation approval by itself.
"""
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
DEFAULT_CONTRACT = ROOT / "config" / "academic_book_quality_contract.json"
DEFAULT_JSON = ROOT / "reports" / "editorial" / "academic-book-quality-gate-run48.json"
DEFAULT_MD = ROOT / "reports" / "editorial" / "academic-book-quality-gate-run48.md"

FALSE_FLAGS = {
    "author_allowed": False,
    "publication_approved": False,
    "eligible_for_claim_insertion": False,
    "eligible_for_authoring": False,
    "eligible_for_publication": False,
    "chapter_update_allowed": False,
}
MAIN_CHAPTER_UPDATE_TYPES = {
    "academic_chapter_update",
    "methodology_update",
    "literature_context_update",
    "conceptual_framework_update",
    "case_study_update",
}
LEGACY_ACADEMIC_COMPATIBLE_TYPES = {
    "existing_chapter_delta",
    "new_chapter_candidate",
    "guarded_substantive_canary",
    "caveated_substantive_canary",
    "substantive_chapter_delta",
    "caveated_note",
}
REPORT_ONLY_TYPES = {"daily_status_only", "no_publication", "safe_reports_only"}
RAW_ID_PATTERNS = [
    re.compile(r"\bclaim[:_][A-Za-z0-9_.:-]+", re.I),
    re.compile(r"\bsource[:_][A-Za-z0-9_.:-]+", re.I),
    re.compile(r"\braw[_-]?capture[_:-]?[A-Za-z0-9_.:-]*", re.I),
    re.compile(r"\bevidence[_:-]\d+\b", re.I),
]
STATUS_LABEL_RE = re.compile(r"\b(supported|weakly_supported|needs_review|source mapping|claim ledger|source status|status:)\b", re.I)
INTERNAL_LANGUAGE_RE = re.compile(r"\b(editor note|author should|book role|workflow|changelog|publication pipeline status|machine disposition)\b", re.I)
SOCIAL_ONLY_RE = re.compile(r"\b(social signal only|social/discovery-only|discovery-only|linkedin post|tweet|x post|without corroboration|no corroboration)\b", re.I)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def resolve(path: str | Path) -> Path:
    p = Path(path)
    return p if p.is_absolute() else ROOT / p


def load_contract(path: str | Path = DEFAULT_CONTRACT) -> dict[str, Any]:
    p = resolve(path)
    data = json.loads(p.read_text(encoding="utf-8"))
    required = [
        "allowed_public_chapter_update_types",
        "blocked_reader_facing_update_types",
        "minimum_requirements_for_academic_chapter_prose",
        "required_academic_apparatus",
        "hard_safety_flags",
    ]
    missing = [k for k in required if k not in data]
    if missing:
        raise ValueError(f"contract missing keys: {missing}")
    flags = data.get("hard_safety_flags") or {}
    bad_flags = [k for k, v in FALSE_FLAGS.items() if flags.get(k) is not v]
    if bad_flags:
        raise ValueError(f"contract hard safety flags must be false: {bad_flags}")
    return data


def load_json(path: str | Path) -> Any:
    return json.loads(resolve(path).read_text(encoding="utf-8"))


def extract_updates(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if not isinstance(data, dict):
        return []
    for key in ["publish_packets", "patch_previews", "packets", "updates"]:
        value = data.get(key)
        if isinstance(value, list):
            return [x for x in value if isinstance(x, dict)]
    if any(k in data for k in ["proposed_markdown_delta", "update_type", "target_file_suggestion"]):
        return [data]
    return []


def text_for(update: dict[str, Any]) -> str:
    fields = [
        update.get("proposed_markdown_delta"),
        update.get("summary"),
        update.get("source_quality_summary"),
        update.get("title"),
    ]
    return "\n".join(str(x or "") for x in fields)


def _paragraph_count(text: str) -> int:
    return sum(1 for p in re.split(r"\n\s*\n", text.strip()) if len(p.split()) >= 12)


def _bullet_line_count(text: str) -> int:
    return sum(1 for line in text.splitlines() if line.strip().startswith(("- ", "* ", "• ")))


def _has_any(patterns: list[str], text: str) -> bool:
    lower = text.lower()
    return any(p in lower for p in patterns)


def classify_update(update: dict[str, Any], contract: dict[str, Any]) -> str:
    update_type = str(update.get("update_type") or "").strip()
    text = text_for(update)
    blocked = set(contract.get("blocked_reader_facing_update_types") or [])
    if update_type in blocked:
        return update_type
    prose = str(update.get("proposed_markdown_delta") or "")
    if SOCIAL_ONLY_RE.search(text):
        return "social_signal_without_corroboration"
    if STATUS_LABEL_RE.search(text) and (RAW_ID_PATTERNS[0].search(text) or RAW_ID_PATTERNS[1].search(text) or "evidence:" in text.lower()):
        return "evidence_stub"
    if INTERNAL_LANGUAGE_RE.search(prose):
        return "editor_workflow_note"
    if update_type in set(contract.get("allowed_public_chapter_update_types") or []):
        return update_type
    if update_type in LEGACY_ACADEMIC_COMPATIBLE_TYPES:
        return "academic_chapter_update"
    if update_type in REPORT_ONLY_TYPES:
        return "source_status_summary"
    return update_type or "unsupported_update_type"


def academic_prose_failures(update: dict[str, Any], *, strict: bool = True) -> list[str]:
    text = str(update.get("proposed_markdown_delta") or "")
    lower = text.lower()
    failures: list[str] = []
    if strict:
        if "purpose:" not in lower and "this chapter" not in lower and "chapter explains" not in lower and "this introduction" not in lower and "the introduction" not in lower and "introduction explains" not in lower:
            failures.append("missing_explicit_chapter_purpose")
        if not any(term in lower for term in ["argument", "argues", "thesis", "contends"]):
            failures.append("missing_sustained_argument")
        if not any(term in lower for term in ["definition:", "defined as", "means", "refers to"]):
            failures.append("missing_definitions")
        if _paragraph_count(text) < 2 or _bullet_line_count(text) >= _paragraph_count(text):
            failures.append("missing_evidence_grounded_paragraphs")
        if not any(term in lower for term in ["limitation", "caveat", "bounded", "does not claim", "limited to"]):
            failures.append("missing_limitations_caveats")
    if any(p.search(text) for p in RAW_ID_PATTERNS):
        failures.append("raw_or_internal_id_in_main_prose")
    if STATUS_LABEL_RE.search(text):
        failures.append("status_labels_in_main_prose")
    if INTERNAL_LANGUAGE_RE.search(text):
        failures.append("internal_editorial_or_workflow_language")
    if SOCIAL_ONLY_RE.search(text_for(update)):
        failures.append("social_or_discovery_only_without_corroboration")
    return sorted(set(failures))


def evaluate_update(update: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    classification = classify_update(update, contract)
    update_type = str(update.get("update_type") or "")
    blocked_types = set(contract.get("blocked_reader_facing_update_types") or [])
    allowed_types = set(contract.get("allowed_public_chapter_update_types") or [])
    appendix_types = set(contract.get("appendix_only_update_types") or ["appendix_evidence_update"])
    failures: list[str] = []
    decision = "safe_reports_only"
    academic_allowed = False
    appendix_only = False
    safe_reports = False

    missing_flags = [k for k in ["human_in_loop_dependency_added", "raw_text_publication_allowed"] if k not in update]
    if missing_flags:
        failures.append("missing_safety_flags:" + ",".join(missing_flags))

    for flag, expected in FALSE_FLAGS.items():
        if update.get(flag, False) is not False:
            failures.append(f"hard_flag_must_remain_false:{flag}")

    if classification in appendix_types:
        decision = "appendix_only_allowed"
        appendix_only = True
    elif classification == "social_signal_without_corroboration" or _has_any(["unsupported field claim", "unsupported_field_claim"], text_for(update)):
        decision = "blocked_needs_literature_support"
        safe_reports = True
    elif classification in blocked_types or classification in {"evidence_stub", "claim_ledger_dump", "source_status_summary", "editor_workflow_note", "changelog_only_update"}:
        decision = "blocked_evidence_stub_not_chapter_prose"
        failures.extend(academic_prose_failures(update))
        safe_reports = True
    elif classification in allowed_types or classification in MAIN_CHAPTER_UPDATE_TYPES:
        strict = str(update.get("update_type") or "") not in LEGACY_ACADEMIC_COMPATIBLE_TYPES
        failures.extend(academic_prose_failures(update, strict=strict))
        if failures:
            if "social_or_discovery_only_without_corroboration" in failures:
                decision = "blocked_needs_literature_support"
            else:
                decision = "blocked_evidence_stub_not_chapter_prose"
            safe_reports = True
        else:
            decision = "academic_book_update_allowed"
            academic_allowed = True
    else:
        failures.append(f"unsupported_update_type:{update_type or classification}")
        decision = "safe_reports_only"
        safe_reports = True

    if missing_flags or any(f.startswith("hard_flag") for f in failures):
        decision = "safe_reports_only"
        academic_allowed = False
        appendix_only = False
        safe_reports = True

    return {
        "update_id": str(update.get("publish_packet_id") or update.get("packet_id") or update.get("id") or ""),
        "update_type": update_type,
        "classification": classification,
        "decision": decision,
        "academic_book_update_allowed": academic_allowed,
        "appendix_only_allowed": appendix_only,
        "safe_reports_only": safe_reports,
        "blocked_needs_literature_support": decision == "blocked_needs_literature_support",
        "blocked_evidence_stub_not_chapter_prose": decision == "blocked_evidence_stub_not_chapter_prose",
        "failed_checks": sorted(set(failures)),
        "minimum_requirements_checked": contract.get("minimum_requirements_for_academic_chapter_prose", []),
        **FALSE_FLAGS,
    }


def evaluate_document(data: Any, contract: dict[str, Any], run_id: str = "run48") -> dict[str, Any]:
    updates = extract_updates(data)
    results = [evaluate_update(update, contract) for update in updates]
    counts = Counter(r["decision"] for r in results)
    classification_counts = Counter(r["classification"] for r in results)
    failed_closed = not updates
    return {
        "mode": "academic_book_quality_gate",
        "run_id": run_id,
        "generated_at": utc_now(),
        "contract_name": contract.get("contract_name", "academic_book_quality_contract"),
        "contract_version": contract.get("version", ""),
        "failed_closed": failed_closed,
        "decision": "safe_reports_only" if failed_closed else (results[0]["decision"] if len(results) == 1 else "mixed_quality_gate_decisions"),
        "update_count": len(updates),
        "decision_counts": dict(counts),
        "classification_counts": dict(classification_counts),
        "blocked_evidence_stub_count": sum(1 for r in results if r["classification"] == "evidence_stub" or r["blocked_evidence_stub_not_chapter_prose"]),
        "academic_chapter_candidate_count": counts.get("academic_book_update_allowed", 0),
        "appendix_only_count": counts.get("appendix_only_allowed", 0),
        "safe_reports_only_count": counts.get("safe_reports_only", 0) + counts.get("blocked_evidence_stub_not_chapter_prose", 0) + counts.get("blocked_needs_literature_support", 0),
        "updates": results,
        "required_academic_apparatus": contract.get("required_academic_apparatus", []),
        "report_only": True,
        "db_modified": False,
        "docs_book_modified": False,
        "source_registry_modified": False,
        "raw_modified": False,
        "schema_modified": False,
        "daily_worker_modified": False,
        "human_in_loop_dependency_added": False,
        "gpt55_used": False,
        "reasoning_status": "deterministic_contract_gate",
        **FALSE_FLAGS,
    }


def fail_closed_report(run_id: str, error: str) -> dict[str, Any]:
    return {
        "mode": "academic_book_quality_gate",
        "run_id": run_id,
        "generated_at": utc_now(),
        "failed_closed": True,
        "decision": "safe_reports_only",
        "error": error,
        "update_count": 0,
        "decision_counts": {"safe_reports_only": 1},
        "classification_counts": {},
        "blocked_evidence_stub_count": 0,
        "academic_chapter_candidate_count": 0,
        "appendix_only_count": 0,
        "safe_reports_only_count": 1,
        "safe_reports_only": True,
        "blocked_needs_literature_support": False,
        "blocked_evidence_stub_not_chapter_prose": False,
        "updates": [],
        "report_only": True,
        "db_modified": False,
        "docs_book_modified": False,
        "source_registry_modified": False,
        "raw_modified": False,
        "schema_modified": False,
        "daily_worker_modified": False,
        "human_in_loop_dependency_added": False,
        "gpt55_used": False,
        "reasoning_status": "failed_closed",
        **FALSE_FLAGS,
    }


def write_json(path: str | Path, obj: Any) -> None:
    out = resolve(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def markdown(report: dict[str, Any]) -> str:
    lines = ["# Academic book quality gate", "", f"Generated: {report.get('generated_at')}", ""]
    for key in ["run_id", "decision", "update_count", "blocked_evidence_stub_count", "academic_chapter_candidate_count", "appendix_only_count", "safe_reports_only_count", "gpt55_used"]:
        if key in report:
            lines.append(f"- {key}: `{report.get(key)}`")
    if report.get("decision_counts"):
        lines += ["", "## Decision counts", ""]
        for k, v in sorted(report["decision_counts"].items()):
            lines.append(f"- {k}: {v}")
    if report.get("updates"):
        lines += ["", "## Updates", ""]
        for item in report["updates"]:
            lines.append(f"- `{item.get('update_id') or '(no id)'}`: {item.get('classification')} -> {item.get('decision')}")
            for failed in item.get("failed_checks") or []:
                lines.append(f"  - failed: `{failed}`")
    lines += [
        "",
        "## Safety",
        "",
        "This gate is deterministic/report-only. It does not create human/editor approval, does not approve publication, and does not allow chapter mutation by itself.",
    ]
    return "\n".join(lines) + "\n"


def write_md(path: str | Path, report: dict[str, Any]) -> None:
    out = resolve(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(markdown(report), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Evaluate publication packets against the academic book quality contract")
    ap.add_argument("--input", required=True)
    ap.add_argument("--contract", default=str(DEFAULT_CONTRACT))
    ap.add_argument("--run-id", default="run48")
    ap.add_argument("--output-json", default=str(DEFAULT_JSON))
    ap.add_argument("--output-md", default=str(DEFAULT_MD))
    args = ap.parse_args(argv)
    try:
        contract = load_contract(args.contract)
        data = load_json(args.input)
        report = evaluate_document(data, contract, run_id=args.run_id)
        code = 2 if report.get("failed_closed") else 0
    except Exception as exc:
        report = fail_closed_report(args.run_id, str(exc))
        code = 2
    write_json(args.output_json, report)
    write_md(args.output_md, report)
    if code:
        print(json.dumps({"ok": False, "decision": report.get("decision"), "error": report.get("error", "failed_closed")}, sort_keys=True), file=sys.stderr)
    else:
        print(json.dumps({"ok": True, "decision": report.get("decision"), "decision_counts": report.get("decision_counts")}, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
