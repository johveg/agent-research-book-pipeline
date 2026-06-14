#!/usr/bin/env python3
"""Run 13 controlled corroboration source collection layer.

This script is report-only by default and intentionally does not mutate SQLite,
source registry, raw captures, docs/book, schema, daily worker, statuses, claims,
or editorial reviews. When no safe bounded collection input is provided, it
produces a collection plan rather than improvising uncontrolled browsing.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from research_common import DB_PATH as DEFAULT_DB_PATH, ROOT as REPO_ROOT, sha256_text, write_json  # noqa: E402

MODE = "corroboration_source_collection"
IMPORT_MODE = "corroboration_source_import"
DEFAULT_CURATED_CANDIDATES = "reports/editorial/citation-pipeline-test-20260612-curated-candidate-sources-run14.json"

ALLOWED_SOURCE_TYPES = {
    "primary_source",
    "official_report",
    "academic_paper",
    "reputable_industry_analysis",
    "reputable_news_or_magazine",
    "public_documentation",
    "public_original_interview",
}
SOURCE_TYPE_ALIASES = {
    "primary sources": "primary_source",
    "official reports": "official_report",
    "academic papers": "academic_paper",
    "reputable industry analysis": "reputable_industry_analysis",
    "reputable news or magazine sources": "reputable_news_or_magazine",
    "original interviews only if already public and attributable": "public_original_interview",
    "public documentation": "public_documentation",
}
DISALLOWED_SOURCE_TYPES = {
    "social_media_post",
    "seo_content_farm",
    "unsourced_blog_post",
    "scraped_repost",
    "ai_generated_summary",
    "vendor_marketing_page",
    "private_or_raw_capture",
    "unverifiable_screenshot",
    "unattributed_source",
}
DISALLOWED_SOURCE_TYPE_ALIASES = {
    "social media posts": "social_media_post",
    "SEO content farms": "seo_content_farm",
    "seo content farms": "seo_content_farm",
    "unsourced blog posts": "unsourced_blog_post",
    "scraped reposts": "scraped_repost",
    "AI-generated summaries": "ai_generated_summary",
    "ai-generated summaries": "ai_generated_summary",
    "vendor marketing pages": "vendor_marketing_page",
    "private/raw captures": "private_or_raw_capture",
    "unverifiable screenshots": "unverifiable_screenshot",
    "sources without stable attribution": "unattributed_source",
}
SUPPORT_DIRECTIONS = {"supports", "partially_supports", "contradicts", "context_only", "unclear"}
EVIDENCE_STRENGTHS = {"strong", "moderate", "weak", "unsuitable"}
COLLECTION_STATUSES = {
    "candidate_sources_collected",
    "no_suitable_sources_found",
    "collection_not_executed_tooling_unavailable",
    "collection_failed_closed",
}
ASSESSMENTS = {
    "enough_candidates_for_re_review",
    "needs_more_collection",
    "likely_exclude",
    "contradiction_requires_review",
}
NEXT_STAGES = {
    "run_source_support_re_review",
    "run_additional_source_collection",
    "needs_editor_review",
    "exclude_from_pipeline",
}


class CollectionError(RuntimeError):
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


def listify(value: Any, max_len: int = 220) -> list[str]:
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
            raise CollectionError(f"missing input report: {path}")
        return {}
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CollectionError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(obj, dict):
        raise CollectionError(f"input JSON must be an object: {path}")
    return obj


def validate_input_report(report: dict[str, Any]) -> str:
    mode = report.get("mode")
    if mode not in {"corroboration_research", "corroboration_source_collection"}:
        raise CollectionError("input report mode must be corroboration_research or corroboration_source_collection")
    if report.get("changed_db") not in (False, None):
        raise CollectionError("input report indicates DB changed; refusing")
    if report.get("claims_inserted") not in (0, None):
        raise CollectionError("input report indicates claims inserted; refusing")
    if report.get("editorial_reviews_inserted") not in (0, None):
        raise CollectionError("input report indicates editorial reviews inserted; refusing")
    if mode == "corroboration_research" and not isinstance(report.get("corroboration_reviews"), list):
        raise CollectionError("Run 12 report missing corroboration_reviews list")
    if mode == "corroboration_source_collection" and not isinstance(report.get("collection_results"), list):
        raise CollectionError("Run 13 report missing collection_results list")
    return str(mode)


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


def file_hash(rel: str) -> str:
    p = REPO_ROOT / rel
    return sha256_text(p.read_text(encoding="utf-8", errors="replace")) if p.exists() else ""


def raw_snapshot() -> dict[str, Any]:
    # Repository currently has no data/raw path. Keep this generic and read-only.
    candidates = [REPO_ROOT / "data" / "raw", REPO_ROOT / "raw", REPO_ROOT / "captures"]
    files: list[str] = []
    for root in candidates:
        if root.exists():
            for p in root.rglob("*"):
                if p.is_file():
                    files.append(repo_relative(p))
    return {"paths_checked": [repo_relative(p) for p in candidates], "file_count": len(files), "file_list_hash": sha256_text(json.dumps(sorted(files), ensure_ascii=False))}


def docs_book_snapshot() -> str:
    root = REPO_ROOT / "docs" / "book"
    rows = []
    if root.exists():
        for p in sorted(root.rglob("*")):
            if p.is_file():
                rows.append([repo_relative(p), sha256_text(p.read_text(encoding="utf-8", errors="replace"))])
    return sha256_text(json.dumps(rows, ensure_ascii=False))


def selection_reason(item: dict[str, Any]) -> str | None:
    if (
        item.get("recommended_next_stage") == "run_additional_source_collection"
        and item.get("evidence_use_decision") == "needs_more_sources"
        and item.get("corroboration_status") == "insufficient_evidence"
    ):
        return None
    # Run 13 collection-plan reports preserve the selection as collection_results,
    # not as full Run 12 corroboration decisions. For Run 14A, accept those
    # unresolved collection-plan items without requiring fields Run 13 omitted.
    if (
        item.get("recommended_next_stage") == "run_additional_source_collection"
        and item.get("source_collection_status") == "collection_not_executed_tooling_unavailable"
        and item.get("candidate_source_count") in {0, None}
    ):
        return None
    if item.get("recommended_next_stage") == "needs_editor_review":
        return "needs_editor_review_not_source_collection"
    if item.get("recommended_next_stage") == "eligible_for_review_note_persistence":
        return "not_additional_source_collection_candidate"
    return "not_additional_source_collection_candidate"


def report_items(report: dict[str, Any]) -> list[dict[str, Any]]:
    if report.get("mode") == "corroboration_source_collection":
        return [i for i in report.get("collection_results", []) if isinstance(i, dict)]
    return [i for i in report.get("corroboration_reviews", []) if isinstance(i, dict)]


def select_items(report: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    selected: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for item in report_items(report):
        if not isinstance(item, dict):
            skipped.append({"source_review_id": "unknown", "skip_reason": "not_object"})
            continue
        reason = selection_reason(item)
        row = {
            "item_id": item.get("item_id", ""),
            "source_review_id": item.get("source_review_id", ""),
            "source_id": item.get("source_id", ""),
            "corroboration_status": item.get("corroboration_status", ""),
            "evidence_use_decision": item.get("evidence_use_decision", ""),
            "recommended_next_stage": item.get("recommended_next_stage", ""),
        }
        if reason is None:
            selected.append(item)
        else:
            row["skip_reason"] = reason
            skipped.append(row)
    if report.get("mode") == "corroboration_source_collection":
        seen = {s.get("source_review_id") for s in skipped} | {s.get("source_review_id") for s in selected}
        for item in report.get("skipped_items", []):
            if isinstance(item, dict) and item.get("source_review_id") not in seen:
                row = {
                    "item_id": item.get("item_id", ""),
                    "source_review_id": item.get("source_review_id", ""),
                    "source_id": item.get("source_id", ""),
                    "corroboration_status": item.get("corroboration_status", ""),
                    "evidence_use_decision": item.get("evidence_use_decision", ""),
                    "recommended_next_stage": item.get("recommended_next_stage", ""),
                    "skip_reason": item.get("skip_reason") or selection_reason(item) or "not_additional_source_collection_candidate",
                }
                skipped.append(row)
    return selected, skipped


def candidate_id(item_id: str, url: str) -> str:
    return "cand_" + sha256_text(f"{item_id}|{url.strip().lower()}")[:24]


def normalize_source_type(value: Any) -> str:
    text = clean_text(value, 120)
    lower = text.lower()
    if text in ALLOWED_SOURCE_TYPES or lower in ALLOWED_SOURCE_TYPES:
        return lower if lower in ALLOWED_SOURCE_TYPES else text
    if text in DISALLOWED_SOURCE_TYPES or lower in DISALLOWED_SOURCE_TYPES:
        return lower if lower in DISALLOWED_SOURCE_TYPES else text
    if text in SOURCE_TYPE_ALIASES:
        return SOURCE_TYPE_ALIASES[text]
    if lower in SOURCE_TYPE_ALIASES:
        return SOURCE_TYPE_ALIASES[lower]
    if text in DISALLOWED_SOURCE_TYPE_ALIASES:
        return DISALLOWED_SOURCE_TYPE_ALIASES[text]
    if lower in DISALLOWED_SOURCE_TYPE_ALIASES:
        return DISALLOWED_SOURCE_TYPE_ALIASES[lower]
    return text


def stable_public_url(url: str) -> bool:
    return url.startswith("https://") or url.startswith("http://")


def validate_candidate(raw: dict[str, Any], selected_by_sr: dict[str, dict[str, Any]], selected_by_item: dict[str, dict[str, Any]]) -> tuple[dict[str, Any] | None, str | None]:
    if not isinstance(raw, dict):
        return None, "candidate_not_object"
    item_id = str(raw.get("item_id") or "")
    srid = str(raw.get("source_review_id") or "")
    item = selected_by_item.get(item_id) or selected_by_sr.get(srid)
    if not item:
        return None, "candidate_for_unselected_item"
    url = clean_text(raw.get("url"), 1000)
    title = clean_text(raw.get("title"), 220)
    if not url or not title:
        return None, "missing_title_or_url"
    if not stable_public_url(url):
        return None, "invalid_public_url"
    if raw.get("raw_content_stored") is not False:
        return None, "raw_content_stored_not_false"
    if clean_text(raw.get("access_type"), 80) != "public":
        return None, "access_type_not_public"
    if not clean_text(raw.get("publisher"), 160):
        return None, "missing_publisher"
    stype = normalize_source_type(raw.get("source_type"))
    if stype in DISALLOWED_SOURCE_TYPES:
        return None, "disallowed_source_type"
    if stype not in ALLOWED_SOURCE_TYPES:
        return None, "unknown_source_type"
    support = clean_text(raw.get("support_direction"), 80)
    strength = clean_text(raw.get("evidence_strength"), 80)
    if support not in SUPPORT_DIRECTIONS:
        return None, "invalid_support_direction"
    if strength not in EVIDENCE_STRENGTHS:
        return None, "invalid_evidence_strength"
    if strength == "unsuitable":
        return None, "unsuitable_evidence_strength"
    out = {
        "candidate_source_id": candidate_id(item.get("item_id") or item_id, url),
        "item_id": item.get("item_id") or item_id,
        "source_review_id": item.get("source_review_id") or srid,
        "source_id": item.get("source_id", ""),
        "title": title,
        "url": url,
        "publisher": clean_text(raw.get("publisher"), 160),
        "author": clean_text(raw.get("author"), 160),
        "publication_date": clean_text(raw.get("publication_date"), 80),
        "retrieved_at": utc_now(),
        "source_type": stype,
        "access_type": "public",
        "candidate_relevance": clean_text(raw.get("candidate_relevance"), 320),
        "support_direction": support,
        "evidence_strength": strength,
        "reason_for_inclusion": clean_text(raw.get("reason_for_inclusion"), 320),
        "limitations": clean_text(raw.get("limitations"), 320),
        "safe_summary": clean_text(raw.get("safe_summary"), 500),
        "raw_content_stored": False,
    }
    return out, None


def load_candidates(path: str, selected: list[dict[str, Any]], max_per_item: int, *, require_candidates: bool = False) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]], bool, str, int, int]:
    if not path:
        if require_candidates:
            raise CollectionError("curated candidate-source JSON is required for Run 14A")
        return {}, [], False, "collection_plan_only_tooling_unavailable", 0, 0
    resolved = resolve(path)
    if not resolved.exists() and require_candidates:
        raise CollectionError(f"curated candidate-source JSON missing: {resolved}")
    obj = load_json(resolved)
    raw_candidates = obj.get("candidate_sources")
    if not isinstance(raw_candidates, list):
        raise CollectionError("candidate sources JSON must contain candidate_sources list")
    selected_by_sr = {str(i.get("source_review_id")): i for i in selected}
    selected_by_item = {str(i.get("item_id")): i for i in selected}
    by_item: dict[str, list[dict[str, Any]]] = defaultdict(list)
    rejected: list[dict[str, Any]] = []
    seen_urls_by_item: dict[str, set[str]] = defaultdict(set)
    seen_url_global: dict[str, str] = {}
    for raw in raw_candidates:
        cand, reason = validate_candidate(raw, selected_by_sr, selected_by_item)
        if cand is None:
            rejected.append({"reason": reason, "source_review_id": raw.get("source_review_id") if isinstance(raw, dict) else "", "url": raw.get("url") if isinstance(raw, dict) else ""})
            continue
        item_id = cand["item_id"]
        url_key = cand["url"].strip().lower()
        if url_key in seen_urls_by_item[item_id]:
            rejected.append({"reason": "duplicate_url_for_item", "source_review_id": cand["source_review_id"], "url": cand["url"]})
            continue
        if url_key in seen_url_global and seen_url_global[url_key] != item_id:
            rejected.append({"reason": "duplicate_url_across_items", "source_review_id": cand["source_review_id"], "url": cand["url"], "first_item_id": seen_url_global[url_key]})
            continue
        if len(by_item[item_id]) >= max_per_item:
            rejected.append({"reason": "bounded_collection_limit_enforced", "source_review_id": cand["source_review_id"], "url": cand["url"]})
            continue
        seen_urls_by_item[item_id].add(url_key)
        seen_url_global[url_key] = item_id
        by_item[item_id].append(cand)
    accepted_count = sum(len(v) for v in by_item.values())
    return dict(by_item), rejected, True, "curated_candidate_json_import" if require_candidates else "bounded_candidate_json_import", len(raw_candidates), accepted_count


def assessment_for(cands: list[dict[str, Any]]) -> tuple[str, str, list[str], list[str]]:
    if not cands:
        return "needs_more_collection", "run_additional_source_collection", [], []
    contradiction = [c["candidate_source_id"] for c in cands if c["support_direction"] == "contradicts"]
    strongest = [c["candidate_source_id"] for c in cands if c["evidence_strength"] in {"strong", "moderate"} and c["support_direction"] in {"supports", "partially_supports", "context_only"}]
    if contradiction:
        return "contradiction_requires_review", "needs_editor_review", strongest, contradiction
    if strongest:
        return "enough_candidates_for_re_review", "run_source_support_re_review", strongest, contradiction
    return "needs_more_collection", "run_additional_source_collection", strongest, contradiction


def build_result(item: dict[str, Any], cands: list[dict[str, Any]], collection_executed: bool) -> dict[str, Any]:
    strongest, contradictions = [], []
    if collection_executed:
        if cands:
            status = "candidate_sources_collected"
        else:
            status = "no_suitable_sources_found"
        assessment, next_stage, strongest, contradictions = assessment_for(cands)
    else:
        status = "collection_not_executed_tooling_unavailable"
        assessment = "needs_more_collection"
        next_stage = "run_additional_source_collection"
    return {
        "item_id": item.get("item_id", ""),
        "source_review_id": item.get("source_review_id", ""),
        "source_id": item.get("source_id", ""),
        "original_statement": clean_text(item.get("original_statement"), 500),
        "what_needs_corroboration": clean_text(item.get("what_needs_corroboration"), 500),
        "search_queries_used": listify(item.get("suggested_search_queries"), 200),
        "source_types_requested": listify(item.get("required_source_types"), 160),
        "candidate_sources": cands,
        "candidate_source_count": len(cands),
        "strongest_candidate_source_ids": strongest,
        "contradiction_candidate_source_ids": contradictions,
        "source_collection_status": status,
        "preliminary_collection_assessment": assessment,
        "recommended_next_stage": next_stage,
        "advisory_only": True,
        "author_allowed": False,
        "publication_approved": False,
    }


def build_payload(args: argparse.Namespace, run12: dict[str, Any], optional_inputs: dict[str, str]) -> dict[str, Any]:
    selected, skipped = select_items(run12)
    con = connect_readonly()
    try:
        db_before = {"sources": table_count(con, "sources"), "source_notes": table_count(con, "source_notes"), "claims": table_count(con, "claims"), "editorial_reviews": table_count(con, "editorial_reviews")}
        hashes_before = status_hashes(con)
        registry_before = file_hash("data/source_registry.json")
        schema_before = file_hash("data/schema.sql")
        worker_before = file_hash("scripts/daily_book_worker.py")
        raw_before = raw_snapshot()
        docs_before = docs_book_snapshot()
        cands_by_item, rejected_candidates, executed, method, submitted_count, accepted_count = load_candidates(args.candidate_sources_json, selected, args.max_candidates_per_item, require_candidates=args.require_candidate_sources)
        results = [build_result(i, cands_by_item.get(i.get("item_id", ""), []), executed) for i in selected]
        db_after = {"sources": table_count(con, "sources"), "source_notes": table_count(con, "source_notes"), "claims": table_count(con, "claims"), "editorial_reviews": table_count(con, "editorial_reviews")}
        hashes_after = status_hashes(con)
    finally:
        if con is not None:
            con.close()
    registry_after = file_hash("data/source_registry.json")
    schema_after = file_hash("data/schema.sql")
    worker_after = file_hash("scripts/daily_book_worker.py")
    raw_after = raw_snapshot()
    docs_after = docs_book_snapshot()
    all_cands = [c for item in results for c in item["candidate_sources"]]
    changed_db = db_before != db_after
    source_status_changed = hashes_before["sources_status_hash"] != hashes_after["sources_status_hash"]
    claim_status_changed = hashes_before["claims_status_hash"] != hashes_after["claims_status_hash"]
    editorial_status_changed = hashes_before["editorial_reviews_hash"] != hashes_after["editorial_reviews_hash"]
    payload = {
        "run_id": args.run_id if args.run_id != "latest" else run12.get("run_id", "latest"),
        "generated_at": utc_now(),
        "mode": IMPORT_MODE if args.require_candidate_sources else MODE,
        "input_paths": {"corroboration_research_report": repo_relative(resolve(args.corroboration_research_report)), **optional_inputs},
        "selected_items_count": len(selected),
        "skipped_items_count": len(skipped),
        "collected_candidate_sources_count": len(all_cands),
        "candidate_sources_json": repo_relative(resolve(args.candidate_sources_json)) if args.candidate_sources_json else "",
        "candidate_sources_submitted_count": submitted_count,
        "candidate_sources_accepted_count": accepted_count,
        "candidate_sources_rejected_count": len(rejected_candidates),
        "duplicate_url_count": sum(1 for r in rejected_candidates if r.get("reason") in {"duplicate_url_for_item", "duplicate_url_across_items"}),
        "source_collection_executed": executed,
        "collection_method": method,
        "report_only": True,
        "changed_db": changed_db,
        "changed_source_registry": registry_before != registry_after,
        "changed_raw_captures": raw_before != raw_after,
        "changed_docs_book": docs_before != docs_after,
        "changed_schema": schema_before != schema_after,
        "changed_daily_worker": worker_before != worker_after,
        "claims_inserted": max(0, db_after.get("claims", 0) - db_before.get("claims", 0)),
        "editorial_reviews_inserted": max(0, db_after.get("editorial_reviews", 0) - db_before.get("editorial_reviews", 0)),
        "source_status_changed": source_status_changed,
        "claim_status_changed": claim_status_changed,
        "editorial_status_changed": editorial_status_changed,
        "selected_items": [{"item_id": i.get("item_id"), "source_review_id": i.get("source_review_id"), "source_id": i.get("source_id"), "corroboration_status": i.get("corroboration_status"), "evidence_use_decision": i.get("evidence_use_decision"), "recommended_next_stage": i.get("recommended_next_stage")} for i in selected],
        "skipped_items": skipped,
        "collection_results": results,
        "candidate_sources_by_item": {r["item_id"]: r["candidate_sources"] for r in results},
        "candidate_source_type_counts": dict(sorted(Counter(c["source_type"] for c in all_cands).items())),
        "support_direction_counts": dict(sorted(Counter(c["support_direction"] for c in all_cands).items())),
        "evidence_strength_counts": dict(sorted(Counter(c["evidence_strength"] for c in all_cands).items())),
        "preliminary_collection_assessment_counts": dict(sorted(Counter(r["preliminary_collection_assessment"] for r in results).items())),
        "recommended_next_stage_counts": dict(sorted(Counter(r["recommended_next_stage"] for r in results).items())),
        "rejected_candidate_sources": rejected_candidates,
        "db_counts_before": db_before,
        "db_counts_after": db_after,
        "status_hashes_before": hashes_before,
        "status_hashes_after": hashes_after,
        "source_registry_hash_before": registry_before,
        "source_registry_hash_after": registry_after,
        "raw_capture_snapshot_before": raw_before,
        "raw_capture_snapshot_after": raw_after,
        "schema_hash_before": schema_before,
        "schema_hash_after": schema_after,
        "daily_worker_hash_before": worker_before,
        "daily_worker_hash_after": worker_after,
        "safety_flags": {
            "advisory_only": True,
            "author_allowed": False,
            "publication_approved": False,
            "raw_content_stored": False,
            "no_db_writes": True,
            "no_source_registry_writes": True,
            "no_raw_capture_writes": True,
            "no_claim_insertion": True,
            "no_editorial_review_insertion": True,
            "no_status_changes": True,
            "no_docs_book_changes": True,
            "no_schema_changes": True,
            "no_daily_worker_changes": True,
        },
        "limitations": [
            "Candidate links are not source-registry entries and are not validated support.",
            "Run 13 stores no raw page content and performs no persistence.",
            "When no bounded candidate input is supplied, collection is not executed and the report contains a plan only.",
        ],
        "next_run_recommendation": recommend_run14(results),
    }
    forbidden = ["changed_db", "changed_source_registry", "changed_raw_captures", "changed_docs_book", "changed_schema", "changed_daily_worker", "source_status_changed", "claim_status_changed", "editorial_status_changed"]
    if any(payload[k] for k in forbidden) or payload["claims_inserted"] or payload["editorial_reviews_inserted"]:
        raise CollectionError("forbidden side effect detected during report-only run")
    return payload


def recommend_run14(results: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(r["recommended_next_stage"] for r in results)
    if counts.get("run_source_support_re_review", 0):
        rec = "source_support_re_review_for_collected_candidates"
    elif counts.get("run_additional_source_collection", 0):
        rec = "rerun_controlled_source_collection_with_safe_tooling_or_curated_candidate_json"
    elif counts.get("needs_editor_review", 0):
        rec = "editor_review_for_contradictions_or_source_context"
    else:
        rec = "exclude_or_stop_due_to_source_collection_risk"
    return {
        "recommendation": rec,
        "conditions": [
            "remain report-only by default",
            "do not persist candidate sources as source-registry entries without a later explicit persistence design",
            "do not create narrative packets until source-support re-review passes or items are explicitly excluded",
        ],
    }


def md(v: Any) -> str:
    return clean_text(v, 100).replace("|", "\\|")


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [f"# Corroboration source collection: {payload['run_id']}", "", "## Executive summary", ""]
    for k in ["selected_items_count", "skipped_items_count", "collected_candidate_sources_count", "source_collection_executed", "collection_method"]:
        lines.append(f"- {k}: `{payload[k]}`")
    lines += [
        f"- Source type counts: `{payload['candidate_source_type_counts']}`",
        f"- Support direction counts: `{payload['support_direction_counts']}`",
        f"- Evidence strength counts: `{payload['evidence_strength_counts']}`",
        f"- Recommended next-stage counts: `{payload['recommended_next_stage_counts']}`",
        "- Safety: report-only; no DB/source-registry/raw-capture/book/schema/daily-worker/status changes; no claims/editorial-review inserts.",
        "",
        "## Selected items",
        "",
        "| item id | source review id | status | evidence use | Run 12 next stage |",
        "|---|---|---|---|---|",
    ]
    for i in payload["selected_items"]:
        lines.append("| " + " | ".join([md(i.get("item_id")), md(i.get("source_review_id")), md(i.get("corroboration_status")), md(i.get("evidence_use_decision")), md(i.get("recommended_next_stage"))]) + " |")
    lines += ["", "## Skipped items", "", "| item id | source review id | reason |", "|---|---|---|"]
    for i in payload["skipped_items"]:
        lines.append("| " + " | ".join([md(i.get("item_id")), md(i.get("source_review_id")), md(i.get("skip_reason"))]) + " |")
    lines += ["", "## Collection results"]
    for r in payload["collection_results"]:
        lines += [
            "",
            f"### {r['source_review_id']}",
            f"- Original statement: {r['original_statement']}",
            f"- What needs corroboration: {r['what_needs_corroboration']}",
            f"- Queries used/planned: {', '.join(r['search_queries_used'])}",
            f"- Source types requested: {', '.join(r['source_types_requested'])}",
            f"- Candidate source count: `{r['candidate_source_count']}`",
            f"- Collection status: `{r['source_collection_status']}`",
            f"- Preliminary assessment: `{r['preliminary_collection_assessment']}`",
            f"- Recommended next stage: `{r['recommended_next_stage']}`",
        ]
        for c in r["candidate_sources"]:
            lines += [
                f"  - `{c['candidate_source_id']}` — [{c['title']}]({c['url']})",
                f"    - publisher: {c['publisher']}; type: `{c['source_type']}`; direction: `{c['support_direction']}`; strength: `{c['evidence_strength']}`",
                f"    - safe summary: {c['safe_summary']}",
            ]
    lines += [
        "",
        "## Limitations",
        "",
    ]
    lines += [f"- {x}" for x in payload["limitations"]]
    lines += ["", "## Safety confirmations", ""]
    for k in ["changed_db", "changed_source_registry", "changed_raw_captures", "changed_docs_book", "changed_schema", "changed_daily_worker", "claims_inserted", "editorial_reviews_inserted", "source_status_changed", "claim_status_changed", "editorial_status_changed"]:
        lines.append(f"- {k}: `{payload[k]}`")
    lines += ["", "## Recommended Run 14", "", f"- Recommendation: `{payload['next_run_recommendation']['recommendation']}`"]
    for c in payload["next_run_recommendation"]["conditions"]:
        lines.append(f"- Condition: {c}")
    return "\n".join(lines) + "\n"


def write_reports(payload: dict[str, Any], output_dir: Path, suffix: str, *, json_only: bool, markdown_only: bool) -> dict[str, str]:
    output_dir = output_dir if output_dir.is_absolute() else REPO_ROOT / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    kind = "corroboration-source-import" if payload.get("mode") == IMPORT_MODE else "corroboration-source-collection"
    stem = f"{payload['run_id']}-{kind}-{suffix}" if suffix else f"{payload['run_id']}-{kind}"
    json_path = output_dir / f"{stem}.json"
    md_path = output_dir / f"{stem}.md"
    outputs = {"json": repo_relative(json_path), "markdown": repo_relative(md_path)}
    payload["output_paths"] = outputs
    if not markdown_only:
        write_json(json_path, payload)
    if not json_only:
        md_path.write_text(render_markdown(payload), encoding="utf-8")
    return outputs



def missing_candidate_payload(args: argparse.Namespace, report: dict[str, Any], optional_inputs: dict[str, str]) -> dict[str, Any]:
    selected, skipped = select_items(report)
    cand_path = resolve(args.candidate_sources_json)
    return {
        "run_id": args.run_id if args.run_id != "latest" else report.get("run_id", "latest"),
        "generated_at": utc_now(),
        "mode": IMPORT_MODE,
        "input_paths": {"corroboration_research_report": repo_relative(resolve(args.corroboration_research_report)), **optional_inputs},
        "candidate_sources_json": repo_relative(cand_path),
        "candidate_json_present": False,
        "selected_items_count": len(selected),
        "skipped_items_count": len(skipped),
        "candidate_sources_submitted_count": 0,
        "candidate_sources_accepted_count": 0,
        "candidate_sources_rejected_count": 0,
        "collected_candidate_sources_count": 0,
        "duplicate_url_count": 0,
        "source_collection_executed": False,
        "collection_method": "curated_candidate_json_missing",
        "report_only": True,
        "changed_db": False,
        "changed_source_registry": False,
        "changed_raw_captures": False,
        "changed_docs_book": False,
        "changed_schema": False,
        "changed_daily_worker": False,
        "claims_inserted": 0,
        "editorial_reviews_inserted": 0,
        "source_status_changed": False,
        "claim_status_changed": False,
        "editorial_status_changed": False,
        "selected_items": [{"item_id": i.get("item_id"), "source_review_id": i.get("source_review_id"), "source_id": i.get("source_id"), "corroboration_status": i.get("corroboration_status"), "evidence_use_decision": i.get("evidence_use_decision"), "recommended_next_stage": i.get("recommended_next_stage")} for i in selected],
        "skipped_items": skipped,
        "collection_results": [build_result(i, [], False) for i in selected],
        "candidate_sources_by_item": {},
        "rejected_candidate_sources": [{"reason": "curated_candidate_json_missing", "path": repo_relative(cand_path)}],
        "candidate_source_type_counts": {},
        "support_direction_counts": {},
        "evidence_strength_counts": {},
        "preliminary_collection_assessment_counts": {"needs_more_collection": len(selected)} if selected else {},
        "recommended_next_stage_counts": {"run_additional_source_collection": len(selected)} if selected else {},
        "safety_flags": {"advisory_only": True, "author_allowed": False, "publication_approved": False, "raw_content_stored": False, "no_db_writes": True, "no_source_registry_writes": True, "no_raw_capture_writes": True, "no_claim_insertion": True, "no_editorial_review_insertion": True, "no_status_changes": True, "no_docs_book_changes": True, "no_schema_changes": True, "no_daily_worker_changes": True},
        "limitations": ["Curated candidate-source JSON was required but missing; no candidates were imported.", "Candidate sources must be provided explicitly or via a separately designed safe collector."],
        "next_run_recommendation": {"recommendation": "provide_curated_candidate_sources_json_then_rerun_run14a", "conditions": ["remain report-only", "do not treat candidate links as source-registry entries", "do not create narrative packets"]},
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run 13 controlled report-only corroboration source collection layer.")
    p.add_argument("--run-id", default="latest")
    p.add_argument("--output-dir", default="reports/editorial")
    p.add_argument("--corroboration-research-report", required=True)
    p.add_argument("--source-support-review-report", default="")
    p.add_argument("--filing-novelty-report", default="")
    p.add_argument("--editor-packet-report", default="")
    p.add_argument("--quality-gate-report", default="")
    p.add_argument("--source-card-report", default="")
    p.add_argument("--semantic-object-report", default="")
    p.add_argument("--candidate-selection-report", default="")
    p.add_argument("--candidate-sources-json", default="", help="Optional bounded curated candidate-source JSON. No live browsing is performed without this.")
    p.add_argument("--require-candidate-sources", action="store_true", help="Run 14A mode: fail closed if curated candidate-source JSON is missing.")
    p.add_argument("--max-candidates-per-item", type=int, default=5)
    p.add_argument("--json-only", action="store_true")
    p.add_argument("--markdown-only", action="store_true")
    p.add_argument("--report-suffix", default="run13")
    args = p.parse_args(argv)
    if args.require_candidate_sources and not args.candidate_sources_json:
        args.candidate_sources_json = DEFAULT_CURATED_CANDIDATES
    if args.max_candidates_per_item < 0 or args.max_candidates_per_item > 5:
        raise CollectionError("--max-candidates-per-item must be between 0 and 5")
    if args.json_only and args.markdown_only:
        raise CollectionError("--json-only and --markdown-only are mutually exclusive")
    return args


def main(argv: list[str] | None = None) -> int:
    try:
        args = parse_args(argv or sys.argv[1:])
        run12 = load_json(resolve(args.corroboration_research_report))
        validate_input_report(run12)
        optional = {}
        for attr, label in [
            ("source_support_review_report", "source_support_review_report"),
            ("filing_novelty_report", "filing_novelty_report"),
            ("editor_packet_report", "editor_packet_report"),
            ("quality_gate_report", "quality_gate_report"),
            ("source_card_report", "source_card_report"),
            ("semantic_object_report", "semantic_object_report"),
            ("candidate_selection_report", "candidate_selection_report"),
        ]:
            value = getattr(args, attr)
            if value:
                load_json(resolve(value), required=True)
                optional[label] = repo_relative(resolve(value))
        if args.require_candidate_sources and not resolve(args.candidate_sources_json).exists():
            payload = missing_candidate_payload(args, run12, optional)
            outputs = write_reports(payload, Path(args.output_dir), args.report_suffix, json_only=args.json_only, markdown_only=args.markdown_only)
            print(json.dumps({"status": "blocked", "error": "curated candidate-source JSON missing", "outputs": outputs, "candidate_sources_json": payload["candidate_sources_json"], "selected_items_count": payload["selected_items_count"], "skipped_items_count": payload["skipped_items_count"]}, indent=2, sort_keys=True))
            return 2
        payload = build_payload(args, run12, optional)
        outputs = write_reports(payload, Path(args.output_dir), args.report_suffix, json_only=args.json_only, markdown_only=args.markdown_only)
        print(json.dumps({
            "status": "ok",
            "run_id": payload["run_id"],
            "outputs": outputs,
            "selected_items_count": payload["selected_items_count"],
            "skipped_items_count": payload["skipped_items_count"],
            "collected_candidate_sources_count": payload["collected_candidate_sources_count"],
            "candidate_sources_submitted_count": payload["candidate_sources_submitted_count"],
            "candidate_sources_accepted_count": payload["candidate_sources_accepted_count"],
            "candidate_sources_rejected_count": payload["candidate_sources_rejected_count"],
            "duplicate_url_count": payload["duplicate_url_count"],
            "source_collection_executed": payload["source_collection_executed"],
            "collection_method": payload["collection_method"],
            "candidate_source_type_counts": payload["candidate_source_type_counts"],
            "support_direction_counts": payload["support_direction_counts"],
            "evidence_strength_counts": payload["evidence_strength_counts"],
            "preliminary_collection_assessment_counts": payload.get("preliminary_collection_assessment_counts", {}),
            "recommended_next_stage_counts": payload["recommended_next_stage_counts"],
            "changed_db": payload["changed_db"],
            "claims_inserted": payload["claims_inserted"],
            "editorial_reviews_inserted": payload["editorial_reviews_inserted"],
        }, indent=2, sort_keys=True))
        return 0
    except CollectionError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except sqlite3.Error as exc:
        print(f"ERROR: SQLite read-only inspection failed safely: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
