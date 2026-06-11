#!/usr/bin/env python3
"""Conservatively synthesize chapter evidence-status sections from claim records."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from research_common import DOCS, connect_db, init_db, utc_now
from editorial_common import ensure_editorial_schema

CHAPTERS = {
    "book/preface.md": {
        "title": "Preface",
        "brief": "chapter-briefs/preface.md",
        "intro": "This book tracks practical agent engineering as it develops in public: tools, operating patterns, context architecture, memory architecture, and durable loops.",
        "terms": ["agent", "agents", "workflow", "automation"],
    },
    "book/01-the-agent-loop.md": {
        "title": "1. The Agent Loop",
        "brief": "chapter-briefs/01-the-agent-loop.md",
        "intro": "The central pattern is a closed loop: goal, context, action, verification, saved state, report, retry, and escalation.",
        "terms": ["agent", "loop", "workflow", "verification", "automation"],
    },
    "book/02-hermes.md": {
        "title": "2. Hermes",
        "brief": "chapter-briefs/02-hermes.md",
        "intro": "Hermes Agent is treated here as an operating environment for tool-using agents, cron loops, memory, skills, and multi-platform delivery.",
        "terms": ["hermes", "nous research"],
    },
    "book/03-openclaw.md": {
        "title": "3. OpenClaw",
        "brief": "chapter-briefs/03-openclaw.md",
        "intro": "This chapter tracks public signals around OpenClaw and adjacent agentic coding/operator systems.",
        "terms": ["openclaw"],
    },
    "book/04-loop-engineering.md": {
        "title": "4. Loop Engineering",
        "brief": "chapter-briefs/04-loop-engineering.md",
        "intro": "Loop engineering means designing the system around closed agent loops rather than only improving prompts.",
        "terms": ["loop engineering", "loop engineer"],
    },
    "book/05-context-memory-architecture.md": {
        "title": "5. Context and Memory Architecture",
        "brief": "chapter-briefs/05-context-memory-architecture.md",
        "intro": "Context architecture controls what the agent sees; memory architecture controls what is remembered, where, and for how long.",
        "terms": ["context", "memory", "architecture"],
    },
    "book/06-operating-loops.md": {
        "title": "6. Operating Loops in Production",
        "brief": "chapter-briefs/06-operating-loops.md",
        "intro": "Production loops need manifests, verification, state files, safe retries, non-destructive watchdogs, and human escalation boundaries.",
        "terms": ["production", "cron", "watchdog", "operating", "loop"],
    },
    "book/open-questions.md": {
        "title": "Open Questions",
        "brief": "chapter-briefs/open-questions.md",
        "intro": "This page records unresolved questions and weak signals that need more evidence.",
        "terms": ["question", "candidate", "weak", "trend"],
    },
}

REQUIRED_BRIEF_HEADINGS = [
    "Purpose", "Target reader", "Main argument", "Required concepts", "Required claims",
    "Required examples", "Allowed source types", "Excluded source types", "Open questions",
    "What this chapter must not claim", "Desired tone", "Desired length", "Related entities",
    "Publication readiness criteria",
]


def validate_brief(rel: str) -> None:
    path = DOCS / rel
    if not path.exists():
        raise SystemExit(f"Missing chapter brief before Author synthesis: {rel}")
    text = path.read_text(encoding="utf-8", errors="ignore")
    missing = [h for h in REQUIRED_BRIEF_HEADINGS if f"## {h}" not in text]
    if missing:
        raise SystemExit(f"Chapter brief {rel} is missing required headings: {', '.join(missing)}")


def find_claims(con, terms: list[str], approved_only: bool = True):
    clauses = []
    params = []
    for t in terms:
        clauses.append("lower(claim_text) LIKE ?")
        params.append(f"%{t.lower()}%")
    # Author usage rule: supported claims may be used; weakly_supported claims
    # may be used only with caveat; promoted_to_chapter claims are Editor-approved.
    status_clause = "status IN ('supported','weakly_supported','promoted_to_chapter')" if approved_only else "1=1"
    sql = f"""
      SELECT c.*, COUNT(cs.source_id) AS linked_sources
      FROM claims c LEFT JOIN claim_sources cs ON cs.claim_id = c.id
      WHERE ({' OR '.join(clauses)}) AND ({status_clause})
      GROUP BY c.id
      ORDER BY CASE c.status WHEN 'supported' THEN 0 ELSE 1 END,
               CASE c.evidence_strength WHEN 'strong' THEN 0 WHEN 'moderate' THEN 1 ELSE 2 END,
               linked_sources DESC
      LIMIT 12
    """
    return con.execute(sql, params).fetchall()


def write_chapter(path: Path, title: str, intro: str, claims, candidate_count: int, now: str) -> None:
    lines = [f"# {title}", "", intro, "", "## Current evidence status", ""]
    if claims:
        lines.append("The following points are synthesized only from claim records whose status allows Author use:")
        lines.append("")
        for c in claims:
            caveat = "Current evidence suggests: " if c["status"] == "weakly_supported" else ""
            lines.append(f"- {caveat}{c['claim_text']} (`{c['id']}`, status `{c['status']}`, {c['evidence_strength'] or 'weak'} evidence, {c['linked_sources']} source(s))")
    else:
        lines.append("No publishable chapter update is recommended for this section because the current evidence base does not contain enough approved claims.")
        lines.append("")
        lines.append(f"Claims matching this chapter but not usable in prose: {candidate_count}.")
    lines += ["", "## Editorial policy", "", f"Last generated: {now}. This chapter is not synthesized directly from raw LinkedIn/web captures; it only uses claim records from `docs/research/claims.md`."]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", default="manual")
    args = ap.parse_args()
    init_db()
    now = utc_now()
    updated = []
    with connect_db() as con:
        ensure_editorial_schema(con)
        for rel, cfg in CHAPTERS.items():
            validate_brief(cfg["brief"])
            supported = find_claims(con, cfg["terms"], approved_only=True)
            candidates = find_claims(con, cfg["terms"], approved_only=False)
            out = DOCS / rel
            write_chapter(out, cfg["title"], cfg["intro"], supported, len(candidates), now)
            updated.append(rel)
    print(json.dumps({"status": "ok", "updated": updated}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
