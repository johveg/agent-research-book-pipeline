#!/usr/bin/env python3
"""Generate entity index and per-entity pages from editorial tables."""
from __future__ import annotations

import argparse
import json

from research_common import DOCS, connect_db, init_db, slugify, utc_now
from editorial_common import ensure_editorial_schema, is_publishable_entity

ENTITY_DIR = DOCS / "entities"
PROTECTED_ENTITY_PAGES = {"index.md", "companies.md", "people.md", "projects.md", "concepts.md"}


def entity_file(entity) -> str:
    return f"entities/{slugify(entity['canonical_name'], 70)}.md"


def source_label(row) -> str:
    return row["title"] or row["url"] or row["id"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", default="manual")
    ap.add_argument("--limit", type=int, default=120)
    args = ap.parse_args()
    init_db()
    now = utc_now()
    ENTITY_DIR.mkdir(parents=True, exist_ok=True)
    for old in ENTITY_DIR.glob("*.md"):
        if old.name not in PROTECTED_ENTITY_PAGES:
            old.unlink()
    generated = []
    with connect_db() as con:
        ensure_editorial_schema(con)
        candidates = con.execute(
            """
            SELECT e.*, COUNT(es.source_id) AS source_count, COALESCE(SUM(es.mention_count),0) AS mention_count
            FROM entities e
            LEFT JOIN entity_sources es ON es.entity_id = e.id
            GROUP BY e.id
            HAVING source_count >= 2
            ORDER BY source_count DESC, mention_count DESC, canonical_name ASC
            LIMIT ?
            """,
            (min(args.limit * 10, 1000),),
        ).fetchall()
        entities = [e for e in candidates if is_publishable_entity(e['canonical_name'], e['type'], e['source_count'])][:args.limit]
        index = ["# Entities", "", f"Last generated: {now}", "", "Entities are conservative candidates extracted from collected source metadata and archived text. They require human review before being treated as canonical.", "", "| Entity | Type | Confidence | Source count |", "|---|---:|---:|---:|"]
        for e in entities:
            rel = entity_file(e)
            index.append(f"| [{e['canonical_name']}]({rel.replace('entities/', '')}) | {e['type']} | {e['confidence']} | {e['source_count']} |")
            claims = con.execute(
                """
                SELECT c.*, COUNT(cs.source_id) AS linked_sources
                FROM claims c
                LEFT JOIN claim_sources cs ON cs.claim_id = c.id
                WHERE lower(c.claim_text) LIKE ?
                GROUP BY c.id
                ORDER BY c.status, linked_sources DESC, c.claim_text
                LIMIT 20
                """,
                (f"%{e['canonical_name'].lower()}%",),
            ).fetchall()
            sources = con.execute(
                """
                SELECT s.*, es.mention_count
                FROM entity_sources es JOIN sources s ON s.id = es.source_id
                WHERE es.entity_id = ?
                ORDER BY es.mention_count DESC, s.captured_at DESC
                LIMIT 25
                """,
                (e["id"],),
            ).fetchall()
            lines = [
                f"# {e['canonical_name']}", "",
                f"Last generated: {now}", "",
                f"- Type: `{e['type']}`",
                f"- Confidence: `{e['confidence']}`",
                f"- First seen: {e['first_seen_at'] or 'unknown'}",
                f"- Last seen: {e['last_seen_at'] or 'unknown'}",
                f"- Source count: {e['source_count']}",
                f"- Mention count: {e['mention_count']}", "",
                "## Description", "", e["summary"] or "Candidate entity extracted from source evidence; no human-written description yet.", "",
                "## Related claims", "",
            ]
            if claims:
                for c in claims:
                    lines.append(f"- **{c['status']} / {c['evidence_strength'] or 'weak'}** — {c['claim_text']} (`{c['id']}`)")
            else:
                lines.append("No related claim records yet.")
            lines += ["", "## Source references", ""]
            for s in sources:
                lines.append(f"- `{s['id']}` — {source_label(s)}")
                if s["url"]:
                    lines.append(f"  - URL: {s['url']}")
                if s["archived_path"]:
                    lines.append(f"  - Archive: `{s['archived_path']}`")
            out = DOCS / rel
            out.write_text("\n".join(lines) + "\n", encoding="utf-8")
            generated.append(str(out))
    (ENTITY_DIR / "index.md").write_text("\n".join(index) + "\n", encoding="utf-8")
    print(json.dumps({"status": "ok", "entities": len(generated), "index": str(ENTITY_DIR / "index.md")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
