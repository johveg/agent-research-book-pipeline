#!/usr/bin/env python3
"""Fill the public book pages from already harvested, source-backed metadata.

Public-book hygiene:
- Use public web sources as named citations/examples.
- Use LinkedIn search-result captures only as aggregate signal counts in public pages.
- Keep raw/authenticated detail local unless an Editor explicitly promotes it.
"""
from __future__ import annotations

import re
import sqlite3
from collections import Counter

from research_common import DOCS, connect_db, slugify, utc_now

TOPICS = {
    "hermes": {
        "title": "2. Hermes",
        "path": DOCS / "book/02-hermes.md",
        "patterns": ["hermes", "hermes agent", "hermes atlas"],
        "intro": "Hermes is treated in this book as an operating environment for tool-using agents, persistent memory, skills, scheduled loops, and delivery across human-facing channels.",
    },
    "openclaw": {
        "title": "3. OpenClaw",
        "path": DOCS / "book/03-openclaw.md",
        "patterns": ["openclaw", "open claw"],
        "intro": "OpenClaw appears in the harvested material mostly as a comparison point for local/personal AI agent systems and skill/plugin ecosystems.",
    },
    "loop-engineering": {
        "title": "4. Loop Engineering",
        "path": DOCS / "book/04-loop-engineering.md",
        "patterns": ["loop engineering", "loop engineer", "agent loop", "closed loop"],
        "intro": "Loop engineering means designing reliable agent systems around recurring loops: context gathering, action, verification, state, reporting, retry, and escalation.",
    },
    "context-memory": {
        "title": "5. Context and Memory Architecture",
        "path": DOCS / "book/05-context-memory-architecture.md",
        "patterns": ["context", "memory", "persistent", "skill", "skills", "rag", "mcp"],
        "intro": "Context and memory architecture decide what the agent sees now, what is stored outside the model, what is retrieved later, and how procedures become reusable skills.",
    },
    "operating-loops": {
        "title": "6. Operating Loops in Production",
        "path": DOCS / "book/06-operating-loops.md",
        "patterns": ["cron", "watchdog", "monitor", "production", "retry", "verification", "github pages", "self-healing"],
        "intro": "Production loops need operational machinery around the model: schedules, manifests, verification, safe commits, status reports, and non-disruptive watchdogs.",
    },
}

STOP_TERMS = {
    "hashtag", "https", "http", "query", "captured", "result", "search", "visible", "urn", "url", "text",
    "linkedin", "source", "markdown", "path", "profile", "activity", "comment", "like", "share",
}


def rows(con, sql, params=()):
    con.row_factory = sqlite3.Row
    return con.execute(sql, params).fetchall()


def match_topic(text: str, topic: dict) -> bool:
    t = text.lower()
    return any(p.lower() in t for p in topic["patterns"])


def source_display(s: sqlite3.Row) -> str:
    title = re.sub(r"\s+", " ", (s["title"] or s["url"] or s["id"] or "Untitled source").strip())
    q = s["query"] or ""
    url = s["url"] or ""
    if url:
        return f"[{title}]({url}) — query `{q}`"
    return f"{title} — query `{q}`"


def topic_sources(con, topic):
    all_sources = rows(con, "SELECT * FROM sources ORDER BY captured_at DESC")
    matched=[]
    for s in all_sources:
        hay = " ".join(str(s[k] or "") for k in ["title", "url", "query", "publisher"])
        if match_topic(hay, topic): matched.append(s)
    web=[s for s in matched if s["source_type"] == "web"]
    li=[s for s in matched if s["source_type"] != "web"]
    return matched, web, li


def topic_entities(con, topic):
    ents=[]
    sql = """
    SELECT e.*, COALESCE(SUM(es.mention_count),0) mentions, COUNT(es.source_id) source_count
    FROM entities e LEFT JOIN entity_sources es ON es.entity_id=e.id
    GROUP BY e.id ORDER BY mentions DESC LIMIT 500
    """
    for e in rows(con, sql):
        hay = " ".join(str(e[k] or "") for k in ["name", "canonical_name", "summary", "type"])
        if match_topic(hay, topic): ents.append(e)
    return ents[:30]


def source_themes(web_sources):
    text=" ".join((s["title"] or "") + " " + (s["url"] or "") for s in web_sources).lower()
    themes=[]
    for label, words in [
        ("agent comparison", ["vs", "compared", "comparison", "differences"]),
        ("skills and reusable procedures", ["skill", "skills"]),
        ("cost and operations", ["cost", "run", "deploy", "deployment"]),
        ("interfaces and workspaces", ["webui", "desktop", "workspace", "gui"]),
        ("memory and persistence", ["memory", "persistent", "context"]),
        ("MCP/tool integration", ["mcp", "tool", "tools"]),
    ]:
        if any(w in text for w in words): themes.append(label)
    return themes


