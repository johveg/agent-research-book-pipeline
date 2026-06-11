#!/usr/bin/env python3
"""Produce a conservative weekly editorial curation report.

Daily runs collect, classify, extract, and propose. This weekly report is the judgment layer:
it reviews the week's sources/entities/claims/trends and recommends whether book movement is
ready. It does not rewrite chapters or promote claims mechanically.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

from research_common import DOCS, REPORTS, connect_db, init_db, utc_now

QUALITY_ORDER = ["A", "B", "C", "D", "E", "unknown"]
BOOK_CHAPTERS = [
    "book/preface.md",
    "book/01-the-agent-loop.md",
    "book/02-hermes.md",
    "book/03-openclaw.md",
    "book/04-loop-engineering.md",
    "book/05-context-memory-architecture.md",
    "book/06-operating-loops.md",
    "book/open-questions.md",
]


def iso_days_ago(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")


def rows(con, sql: str, params=()):
    return [dict(r) for r in con.execute(sql, params).fetchall()]


def counts_by(rows_: list[dict], key: str) -> dict:
    c = Counter((r.get(key) or "unknown") for r in rows_)
    return {k: c.get(k, 0) for k in QUALITY_ORDER if k in c or k != "unknown"} | ({"unknown": c.get("unknown", 0)} if c.get("unknown", 0) else {})


def as_item(item: dict, fields: list[str]) -> dict:
    return {f: item.get(f) for f in fields if f in item}


def chapter_readiness(claims: list[dict], contradictions: list[dict]) -> tuple[list[dict], list[dict]]:
    usable = [c for c in claims if c.get("status") in {"supported", "promoted_to_chapter"}]
    weak = [c for c in claims if c.get("status") == "weakly_supported"]
    updates = []
    not_ready = []
    for chapter in BOOK_CHAPTERS:
        if len(usable) >= 3:
            updates.append({
                "chapter": chapter,
                "recommendation": "eligible_for_editor_review",
                "reason": "At least three supported/promoted claims exist in the corpus; Editor must still approve any material chapter diff.",
            })
        elif contradictions:
            updates.append({
                "chapter": chapter,
                "recommendation": "review_for_correction_only",
                "reason": "Possible contradictions/corrections appeared; do not add new prose without Editor review.",
            })
        else:
            not_ready.append({
                "chapter": chapter,
                "reason": f"Only {len(usable)} supported/promoted claims found; {len(weak)} weakly supported claims remain caveated evidence, not enough for material chapter movement.",
            })
    return updates, not_ready


def write_docs_weekly_index() -> None:
    weekly = sorted((REPORTS / "weekly").glob("*.md"), reverse=True)[:100]
    lines = ["# Weekly Editorial Reports", "", f"Last generated: {utc_now()}", "", "Weekly curation is the judgment layer. Daily runs collect, classify, extract, and propose; weekly reports decide whether the book should move.", ""]
    if not weekly:
        lines.append("- No weekly reports yet.")
    else:
        for p in weekly:
            lines.append(f"- **{p.stem}** — local report `{p.relative_to(DOCS.parent)}`")
    out = DOCS / "reports/weekly.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--json-out")
    args = ap.parse_args()

    init_db()
    since = iso_days_ago(args.days)
    now = utc_now()
    with connect_db() as con:
        sources = rows(con, """
            SELECT id,url,title,author,publisher,published_at,captured_at,source_type,quality_score,
                   summary,relevant_entities,extracted_candidate_claims,duplicate_status,
                   privacy_publication_status,quality_notes
            FROM sources
            WHERE captured_at >= ?
            ORDER BY captured_at DESC
        """, (since,))
        entities = rows(con, """
            SELECT id,type,name,canonical_name,summary,confidence,first_seen_at,last_seen_at
            FROM entities
            WHERE COALESCE(first_seen_at,last_seen_at,'') >= ?
            ORDER BY last_seen_at DESC LIMIT 100
        """, (since,))
        claims = rows(con, """
            SELECT id,claim_text,claim_type,status,evidence_strength,source_count,source_quality,
                   contradiction_status,publication_decision,editor_notes,first_seen_at,last_seen_at
            FROM claims
            WHERE COALESCE(first_seen_at,last_seen_at,'') >= ? OR updated_at >= ?
            ORDER BY last_seen_at DESC LIMIT 200
        """, (since, since))
        trends = rows(con, """
            SELECT id,term,term_type,count,first_seen_at,last_seen_at,status,evidence_path,run_id
            FROM trend_terms
            WHERE COALESCE(first_seen_at,last_seen_at,'') >= ?
            ORDER BY count DESC, last_seen_at DESC LIMIT 100
        """, (since,))

    quality_summary = counts_by(sources, "quality_score")
    best_sources = [as_item(s, ["id", "title", "url", "publisher", "author", "captured_at", "quality_score", "summary"]) for s in sources if s.get("quality_score") in {"A", "B"} and s.get("duplicate_status") == "unique"][:10]
    weak_sources = [as_item(s, ["id", "title", "url", "captured_at", "quality_score", "duplicate_status", "privacy_publication_status", "quality_notes"]) for s in sources if s.get("quality_score") in {"D", "E"} or s.get("privacy_publication_status") != "publishable_metadata_only"][:15]
    supported = [c for c in claims if c.get("status") in {"supported", "promoted_to_chapter"}]
    weak_claims = [c for c in claims if c.get("status") == "weakly_supported"]
    rejected = [c for c in claims if c.get("status") == "rejected"]
    contradictions = [c for c in claims if c.get("status") == "contradicted" or c.get("contradiction_status") == "contradicted"]
    accepted_trends = [t for t in trends if t.get("status") in {"accepted", "monitor", "promoted"}]
    rejected_trends = [t for t in trends if t.get("status") in {"reject", "rejected"}]
    recommended_updates, not_ready = chapter_readiness(claims, contradictions)

    human_decisions = []
    if weak_claims:
        human_decisions.append("Review weakly_supported claims before any chapter prose uses them beyond caveated status sections.")
    if weak_sources:
        human_decisions.append("Review D/E or privacy-sensitive sources; they should not support factual claims.")
    if recommended_updates:
        human_decisions.append("Editor must approve any material chapter diff before publication.")
    if not supported:
        human_decisions.append("No candidate claims were automatically promoted; human Editor review is required before book movement.")

    payload = {
        "run_id": args.run_id,
        "created_at": now,
        "window_days": args.days,
        "since": since,
        "executive_summary": {
            "sources_reviewed": len(sources),
            "new_entities_reviewed": len(entities),
            "candidate_claims_reviewed": len(claims),
            "trend_candidates_reviewed": len(trends),
            "book_movement_recommendation": "hold_chapters_unless_editor_approves" if not supported else "editor_review_required_before_update",
            "principle": "Daily is for collection and preparation; weekly is for judgment and book movement.",
        },
        "source_quality_summary": quality_summary,
        "new_entities_worth_keeping": [as_item(e, ["id", "type", "canonical_name", "confidence", "summary"]) for e in entities if e.get("confidence") in {"medium", "high"}][:30],
        "candidate_claims_promoted": [as_item(c, ["id", "claim_text", "status", "evidence_strength", "source_quality", "publication_decision"]) for c in supported],
        "candidate_claims_rejected": [as_item(c, ["id", "claim_text", "status", "editor_notes"]) for c in rejected],
        "weak_signals_to_monitor": [as_item(c, ["id", "claim_text", "status", "source_quality", "editor_notes"]) for c in weak_claims[:30]],
        "trends_accepted": accepted_trends[:30],
        "trends_rejected": rejected_trends[:30],
        "contradictions_or_corrections": contradictions,
        "recommended_chapter_updates": recommended_updates,
        "chapters_not_ready_for_update": not_ready,
        "required_human_decisions": human_decisions,
        "next_week_watchlist": [t.get("term") for t in accepted_trends[:20]] or ["loop engineering", "agent verification", "observable agent state", "human escalation boundaries"],
        "best_sources": best_sources,
        "weak_sources": weak_sources,
        "final_rule": "Daily is for collection and preparation. Weekly is for judgment and book movement.",
    }

    out = REPORTS / "weekly" / f"{args.run_id}-weekly-curation.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Weekly editorial curation report", "", f"- Run ID: `{args.run_id}`", f"- Created: {now}", f"- Window: last {args.days} days since `{since}`", "", "## Executive summary", ""]
    for k, v in payload["executive_summary"].items():
        lines.append(f"- {k.replace('_',' ')}: `{v}`")
    lines += ["", "## Source quality summary", ""]
    for k, v in quality_summary.items():
        lines.append(f"- {k}: `{v}`")
    for title, key in [
        ("New entities worth keeping", "new_entities_worth_keeping"),
        ("Candidate claims promoted", "candidate_claims_promoted"),
        ("Candidate claims rejected", "candidate_claims_rejected"),
        ("Weak signals to monitor", "weak_signals_to_monitor"),
        ("Trends accepted", "trends_accepted"),
        ("Trends rejected", "trends_rejected"),
        ("Contradictions or corrections", "contradictions_or_corrections"),
        ("Recommended chapter updates", "recommended_chapter_updates"),
        ("Chapters not ready for update", "chapters_not_ready_for_update"),
        ("Required human decisions", "required_human_decisions"),
        ("Next week's watchlist", "next_week_watchlist"),
        ("Best sources", "best_sources"),
        ("Weak sources", "weak_sources"),
    ]:
        lines += ["", f"## {title}", ""]
        val = payload[key]
        if not val:
            lines.append("- None")
        else:
            for item in val[:40]:
                lines.append(f"- `{json.dumps(item, ensure_ascii=False)[:900]}`")
    lines += ["", "## Final rule", "", payload["final_rule"]]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    write_docs_weekly_index()
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": "ok", "report": str(out), "docs_index": str(DOCS / "reports/weekly.md"), "summary": payload["executive_summary"]}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
