#!/usr/bin/env python3
"""Run 12 controlled corroboration research report.

This script creates a report-only corroboration research layer for Run 10
source-review items that require corroboration. It does not browse the web,
write SQLite, update source registry, create claims/editorial reviews, change
statuses, modify docs/book, or approve author/publication use.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from hermes_high_reasoning_json import DEFAULT_MODEL, DEFAULT_PROVIDER, HighReasoningError, call_high_reasoning_json  # noqa: E402
from research_common import DB_PATH as DEFAULT_DB_PATH, ROOT as REPO_ROOT, sha256_text, write_json  # noqa: E402

MODE = "corroboration_research"
ALLOWED_STATUS = {
    "corroborated",
    "partially_corroborated",
    "not_corroborated",
    "contradiction_found",
    "insufficient_evidence",
    "source_context_unclear",
}
ALLOWED_EVIDENCE_USE = {
    "eligible_as_caveat_only_after_corroboration",
    "eligible_for_filing_later_after_corroboration",
    "needs_more_sources",
    "needs_source_review",
    "do_not_use",
    "contradiction_requires_editor_review",
}
ALLOWED_NEXT = {
    "eligible_for_review_note_persistence",
    "run_additional_source_collection",
    "needs_editor_review",
    "exclude_from_pipeline",
    "contradiction_review_required",
}
PROVENANCE_KEYS = [
    "source_review_id",
    "filing_evaluation_id",
    "packet_item_id",
    "source_id",
    "source_card_id",
    "semantic_object_id",
    "quality_review_id",
]


class CorroborationError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def db_path() -> Path:
    override = os.environ.get("TEREFO_BOOK_DB_PATH", "").strip()
    return Path(override) if override else DEFAULT_DB_PATH


def resolve(path: str) -> Path:
    p = Path(path)
    return p if p.is_absolute() else REPO_ROOT / p


def repo_relative(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def clean_text(value: Any, max_len: int = 500) -> str:
    text = " ".join(str(value or "").split())
    if len(text) > max_len:
        return text[: max_len - 1].rstrip() + "…"
    return text


def listify(value: Any, max_len: int = 180) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [clean_text(v, max_len) for v in value if clean_text(v, max_len)]
    if isinstance(value, str):
        return [clean_text(value, max_len)] if value.strip() else []
    return [clean_text(value, max_len)]


def load_json(path: Path, *, required: bool = True) -> dict[str, Any]:
    if not path.exists():
        if required:
            raise CorroborationError(f"missing input report: {path}")
        return {}
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CorroborationError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(obj, dict):
        raise CorroborationError(f"input report must be JSON object: {path}")
    return obj


def validate_source_support_report(report: dict[str, Any]) -> None:
    if report.get("mode") != "source_support_review":
        raise CorroborationError("source-support report mode must be source_support_review")
    if report.get("author_allowed") is not False or report.get("publication_approved") is not False or report.get("advisory_only") is not True:
        raise CorroborationError("source-support report safety flags invalid")
    if report.get("db_modified") not in (False, None):
        raise CorroborationError("source-support report indicates DB modification; refusing")
    if not isinstance(report.get("source_reviews"), list):
        raise CorroborationError("source-support report missing source_reviews list")


def connect_readonly() -> sqlite3.Connection | None:
    path = db_path()
    if not path.exists():
        return None
    con = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA query_only = ON")
    return con


def table_count(con: sqlite3.Connection | None, table: str) -> int:
    if con is None:
        return 0
    try:
        return int(con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
    except sqlite3.Error:
        return 0


def status_hashes(con: sqlite3.Connection | None) -> dict[str, str]:
    if con is None:
        return {"sources_status_hash": "", "claims_status_hash": "", "editorial_reviews_hash": ""}
    specs = {
        "sources_status_hash": "SELECT id, quality_score, privacy_publication_status, duplicate_status FROM sources ORDER BY id",
        "claims_status_hash": "SELECT id, status, publication_decision, contradiction_status FROM claims ORDER BY id",
        "editorial_reviews_hash": "SELECT id, run_id, review_type, status, summary, report_path, created_at FROM editorial_reviews ORDER BY id",
    }
    out: dict[str, str] = {}
    for name, sql in specs.items():
        try:
            rows = [dict(r) for r in con.execute(sql)]
        except sqlite3.Error:
            rows = []
        out[name] = sha256_text(json.dumps(rows, sort_keys=True, ensure_ascii=False))
    return out


def source_context(con: sqlite3.Connection | None, source_ids: list[str]) -> dict[str, Any]:
    ctx: dict[str, Any] = {"sources": [], "source_notes_count_by_type": {}}
    if con is None or not source_ids:
        return ctx
    uniq = sorted(set(source_ids))
    q = ",".join("?" for _ in uniq)
    try:
        cols = {r[1] for r in con.execute("PRAGMA table_info(sources)")}
        select = [c for c in ["id", "title", "source_type", "publisher", "quality_score", "privacy_publication_status", "duplicate_status", "url"] if c in cols]
        if select:
            for row in con.execute(f"SELECT {', '.join(select)} FROM sources WHERE id IN ({q})", uniq):
                d = dict(row)
                for key in ["title", "publisher", "url"]:
                    if key in d:
                        d[key] = clean_text(d[key], 180)
                ctx["sources"].append(d)
    except sqlite3.Error:
        pass
    try:
        for row in con.execute(f"SELECT note_type, COUNT(*) c FROM source_notes WHERE source_id IN ({q}) GROUP BY note_type", uniq):
            ctx["source_notes_count_by_type"][row["note_type"]] = row["c"]
    except sqlite3.Error:
        pass
    return ctx


def has_corroboration_requirement(item: dict[str, Any]) -> bool:
    return (
        item.get("next_stage_recommendation") == "run_corroboration_research"
        or item.get("evidence_use_decision") == "needs_corroboration_before_filing"
        or item.get("corroboration_decision") == "corroboration_required"
    )


def skip_reason(item: dict[str, Any]) -> str | None:
    missing = [k for k in PROVENANCE_KEYS if not item.get(k)]
    if missing:
        return "missing_provenance"
    if item.get("author_allowed") is not False or item.get("publication_approved") is not False or item.get("advisory_only") is not True:
        return "missing_safety_flags"
    if has_corroboration_requirement(item):
        return None
    if item.get("source_support_decision") == "unsupported":
        return "unsupported_without_corroboration_requirement"
    if item.get("source_support_decision") == "unclear" or item.get("evidence_use_decision") == "needs_source_review":
        return "unclear_without_corroboration_requirement"
    if item.get("next_stage_recommendation") == "eligible_for_filing_persistence" or item.get("evidence_use_decision") in {"eligible_as_caveat_only", "eligible_for_filing_later"}:
        return "already_eligible_or_persisted"
    return "not_corroboration_required"


def select_items(report: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    selected: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for item in report.get("source_reviews", []):
        if not isinstance(item, dict):
            skipped.append({"source_review_id": "unknown", "skip_reason": "not_object"})
            continue
        reason = skip_reason(item)
        row = {
            "source_review_id": item.get("source_review_id", ""),
            "filing_evaluation_id": item.get("filing_evaluation_id", ""),
            "source_id": item.get("source_id", ""),
            "semantic_object_id": item.get("semantic_object_id", ""),
            "source_support_decision": item.get("source_support_decision", ""),
            "corroboration_decision": item.get("corroboration_decision", ""),
            "evidence_use_decision": item.get("evidence_use_decision", ""),
            "next_stage_recommendation": item.get("next_stage_recommendation", ""),
        }
        if reason is None:
            selected.append(item)
        else:
            row["skip_reason"] = reason
            skipped.append(row)
    return selected, skipped


def item_id_for(item: dict[str, Any]) -> str:
    return "corrob_item_" + sha256_text(f"{item.get('source_review_id')}:{item.get('output_hash')}")[:20]


def structural_review(item: dict[str, Any], *, llm_used: bool, provider: str, model: str, bridge: str, reasoning_status: str) -> dict[str, Any]:
    support = item.get("source_support_decision")
    if support == "unsupported":
        status = "source_context_unclear"
        evidence = "needs_source_review"
        next_stage = "needs_editor_review"
    elif support == "unclear":
        status = "source_context_unclear"
        evidence = "needs_source_review"
        next_stage = "needs_editor_review"
    else:
        status = "insufficient_evidence"
        evidence = "needs_more_sources"
        next_stage = "run_additional_source_collection"
    review = {
        "item_id": item_id_for(item),
        "source_review_id": item["source_review_id"],
        "filing_evaluation_id": item.get("filing_evaluation_id", ""),
        "packet_item_id": item.get("packet_item_id", ""),
        "source_id": item["source_id"],
        "source_card_id": item.get("source_card_id", ""),
        "semantic_object_id": item.get("semantic_object_id", ""),
        "quality_review_id": item.get("quality_review_id", ""),
        "original_statement": clean_text(item.get("semantic_object_text"), 420),
        "what_needs_corroboration": clean_text(item.get("corroboration_rationale") or item.get("support_rationale") or "Independent support for the advisory statement.", 300),
        "corroboration_strategy": "No live source collection was performed in Run 12; identify independent public/primary sources before later persistence or narrative use.",
        "suggested_search_queries": listify(item.get("corroboration_questions")) or [clean_text(item.get("semantic_object_text"), 140)],
        "required_source_types": listify(item.get("suggested_corroboration_sources")) or ["official primary source", "independent public analysis"],
        "corroboration_findings": ["Report-only planning assessment only; no external source collection or browsing was performed."],
        "current_source_support_enough": False,
        "corroboration_status": status,
        "evidence_use_decision": evidence,
        "recommended_next_stage": next_stage,
        "risk_flags": sorted(set(listify(item.get("risk_flags")) + ["requires_corroboration", "no_external_sources_collected_run12"])),
        "advisory_only": True,
        "author_allowed": False,
        "publication_approved": False,
        "llm_used": llm_used,
        "provider": provider if llm_used else "none",
        "model": model if llm_used else "none",
        "bridge": bridge if llm_used else "none",
        "reasoning_status": reasoning_status,
        "input_hash": sha256_text(json.dumps(item, sort_keys=True, ensure_ascii=False)),
        "output_hash": "",
    }
    review["output_hash"] = sha256_text(json.dumps({k: v for k, v in review.items() if k != "output_hash"}, sort_keys=True, ensure_ascii=False))
    return review


def validate_llm_response(obj: dict[str, Any]) -> None:
    reviews = obj.get("corroboration_reviews")
    if not isinstance(reviews, list):
        raise ValueError("corroboration_reviews must be a list")
    for r in reviews:
        if not isinstance(r, dict):
            raise ValueError("review must be object")
        if not r.get("source_review_id"):
            raise ValueError("source_review_id required")
        for key in ["corroboration_status", "evidence_use_decision", "recommended_next_stage"]:
            if not isinstance(r.get(key), str):
                raise ValueError(f"{key} must be a single string, not an array/object")
        if r.get("corroboration_status") not in ALLOWED_STATUS:
            raise ValueError("invalid corroboration_status")
        if r.get("evidence_use_decision") not in ALLOWED_EVIDENCE_USE:
            raise ValueError("invalid evidence_use_decision")
        if r.get("recommended_next_stage") not in ALLOWED_NEXT:
            raise ValueError("invalid recommended_next_stage")
        if r.get("advisory_only") is not True or r.get("author_allowed") is not False or r.get("publication_approved") is not False:
            raise ValueError("safety flags must be advisory_only true and approvals false")


def build_prompt(base_reviews: list[dict[str, Any]], source_ctx: dict[str, Any]) -> str:
    items = []
    for r in base_reviews:
        items.append({
            "item_id": r["item_id"],
            "source_review_id": r["source_review_id"],
            "filing_evaluation_id": r["filing_evaluation_id"],
            "source_id": r["source_id"],
            "semantic_object_id": r["semantic_object_id"],
            "original_statement": r["original_statement"],
            "what_needs_corroboration": r["what_needs_corroboration"],
            "suggested_search_queries_seed": r["suggested_search_queries"],
            "required_source_types_seed": r["required_source_types"],
        })
    schema = {
        "corroboration_reviews": [{
            "source_review_id": "must match input exactly",
            "corroboration_status": "ONE STRING ONLY: corroborated OR partially_corroborated OR not_corroborated OR contradiction_found OR insufficient_evidence OR source_context_unclear",
            "evidence_use_decision": "ONE STRING ONLY: eligible_as_caveat_only_after_corroboration OR eligible_for_filing_later_after_corroboration OR needs_more_sources OR needs_source_review OR do_not_use OR contradiction_requires_editor_review",
            "recommended_next_stage": "ONE STRING ONLY: eligible_for_review_note_persistence OR run_additional_source_collection OR needs_editor_review OR exclude_from_pipeline OR contradiction_review_required",
            "what_needs_corroboration": "short text",
            "corroboration_strategy": "short strategy, no claim of browsing",
            "suggested_search_queries": ["strings"],
            "required_source_types": ["strings"],
            "corroboration_findings": ["strings"],
            "current_source_support_enough": False,
            "risk_flags": ["strings"],
            "advisory_only": True,
            "author_allowed": False,
            "publication_approved": False,
        }]
    }
    return "\n".join([
        "You are producing a strict JSON corroboration research planning assessment for advisory book-pipeline items.",
        "CRITICAL: For corroboration_status, evidence_use_decision, and recommended_next_stage choose exactly ONE allowed string each. Do NOT return arrays for these fields.",
        "Do not browse the web. Do not claim external sources were found. Use only provided context and propose exact queries/source types for a future controlled collection run.",
        "This is not claim insertion, not editor approval, not author approval, and not publication approval.",
        "Return JSON only. Preserve safety flags: advisory_only=true, author_allowed=false, publication_approved=false.",
        "Allowed schema:", json.dumps(schema, ensure_ascii=False),
        "Items:", json.dumps(items, ensure_ascii=False),
        "Read-only source context:", json.dumps(source_ctx, ensure_ascii=False),
    ])


def merge_llm(base_reviews: list[dict[str, Any]], parsed: dict[str, Any], provider: str, model: str) -> list[dict[str, Any]]:
    by_id = {str(r.get("source_review_id")): r for r in parsed.get("corroboration_reviews", []) if isinstance(r, dict)}
    missing = [r["source_review_id"] for r in base_reviews if r["source_review_id"] not in by_id]
    if missing:
        raise CorroborationError(f"LLM response missing selected source_review_id(s): {missing}")
    out: list[dict[str, Any]] = []
    for base in base_reviews:
        src = by_id[base["source_review_id"]]
        r = dict(base)
        for key in [
            "what_needs_corroboration",
            "corroboration_strategy",
            "current_source_support_enough",
            "corroboration_status",
            "evidence_use_decision",
            "recommended_next_stage",
        ]:
            if key in src:
                r[key] = src[key]
        for key in ["suggested_search_queries", "required_source_types", "corroboration_findings", "risk_flags"]:
            if key in src:
                r[key] = listify(src[key])
        if r["corroboration_status"] not in ALLOWED_STATUS or r["evidence_use_decision"] not in ALLOWED_EVIDENCE_USE or r["recommended_next_stage"] not in ALLOWED_NEXT:
            raise CorroborationError(f"invalid LLM decision for {r['source_review_id']}")
        r.update({
            "advisory_only": True,
            "author_allowed": False,
            "publication_approved": False,
            "llm_used": True,
            "provider": provider,
            "model": model,
            "bridge": "hermes_cli",
            "reasoning_status": "high_reasoning_used",
        })
        r["output_hash"] = sha256_text(json.dumps({k: v for k, v in r.items() if k != "output_hash"}, sort_keys=True, ensure_ascii=False))
        out.append(r)
    return out


def build_payload(args: argparse.Namespace, source_support: dict[str, Any], optional_inputs: dict[str, str]) -> dict[str, Any]:
    selected_items, skipped_items = select_items(source_support)
    con = connect_readonly()
    try:
        counts_before = {
            "sources": table_count(con, "sources"),
            "source_notes": table_count(con, "source_notes"),
            "claims": table_count(con, "claims"),
            "editorial_reviews": table_count(con, "editorial_reviews"),
        }
        status_before = status_hashes(con)
        ctx = source_context(con, [str(i.get("source_id")) for i in selected_items])
        llm_used = not args.no_llm
        reasoning_status = "high_reasoning_used" if llm_used else "no_llm_structural_only"
        base_reviews = [structural_review(i, llm_used=llm_used, provider=args.provider, model=args.model, bridge="hermes_cli", reasoning_status=reasoning_status) for i in selected_items]
        bridge_result: dict[str, Any] = {}
        if llm_used:
            bridge_result = call_high_reasoning_json(build_prompt(base_reviews, ctx), "corroboration_research_v1", validate_llm_response, provider=args.provider, model=args.model)
            base_reviews = merge_llm(base_reviews, bridge_result["parsed_json"], args.provider, args.model)
        counts_after = {
            "sources": table_count(con, "sources"),
            "source_notes": table_count(con, "source_notes"),
            "claims": table_count(con, "claims"),
            "editorial_reviews": table_count(con, "editorial_reviews"),
        }
        status_after = status_hashes(con)
    finally:
        if con is not None:
            con.close()
    status_counts = dict(Counter(r["corroboration_status"] for r in base_reviews))
    evidence_counts = dict(Counter(r["evidence_use_decision"] for r in base_reviews))
    next_counts = dict(Counter(r["recommended_next_stage"] for r in base_reviews))
    changed_db = counts_before != counts_after
    payload: dict[str, Any] = {
        "run_id": args.run_id if args.run_id != "latest" else source_support.get("run_id", "latest"),
        "generated_at": utc_now(),
        "mode": MODE,
        "input_paths": {
            "source_support_review_report": repo_relative(resolve(args.source_support_review_report)),
            **optional_inputs,
        },
        "selected_items_count": len(selected_items),
        "reviewed_items_count": len(base_reviews),
        "skipped_items_count": len(skipped_items),
        "llm_used": llm_used,
        "provider": args.provider if llm_used else "none",
        "model": args.model if llm_used else "none",
        "bridge": "hermes_cli" if llm_used else "none",
        "reasoning_status": reasoning_status,
        "report_only": True,
        "changed_db": changed_db,
        "changed_docs_book": False,
        "changed_schema": False,
        "changed_daily_worker": False,
        "claims_inserted": 0,
        "editorial_reviews_inserted": 0,
        "source_status_changed": status_before.get("sources_status_hash") != status_after.get("sources_status_hash"),
        "claim_status_changed": status_before.get("claims_status_hash") != status_after.get("claims_status_hash"),
        "editorial_status_changed": status_before.get("editorial_reviews_hash") != status_after.get("editorial_reviews_hash"),
        "status_counts": status_counts,
        "evidence_use_counts": evidence_counts,
        "recommended_next_stage_counts": next_counts,
        "selected_items": [{
            "source_review_id": i.get("source_review_id"),
            "filing_evaluation_id": i.get("filing_evaluation_id"),
            "source_id": i.get("source_id"),
            "semantic_object_id": i.get("semantic_object_id"),
            "source_support_decision": i.get("source_support_decision"),
            "corroboration_decision": i.get("corroboration_decision"),
            "evidence_use_decision": i.get("evidence_use_decision"),
            "next_stage_recommendation": i.get("next_stage_recommendation"),
            "selection_reason": "corroboration_required",
        } for i in selected_items],
        "skipped_items": skipped_items,
        "corroboration_reviews": base_reviews,
        "safety_flags": {
            "advisory_only": True,
            "author_allowed": False,
            "publication_approved": False,
            "no_external_web_search": True,
            "no_db_writes": True,
            "no_claim_insertion": True,
            "no_editorial_review_insertion": True,
            "no_docs_book_changes": True,
            "no_schema_changes": True,
            "no_daily_worker_changes": True,
        },
        "db_counts_before": counts_before,
        "db_counts_after": counts_after,
        "status_hashes_before": status_before,
        "status_hashes_after": status_after,
        "high_reasoning_bridge": bridge_result,
        "risks": [
            "Run 12 did not collect live external sources or browse the web.",
            "GPT-5.5 output is advisory and not human/editor approval.",
            "Items may be recommended for later persistence but Run 12 does not persist them.",
        ],
        "next_run_recommendation": {},
        "verification": {},
    }
    if changed_db or payload["source_status_changed"] or payload["claim_status_changed"] or payload["editorial_status_changed"]:
        raise CorroborationError("DB counts or status hashes changed during report-only run")
    payload["next_run_recommendation"] = recommend_run13(payload)
    return payload


def recommend_run13(payload: dict[str, Any]) -> dict[str, Any]:
    if payload["recommended_next_stage_counts"].get("run_additional_source_collection", 0) > 0:
        rec = "controlled_external_source_collection_for_corroboration_candidates"
    elif payload["recommended_next_stage_counts"].get("eligible_for_review_note_persistence", 0) > 0:
        rec = "disabled_by_default_persistence_of_corroboration_review_notes"
    elif payload["recommended_next_stage_counts"].get("needs_editor_review", 0) > 0:
        rec = "human_editor_review_of_source_context_and_contradiction_risks"
    else:
        rec = "stop_or_rerun_source_selection_due_to_corroboration_risk"
    return {
        "recommendation": rec,
        "conditions": [
            "remain report-only by default",
            "do not create narrative packets until corroboration-required items are resolved or explicitly excluded",
            "do not insert claims, approve author use, or approve publication",
        ],
    }


def md_cell(v: Any) -> str:
    return clean_text(v, 90).replace("|", "\\|")


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [f"# Corroboration research: {payload['run_id']}", "", "## Executive summary", ""]
    for key in ["selected_items_count", "reviewed_items_count", "skipped_items_count", "llm_used", "provider", "model", "bridge", "reasoning_status"]:
        lines.append(f"- {key}: `{payload[key]}`")
    lines += [
        f"- Corroboration status counts: `{payload['status_counts']}`",
        f"- Evidence-use counts: `{payload['evidence_use_counts']}`",
        f"- Recommended next-stage counts: `{payload['recommended_next_stage_counts']}`",
        "- Safety: report-only; no DB/book/status/schema/daily-worker changes; no claim/editorial-review inserts; not author/publication approved.",
        "",
        "## Reviewed items",
        "",
        "| source review id | source id | why selected | corroboration status | evidence use | recommended next stage |",
        "|---|---|---|---|---|---|",
    ]
    review_by_id = {r["source_review_id"]: r for r in payload["corroboration_reviews"]}
    for item in payload["selected_items"]:
        r = review_by_id.get(item["source_review_id"], {})
        lines.append("| " + " | ".join([
            md_cell(item["source_review_id"]),
            md_cell(item["source_id"]),
            md_cell(item["selection_reason"]),
            md_cell(r.get("corroboration_status")),
            md_cell(r.get("evidence_use_decision")),
            md_cell(r.get("recommended_next_stage")),
        ]) + " |")
    lines += ["", "## Per-item corroboration assessments"]
    for r in payload["corroboration_reviews"]:
        lines += [
            "",
            f"### {r['source_review_id']}",
            "",
            f"- Filing evaluation: `{r.get('filing_evaluation_id')}`",
            f"- Source: `{r.get('source_id')}` / semantic object `{r.get('semantic_object_id')}`",
            f"- Original statement: {r.get('original_statement')}",
            f"- What needs corroboration: {r.get('what_needs_corroboration')}",
            f"- Corroboration strategy: {r.get('corroboration_strategy')}",
            f"- Suggested search queries: {', '.join(r.get('suggested_search_queries') or [])}",
            f"- Required source types: {', '.join(r.get('required_source_types') or [])}",
            f"- Corroboration findings: {', '.join(r.get('corroboration_findings') or [])}",
            f"- Current source support enough: `{r.get('current_source_support_enough')}`",
            f"- Corroboration status: `{r.get('corroboration_status')}`",
            f"- Recommended next stage: `{r.get('recommended_next_stage')}`",
            "- Explicit safety: advisory-only, not author-approved, not publication-approved.",
        ]
    lines += [
        "",
        "## Skipped items",
        "",
        "| source review id | source support | evidence use | next stage | skip reason |",
        "|---|---|---|---|---|",
    ]
    for item in payload["skipped_items"]:
        lines.append("| " + " | ".join([
            md_cell(item.get("source_review_id")),
            md_cell(item.get("source_support_decision")),
            md_cell(item.get("evidence_use_decision")),
            md_cell(item.get("next_stage_recommendation")),
            md_cell(item.get("skip_reason")),
        ]) + " |")
    lines += ["", "## Safety assessment", ""]
    for key in [
        "changed_db",
        "changed_docs_book",
        "changed_schema",
        "changed_daily_worker",
        "claims_inserted",
        "editorial_reviews_inserted",
        "source_status_changed",
        "claim_status_changed",
        "editorial_status_changed",
    ]:
        lines.append(f"- {key}: `{payload[key]}`")
    lines += [
        "- Why no DB/book/status changes were made: Run 12 is a report-only corroboration planning layer; later source collection or persistence must be explicitly scoped in a future run.",
        "",
        "## Recommendation for Run 13",
        "",
        f"- Recommendation: `{payload['next_run_recommendation']['recommendation']}`",
    ]
    for c in payload["next_run_recommendation"]["conditions"]:
        lines.append(f"- Condition: {c}")
    return "\n".join(lines) + "\n"


def write_reports(payload: dict[str, Any], output_dir: Path, suffix: str, *, json_only: bool, markdown_only: bool) -> dict[str, str]:
    output_dir = output_dir if output_dir.is_absolute() else REPO_ROOT / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{payload['run_id']}-corroboration-research-{suffix}" if suffix else f"{payload['run_id']}-corroboration-research"
    json_path = output_dir / f"{stem}.json"
    md_path = output_dir / f"{stem}.md"
    outputs = {"json": repo_relative(json_path), "markdown": repo_relative(md_path)}
    payload["output_paths"] = outputs
    if not markdown_only:
        write_json(json_path, payload)
    if not json_only:
        md_path.write_text(render_markdown(payload), encoding="utf-8")
    return outputs


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run 12 controlled report-only corroboration research planning.")
    p.add_argument("--run-id", default="latest")
    p.add_argument("--output-dir", default="reports/editorial")
    p.add_argument("--source-support-review-report", required=True)
    p.add_argument("--filing-novelty-report", default="")
    p.add_argument("--editor-packet-report", default="")
    p.add_argument("--quality-gate-report", default="")
    p.add_argument("--source-card-report", default="")
    p.add_argument("--semantic-object-report", default="")
    p.add_argument("--candidate-selection-report", default="")
    p.add_argument("--provider", default=DEFAULT_PROVIDER)
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--no-llm", action="store_true")
    p.add_argument("--require-high-reasoning", action="store_true")
    p.add_argument("--json-only", action="store_true")
    p.add_argument("--markdown-only", action="store_true")
    p.add_argument("--report-suffix", default="run12")
    args = p.parse_args(argv)
    if args.no_llm and args.require_high_reasoning:
        raise CorroborationError("--no-llm and --require-high-reasoning are mutually exclusive")
    if args.json_only and args.markdown_only:
        raise CorroborationError("--json-only and --markdown-only are mutually exclusive")
    if not args.no_llm and not args.require_high_reasoning:
        args.require_high_reasoning = True
    return args


def main(argv: list[str] | None = None) -> int:
    try:
        args = parse_args(argv or sys.argv[1:])
        source_support = load_json(resolve(args.source_support_review_report))
        validate_source_support_report(source_support)
        optional_inputs = {}
        for attr, label in [
            ("filing_novelty_report", "filing_novelty_report"),
            ("editor_packet_report", "editor_packet_report"),
            ("quality_gate_report", "quality_gate_report"),
            ("source_card_report", "source_card_report"),
            ("semantic_object_report", "semantic_object_report"),
            ("candidate_selection_report", "candidate_selection_report"),
        ]:
            value = getattr(args, attr)
            if value:
                # Validate JSON if provided, but only source-support report drives selection.
                load_json(resolve(value), required=True)
                optional_inputs[label] = repo_relative(resolve(value))
        payload = build_payload(args, source_support, optional_inputs)
        outputs = write_reports(payload, Path(args.output_dir), args.report_suffix, json_only=args.json_only, markdown_only=args.markdown_only)
        print(json.dumps({
            "status": "ok",
            "run_id": payload["run_id"],
            "outputs": outputs,
            "selected_items_count": payload["selected_items_count"],
            "reviewed_items_count": payload["reviewed_items_count"],
            "skipped_items_count": payload["skipped_items_count"],
            "llm_used": payload["llm_used"],
            "provider": payload["provider"],
            "model": payload["model"],
            "bridge": payload["bridge"],
            "status_counts": payload["status_counts"],
            "recommended_next_stage_counts": payload["recommended_next_stage_counts"],
            "changed_db": payload["changed_db"],
            "claims_inserted": payload["claims_inserted"],
            "editorial_reviews_inserted": payload["editorial_reviews_inserted"],
        }, indent=2, sort_keys=True))
        return 0
    except HighReasoningError as exc:
        print("ERROR: high-reasoning corroboration call failed; weak/local fallback refused; no DB writes attempted", file=sys.stderr)
        print(json.dumps(exc.result, sort_keys=True), file=sys.stderr)
        return 2
    except CorroborationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except sqlite3.Error as exc:
        print(f"ERROR: SQLite read-only inspection failed safely: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
