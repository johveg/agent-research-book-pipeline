#!/usr/bin/env python3
"""Extract conservative candidate entities from archived source metadata/text."""
from __future__ import annotations

import argparse
import json
from collections import defaultdict

from research_common import connect_db, init_db, utc_now
from editorial_common import (
    candidate_entity_names,
    classify_entity,
    confidence_from_source_count,
    ensure_editorial_schema,
    entity_id_for,
    normalize_entity_name,
    source_text,
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=500)
    ap.add_argument("--min-mentions", type=int, default=1)
    args = ap.parse_args()
    init_db()
    now = utc_now()
    inserted = 0
    mentions: dict[str, dict] = {}
    with connect_db() as con:
        ensure_editorial_schema(con)
        rows = con.execute(
            "SELECT * FROM sources ORDER BY captured_at DESC LIMIT ?", (args.limit,)
        ).fetchall()
        for row in rows:
            text = source_text(row)
            for name, count in candidate_entity_names(text).items():
                canonical = normalize_entity_name(name)
                key = canonical.lower()
                rec = mentions.setdefault(
                    key,
                    {
                        "canonical_name": canonical,
                        "name": canonical,
                        "contexts": [],
                        "sources": defaultdict(int),
                    },
                )
                rec["sources"][row["id"]] += count
                rec["contexts"].append(text[:500])
        for rec in mentions.values():
            source_count = len(rec["sources"])
            total_mentions = sum(rec["sources"].values())
            if total_mentions < args.min_mentions:
                continue
            canonical = rec["canonical_name"]
            typ = classify_entity(canonical, " ".join(rec["contexts"][:3]))
            eid = entity_id_for(canonical)
            confidence = confidence_from_source_count(source_count)
            summary = f"Candidate {typ} entity extracted from {source_count} source(s)."
            con.execute(
                """
                INSERT INTO entities (id, type, name, canonical_name, summary, confidence, first_seen_at, last_seen_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                  type=excluded.type,
                  name=excluded.name,
                  canonical_name=excluded.canonical_name,
                  summary=excluded.summary,
                  confidence=excluded.confidence,
                  last_seen_at=excluded.last_seen_at,
                  updated_at=excluded.updated_at
                """,
                (eid, typ, rec["name"], canonical, summary, confidence, now, now, now),
            )
            for sid, count in rec["sources"].items():
                con.execute(
                    """
                    INSERT INTO entity_sources (entity_id, source_id, mention_count, first_seen_at, last_seen_at, sample)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(entity_id, source_id) DO UPDATE SET
                      mention_count=entity_sources.mention_count + excluded.mention_count,
                      last_seen_at=excluded.last_seen_at,
                      sample=COALESCE(entity_sources.sample, excluded.sample)
                    """,
                    (eid, sid, count, now, now, rec["contexts"][0][:300]),
                )
            inserted += 1
        con.commit()
    print(json.dumps({"status": "ok", "entities_seen": inserted, "sources_read": len(rows)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
