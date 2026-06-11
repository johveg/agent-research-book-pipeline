#!/usr/bin/env python3
"""Generate conservative candidate claims from source records."""
from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict

from research_common import connect_db, init_db, utc_now
from editorial_common import (
    claim_id_for,
    clean_text,
    confidence_from_source_count,
    ensure_editorial_schema,
    evidence_strength,
    source_text,
    split_sentences,
)

TOPIC_TERMS = [
    "hermes", "openclaw", "loop engineering", "loop engineer", "agent", "agents",
    "context", "memory", "workflow", "automation", "continual learning", "coding agent",
]
GENERIC_SENTENCE_BITS = ["follow", "followers", "captured", "query:", "visible text", "linkedin search result"]


def candidate_sentence(sentence: str) -> str | None:
    s = clean_text(sentence, 420)
    low = s.lower()
    if len(s) < 60 or len(s) > 420:
        return None
    if not any(t in low for t in TOPIC_TERMS):
        return None
    if any(bit in low for bit in GENERIC_SENTENCE_BITS):
        return None
    if re.search(r"\b(i|we|you)\s+(am|are|was|were|have|think|believe)\b", low) and len(s) > 250:
        # Avoid turning long personal marketing posts into claims.
        return None
    if not re.search(r"\b(is|are|was|were|has|have|launches|launched|uses|enables|supports|tracks|needs|requires|helps|builds|provides|announced|introduced)\b", low):
        return None
    s = re.sub(r"^#+\s*", "", s).strip(" -")
    return s


def normalize_claim(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    text = text[0].upper() + text[1:] if text else text
    return text.rstrip(".") + "."


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=500)
    ap.add_argument("--max-claims", type=int, default=120)
    args = ap.parse_args()
    init_db()
    now = utc_now()
    grouped: dict[str, dict] = {}
    with connect_db() as con:
        ensure_editorial_schema(con)
        rows = con.execute("SELECT * FROM sources ORDER BY captured_at DESC LIMIT ?", (args.limit,)).fetchall()
        for row in rows:
            text = source_text(row, max_len=12000)
            # Prefer title/snippet-like first lines by processing full text but capped.
            for sent in split_sentences(text)[:80]:
                cand = candidate_sentence(sent)
                if not cand:
                    continue
                claim = normalize_claim(cand)
                key = claim.lower()
                rec = grouped.setdefault(key, {"claim_text": claim, "sources": {}, "quotes": {}})
                rec["sources"][row["id"]] = row
                rec["quotes"][row["id"]] = cand[:500]
                if len(grouped) >= args.max_claims:
                    break
            if len(grouped) >= args.max_claims:
                break
        for rec in grouped.values():
            source_count = len(rec["sources"])
            confidence = confidence_from_source_count(source_count)
            strength = evidence_strength(source_count, confidence)
            cid = claim_id_for(rec["claim_text"])
            status = "candidate"
            con.execute(
                """
                INSERT INTO claims (id, claim_text, claim_type, confidence, status, first_seen_at, last_seen_at,
                                    current_best_understanding, evidence_strength, source_count, updated_at)
                VALUES (?, ?, 'observation', ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                  confidence=excluded.confidence,
                  status=CASE WHEN claims.status IN ('supported','rejected','deprecated') THEN claims.status ELSE excluded.status END,
                  last_seen_at=excluded.last_seen_at,
                  current_best_understanding=excluded.current_best_understanding,
                  evidence_strength=excluded.evidence_strength,
                  source_count=excluded.source_count,
                  updated_at=excluded.updated_at
                """,
                (cid, rec["claim_text"], confidence, status, now, now, rec["claim_text"], strength, source_count, now),
            )
            for sid, quote in rec["quotes"].items():
                con.execute(
                    """
                    INSERT OR REPLACE INTO claim_sources (claim_id, source_id, quote, support_type)
                    VALUES (?, ?, ?, 'supports')
                    """,
                    (cid, sid, quote),
                )
        con.commit()
    print(json.dumps({"status": "ok", "claims_seen": len(grouped), "sources_read": len(rows)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
