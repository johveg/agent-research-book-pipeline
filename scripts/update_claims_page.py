#!/usr/bin/env python3
"""Generate the research claims page from claim records and evidence links."""
from __future__ import annotations

import argparse
import json
from collections import defaultdict

from research_common import DOCS, connect_db, init_db, utc_now
from editorial_common import ensure_editorial_schema

CLAIMS_PAGE = DOCS / "research" / "claims.md"

STATUS_ORDER = ["supported", "candidate", "observed", "rejected", "deprecated"]
STRENGTH_ORDER = ["strong", "moderate", "weak", None]


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
            SELECT c.*, COUNT(cs.source_id) AS linked_sources
            FROM claims c
            LEFT JOIN claim_sources cs ON cs.claim_id = c.id
            GROUP BY c.id
            ORDER BY CASE c.status WHEN 'supported' THEN 0 WHEN 'candidate' THEN 1 WHEN 'observed' THEN 2 ELSE 3 END,
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
                SELECT s.id, s.title, s.url, s.archived_path, cs.quote
                FROM claim_sources cs JOIN sources s ON s.id = cs.source_id
                WHERE cs.claim_id = ?
                ORDER BY s.captured_at DESC
                LIMIT 6
                """,
                (c["id"],),
            ).fetchall()
    groups = defaultdict(list)
    for c in claims:
        groups[(c["status"] or "candidate", c["evidence_strength"] or "weak")].append(c)
    lines = [
        "# Claims", "", f"Last generated: {now}", "",
        "Claims are explicit editorial records linked to source IDs. Candidate claims are not accepted facts; supported claims require human review or repeated strong evidence.", "",
        "## Summary", "",
        f"- Total claims: {len(claims)}",
        f"- Candidate claims: {sum(1 for c in claims if (c['status'] or 'candidate') == 'candidate')}",
        f"- Supported claims: {sum(1 for c in claims if c['status'] == 'supported')}", "",
    ]
    if not claims:
        lines += ["## Candidate claims", "", "No claim records have been extracted yet."]
    for status in STATUS_ORDER:
        title = "Candidate claims" if status == "candidate" else f"{status.title()} claims"
        emitted_status = False
        for strength in STRENGTH_ORDER:
            items = groups.get((status, strength), [])
            if not items:
                continue
            if not emitted_status:
                lines += [f"## {title}", ""]
                emitted_status = True
            lines += [f"### Evidence strength: {strength or 'unknown'}", ""]
            for c in items:
                lines.append(f"- **{c['claim_text']}**")
                lines.append(f"  - Claim ID: `{c['id']}`")
                lines.append(f"  - Confidence: `{c['confidence']}`; sources: {c['linked_sources']}")
                if c["current_best_understanding"]:
                    lines.append(f"  - Current best understanding: {c['current_best_understanding']}")
                refs = sources_by_claim.get(c["id"], [])
                if refs:
                    lines.append("  - Source IDs:")
                    for s in refs:
                        label = s["title"] or s["url"] or s["id"]
                        lines.append(f"    - `{s['id']}` — {label}")
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
