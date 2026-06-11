#!/usr/bin/env python3
"""Update book research pages from the local SQLite database and latest reports."""
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from research_common import DOCS, REPORTS, connect_db, init_db, utc_now


def q(con, sql): return con.execute(sql).fetchall()


def main() -> int:
    ap=argparse.ArgumentParser(); ap.add_argument('--run-id', required=True); args=ap.parse_args()
    init_db(); now=utc_now()
    with connect_db() as con:
        sources=q(con, 'SELECT * FROM sources ORDER BY captured_at DESC LIMIT 200')
        trends=q(con, 'SELECT * FROM trend_terms ORDER BY last_seen_at DESC, count DESC LIMIT 100')
    lines=['# Sources','',f'Last generated: {now}','', 'This page is generated from the local source database and contains sanitized source metadata only.','', 'Volume is not evidence. Quality and independence matter more than count.','']
    for r in sources:
        title = r['title'] or r['url'] or r['id']
        lines.append(f"- **{title}**")
        lines.append(f"  - Source ID: `{r['id']}`")
        if r['url']: lines.append(f"  - URL: {r['url']}")
        lines.append(f"  - Title: {r['title'] or 'unknown'}")
        lines.append(f"  - Author/organization: {r['author'] or r['publisher'] or 'unknown'}")
        lines.append(f"  - Date: {r['published_at'] or 'unknown'}; capture date: {r['captured_at']}")
        lines.append(f"  - Source type: `{r['source_type']}`; quality score: `{r['quality_score'] or 'unknown'}`")
        lines.append(f"  - Summary: {r['summary'] or 'No sanitized summary available.'}")
        lines.append(f"  - Relevant entities: `{r['relevant_entities'] or '[]'}`")
        lines.append(f"  - Extracted candidate claims: `{r['extracted_candidate_claims'] or '[]'}`")
        lines.append(f"  - Duplicate status: `{r['duplicate_status'] or 'unknown'}`")
        lines.append(f"  - Privacy/publication status: `{r['privacy_publication_status'] or r['visibility'] or 'unknown'}`")
        if r['quality_notes'] or r['publication_notes']:
            lines.append(f"  - Notes: {r['quality_notes'] or ''} {r['publication_notes'] or ''}".strip())
        if r['archived_path']: lines.append(f"  - Archive: `{r['archived_path']}`")
    (DOCS/'research/sources.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    lines=['# Trend Discovery','',f'Last generated: {now}','', 'Candidate terms are **not automatically promoted** into recurring searches. They are proposed for review.','']
    for r in trends:
        lines.append(f"- **{r['term']}** — {r['count']} mentions; status: `{r['status']}`; run: `{r['run_id']}`")
    (DOCS/'research/trend-discovery.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    # Daily report index
    daily=sorted((REPORTS/'daily').glob('*.md'), reverse=True)[:100]
    lines=['# Daily Reports','',f'Last generated: {now}','']
    for p in daily:
        lines.append(f"- **{p.stem}** — local report `{p.relative_to(DOCS.parent)}`")
    (DOCS/'reports/index.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    print('updated docs/research and docs/reports pages')
    return 0
if __name__=='__main__': raise SystemExit(main())
