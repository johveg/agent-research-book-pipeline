#!/usr/bin/env python3
"""Generate the research claims page from claim records and evidence links."""
from __future__ import annotations

import argparse
import json
from collections import defaultdict

from research_common import DOCS, connect_db, init_db, utc_now
from editorial_common import ensure_editorial_schema

CLAIMS_PAGE = DOCS / "research" / "claims.md"
ALLOWED_STATUSES = ["candidate", "needs_review", "supported", "weakly_supported", "contradicted", "rejected", "promoted_to_chapter"]
STATUS_ORDER = ["promoted_to_chapter", "supported", "weakly_supported", "needs_review", "candidate", "contradicted", "rejected"]
STRENGTH_ORDER = ["strong", "moderate", "weak", None]


def safe_value(row, key: str, default: str = "unknown") -> str:
    try:
        return row[key] if row[key] not in (None, "") else default
    except Exception:
        return default


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", default="manual")
    ap.add_argument("--limit", type=int, default=200)
    args = ap.parse_args()
    init_db()
    now = utc_now()
    with connect_db() as con:
        ensure_editorial_schema(con)
        claims = con.execute(
            """
            SELECT c.*, COUNT(cs.source_id) AS linked_sources,
                   GROUP_CONCAT(DISTINCT s.quality_score) AS linked_source_quality,
                   GROUP_CONCAT(DISTINCT es.entity_id) AS related_entities
            FROM claims c
            LEFT JOIN claim_sources cs ON cs.claim_id = c.id
            LEFT JOIN sources s ON s.id = cs.source_id
            LEFT JOIN entity_sources es ON es.source_id = cs.source_id
            GROUP BY c.id
            ORDER BY CASE c.status
                       WHEN 'promoted_to_chapter' THEN 0
                       WHEN 'supported' THEN 1
                       WHEN 'weakly_supported' THEN 2
                       WHEN 'needs_review' THEN 3
                       WHEN 'candidate' THEN 4
                       WHEN 'contradicted' THEN 5
                       WHEN 'rejected' THEN 6
                       ELSE 7 END,
                     CASE c.evidence_strength WHEN 'strong' THEN 0 WHEN 'moderate' THEN 1 ELSE 2 END,
                     linked_sources DESC, c.claim_text
            LIMIT ?
            """,
            (args.limit,),
        ).fetchall()
        sources_by_claim = {}
        for c in claims:
            sources_by_claim[c["id"]] = con.execute(
                """
                SELECT s.id, s.title, s.url, s.archived_path, s.quality_score, cs.quote
                FROM claim_sources cs JOIN sources s ON s.id = cs.source_id
                WHERE cs.claim_id = ?
                ORDER BY s.captured_at DESC
                LIMIT 8
                """,
                (c["id"],),
            ).fetchall()
    groups = defaultdict(list)
    for c in claims:
        groups[(safe_value(c, "status", "candidate"), safe_value(c, "evidence_strength", "weak"))].append(c)
    status_counts = {s: sum(1 for c in claims if safe_value(c, "status", "candidate") == s) for s in ALLOWED_STATUSES}
    lines = [
        "# Claims", "", f"Last generated: {now}", "",
        "Claims are explicit editorial records linked to source IDs. No source ID, no claim. No claim, no chapter fact.", "",
        "## Status policy", "",
        "Author-usable statuses: `supported`, `weakly_supported` with caveat, and `promoted_to_chapter`.", "",
        "Not usable as chapter facts: `candidate`, `needs_review`, `contradicted`, and `rejected`.", "",
        "## Summary", "",
        f"- Total claims shown: {len(claims)}",
    ]
    for status in ALLOWED_STATUSES:
        lines.append(f"- {status}: {status_counts.get(status, 0)}")
    lines.append("")
    if not claims:
        lines += ["## Candidate claims", "", "No claim records have been extracted yet."]
    for status in STATUS_ORDER:
        title = f"{status.replace('_', ' ').title()} claims"
        emitted_status = False
        for strength in STRENGTH_ORDER:
            items = groups.get((status, strength or "weak"), []) + ([] if strength is not None else groups.get((status, "unknown"), []))
            if not items:
                continue
            if not emitted_status:
                lines += [f"## {title}", ""]
                emitted_status = True
            lines += [f"### Evidence strength: {strength or 'unknown'}", ""]
            for c in items:
                source_quality = safe_value(c, "source_quality", safe_value(c, "linked_source_quality", "unknown"))
                related = safe_value(c, "related_entities", "none")
                if related != "none":
                    related = ", ".join(related.split(",")[:8])
                lines.append(f"- **{c['claim_text']}**")
                lines.append(f"  - Claim ID: `{c['id']}`")
                lines.append(f"  - Claim type: `{safe_value(c, 'claim_type', 'observation')}`")
                lines.append(f"  - Status: `{safe_value(c, 'status', 'candidate')}`")
                lines.append(f"  - Source count: `{c['linked_sources']}`")
                lines.append(f"  - Evidence strength: `{safe_value(c, 'evidence_strength', 'weak')}`")
                lines.append(f"  - Source quality: `{source_quality}`")
                lines.append(f"  - First seen: `{safe_value(c, 'first_seen_at', 'unknown')}`")
                lines.append(f"  - Last seen: `{safe_value(c, 'last_seen_at', 'unknown')}`")
                lines.append(f"  - Related entities: `{related}`")
                lines.append(f"  - Contradiction status: `{safe_value(c, 'contradiction_status', 'not_checked')}`")
                lines.append(f"  - Editor note: {safe_value(c, 'editor_notes', 'none')}")
                lines.append(f"  - Publication decision: `{safe_value(c, 'publication_decision', 'do_not_use')}`")
                if c["current_best_understanding"]:
                    lines.append(f"  - Current best understanding: {c['current_best_understanding']}")
                refs = sources_by_claim.get(c["id"], [])
                if refs:
                    lines.append("  - Source IDs:")
                    for s in refs:
                        label = s["title"] or s["url"] or s["id"]
                        lines.append(f"    - `{s['id']}` — {label}")
                        lines.append(f"      - Quality: `{s['quality_score'] or 'unknown'}`")
                        if s["url"]:
                            lines.append(f"      - URL: {s['url']}")
                        if s["archived_path"]:
                            lines.append(f"      - Archive: `{s['archived_path']}`")
                lines.append("")
    CLAIMS_PAGE.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    print(json.dumps({"status": "ok", "claims": len(claims), "path": str(CLAIMS_PAGE)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