def write_chapter(con, topic):
    matched, web, li = topic_sources(con, topic)
    ents = topic_entities(con, topic)
    themes = source_themes(web)
    now=utc_now()
    lines=[f"# {topic['title']}", "", topic["intro"], "", "## What the existing harvest contributes", ""]
    lines.append(f"The current corpus has **{len(matched)} matching source records** for this topic: **{len(web)} public web records** and **{len(li)} LinkedIn search-result records**.")
    if li:
        lines.append("LinkedIn records are used here as aggregate signal, not as individually published citations. This keeps the public book focused on professional/public evidence while avoiding unnecessary publication of social-search snippets.")
    lines.append("")
    if themes:
        lines += ["## Repeated themes in the web harvest", ""]
        for t in themes: lines.append(f"- {t}")
        lines.append("")
    if ents:
        lines += ["## Important related entities", ""]
        for e in ents[:12]:
            slug=slugify(e["canonical_name"])
            page=DOCS/"entities"/f"{slug}.md"
            link=f"[{e['canonical_name']}](../entities/{slug}.md)" if page.exists() else e["canonical_name"]
            lines.append(f"- {link} — `{e['type']}`, mentions: {e['mentions']}, linked sources: {e['source_count']}")
        lines.append("")
    if web:
        lines += ["## Representative public web sources", ""]
        for s in web[:12]: lines.append(f"- {source_display(s)}")
        lines.append("")
    else:
        lines += ["## Public-source gap", "", "The current harvest has no public web source records for this topic yet. The topic is visible in social/search signals, but the Editor role should not promote stronger narrative claims until public corroborating sources are added.", ""]
    lines += [
        "## Draft synthesis",
        "",
        "At this stage, the book can safely say that this topic appears in the harvested monitoring corpus and is connected to the entities and public sources listed above. Stronger prose should be written after the Editor role reviews source quality, removes false positives, and decides which claims deserve promotion.",
        "",
        f"Last generated from harvest: {now}.",
    ]
    topic["path"].write_text("\n".join(lines)+"\n", encoding="utf-8")


def write_preface_and_ch1(con):
    now=utc_now()
    total_sources=rows(con,"SELECT COUNT(*) n FROM sources")[0]["n"]
    total_entities=rows(con,"SELECT COUNT(*) n FROM entities")[0]["n"]
    total_claims=rows(con,"SELECT COUNT(*) n FROM claims")[0]["n"]
    by_type=rows(con,"SELECT source_type, COUNT(*) n FROM sources GROUP BY source_type ORDER BY n DESC")
    latest=rows(con,"SELECT id,status,started_at,ended_at FROM runs ORDER BY started_at DESC LIMIT 5")
    preface=["# Preface", "", "This is a living research book about Hermes, OpenClaw, and loop engineering. It is generated from a daily loop that collects public web material and authenticated LinkedIn search-result text, stores source metadata, extracts entities and claims, refreshes local search/vector state, and publishes curated Markdown through GitHub Pages.", "", "## Current corpus", "", f"- Sources: **{total_sources}**", f"- Entities: **{total_entities}**", f"- Claims: **{total_claims}**", "", "## Source mix", ""]
    for r in by_type: preface.append(f"- `{r['source_type']}`: {r['n']}")
    preface += ["", "## Recent runs", ""]
    for r in latest: preface.append(f"- `{r['id']}` — {r['status']} — {r['started_at']} to {r['ended_at'] or 'running'}")
    preface += ["", "## Reading note", "", "The book separates harvested evidence from polished claims. LinkedIn captures influence aggregate signals and discovery, while public-facing citations should prefer web sources or explicitly promoted professional/public evidence.", "", f"Last generated from harvest: {now}."]
    (DOCS/"book/preface.md").write_text("\n".join(preface)+"\n", encoding="utf-8")

    ch1=["# 1. The Agent Loop", "", "The central thesis of this book is that useful AI agents are not just prompts. They are loops: systems that repeatedly gather context, act through tools, verify outputs, save state, and report back to people.", "", "## The basic loop", "", "1. Define the goal.", "2. Gather current context from files, web, databases, sessions, or messages.", "3. Act through tools or scripts.", "4. Verify the result with explicit checks.", "5. Save durable state outside the model.", "6. Report the result to a human channel.", "7. Retry safe failures and escalate unsafe or ambiguous ones.", "", "## Evidence in this project", "", f"The book loop itself has already processed {total_sources} source records and maintains {total_entities} entity records and {total_claims} claim records. Its daily collector, status poller, watchdog, database, vector index, Git commits, and GitHub Pages publication are all examples of the loop pattern described here.", "", "## Cross-links", "", "- [Hermes](02-hermes.md)", "- [OpenClaw](03-openclaw.md)", "- [Loop Engineering](04-loop-engineering.md)", "- [Context and Memory Architecture](05-context-memory-architecture.md)", "- [Operating Loops in Production](06-operating-loops.md)", "", f"Last generated from harvest: {now}."]
    (DOCS/"book/01-the-agent-loop.md").write_text("\n".join(ch1)+"\n", encoding="utf-8")


