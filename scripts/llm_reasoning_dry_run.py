#!/usr/bin/env python3
"""Dry-run advisory reasoning report for the book research pipeline.

This script is intentionally side-effect limited:
- reads existing SQLite/source metadata in read-only mode
- reads sanitized source text through editorial_common.source_text()
- writes advisory Markdown/JSON reports only
- does not update SQLite, chapters, statuses, the daily worker, or commit allowlists
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from editorial_common import source_text  # noqa: E402
from research_common import DB_PATH, ROOT as REPO_ROOT, write_json  # noqa: E402

MODE = "dry_run_advisory_only"
DEFAULT_MODEL = os.environ.get("TEREFO_LLM_REASONING_MODEL", "configured-high-reasoning-model")
SAFE_ACTIONS = {
    "ignore",
    "monitor",
    "needs_review",
    "candidate_source_card",
    "candidate_semantic_extraction",
    "candidate_chapter_packet_later",
}
RAW_ID_RE = re.compile(r"\b(?:src|claim)_[0-9a-f]{8,}\b")


class DryRunError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def today_yyyymmdd() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d")


def repo_relative(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def sanitize_for_report(text: str, max_len: int = 360) -> str:
    """Keep advisory reports compact and avoid long source passages."""
    text = re.sub(r"https?://\S+", "[url]", text or "")
    text = RAW_ID_RE.sub("[internal-id]", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > max_len:
        return text[: max_len - 1].rstrip() + "…"
    return text


def connect_readonly(db_path: Path = DB_PATH) -> sqlite3.Connection:
    if not db_path.exists():
        raise DryRunError(f"SQLite database not found: {db_path}")
    uri = f"file:{db_path.resolve()}?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA query_only = ON")
    return con


def table_columns(con: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in con.execute(f"PRAGMA table_info({table})")}


def resolve_run_id(con: sqlite3.Connection, requested: str) -> str:
    if requested != "latest":
        return requested
    row = con.execute(
        "SELECT id FROM runs ORDER BY COALESCE(started_at, id) DESC LIMIT 1"
    ).fetchone()
    if row and row["id"]:
        return str(row["id"])
    row = con.execute(
        "SELECT run_id FROM sources WHERE run_id IS NOT NULL ORDER BY captured_at DESC LIMIT 1"
    ).fetchone()
    return str(row["run_id"]) if row and row["run_id"] else "latest"


def fetch_sources(con: sqlite3.Connection, run_id: str, limit: int) -> list[sqlite3.Row]:
    cols = table_columns(con, "sources")
    wanted = [
        "id",
        "source_type",
        "query",
        "url",
        "title",
        "publisher",
        "author",
        "published_at",
        "captured_at",
        "archived_path",
        "content_hash",
        "reliability_tier",
        "visibility",
        "run_id",
        "quality_score",
        "quality_notes",
        "summary",
        "relevant_entities",
        "duplicate_status",
        "privacy_publication_status",
        "publication_notes",
    ]
    select_cols = [c for c in wanted if c in cols]
    order = "captured_at DESC" if "captured_at" in cols else "id DESC"
    if run_id == "latest":
        where = "1=1"
        params: list[Any] = []
    else:
        where = "run_id = ?"
        params = [run_id]
    rows = con.execute(
        f"SELECT {', '.join(select_cols)} FROM sources WHERE {where} ORDER BY {order} LIMIT ?",
        [*params, limit],
    ).fetchall()
    if not rows and run_id != "latest":
        rows = con.execute(
            f"SELECT {', '.join(select_cols)} FROM sources ORDER BY {order} LIMIT ?",
            [limit],
        ).fetchall()
    return rows


def fetch_claims(con: sqlite3.Connection, run_id: str, limit: int) -> list[sqlite3.Row]:
    cols = table_columns(con, "claims")
    wanted = [
        "id",
        "claim_text",
        "claim_type",
        "subject_entity_id",
        "confidence",
        "status",
        "evidence_strength",
        "source_count",
        "source_quality",
        "contradiction_status",
        "publication_decision",
        "editor_notes",
        "updated_at",
        "reviewed_at",
        "last_seen_at",
        "first_seen_at",
    ]
    select_cols = [c for c in wanted if c in cols]
    if run_id != "latest" and "claim_sources" in tables(con):
        query = f"""
            SELECT DISTINCT {', '.join('c.' + c for c in select_cols)}
            FROM claims c
            JOIN claim_sources cs ON cs.claim_id = c.id
            JOIN sources s ON s.id = cs.source_id
            WHERE s.run_id = ?
            ORDER BY COALESCE(c.reviewed_at, c.updated_at, c.last_seen_at, c.first_seen_at, c.id) DESC
            LIMIT ?
        """
        rows = con.execute(query, [run_id, limit]).fetchall()
        if rows:
            return rows
    order_col = "COALESCE(reviewed_at, updated_at, last_seen_at, first_seen_at, id)" if cols & {"reviewed_at", "updated_at", "last_seen_at", "first_seen_at"} else "id"
    return con.execute(
        f"SELECT {', '.join(select_cols)} FROM claims ORDER BY {order_col} DESC LIMIT ?",
        [limit],
    ).fetchall()


def tables(con: sqlite3.Connection) -> set[str]:
    return {row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def fetch_entities_count(con: sqlite3.Connection) -> int:
    if "entities" not in tables(con):
        return 0
    return int(con.execute("SELECT COUNT(*) FROM entities").fetchone()[0])


def linked_source_ids(con: sqlite3.Connection, claim_id: str) -> list[str]:
    if "claim_sources" not in tables(con):
        return []
    rows = con.execute(
        "SELECT source_id FROM claim_sources WHERE claim_id = ? ORDER BY source_id LIMIT 8",
        [claim_id],
    ).fetchall()
    return [str(r["source_id"]) for r in rows]


def classify_source(row: sqlite3.Row, text: str) -> tuple[str, str, str]:
    quality = (row["quality_score"] if "quality_score" in row.keys() else None) or "unknown"
    privacy = (row["privacy_publication_status"] if "privacy_publication_status" in row.keys() else None) or "unknown"
    duplicate = (row["duplicate_status"] if "duplicate_status" in row.keys() else None) or "unknown"
    source_type = (row["source_type"] if "source_type" in row.keys() else None) or "unknown"
    lower_text = text.lower()

    if duplicate not in {"unknown", "unique", ""}:
        return "duplicate", "monitor", "Existing duplicate/repeated-signal marker suggests this should not be promoted without review."
    if "linkedin" in source_type.lower() or privacy not in {"publishable", "publishable_metadata_only", "unknown", ""}:
        return "weak", "needs_review", "Social/private-adjacent or privacy-limited source should remain discovery context unless independently corroborated."
    if quality in {"high", "strong", "reliable"}:
        return "useful", "candidate_source_card", "Higher-quality source metadata makes it a good candidate for a future source-card pass."
    if any(term in lower_text for term in ["hermes", "openclaw", "loop engineering", "agent", "memory", "context"]):
        return "useful", "candidate_semantic_extraction", "Text appears relevant to existing book themes and could support semantic extraction later."
    if quality in {"low", "weak"}:
        return "weak", "monitor", "Low-quality signal; useful mostly as trend context."
    return "new", "needs_review", "Insufficient structured review metadata; keep as advisory review candidate."


def chapter_relevance(text: str) -> str:
    low = text.lower()
    mapping = [
        ("Hermes / assistant operating model", ["hermes", "agent loop", "memory", "context"]),
        ("OpenClaw / local control", ["openclaw", "browser", "local", "control"]),
        ("Loop engineering", ["loop engineering", "loop engineer", "workflow", "operating loop"]),
        ("Context and memory architecture", ["memory", "context architecture", "rag", "retrieval"]),
        ("Operating loops and governance", ["governance", "eval", "verification", "safety", "workflow"]),
    ]
    scores = [(label, sum(1 for term in terms if term in low)) for label, terms in mapping]
    best = max(scores, key=lambda item: item[1])
    return best[0] if best[1] else "unclear / needs review"


def deterministic_source_findings(sources: list[sqlite3.Row]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for row in sources:
        text = source_text(row, max_len=5000)
        assessment, action, rationale = classify_source(row, text)
        findings.append(
            {
                "source_id": row["id"],
                "title": sanitize_for_report(row["title"] if "title" in row.keys() else "", 160),
                "publisher": sanitize_for_report(row["publisher"] if "publisher" in row.keys() else "", 120),
                "source_type": row["source_type"] if "source_type" in row.keys() else "unknown",
                "quality_score": row["quality_score"] if "quality_score" in row.keys() else None,
                "privacy_publication_status": row["privacy_publication_status"] if "privacy_publication_status" in row.keys() else None,
                "safe_summary": sanitize_for_report(row["summary"] if "summary" in row.keys() and row["summary"] else text, 300),
                "likely_chapter_relevance": chapter_relevance(text),
                "assessment": assessment,
                "recommended_next_action": action,
                "rationale": rationale,
                "llm_commentary": "Deterministic no-LLM heuristic; draft-only advisory signal.",
            }
        )
    return findings


def deterministic_claim_findings(con: sqlite3.Connection, claims: list[sqlite3.Row]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for row in claims:
        linked = linked_source_ids(con, row["id"])
        text = row["claim_text"] if "claim_text" in row.keys() else ""
        status = row["status"] if "status" in row.keys() else "unknown"
        pub = row["publication_decision"] if "publication_decision" in row.keys() else None
        contradiction = row["contradiction_status"] if "contradiction_status" in row.keys() else "not_checked"
        source_count = row["source_count"] if "source_count" in row.keys() and row["source_count"] is not None else len(linked)
        vague = len(text.split()) < 8 or any(x in text.lower() for x in ["many", "some", "things", "stuff"])
        if contradiction and contradiction not in {"not_checked", "none", ""}:
            assessment = "contradicted"
            action = "needs_review"
        elif source_count >= 2 and status in {"supported", "weakly_supported", "promoted_to_chapter"}:
            assessment = "well-supported"
            action = "candidate_chapter_packet_later"
        elif source_count <= 1:
            assessment = "under-supported"
            action = "candidate_source_card"
        elif vague:
            assessment = "too vague"
            action = "needs_review"
        else:
            assessment = "needs review"
            action = "candidate_semantic_extraction"
        findings.append(
            {
                "claim_id": row["id"],
                "claim_text": sanitize_for_report(text, 260),
                "current_status": status,
                "publication_decision": pub,
                "linked_source_ids": linked,
                "assessment": assessment,
                "recommended_next_action": action,
                "rationale": "Advisory-only classification based on current status, publication decision, contradiction marker, and linked source count.",
            }
        )
    return findings


def missing_middle_findings(source_findings: list[dict[str, Any]], claim_findings: list[dict[str, Any]]) -> list[dict[str, str]]:
    source_card_candidates = sum(1 for f in source_findings if f["recommended_next_action"] == "candidate_source_card")
    semantic_candidates = sum(1 for f in source_findings if f["recommended_next_action"] == "candidate_semantic_extraction")
    under_supported = sum(1 for f in claim_findings if f["assessment"] == "under-supported")
    return [
        {
            "finding": "missing source cards",
            "analysis": f"{source_card_candidates} sampled sources look like potential source-card candidates; current source rows have useful metadata but not a durable source-card shape.",
            "recommendation": "Add source cards only after confirming whether source_notes can store the first version without schema churn.",
        },
        {
            "finding": "missing semantic extraction",
            "analysis": f"{semantic_candidates} sampled sources look semantically relevant but current extraction remains sentence/entity oriented.",
            "recommendation": "Introduce semantic extraction as advisory source-card fields before any chapter packet generation.",
        },
        {
            "finding": "missing clusters and narrative packets",
            "analysis": "Claims and sources are linked, but there is no explicit cluster/narrative-packet object for book-ready argument structure.",
            "recommendation": "Defer narrative packets until source cards and semantic extraction are stable.",
        },
        {
            "finding": "missing editor-approved author briefs",
            "analysis": f"{under_supported} sampled claims appear under-supported; Author should not consume them directly.",
            "recommendation": "Keep chapter authoring gated; produce proposed briefs in reports before touching docs/book.",
        },
        {
            "finding": "missing paragraph-to-claim/source traceability",
            "analysis": "Citation checks prevent raw ID leaks, but paragraph-level traceability is not represented as its own reviewed object.",
            "recommendation": "Consider traceability after source cards; do not add it in Run 2 unless source-card fields prove insufficient.",
        },
    ]


def schema_recommendations() -> list[dict[str, str]]:
    return [
        {
            "category": "reuse existing table",
            "target": "source_notes",
            "recommendation": "Use for first source-card draft notes with note_type values such as source_card_draft, semantic_observation, and risk_note.",
            "reason": "The table already links notes to source_id and avoids a migration for Run 2.",
        },
        {
            "category": "reuse existing table",
            "target": "editorial_reviews",
            "recommendation": "Use for run-level review summaries of LLM advisory passes.",
            "reason": "The table already stores review_type, status, summary, report_path, and created_at.",
        },
        {
            "category": "add column",
            "target": "sources",
            "recommendation": "Defer adding structured source_card_json/source_card_status until the report-only dry run proves the shape.",
            "reason": "Avoid schema churn; current source_notes can hold drafts.",
        },
        {
            "category": "add new table",
            "target": "source_cards",
            "recommendation": "Defer unless source_notes becomes too ambiguous for structured source-card lifecycle.",
            "reason": "A dedicated table may be useful later for card status, model metadata, and editor approval, but it is not required for Run 2 discovery.",
        },
        {
            "category": "defer",
            "target": "chapter_packets / narrative_clusters",
            "recommendation": "Do not implement until source cards and semantic extraction have tests and editor review gates.",
            "reason": "Packets are closer to chapter authoring and carry higher publication risk.",
        },
    ]


def build_payload(run_id: str, model: str, llm_used: bool, sources: list[sqlite3.Row], claims: list[sqlite3.Row], entity_count: int, con: sqlite3.Connection, llm_note: str) -> dict[str, Any]:
    source_findings = deterministic_source_findings(sources)
    claim_findings = deterministic_claim_findings(con, claims)
    missing = missing_middle_findings(source_findings, claim_findings)
    high_conf = llm_used and model and model != "local-fallback"
    return {
        "run_id": run_id,
        "generated_at": utc_now(),
        "mode": MODE,
        "model": model,
        "llm_used": llm_used,
        "confidence_level": "medium_advisory" if high_conf else "low_draft_structural",
        "llm_note": llm_note,
        "db_modified": False,
        "chapters_modified": False,
        "statuses_modified": False,
        "daily_worker_modified": False,
        "commit_allowlist_modified": False,
        "raw_private_material_written": False,
        "safe_for_advisory_use_only": True,
        "sample_counts": {
            "sources": len(source_findings),
            "claims": len(claim_findings),
            "entities": entity_count,
        },
        "source_findings": source_findings,
        "claim_findings": claim_findings,
        "missing_middle_findings": missing,
        "schema_recommendations": schema_recommendations(),
        "next_run_recommendation": {
            "recommendation": "Proceed to source cards using existing source_notes first; defer new schema unless structured fields cannot be represented safely.",
            "likely_files_to_change": [
                "scripts/llm_reasoning_dry_run.py",
                "tests/test_llm_reasoning_dry_run.py",
                "possibly scripts/editorial_pipeline_report.py after Run 2 review",
                "possibly data/schema.sql only after source_notes reuse is proven insufficient",
            ],
            "tests_needed": [
                "no-LLM report generation",
                "read-only DB safety",
                "no docs/book writes",
                "source-card JSON shape validation",
                "privacy/raw wording length guard",
            ],
        },
        "risks": [
            "No-LLM mode is structural and low-confidence by design.",
            "LLM output may be unstable unless constrained by schema validation.",
            "Sanitized source text can still contain too much source wording if max-length guards are loosened.",
            "Vector DB chunks must remain non-authoritative context only.",
        ],
        "verification": {},
    }


def render_markdown(payload: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append(f"# LLM reasoning dry-run advisory report: {payload['run_id']}")
    lines.append("")
    lines.append("## Executive summary")
    lines.append("")
    lines.append(f"- Mode: `{payload['mode']}`")
    lines.append(f"- Generated at: {payload['generated_at']}")
    lines.append("- Inspected: SQLite sources, claims, claim/source links, entity counts, and sanitized source text via existing pipeline helpers.")
    lines.append(f"- Sample counts: {payload['sample_counts']['sources']} sources; {payload['sample_counts']['claims']} claims; {payload['sample_counts']['entities']} total entities in DB.")
    lines.append(f"- LLM used: {payload['llm_used']}")
    lines.append(f"- Model: `{payload['model']}`")
    lines.append(f"- Confidence level: `{payload['confidence_level']}`")
    lines.append(f"- LLM note: {payload['llm_note']}")
    lines.append("- Safety: advisory use only; this report is not publishable chapter prose and performs no filing/promotions.")
    lines.append("")

    lines.append("## Source reasoning sample")
    lines.append("")
    for f in payload["source_findings"]:
        lines.append(f"### Source `{f['source_id']}`")
        lines.append(f"- Title: {f['title'] or '(untitled)'}")
        lines.append(f"- Publisher: {f['publisher'] or '(unknown)'}")
        lines.append(f"- Source type: `{f['source_type']}`")
        lines.append(f"- Quality score: `{f['quality_score']}`")
        lines.append(f"- Privacy/publication status: `{f['privacy_publication_status']}`")
        lines.append(f"- Safe summary: {f['safe_summary']}")
        lines.append(f"- Likely chapter relevance: {f['likely_chapter_relevance']}")
        lines.append(f"- Assessment: `{f['assessment']}`")
        lines.append(f"- Recommended next action: `{f['recommended_next_action']}`")
        lines.append(f"- Rationale: {f['rationale']}")
        lines.append("")
    if not payload["source_findings"]:
        lines.append("No source samples found.\n")

    lines.append("## Claim reasoning sample")
    lines.append("")
    for f in payload["claim_findings"]:
        lines.append(f"### Claim `{f['claim_id']}`")
        lines.append(f"- Claim text: {f['claim_text']}")
        lines.append(f"- Current status: `{f['current_status']}`")
        lines.append(f"- Publication decision: `{f['publication_decision']}`")
        lines.append(f"- Linked source IDs: {', '.join(f['linked_source_ids']) if f['linked_source_ids'] else '(none)' }")
        lines.append(f"- Assessment: `{f['assessment']}`")
        lines.append(f"- Recommended next action: `{f['recommended_next_action']}`")
        lines.append(f"- Rationale: {f['rationale']}")
        lines.append("")
    if not payload["claim_findings"]:
        lines.append("No claim samples found.\n")

    lines.append("## Missing-middle analysis")
    lines.append("")
    for item in payload["missing_middle_findings"]:
        lines.append(f"- **{item['finding']}**: {item['analysis']} Recommendation: {item['recommendation']}")
    lines.append("")

    lines.append("## Suggested data shape for next run")
    lines.append("")
    for rec in payload["schema_recommendations"]:
        lines.append(f"- `{rec['category']}` — `{rec['target']}`: {rec['recommendation']} Reason: {rec['reason']}")
    lines.append("")

    lines.append("## Suggested next-run implementation plan")
    lines.append("")
    nr = payload["next_run_recommendation"]
    lines.append(f"Recommendation: {nr['recommendation']}")
    lines.append("")
    lines.append("Likely files to change:")
    for p in nr["likely_files_to_change"]:
        lines.append(f"- `{p}`")
    lines.append("")
    lines.append("Tests needed:")
    for t in nr["tests_needed"]:
        lines.append(f"- {t}")
    lines.append("")

    lines.append("## Safety assessment")
    lines.append("")
    lines.append(f"- Modified DB: {'yes' if payload['db_modified'] else 'no'}")
    lines.append(f"- Modified chapters: {'yes' if payload['chapters_modified'] else 'no'}")
    lines.append(f"- Modified source/claim statuses: {'yes' if payload['statuses_modified'] else 'no'}")
    lines.append(f"- Changed daily worker: {'yes' if payload['daily_worker_modified'] else 'no'}")
    lines.append(f"- Changed commit allowlist: {'yes' if payload['commit_allowlist_modified'] else 'no'}")
    lines.append(f"- Wrote raw/private material into reports: {'yes' if payload['raw_private_material_written'] else 'no'}")
    lines.append("")
    lines.append("## Risks")
    lines.append("")
    for r in payload["risks"]:
        lines.append(f"- {r}")
    lines.append("")
    return "\n".join(lines)


def render_evidence_map(payload: dict[str, Any], output_paths: dict[str, str]) -> str:
    lines = [
        f"# Run 1 LLM reasoning dry-run evidence map — {today_yyyymmdd()}",
        "",
        "## Files changed",
        "",
        "- `scripts/llm_reasoning_dry_run.py`: new dry-run advisory report generator; reads SQLite in read-only mode and writes Markdown/JSON reports only.",
        "- `tests/test_llm_reasoning_dry_run.py`: tests no-LLM execution, report outputs, safety booleans, and no docs/book or DB writes.",
        f"- `{output_paths.get('markdown')}`: generated advisory Markdown report.",
        f"- `{output_paths.get('json')}`: generated advisory JSON report.",
        f"- `{output_paths.get('evidence_map')}`: implementation/evidence map for Run 1 evaluation.",
        "",
        "## Files intentionally not changed",
        "",
        "- `docs/book/`: not changed by this script.",
        "- `scripts/daily_book_worker.py`: not changed; no daily-worker wiring in Run 1.",
        "- `data/schema.sql`: not changed; no DB migration in Run 1.",
        "- Commit allowlist: not changed.",
        "- Raw capture paths: not changed.",
        "- `.var/book.sqlite`: opened read-only; not modified by this script.",
        "",
        "## Current working tree status",
        "",
        "Capture final `git status --short` in the final human report after all verification commands complete. This script itself does not stage or commit files.",
        "",
        "## Commands run",
        "",
        "Record final command results after verification. The dry-run invocation that produced this map should be listed there.",
        "",
        "## Evidence from dry-run output",
        "",
        f"- Source sample size: {payload['sample_counts']['sources']}",
        f"- Claim sample size: {payload['sample_counts']['claims']}",
        f"- Entity count inspected: {payload['sample_counts']['entities']}",
        f"- LLM used: {payload['llm_used']}",
        f"- Confidence level: `{payload['confidence_level']}`",
        "- Useful advisory reasoning produced: yes, as deterministic structural/draft analysis in no-LLM mode; high-reasoning LLM output should be evaluated separately if configured.",
        "- Source richness captured better than current sentence extraction: partially; the report surfaces source-card/semantic-extraction candidates but does not yet create durable cards.",
        "- Next step direction: source cards using existing `source_notes` first, while deferring new schema until the card shape is proven.",
        "",
        "## Risks / limitations",
        "",
    ]
    for risk in payload["risks"]:
        lines.append(f"- {risk}")
    lines.extend(
        [
            "- Model availability is not assumed; `--no-llm` produces low-confidence draft-only output.",
            "- Prompt/output instability remains a risk for future real-LLM mode and should be constrained by JSON schema validation.",
            "- Reports deliberately truncate source wording to reduce risk of copying too much raw source text.",
            "",
            "## Recommendation for Run 2",
            "",
            "Proceed to source cards using the existing `source_notes` table first. Do not add chapter packets, modify `docs/book/`, or promote claims/sources until source-card shape, privacy guards, and tests are stable.",
            "",
        ]
    )
    return "\n".join(lines)


def maybe_use_llm(args: argparse.Namespace) -> tuple[bool, str, str]:
    """Return (llm_used, model, note).

    Run 1 intentionally avoids silent weak fallbacks. A real high-reasoning model can be
    added behind this interface later; without explicit configured access this returns
    deterministic no-LLM mode or fails safely when requested.
    """
    model = args.model or DEFAULT_MODEL
    if args.no_llm:
        if args.fail_if_no_high_reasoning_model:
            raise DryRunError("--fail-if-no-high-reasoning-model was set, but --no-llm disables model use")
        return False, model, "No LLM used; deterministic structural analysis only, low-confidence/draft-only."

    configured = bool(os.environ.get("OPENAI_API_KEY") or os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("TEREFO_HIGH_REASONING_MODEL_AVAILABLE"))
    if not configured:
        if args.fail_if_no_high_reasoning_model:
            raise DryRunError("No configured high-reasoning model detected; refusing weak/local fallback")
        return False, model, "No configured high-reasoning model detected; deterministic structural analysis only, low-confidence/draft-only."

    # Deliberately do not call an external model in Run 1 until provider/config is
    # explicitly reviewed. Marking this as not used avoids overstating confidence.
    if args.fail_if_no_high_reasoning_model:
        raise DryRunError("High-reasoning model configuration is detectable but real provider integration is intentionally not wired in Run 1")
    return False, model, "Provider variables detected, but Run 1 does not invoke external LLMs yet; deterministic structural analysis only."


def parse_args(argv: list[str]) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Generate dry-run advisory LLM reasoning reports without changing pipeline state.")
    ap.add_argument("--run-id", default="latest", help="Run id to inspect, or latest")
    ap.add_argument("--limit", type=int, default=20, help="Maximum sampled sources and claims")
    ap.add_argument("--output-dir", default="reports/editorial", help="Directory for Markdown/JSON advisory reports")
    ap.add_argument("--model", default=DEFAULT_MODEL, help="High-reasoning model name to record/use when configured")
    ap.add_argument("--no-llm", action="store_true", help="Force deterministic no-LLM structural report")
    ap.add_argument("--json-only", action="store_true", help="Write only JSON report plus evidence map")
    ap.add_argument("--markdown-only", action="store_true", help="Write only Markdown report plus evidence map")
    ap.add_argument("--fail-if-no-high-reasoning-model", action="store_true", help="Fail safely instead of producing no-LLM report when no high-reasoning model is available")
    args = ap.parse_args(argv)
    if args.limit < 0:
        raise DryRunError("--limit must be non-negative")
    if args.json_only and args.markdown_only:
        raise DryRunError("--json-only and --markdown-only are mutually exclusive")
    return args


def main(argv: list[str] | None = None) -> int:
    try:
        args = parse_args(argv or sys.argv[1:])
        llm_used, model, llm_note = maybe_use_llm(args)

        with connect_readonly() as con:
            run_id = resolve_run_id(con, args.run_id)
            sources = fetch_sources(con, run_id, args.limit)
            claims = fetch_claims(con, run_id, args.limit)
            entity_count = fetch_entities_count(con)
            payload = build_payload(run_id, model, llm_used, sources, claims, entity_count, con, llm_note)

        output_dir = Path(args.output_dir)
        if not output_dir.is_absolute():
            output_dir = REPO_ROOT / output_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        md_path = output_dir / f"{run_id}-llm-reasoning-dry-run.md"
        json_path = output_dir / f"{run_id}-llm-reasoning-dry-run.json"
        arch_dir = REPO_ROOT / "reports" / "architecture"
        arch_dir.mkdir(parents=True, exist_ok=True)
        evidence_path = arch_dir / f"run1-llm-reasoning-dry-run-evidence-map-{today_yyyymmdd()}.md"

        output_paths = {
            "markdown": repo_relative(md_path),
            "json": repo_relative(json_path),
            "evidence_map": repo_relative(evidence_path),
        }
        payload["output_paths"] = output_paths

        if not args.markdown_only:
            write_json(json_path, payload)
        if not args.json_only:
            md_path.write_text(render_markdown(payload), encoding="utf-8")
        evidence_path.write_text(render_evidence_map(payload, output_paths), encoding="utf-8")

        print(json.dumps({"status": "ok", "run_id": run_id, "outputs": output_paths, "llm_used": llm_used}, indent=2, sort_keys=True))
        return 0
    except DryRunError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
