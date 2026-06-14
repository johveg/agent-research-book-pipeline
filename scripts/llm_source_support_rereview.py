#!/usr/bin/env python3
"""Run 15 GPT-5.5 source-support re-review using accepted curated candidate sources.

Advisory/report-only: no DB writes, no source registry writes, no raw capture writes,
no docs/book edits, no schema/daily-worker changes, no claims/editorial_reviews/status changes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
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

RUN_ID_DEFAULT = "citation-pipeline-test-20260612"
MODE = "source_support_rereview"
BRIDGE = "hermes_cli"

DEFAULT_IMPORT = "reports/editorial/citation-pipeline-test-20260612-corroboration-source-import-run14.json"
DEFAULT_CURATED = "reports/editorial/citation-pipeline-test-20260612-curated-candidate-sources-run14.json"
DEFAULT_RUN13 = "reports/editorial/citation-pipeline-test-20260612-corroboration-source-collection-run13.json"
DEFAULT_RUN12 = "reports/editorial/citation-pipeline-test-20260612-corroboration-research-run12.json"
DEFAULT_RUN10 = "reports/editorial/citation-pipeline-test-20260612-source-support-review-run10.json"
DEFAULT_RUN9 = "reports/editorial/citation-pipeline-test-20260612-filing-novelty-evaluation-run9.json"
DEFAULT_RUN8 = "reports/editorial/citation-pipeline-test-20260612-editor-review-packet-run8.json"
DEFAULT_RUN7_QUALITY = "reports/editorial/citation-pipeline-test-20260612-quality-gate-run7-full.json"
DEFAULT_RUN7_CARDS = "reports/editorial/citation-pipeline-test-20260612-source-card-drafts-high-reasoning-run7.json"
DEFAULT_RUN7_OBJECTS = "reports/editorial/citation-pipeline-test-20260612-semantic-object-drafts-high-reasoning-run7.json"
DEFAULT_SELECTION = "reports/editorial/citation-pipeline-test-20260612-reasoning-candidate-selection.json"

ALLOWED_SUPPORT = {"supported", "partially_supported", "weakly_supported", "unsupported", "contradicted", "source_context_unclear"}
ALLOWED_CORROBORATION = {"corroborated", "partially_corroborated", "not_corroborated", "contradiction_found", "insufficient_evidence", "source_context_unclear"}
ALLOWED_EVIDENCE_USE = {"eligible_as_caveat_only_after_corroboration", "eligible_for_filing_later_after_corroboration", "needs_more_sources", "needs_source_review", "do_not_use", "contradiction_requires_editor_review"}
ALLOWED_NEXT = {"eligible_for_review_note_persistence", "run_additional_source_collection", "needs_editor_review", "exclude_from_pipeline", "contradiction_review_required"}
ALLOWED_SOURCE_TYPES = {"public_documentation", "official_documentation", "official_repository", "release_notes", "public_blog", "public_article", "public_code"}
DISALLOWED_SOURCE_TYPES = {"social_media", "linkedin", "private_capture", "raw_capture", "ai_summary", "seo_farm", "screenshot", "unverifiable_repost"}


class Run15Error(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def resolve(path: str | Path) -> Path:
    p = Path(path)
    return p if p.is_absolute() else ROOT / p


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise Run15Error(f"missing input report: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise Run15Error(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise Run15Error(f"input report must be object: {path}")
    return data


def sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else "missing"


def tree_snapshot(path: Path) -> dict[str, Any]:
    files = sorted(p for p in path.rglob("*") if p.is_file()) if path.exists() else []
    h = hashlib.sha256("\n".join(str(p.relative_to(ROOT)) for p in files).encode()).hexdigest()
    return {"file_count": len(files), "file_list_hash": h}


def db_counts_and_hashes() -> tuple[dict[str, int], dict[str, str]]:
    db = ROOT / ".var" / "book.sqlite"
    counts = {"claims": 0, "editorial_reviews": 0, "source_notes": 0, "sources": 0}
    hashes: dict[str, str] = {}
    if not db.exists():
        return counts, hashes
    con = sqlite3.connect(f"file:{db.resolve()}?mode=ro", uri=True)
    try:
        for table in counts:
            try:
                counts[table] = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            except sqlite3.Error:
                counts[table] = 0
        queries = {
            "sources_status_hash": "SELECT id, quality_score, privacy_publication_status, duplicate_status FROM sources ORDER BY id",
            "claims_status_hash": "SELECT id, status, publication_decision, contradiction_status FROM claims ORDER BY id",
            "editorial_reviews_hash": "SELECT id, run_id, review_type, status, summary, report_path, created_at FROM editorial_reviews ORDER BY id",
        }
        for key, query in queries.items():
            try:
                rows = con.execute(query).fetchall()
            except sqlite3.Error:
                rows = []
            hashes[key] = hashlib.sha256(json.dumps(rows, sort_keys=True, default=str).encode()).hexdigest()
    finally:
        con.close()
    return counts, hashes


def validate_import_report(data: dict[str, Any]) -> None:
    if data.get("mode") != "corroboration_source_import":
        raise Run15Error("Run 14 import report mode mismatch")
    for k in ["report_only", "changed_db", "changed_source_registry", "changed_raw_captures", "changed_docs_book", "changed_schema", "changed_daily_worker"]:
        if k == "report_only":
            if data.get(k) is not True:
                raise Run15Error("Run 14 import report must be report_only=true")
        elif data.get(k) is not False:
            raise Run15Error(f"Run 14 import report unsafe flag: {k}")


def candidate_ok(c: dict[str, Any]) -> tuple[bool, str]:
    if c.get("raw_content_stored") is not False:
        return False, "raw_content_stored_candidate_ignored"
    if c.get("access_type") != "public":
        return False, "non_public_candidate_ignored"
    if not c.get("url") or not c.get("title"):
        return False, "missing_url_or_title_candidate_ignored"
    st = str(c.get("source_type") or "")
    if st in DISALLOWED_SOURCE_TYPES or (st and st not in ALLOWED_SOURCE_TYPES and st != "public_documentation"):
        return False, "disallowed_source_type_candidate_ignored"
    return True, "accepted"


def run10_index(run10: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(r.get("source_review_id")): r for r in run10.get("source_reviews", []) if r.get("source_review_id")}


def curated_item_index(curated: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(i.get("source_review_id")): i for i in curated.get("items", []) if i.get("source_review_id")}


def source_collection_index(*reports: dict[str, Any]) -> dict[str, dict[str, Any]]:
    idx: dict[str, dict[str, Any]] = {}
    for report in reports:
        for r in report.get("collection_results", []) or []:
            if r.get("source_review_id"):
                idx[str(r["source_review_id"])] = r
    return idx


def build_candidates_by_review(import_report: dict[str, Any], curated: dict[str, Any]) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    by_review: dict[str, list[dict[str, Any]]] = {}
    rejected: list[dict[str, Any]] = []
    import_rejected_keys = {
        (str(r.get("source_review_id") or ""), str(r.get("url") or "").strip().lower())
        for r in import_report.get("rejected_candidate_sources", []) or []
        if r.get("source_review_id") and r.get("url")
    }
    all_candidates: list[dict[str, Any]] = []
    for r in import_report.get("collection_results", []) or []:
        all_candidates.extend(r.get("candidate_sources", []) or [])
    all_candidates.extend(curated.get("candidate_sources", []) or [])
    seen = set()
    for c in all_candidates:
        if not isinstance(c, dict):
            continue
        rid = str(c.get("source_review_id") or "")
        url_key = str(c.get("url") or "").strip().lower()
        id_key = str(c.get("candidate_source_id") or "").strip().lower()
        key = (rid, url_key or id_key)
        if not rid or not key[1] or key in seen:
            continue
        seen.add(key)
        if (rid, url_key) in import_rejected_keys:
            rejected.append({"source_review_id": rid, "candidate_source_id": c.get("candidate_source_id"), "url": c.get("url"), "reason": "run14_import_rejected_candidate_ignored"})
            continue
        ok, reason = candidate_ok(c)
        if not ok:
            rejected.append({"source_review_id": rid, "candidate_source_id": c.get("candidate_source_id"), "url": c.get("url"), "reason": reason})
            continue
        cc = dict(c)
        if not cc.get("candidate_source_id"):
            cc["candidate_source_id"] = "cand_" + hashlib.sha256((rid + "|" + str(cc.get("url"))).encode()).hexdigest()[:24]
        by_review.setdefault(rid, []).append(cc)
    return by_review, rejected


def select_items(import_report: dict[str, Any], curated: dict[str, Any], run10: dict[str, Any], run12: dict[str, Any], run13: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, list[dict[str, Any]]], int]:
    r10 = run10_index(run10)
    curated_idx = curated_item_index(curated)
    collection_idx = source_collection_index(run13, import_report)
    candidates_by_review, rejected_candidates = build_candidates_by_review(import_report, curated)
    skipped: list[dict[str, Any]] = []
    selected: list[dict[str, Any]] = []
    skip_rids = set()
    for report in [import_report, run12, run13, curated]:
        for s in report.get("skipped_items", []) or []:
            rid = str(s.get("source_review_id") or "")
            reason = str(s.get("skip_reason") or s.get("recommended_next_stage") or "skipped_upstream")
            if rid:
                if "editor" in reason or s.get("recommended_next_stage") == "needs_editor_review":
                    skip_rids.add(rid)
                    skipped.append({"source_review_id": rid, "item_id": s.get("item_id"), "skip_reason": "needs_editor_review_not_source_support_rereview"})
    for rid, r in r10.items():
        if r.get("next_stage_recommendation") in {"eligible_for_filing_persistence", "eligible_for_review_note_persistence"} or r.get("evidence_use_decision") in {"eligible_as_caveat_only", "eligible_for_filing_later"}:
            skip_rids.add(rid)
            skipped.append({"source_review_id": rid, "item_id": r.get("item_id"), "skip_reason": "already_persisted_run11_or_already_eligible"})

    for r in import_report.get("collection_results", []) or []:
        rid = str(r.get("source_review_id") or "")
        item_id = r.get("item_id")
        if rid in skip_rids:
            continue
        cands = candidates_by_review.get(rid, [])
        accepted_count = len(cands)
        declared_accepted = int(r.get("accepted_candidate_source_count") or r.get("candidate_source_count") or 0)
        stage_ok = r.get("recommended_next_stage") == "run_source_support_re_review" or r.get("preliminary_collection_assessment") == "enough_candidates_for_re_review"
        if rid not in curated_idx or rid not in r10:
            reason = "unknown_source_review_id_or_missing_provenance" if declared_accepted > 0 else "no_accepted_candidate_sources"
            skipped.append({"source_review_id": rid, "item_id": item_id, "skip_reason": reason})
            continue
        if accepted_count <= 0:
            skipped.append({"source_review_id": rid, "item_id": item_id, "skip_reason": "no_accepted_candidate_sources"})
            continue
        if not stage_ok:
            skipped.append({"source_review_id": rid, "item_id": item_id, "skip_reason": "not_recommended_for_source_support_rereview"})
            continue
        ci = curated_idx[rid]
        original = r10[rid]
        selected.append({
            "source_review_id": rid,
            "item_id": item_id or ci.get("item_id"),
            "original_source_id": ci.get("original_source_id") or r.get("source_id") or original.get("source_id"),
            "original_statement": ci.get("original_statement") or r.get("original_statement") or original.get("semantic_object_text") or "",
            "original_source_support_decision": original.get("source_support_decision"),
            "original_corroboration_decision": original.get("corroboration_decision"),
            "original_evidence_use_decision": original.get("evidence_use_decision"),
            "run12_corroboration_status": (collection_idx.get(rid) or {}).get("corroboration_status"),
            "run13_source_collection_status": (collection_idx.get(rid) or {}).get("source_collection_status"),
            "what_needs_corroboration": ci.get("what_needs_corroboration") or r.get("what_needs_corroboration"),
            "why_current_evidence_is_insufficient": ci.get("why_current_evidence_is_insufficient", ""),
            "accepted_candidate_sources": cands,
            "candidate_source_limitations": [c.get("limitations") for c in cands if c.get("limitations")],
        })
    return selected, skipped, candidates_by_review, len(rejected_candidates) + int(import_report.get("candidate_sources_rejected_count") or 0)


def build_prompt(selected: list[dict[str, Any]]) -> str:
    compact = []
    for item in selected:
        compact.append({
            "source_review_id": item["source_review_id"],
            "item_id": item["item_id"],
            "original_source_id": item["original_source_id"],
            "original_statement": item["original_statement"],
            "original_source_support_decision": item["original_source_support_decision"],
            "original_corroboration_decision": item["original_corroboration_decision"],
            "what_needs_corroboration": item["what_needs_corroboration"],
            "accepted_candidate_sources": [
                {k: c.get(k) for k in ["candidate_source_id", "title", "url", "publisher", "source_type", "support_direction", "evidence_strength", "safe_summary", "limitations"]}
                for c in item["accepted_candidate_sources"]
            ],
        })
    return (
        "Return JSON only, no markdown. You are performing Run 15 advisory source-support re-review. "
        "Use only the provided accepted curated candidate sources; do not browse; do not approve authoring or publication. "
        "For each item, choose exactly ONE allowed string for each enum field. If ambiguous, choose needs_more_sources or needs_editor_review. "
        "Output schema: {\"rereviews\":[{source_review_id,item_id,original_statement,accepted_candidate_source_ids,candidate_source_assessment,original_source_assessment,combined_evidence_assessment,support_decision,corroboration_decision,evidence_use_decision,recommended_next_stage,caveat_required,caveat_text,contradiction_notes,limitations,residual_risk,why_not_author_approved,advisory_only,author_allowed,publication_approved}]}. "
        f"Allowed support_decision: {sorted(ALLOWED_SUPPORT)}. "
        f"Allowed corroboration_decision: {sorted(ALLOWED_CORROBORATION)}. "
        f"Allowed evidence_use_decision: {sorted(ALLOWED_EVIDENCE_USE)}. "
        f"Allowed recommended_next_stage: {sorted(ALLOWED_NEXT)}. "
        "Hard safety flags on every item: advisory_only=true, author_allowed=false, publication_approved=false. "
        "Supported does not mean author-approved. Eligible review-note persistence does not mean claim insertion. "
        "Items: " + json.dumps(compact, ensure_ascii=False, sort_keys=True)
    )


def validate_llm_response(obj: dict[str, Any], expected: list[dict[str, Any]]) -> None:
    reviews = obj.get("rereviews")
    if not isinstance(reviews, list):
        raise ValueError("rereviews must be a list")
    expected_ids = {i["source_review_id"] for i in expected}
    seen = set()
    required = {"source_review_id", "item_id", "original_statement", "accepted_candidate_source_ids", "candidate_source_assessment", "original_source_assessment", "combined_evidence_assessment", "support_decision", "corroboration_decision", "evidence_use_decision", "recommended_next_stage", "caveat_required", "caveat_text", "contradiction_notes", "limitations", "residual_risk", "why_not_author_approved", "advisory_only", "author_allowed", "publication_approved"}
    for r in reviews:
        if not isinstance(r, dict):
            raise ValueError("rereview item must be object")
        missing = required - set(r)
        if missing:
            raise ValueError(f"rereview missing fields: {sorted(missing)}")
        rid = r.get("source_review_id")
        if rid not in expected_ids:
            raise ValueError(f"unexpected source_review_id: {rid}")
        seen.add(rid)
        if r.get("support_decision") not in ALLOWED_SUPPORT:
            raise ValueError("invalid support_decision")
        if r.get("corroboration_decision") not in ALLOWED_CORROBORATION:
            raise ValueError("invalid corroboration_decision")
        if r.get("evidence_use_decision") not in ALLOWED_EVIDENCE_USE:
            raise ValueError("invalid evidence_use_decision")
        if r.get("recommended_next_stage") not in ALLOWED_NEXT:
            raise ValueError("invalid recommended_next_stage")
        if r.get("advisory_only") is not True or r.get("author_allowed") is not False or r.get("publication_approved") is not False:
            raise ValueError("hard safety flags invalid")
        if not isinstance(r.get("accepted_candidate_source_ids"), list):
            raise ValueError("accepted_candidate_source_ids must be list")
    if seen != expected_ids:
        raise ValueError(f"missing rereviews for {sorted(expected_ids - seen)}")


def merge_reviews(selected: list[dict[str, Any]], llm_reviews: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id = {r["source_review_id"]: r for r in llm_reviews}
    out = []
    for item in selected:
        r = dict(by_id[item["source_review_id"]])
        accepted_ids = {c["candidate_source_id"] for c in item["accepted_candidate_sources"]}
        if not set(r.get("accepted_candidate_source_ids", [])).issubset(accepted_ids):
            # Keep GPT honest: candidate IDs must refer only to accepted public candidates.
            r["accepted_candidate_source_ids"] = sorted(accepted_ids)
        r["input_hash"] = hashlib.sha256(json.dumps(item, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        r["output_hash"] = hashlib.sha256(json.dumps(r, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        r["llm_used"] = True
        r["provider"] = DEFAULT_PROVIDER
        r["model"] = DEFAULT_MODEL
        r["bridge"] = BRIDGE
        out.append(r)
    return out


def write_reports(payload: dict[str, Any], output_dir: Path, suffix: str) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{payload['run_id']}-source-support-rereview-{suffix}.json"
    md_path = output_dir / f"{payload['run_id']}-source-support-rereview-{suffix}.md"
    payload["output_paths"] = {"json": rel(json_path), "markdown": rel(md_path)}
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    lines = [
        f"# Run 15 source-support re-review — {payload['run_id']}", "",
        f"- GPT-5.5 used: `{payload['llm_used']}`",
        f"- Provider/model/bridge: `{payload['provider']}` / `{payload['model']}` / `{payload['bridge']}`",
        f"- Selected items: `{payload['selected_items_count']}`",
        f"- Reviewed items: `{payload['reviewed_items_count']}`",
        f"- Skipped items: `{payload['skipped_items_count']}`",
        f"- Accepted candidate sources used: `{payload['accepted_candidate_sources_count']}`",
        "", "## Decisions", "",
        f"- Support decision counts: `{payload['support_decision_counts']}`",
        f"- Corroboration decision counts: `{payload['corroboration_decision_counts']}`",
        f"- Evidence-use decision counts: `{payload['evidence_use_decision_counts']}`",
        f"- Recommended next-stage counts: `{payload['recommended_next_stage_counts']}`",
        "", "## Reviewed items", "",
    ]
    for r in payload["rereviews"]:
        lines += [
            f"### `{r['source_review_id']}`", "",
            f"- Item ID: `{r['item_id']}`",
            f"- Original statement: {r['original_statement']}",
            f"- Accepted candidate source IDs: `{r['accepted_candidate_source_ids']}`",
            f"- Candidate source assessment: {r['candidate_source_assessment']}",
            f"- Original weakness / insufficiency: {r['original_source_assessment']}",
            f"- Combined evidence assessment: {r['combined_evidence_assessment']}",
            f"- Source-support decision: `{r['support_decision']}`",
            f"- Corroboration decision: `{r['corroboration_decision']}`",
            f"- Evidence-use decision: `{r['evidence_use_decision']}`",
            f"- Recommended next stage: `{r['recommended_next_stage']}`",
            f"- Caveat required: `{r['caveat_required']}` — {r['caveat_text']}",
            f"- Limitations: `{r['limitations']}`",
            f"- Safety: advisory_only=`{r['advisory_only']}`, author_allowed=`{r['author_allowed']}`, publication_approved=`{r['publication_approved']}`",
            "",
        ]
    lines += ["## Skipped items", ""]
    for s in payload["skipped_items"]:
        lines.append(f"- `{s.get('source_review_id')}` / `{s.get('item_id')}`: {s.get('skip_reason')}")
    lines += ["", "## Safety confirmations", "", "No DB/source registry/raw/docs/book/schema/daily-worker/status mutations were performed. GPT-5.5 output is advisory only and is not editor approval, claim insertion, author approval, or publication approval.", "", "## Recommended Run 16", "", "Persist only eligible advisory review-note candidates in a disabled-by-default, report-first source_notes persistence run, after checking Run 15 decisions and preserving all safety flags."]
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    return json_path, md_path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", default=RUN_ID_DEFAULT)
    ap.add_argument("--output-dir", default="reports/editorial")
    ap.add_argument("--report-suffix", default="run15")
    ap.add_argument("--source-import-report", default=DEFAULT_IMPORT)
    ap.add_argument("--candidate-sources-report", default=DEFAULT_CURATED)
    ap.add_argument("--source-collection-report", default=DEFAULT_RUN13)
    ap.add_argument("--corroboration-research-report", default=DEFAULT_RUN12)
    ap.add_argument("--source-support-review-report", default=DEFAULT_RUN10)
    ap.add_argument("--filing-novelty-report", default=DEFAULT_RUN9)
    ap.add_argument("--editor-packet-report", default=DEFAULT_RUN8)
    ap.add_argument("--quality-gate-report", default=DEFAULT_RUN7_QUALITY)
    ap.add_argument("--source-card-report", default=DEFAULT_RUN7_CARDS)
    ap.add_argument("--semantic-object-report", default=DEFAULT_RUN7_OBJECTS)
    ap.add_argument("--candidate-selection-report", default=DEFAULT_SELECTION)
    ap.add_argument("--require-high-reasoning", action="store_true", default=True)
    ap.add_argument("--reasoning-profile", default=None)
    ap.add_argument("--provider", default=None)
    ap.add_argument("--model", default=None)
    ap.add_argument("--timeout-seconds", type=int, default=240)
    args = ap.parse_args(argv)

    try:
        paths = {
            "source_import_report": resolve(args.source_import_report),
            "candidate_sources_report": resolve(args.candidate_sources_report),
            "source_collection_report": resolve(args.source_collection_report),
            "corroboration_research_report": resolve(args.corroboration_research_report),
            "source_support_review_report": resolve(args.source_support_review_report),
            "filing_novelty_report": resolve(args.filing_novelty_report),
            "editor_packet_report": resolve(args.editor_packet_report),
            "quality_gate_report": resolve(args.quality_gate_report),
            "source_card_report": resolve(args.source_card_report),
            "semantic_object_report": resolve(args.semantic_object_report),
            "candidate_selection_report": resolve(args.candidate_selection_report),
        }
        import_report = load_json(paths["source_import_report"])
        curated = load_json(paths["candidate_sources_report"])
        run10 = load_json(paths["source_support_review_report"]) if paths["source_support_review_report"].exists() else {"source_reviews": []}
        run12 = load_json(paths["corroboration_research_report"]) if paths["corroboration_research_report"].exists() else {}
        run13 = load_json(paths["source_collection_report"]) if paths["source_collection_report"].exists() else {}
        validate_import_report(import_report)
        if curated.get("ready_for_import") is not True or curated.get("template_only") is not False:
            raise Run15Error("curated candidate-source report is not accepted/import-ready")
        before_counts, before_status = db_counts_and_hashes()
        before_registry = sha_file(ROOT / "data" / "source_registry.json")
        before_schema = sha_file(ROOT / "data" / "schema.sql")
        before_worker = sha_file(ROOT / "scripts" / "daily_book_worker.py")
        before_raw = tree_snapshot(ROOT / "raw")
        before_book = tree_snapshot(ROOT / "docs" / "book")

        selected, skipped, candidates_by_review, rejected_ignored = select_items(import_report, curated, run10, run12, run13)
        if not selected:
            raise Run15Error("no items selected for Run 15 re-review")
        prompt = build_prompt(selected)
        result = call_high_reasoning_json(
            prompt,
            schema_name="run15_source_support_rereview",
            validator=lambda obj: validate_llm_response(obj, selected),
            provider=args.provider,
            model=args.model,
            timeout_seconds=args.timeout_seconds,
            reasoning_profile=args.reasoning_profile,
        )
        rereviews = merge_reviews(selected, result["parsed_json"]["rereviews"])
        support_counts = Counter(r["support_decision"] for r in rereviews)
        corr_counts = Counter(r["corroboration_decision"] for r in rereviews)
        use_counts = Counter(r["evidence_use_decision"] for r in rereviews)
        next_counts = Counter(r["recommended_next_stage"] for r in rereviews)
        after_counts, after_status = db_counts_and_hashes()
        after_registry = sha_file(ROOT / "data" / "source_registry.json")
        after_schema = sha_file(ROOT / "data" / "schema.sql")
        after_worker = sha_file(ROOT / "scripts" / "daily_book_worker.py")
        after_raw = tree_snapshot(ROOT / "raw")
        after_book = tree_snapshot(ROOT / "docs" / "book")
        unique_accepted_candidate_keys = {
            (c.get("source_review_id"), str(c.get("url") or c.get("candidate_source_id") or "").strip().lower())
            for i in selected
            for c in i["accepted_candidate_sources"]
        }
        payload = {
            "run_id": args.run_id,
            "mode": MODE,
            "generated_at": utc_now(),
            "input_paths": {k: rel(v) for k, v in paths.items()},
            "selected_items_count": len(selected),
            "reviewed_items_count": len(rereviews),
            "skipped_items_count": len(skipped),
            "accepted_candidate_sources_count": len(unique_accepted_candidate_keys),
            "rejected_candidate_sources_ignored_count": rejected_ignored,
            "llm_used": True,
            "provider": result["provider"],
            "model": result["model"],
            "bridge": result["bridge"],
            "reasoning_status": result["reasoning_status"],
            "model_profile": result.get("model_profile", "explicit_cli" if args.provider and args.model else ""),
            "strict_json_required": result.get("strict_json_required", True),
            "reasoning_effort": result.get("reasoning_effort", "high"),
            "report_only": True,
            "changed_db": after_counts != before_counts or after_status != before_status,
            "changed_source_registry": after_registry != before_registry,
            "changed_raw_captures": after_raw != before_raw,
            "changed_docs_book": after_book != before_book,
            "changed_schema": after_schema != before_schema,
            "changed_daily_worker": after_worker != before_worker,
            "claims_inserted": max(0, after_counts.get("claims", 0) - before_counts.get("claims", 0)),
            "editorial_reviews_inserted": max(0, after_counts.get("editorial_reviews", 0) - before_counts.get("editorial_reviews", 0)),
            "source_status_changed": after_status.get("sources_status_hash") != before_status.get("sources_status_hash"),
            "claim_status_changed": after_status.get("claims_status_hash") != before_status.get("claims_status_hash"),
            "editorial_status_changed": after_status.get("editorial_reviews_hash") != before_status.get("editorial_reviews_hash"),
            "support_decision_counts": dict(support_counts),
            "corroboration_decision_counts": dict(corr_counts),
            "evidence_use_decision_counts": dict(use_counts),
            "recommended_next_stage_counts": dict(next_counts),
            "selected_items": selected,
            "skipped_items": skipped,
            "rereviews": rereviews,
            "safety_flags": {
                "advisory_only": True,
                "author_allowed": False,
                "publication_approved": False,
                "no_db_writes": True,
                "no_source_registry_writes": True,
                "no_raw_capture_writes": True,
                "no_docs_book_changes": True,
                "no_schema_changes": True,
                "no_daily_worker_changes": True,
                "no_claim_insertion": True,
                "no_editorial_review_insertion": True,
                "no_status_changes": True,
                "raw_content_stored": False,
            },
        }
        forbidden = ["changed_db", "changed_source_registry", "changed_raw_captures", "changed_docs_book", "changed_schema", "changed_daily_worker", "source_status_changed", "claim_status_changed", "editorial_status_changed"]
        if any(payload[k] for k in forbidden) or payload["claims_inserted"] or payload["editorial_reviews_inserted"]:
            raise Run15Error("forbidden side effect detected")
        json_path, md_path = write_reports(payload, resolve(args.output_dir), args.report_suffix)
        print(json.dumps({"status": "ok", "json": rel(json_path), "markdown": rel(md_path), "selected_items_count": len(selected), "reviewed_items_count": len(rereviews)}, sort_keys=True))
        return 0
    except HighReasoningError as exc:
        print(json.dumps({"status": "blocked", "error": exc.result.get("error"), "provider": exc.result.get("provider"), "model": exc.result.get("model"), "bridge": exc.result.get("bridge"), "weak_local_fallback_refused": exc.result.get("weak_local_fallback_refused", True)}, sort_keys=True), file=sys.stderr)
        return 2
    except Exception as exc:
        print(json.dumps({"status": "blocked", "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