def write_entity_indexes(con):
    now=utc_now()
    groups={"companies":["company","organization","org"],"people":["person","people"],"projects":["project","product","repository","tool"],"concepts":["concept","technology","framework","topic"]}
    all_entities=rows(con,"""SELECT e.*, COALESCE(SUM(es.mention_count),0) mentions, COUNT(es.source_id) source_count FROM entities e LEFT JOIN entity_sources es ON es.entity_id=e.id GROUP BY e.id ORDER BY mentions DESC""")
    for name, types in groups.items():
        lines=[f"# {name.title()}", "", f"Last generated: {now}", "", "These entries come from harvested entity records. They are candidates for deeper editorial pages, not final assertions of importance.", ""]
        count=0
        for e in all_entities:
            et=(e["type"] or "").lower()
            is_match=any(t in et for t in types) or (name=="concepts" and not any(t in et for t in ["person","company","organization"]))
            if not is_match: continue
            slug=slugify(e["canonical_name"]); page=DOCS/"entities"/f"{slug}.md"
            link=f"[{e['canonical_name']}]({slug}.md)" if page.exists() else e["canonical_name"]
            lines.append(f"- {link} — `{e['type']}`; mentions: {e['mentions']}; sources: {e['source_count']}")
            count += 1
            if count >= 80: break
        (DOCS/"entities"/f"{name}.md").write_text("\n".join(lines)+"\n", encoding="utf-8")


def write_research_pages(con):
    now=utc_now()
    claims=rows(con,"SELECT * FROM claims ORDER BY source_count DESC, updated_at DESC LIMIT 100")
    candidate_count = sum(1 for c in claims if (c['status'] or 'candidate') == 'candidate')
    supported_count = sum(1 for c in claims if c['status'] == 'supported')
    lines=["# Claims", "", f"Last generated: {now}", "", "Claims are extracted or inferred records requiring editorial review before they become polished narrative. Public chapters should promote only claims with adequate source quality.", "", "## Summary", "", f"- Total claims: {len(claims)}", f"- Candidate claims: {candidate_count}", f"- Supported claims: {supported_count}", "", "## Candidate claims", ""]
    if not claims:
        lines.append("No claim records have been extracted yet.")
    for c in claims:
        lines.append(f"- {c['claim_text']}")
        lines.append(f"  - Type: `{c['claim_type']}`; confidence: `{c['confidence']}`; evidence: `{c['evidence_strength']}`; sources: {c['source_count']}; status: `{c['status']}`")
    (DOCS/"research/claims.md").write_text("\n".join(lines)+"\n", encoding="utf-8")

    trends=rows(con,"SELECT * FROM trend_terms ORDER BY count DESC LIMIT 120")
    lines=["# Trend Discovery", "", f"Last generated: {now}", "", "Candidate terms are **not automatically promoted** into recurring searches. They are proposed for review.", "", "## Candidate terms", ""]
    for r in trends:
        term=(r['term'] or '').strip().lower()
        if term in STOP_TERMS or len(term)<3: continue
        lines.append(f"- **{r['term']}** — {r['count']} mentions; status: `{r['status']}`; run: `{r['run_id']}`")
    (DOCS/"research/trend-discovery.md").write_text("\n".join(lines)+"\n", encoding="utf-8")


def write_open_questions(con):
    now=utc_now()
    weak=rows(con,"SELECT * FROM claims WHERE confidence in ('low','medium') ORDER BY source_count DESC LIMIT 20")
    lines=["# Open Questions", "", "This page tracks questions the Editor role should resolve before the book becomes more assertive.", "", "## Questions", "", "- Which harvested claims deserve promotion from candidate notes into the main narrative?", "- Which trend terms represent real emerging topics rather than LinkedIn/web boilerplate?", "- Which comparisons between Hermes and OpenClaw are source-backed enough for a stable comparison chapter?", "- Which LinkedIn observations are public/professional enough to mention in the public book, and which should remain private/local?"]
    if weak:
        lines += ["", "## Claims needing stronger evidence", ""]
        for c in weak[:12]: lines.append(f"- {c['claim_text']} — confidence `{c['confidence']}`, sources {c['source_count']}")
    lines += ["", f"Last generated from harvest: {now}."]
    (DOCS/"book/open-questions.md").write_text("\n".join(lines)+"\n", encoding="utf-8")


def main():
    with connect_db() as con:
        write_preface_and_ch1(con)
        for topic in TOPICS.values(): write_chapter(con, topic)
        write_entity_indexes(con)
        write_research_pages(con)
        write_open_questions(con)
    print("filled public book pages from harvested metadata")

if __name__ == "__main__": main()
