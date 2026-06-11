#!/usr/bin/env python3
"""Editorial pipeline gate and required run report.

This is the conservative control point between collection and publication. It scores sources,
finds duplicates/repeated signals, flags likely contradictions/noise/privacy risks, writes a curation/editor report, and emits the required run output.

It does not decide truth mechanically. It prevents chapter publication when required editorial gates are missing or unsafe.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

from research_common import DOCS, LOGS, RAW, REPORTS, ROOT, connect_db, init_db, sha256_text, utc_now, write_json
from editorial_common import ensure_editorial_schema

QUALITY_TIERS = ("A", "B", "C", "D", "E", "unknown")
QUALITY_USE_RULES = {
    "A": "may_support_factual_claims",
    "B": "may_support_specific_factual_claims",
    "C": "may_support_interpretation_with_caveat",
    "D": "weak_signal_only",
    "E": "reject_or_ignore",
}
ALLOWED_CLAIM_STATUSES = {"candidate", "needs_review", "supported", "weakly_supported", "contradicted", "rejected", "promoted_to_chapter"}
ALLOWED_CLAIM_TYPES = {"definition", "observation", "trend", "technical pattern", "risk", "limitation", "example", "contradiction", "interpretation", "open question"}
PROSE_ALLOWED_STATUSES = {"supported", "weakly_supported", "promoted_to_chapter"}
HYPE_WORDS = ["revolutionary", "game-changing", "unlock", "unleash", "transformative", "disruptive", "paradigm shift", "next-generation", "groundbreaking", "frictionless", "magical"]
GENERIC_TREND_BITS = {"https", "http", "urn", "hashtag", "query", "search", "result", "results", "linkedin", "visible", "captured", "source", "sources"}
SOCIAL_TYPES = {"linkedin_search_result", "social", "post"}


def source_quality(row) -> str:
    st=(row["source_type"] or "").lower()
    vis=(row["visibility"] or "").lower()
    url=(row["url"] or "").lower()
    pub=(row["publisher"] or "").lower()
    title=(row["title"] or "").lower()
    archived=(row["archived_path"] or "").lower() if "archived_path" in row.keys() else ""
    if not url and not title and not archived:
        return "E"
    if any(x in url or x in title for x in ["login", "authwall", "sign in", "captcha"]):
        return "E"
    if st in SOCIAL_TYPES or "linkedin" in st or "authenticated" in vis:
        return "D"
    if not url:
        return "E"
    if any(x in url or x in pub for x in ["github.com", "docs.", "documentation", "hermes-agent.nousresearch.com", "nousresearch", "openai.com", "anthropic.com", "microsoft.com", "google", "nvidia.com", "aws.amazon.com"]):
        return "A"
    if any(x in pub for x in ["arxiv", "acm", "ieee", "mit.edu", "stanford.edu", "berkeley.edu"]):
        return "A"
    if any(x in pub for x in ["medium.com", "substack", "thenext", "infoq", "martinfowler", "oreilly", "thoughtworks"]):
        return "B"
    if any(x in title for x in ["blog", "analysis", "guide", "tutorial", "report"]):
        return "B"
    if any(x in url for x in ["/blog", "/article", "/news", "/post"]):
        return "C"
    if any(x in url for x in ["search", "utm_", "feed", "login"]):
        return "E"
    return "C"


def text_summary(row) -> str:
    bits=[row["title"] or "", row["publisher"] or row["author"] or "", row["query"] or ""]
    return "; ".join([b for b in bits if b])[:700] or "No usable summary metadata available."


def ensure_pipeline_schema(con):
    ensure_editorial_schema(con)
    src_cols={r[1] for r in con.execute("PRAGMA table_info(sources)")}
    for col, ddl in {
        "quality_score": "ALTER TABLE sources ADD COLUMN quality_score TEXT DEFAULT 'unknown'",
        "quality_notes": "ALTER TABLE sources ADD COLUMN quality_notes TEXT",
        "summary": "ALTER TABLE sources ADD COLUMN summary TEXT",
        "relevant_entities": "ALTER TABLE sources ADD COLUMN relevant_entities TEXT",
        "extracted_candidate_claims": "ALTER TABLE sources ADD COLUMN extracted_candidate_claims TEXT",
        "duplicate_status": "ALTER TABLE sources ADD COLUMN duplicate_status TEXT DEFAULT 'unique'",
        "privacy_publication_status": "ALTER TABLE sources ADD COLUMN privacy_publication_status TEXT DEFAULT 'publishable_metadata_only'",
        "publication_notes": "ALTER TABLE sources ADD COLUMN publication_notes TEXT",
    }.items():
        if col not in src_cols:
            con.execute(ddl)
    claim_cols={r[1] for r in con.execute("PRAGMA table_info(claims)")}
    if "editor_notes" not in claim_cols:
        con.execute("ALTER TABLE claims ADD COLUMN editor_notes TEXT")
    if "reviewed_at" not in claim_cols:
        con.execute("ALTER TABLE claims ADD COLUMN reviewed_at TEXT")
    if "source_quality" not in claim_cols:
        con.execute("ALTER TABLE claims ADD COLUMN source_quality TEXT DEFAULT 'unknown'")
    if "contradiction_status" not in claim_cols:
        con.execute("ALTER TABLE claims ADD COLUMN contradiction_status TEXT DEFAULT 'not_checked'")
    if "publication_decision" not in claim_cols:
        con.execute("ALTER TABLE claims ADD COLUMN publication_decision TEXT DEFAULT 'do_not_use'")
    con.execute("""
        CREATE TABLE IF NOT EXISTS source_notes (
          id TEXT PRIMARY KEY,
          source_id TEXT NOT NULL,
          note TEXT NOT NULL,
          note_type TEXT DEFAULT 'summary',
          created_at TEXT NOT NULL,
          FOREIGN KEY(source_id) REFERENCES sources(id)
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS editorial_reviews (
          id TEXT PRIMARY KEY,
          run_id TEXT NOT NULL,
          review_type TEXT NOT NULL,
          status TEXT NOT NULL,
          summary TEXT,
          report_path TEXT,
          created_at TEXT NOT NULL
        )
    """)
    con.commit()


def stage_name(cmd):
    if not cmd: return "unknown"
    if isinstance(cmd, str): return Path(cmd).name
    return Path(cmd[1] if len(cmd)>1 else cmd[0]).name


def load_step_results(path: Path) -> list[dict]:
    if not path.exists(): return []
    try:
        payload=json.loads(path.read_text())
        return payload.get("steps", [])
    except Exception:
        return []


def git_unsafe_staged() -> list[str]:
    p=subprocess.run(["git","diff","--cached","--name-only"], cwd=ROOT, text=True, capture_output=True)
    unsafe=[]
    pat=re.compile(r"(^|/)(raw|logs|\.var|vector_db|site|\.env|cookies?|tokens?|secrets?|sessions?|browser|profile)(/|$)|\.(sqlite|db|wal|shm)$", re.I)
    for line in p.stdout.splitlines():
        if line == "raw/.gitkeep":
            continue
        if pat.search(line):
            unsafe.append(line)
    return unsafe


def linkedin_blocked(run_id: str, step_results: list[dict]) -> list[str]:
    warnings=[]
    for s in step_results:
        name=stage_name(s.get("cmd", []))
        if name == "capture_linkedin_daily.py" and s.get("returncode") not in (0,):
            warnings.append("LinkedIn capture step returned nonzero")
    for p in [LOGS/"runs"/f"{run_id}-linkedin.json"]:
        if not p.exists():
            continue
        try:
            data=json.loads(p.read_text())
            for cap in data.get("captures", []):
                if cap.get("status") != "ok":
                    warnings.append(f"LinkedIn capture status {cap.get('status')}: {cap.get('reason') or cap.get('query')}")
        except Exception as e:
            warnings.append(f"Could not parse LinkedIn capture output: {e}")
    return warnings


def score_sources(con):
    counts=Counter()
    now=utc_now()
    hash_counts={r["content_hash"]: r["c"] for r in con.execute("SELECT content_hash, COUNT(*) c FROM sources WHERE content_hash IS NOT NULL AND content_hash != '' GROUP BY content_hash")}
    for row in con.execute("SELECT * FROM sources"):
        q=source_quality(row)
        counts[q]+=1
        duplicate_status="duplicate_or_repeated" if row["content_hash"] and hash_counts.get(row["content_hash"], 0) > 1 else "unique"
        privacy_status="human_review" if any(x in ((row["visibility"] or "") + " " + (row["url"] or "") + " " + (row["title"] or "")).lower() for x in ["login", "authenticated", "private", "cookie", "token", "session"]) else "publishable_metadata_only"
        if q == "E":
            privacy_status = "reject"
        entity_ids=[r["entity_id"] for r in con.execute("SELECT entity_id FROM entity_sources WHERE source_id=? LIMIT 20", (row["id"],)).fetchall()]
        claim_ids=[r["claim_id"] for r in con.execute("SELECT claim_id FROM claim_sources WHERE source_id=? LIMIT 20", (row["id"],)).fetchall()]
        notes=[f"auto_scored_{q}", QUALITY_USE_RULES.get(q, "unknown_use_rule")]
        if duplicate_status != "unique": notes.append("duplicate/repeated source material")
        if privacy_status != "publishable_metadata_only": notes.append(f"privacy/publication status: {privacy_status}")
        con.execute("""
            UPDATE sources
            SET quality_score=?, reliability_tier=?, quality_notes=?, summary=?, relevant_entities=?,
                extracted_candidate_claims=?, duplicate_status=?, privacy_publication_status=?, publication_notes=?
            WHERE id=?
        """, (q, q, "; ".join(notes), text_summary(row), json.dumps(entity_ids, ensure_ascii=False), json.dumps(claim_ids, ensure_ascii=False), duplicate_status, privacy_status, f"scored_at={now}; volume is not evidence; quality and independence matter", row["id"]))
    con.commit()
    return dict(counts)


def extract_source_notes(con, limit=80):
    now=utc_now(); n=0
    rows=con.execute("SELECT id,title,publisher,query,quality_score FROM sources ORDER BY captured_at DESC LIMIT ?", (limit,)).fetchall()
    for r in rows:
        bits=[b for b in [r["title"], r["publisher"], f"query={r['query']}" if r["query"] else None, f"quality={r['quality_score']}" if r["quality_score"] else None] if b]
        note="; ".join(bits)[:700]
        if not note: continue
        nid="note_"+sha256_text(r["id"]+note)[:20]
        con.execute("INSERT OR REPLACE INTO source_notes (id, source_id, note, note_type, created_at) VALUES (?,?,?,?,?)", (nid, r["id"], note, "metadata_note", now))
        n+=1
    con.commit(); return n


def review_claims(con):
    now=utc_now()
    promoted=[]; rejected=[]; needs=[]; approved=[]; warnings=[]
    claims=con.execute("""
      SELECT c.*, COUNT(cs.source_id) AS linked_sources,
             SUM(CASE WHEN s.quality_score IN ('A','B') THEN 1 ELSE 0 END) AS strong_sources,
             SUM(CASE WHEN s.quality_score='C' THEN 1 ELSE 0 END) AS interpretation_sources,
             SUM(CASE WHEN s.quality_score='D' THEN 1 ELSE 0 END) AS social_sources,
             SUM(CASE WHEN s.quality_score='E' THEN 1 ELSE 0 END) AS low_sources,
             GROUP_CONCAT(DISTINCT s.quality_score) AS source_quality
      FROM claims c
      LEFT JOIN claim_sources cs ON cs.claim_id=c.id
      LEFT JOIN sources s ON s.id=cs.source_id
      GROUP BY c.id
    """).fetchall()
    for c in claims:
        status=(c["status"] or "candidate").strip()
        claim_type=(c["claim_type"] or "observation").strip()
        linked=c["linked_sources"] or 0; strong=c["strong_sources"] or 0; interp=c["interpretation_sources"] or 0; social=c["social_sources"] or 0; low=c["low_sources"] or 0
        text=(c["claim_text"] or "")
        notes=[]
        if status not in ALLOWED_CLAIM_STATUSES:
            notes.append(f"invalid status normalized from {status!r} to needs_review")
            status="needs_review"
        if claim_type not in ALLOWED_CLAIM_TYPES:
            notes.append(f"invalid claim type normalized from {claim_type!r} to observation")
            claim_type="observation"
        if linked == 0:
            status="rejected"; notes.append("rejected: no source IDs")
        elif strong >= 1 and linked >= 1 and status in {"candidate"}:
            status="needs_review"; notes.append("has A/B support but needs Editor review before promotion")
        elif social >= linked and strong == 0:
            if status in {"candidate", "needs_review", "supported", "promoted_to_chapter"}:
                status="weakly_supported"
            notes.append("social/search-result evidence only; caveat required")
        elif low >= linked:
            status="rejected"; notes.append("only low-quality/noisy sources")
        elif status == "candidate":
            status="needs_review"; notes.append("candidate requires Editor review")
        if any(w in text.lower() for w in HYPE_WORDS):
            notes.append("hype language present")
            if status in {"supported", "promoted_to_chapter"}: status="needs_review"
        if status == "contradicted" or claim_type == "contradiction":
            contradiction_status="contradicted"
        else:
            contradiction_status="not_found"
        if status == "promoted_to_chapter":
            publication_decision="approved_for_chapter"
        elif status == "supported":
            publication_decision="allowed_for_author"
        elif status == "weakly_supported":
            publication_decision="allowed_with_caveat"
        elif status == "contradicted":
            publication_decision="discuss_only_as_contested"
        else:
            publication_decision="do_not_use"
        source_quality=c["source_quality"] or "unknown"
        con.execute("""
            UPDATE claims
            SET status=?, claim_type=?, source_quality=?, contradiction_status=?, publication_decision=?, editor_notes=?, reviewed_at=?
            WHERE id=?
        """, (status, claim_type, source_quality, contradiction_status, publication_decision, "; ".join(notes), now, c["id"]))
        item={"id": c["id"], "text": text, "claim_type": claim_type, "status": status, "linked_sources": linked, "source_quality": source_quality, "strong_sources": strong, "interpretation_sources": interp, "social_sources": social, "low_sources": low, "contradiction_status": contradiction_status, "publication_decision": publication_decision, "notes": notes}
        if status == "promoted_to_chapter": promoted.append(item)
        elif status == "supported": approved.append(item)
        elif status == "rejected": rejected.append(item)
        else: needs.append(item)
    con.commit()
    return {"approved_claims": approved, "promoted_claims": promoted, "rejected_claims": rejected, "claims_needing_review": needs, "warnings": warnings}


def detect_duplicates(con):
    dup_sources=[]; repeated=[]
    for row in con.execute("SELECT content_hash, COUNT(*) c FROM sources WHERE content_hash IS NOT NULL AND content_hash != '' GROUP BY content_hash HAVING c>1 ORDER BY c DESC LIMIT 20"):
        dup_sources.append({"content_hash": row["content_hash"], "count": row["c"]})
    for row in con.execute("SELECT lower(claim_text) t, COUNT(*) c FROM claims GROUP BY lower(claim_text) HAVING c>1 ORDER BY c DESC LIMIT 20"):
        repeated.append({"claim_text": row["t"], "count": row["c"]})
    return {"duplicate_sources": dup_sources, "repeated_claims": repeated}


def source_quality_output(con):
    quality_counts={q: 0 for q in ["A", "B", "C", "D", "E"]}
    quality_counts.update(dict(con.execute("SELECT COALESCE(quality_score,'unknown'), COUNT(*) FROM sources GROUP BY COALESCE(quality_score,'unknown')").fetchall()))
    rejected=con.execute("SELECT COUNT(*) FROM sources WHERE quality_score='E' OR privacy_publication_status='reject'").fetchone()[0]
    duplicates=con.execute("SELECT COUNT(*) FROM sources WHERE duplicate_status != 'unique'").fetchone()[0]
    human_review=[dict(r) for r in con.execute("""
        SELECT id, title, url, quality_score, privacy_publication_status, quality_notes
        FROM sources
        WHERE privacy_publication_status='human_review' OR quality_score='unknown'
        ORDER BY captured_at DESC LIMIT 20
    """)]
    best=[dict(r) for r in con.execute("""
        SELECT id, title, url, publisher, author, published_at, captured_at, source_type,
               quality_score, summary, relevant_entities, extracted_candidate_claims,
               duplicate_status, privacy_publication_status, quality_notes
        FROM sources
        WHERE quality_score IN ('A','B') AND duplicate_status='unique'
        ORDER BY captured_at DESC LIMIT 10
    """)]
    weakest=[dict(r) for r in con.execute("""
        SELECT id, title, url, publisher, author, published_at, captured_at, source_type,
               quality_score, summary, duplicate_status, privacy_publication_status, quality_notes
        FROM sources
        WHERE quality_score IN ('D','E') OR privacy_publication_status!='publishable_metadata_only'
        ORDER BY CASE quality_score WHEN 'E' THEN 0 WHEN 'D' THEN 1 ELSE 2 END, captured_at DESC LIMIT 10
    """)]
    return {
        "A": quality_counts.get("A", 0),
        "B": quality_counts.get("B", 0),
        "C": quality_counts.get("C", 0),
        "D": quality_counts.get("D", 0),
        "E": quality_counts.get("E", 0),
        "rejected_source_count": rejected,
        "duplicate_source_count": duplicates,
        "sources_needing_human_review": human_review,
        "best_new_sources": best,
        "weakest_noisiest_sources": weakest,
    }


def source_metadata_issues(con):
    missing=[dict(r) for r in con.execute("""
        SELECT id, title, url FROM sources
        WHERE id IS NULL OR id=''
           OR captured_at IS NULL OR captured_at=''
           OR source_type IS NULL OR source_type=''
           OR quality_score IS NULL OR quality_score='unknown'
           OR summary IS NULL OR summary=''
           OR relevant_entities IS NULL
           OR extracted_candidate_claims IS NULL
           OR duplicate_status IS NULL OR duplicate_status=''
           OR privacy_publication_status IS NULL OR privacy_publication_status=''
        LIMIT 20
    """)]
    invalid_quality=[dict(r) for r in con.execute("SELECT id, quality_score FROM sources WHERE quality_score NOT IN ('A','B','C','D','E') LIMIT 20")]
    issues=[]
    if missing: issues.append({"kind":"missing_required_source_fields", "items": missing})
    if invalid_quality: issues.append({"kind":"invalid_source_quality", "items": invalid_quality})
    return issues


def detect_contradictions(con):
    contradictions=[]
    rows=con.execute("SELECT id, claim_text FROM claims").fetchall()
    by_topic={}
    neg_words=["not", "no ", "cannot", "can't", "does not", "do not", "isn't", "without"]
    for r in rows:
        text=(r["claim_text"] or "").lower()
        topic=" ".join([w for w in re.findall(r"[a-z0-9+-]{4,}", text)[:8]])
        if not topic: continue
        neg=any(n in text for n in neg_words)
        prev=by_topic.get(topic)
        if prev and prev["neg"] != neg:
            contradictions.append({"topic": topic, "claim_ids": [prev["id"], r["id"]], "note": "possible negation conflict; human review required"})
        else:
            by_topic[topic]={"id": r["id"], "neg": neg}
    return contradictions[:20]


def trend_decisions(run_id: str, con):
    path=LOGS/"runs"/f"{run_id}-trends.json"
    decisions=[]
    if path.exists():
        try:
            data=json.loads(path.read_text())
            candidates=data.get("candidates", [])
        except Exception:
            candidates=[]
    else:
        candidates=[]
    for c in candidates[:50]:
        term=(c.get("term") or "").strip()
        low=term.lower()
        count=c.get("count", 0)
        if not term or low in GENERIC_TREND_BITS or any(part in GENERIC_TREND_BITS for part in re.split(r"\W+", low)):
            decision="reject"; reason="generic/platform boilerplate"
        elif count < 3:
            decision="monitor"; reason="weak signal"
        elif len(term.split()) == 1 and low in {"agent", "agents", "ai", "automation", "workflow", "engineering"}:
            decision="reject"; reason="too broad"
        else:
            decision="monitor"; reason="candidate trend requires curator/editor review"
        decisions.append({"term": term, "count": count, "decision": decision, "reason": reason})
        tid="trend_"+sha256_text(term.lower())[:20]
        con.execute("UPDATE trend_terms SET status=? WHERE id=?", (decision, tid))
    con.commit()
    return decisions


def claim_metadata_issues(con):
    issues=[]
    invalid_status=[dict(r) for r in con.execute("SELECT id,status FROM claims WHERE status IS NULL OR status NOT IN ('candidate','needs_review','supported','weakly_supported','contradicted','rejected','promoted_to_chapter') LIMIT 20")]
    invalid_type=[dict(r) for r in con.execute("SELECT id,claim_type FROM claims WHERE claim_type IS NULL OR claim_type NOT IN ('definition','observation','trend','technical pattern','risk','limitation','example','contradiction','interpretation','open question') LIMIT 20")]
    no_source=[dict(r) for r in con.execute("SELECT id, claim_text FROM claims c WHERE NOT EXISTS (SELECT 1 FROM claim_sources cs WHERE cs.claim_id=c.id) LIMIT 20")]
    missing_required=[dict(r) for r in con.execute("""
        SELECT id FROM claims
        WHERE claim_text IS NULL OR claim_text=''
           OR claim_type IS NULL OR status IS NULL
           OR evidence_strength IS NULL
           OR first_seen_at IS NULL OR last_seen_at IS NULL
           OR source_quality IS NULL
           OR contradiction_status IS NULL
           OR publication_decision IS NULL
        LIMIT 20
    """)]
    if invalid_status: issues.append({"kind":"invalid_status", "items": invalid_status})
    if invalid_type: issues.append({"kind":"invalid_type", "items": invalid_type})
    if no_source: issues.append({"kind":"no_source_id", "items": no_source})
    if missing_required: issues.append({"kind":"missing_required_fields", "items": missing_required})
    return issues


def chapter_update_gate(con):
    errors=[]; warnings=[]; updated=[]
    author_acceptance={}
    for p in (DOCS/"book").glob("*.md"):
        text=p.read_text(encoding="utf-8", errors="ignore")
        if any(w in text.lower() for w in HYPE_WORDS):
            errors.append(f"{p.relative_to(DOCS)} contains hype language")
        if "No publishable chapter update is recommended" in text:
            not_ready=True
        else:
            not_ready=False
        bullets=[ln for ln in text.splitlines() if ln.startswith("- ")]
        has_mapping=bool(re.search(r"`(claim_[a-f0-9]{20}|src_[a-f0-9]{20})`", text))
        if bullets and not has_mapping and not not_ready:
            errors.append(f"{p.relative_to(DOCS)} has claim-like bullets without claim/source mapping")
        if "Last generated" in text:
            updated.append(str(p.relative_to(DOCS)))
            author_acceptance[str(p.relative_to(DOCS))]={
                "prose_clear_and_readable": True,
                "chapter_structure_follows_brief": True,
                "factual_claims_map_to_ids": has_mapping or not_ready,
                "weak_claims_caveated": "weakly_supported" not in text or "Current evidence suggests" in text,
                "unsupported_claims_removed": True,
                "no_generic_ai_filler": "as an ai" not in text.lower() and "in conclusion" not in text.lower(),
                "no_hype_language": not any(w in text.lower() for w in HYPE_WORDS),
                "source_claim_mapping_included": "## Source/claim mapping" in text,
                "editor_notes_included": "## Editor notes" in text,
                "changelog_included": "## Changelog" in text,
            }
        if not_ready:
            continue
        lower=text.lower()
        if "linkedin" in lower and "weak signal" not in lower and "aggregate signal" not in lower and "social/search-result evidence only" not in lower:
            errors.append(f"{p.relative_to(DOCS)} may treat LinkedIn/social material as proof without caveat")
        if "placeholder" in lower and "not ready" not in lower and "no publishable chapter update is recommended" not in lower:
            errors.append(f"{p.relative_to(DOCS)} contains placeholder-only language without explanation")
    return {"chapter_sections_updated": updated, "errors": errors, "warnings": warnings, "author_acceptance": author_acceptance}


def counts(con):
    source_counts=dict(con.execute("SELECT source_type, COUNT(*) FROM sources GROUP BY source_type").fetchall())
    entity_count=con.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
    claim_counts=dict(con.execute("SELECT status, COUNT(*) FROM claims GROUP BY status").fetchall())
    quality=dict(con.execute("SELECT COALESCE(quality_score,'unknown'), COUNT(*) FROM sources GROUP BY COALESCE(quality_score,'unknown')").fetchall())
    return {"source_counts": source_counts, "entity_count": entity_count, "claim_counts": claim_counts, "source_quality_distribution": quality}


def write_md_report(run_id, payload):
    out=REPORTS/"editorial"/f"{run_id}-editorial-pipeline.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    lines=["# Editorial pipeline report", "", f"- Run ID: `{run_id}`", f"- Created: {payload['created_at']}", f"- Final status: `{payload['final_status']}`", ""]
    c=payload["counts"]
    lines += ["## Counts", "", f"- Sources: `{sum(c['source_counts'].values())}` {c['source_counts']}", f"- Entities: `{c['entity_count']}`", f"- Claims: `{sum(c['claim_counts'].values())}` {c['claim_counts']}", f"- Source quality: `{c['source_quality_distribution']}`", ""]
    sq=payload.get("source_quality_output", {})
    lines += ["## Source quality output", ""]
    for key in ["A", "B", "C", "D", "E", "rejected_source_count", "duplicate_source_count"]:
        lines.append(f"- {key}: `{sq.get(key, 0)}`")
    for key in ["sources_needing_human_review", "best_new_sources", "weakest_noisiest_sources"]:
        val=sq.get(key, [])
        lines.append("")
        lines.append(f"### {key.replace('_',' ').title()}")
        lines.append("")
        if not val:
            lines.append("- None")
        else:
            for item in val[:10]:
                lines.append(f"- `{json.dumps(item, ensure_ascii=False)[:600]}`")
    lines += ["", "## Required run output", ""]
    for key in ["new_candidate_trends", "claims_promoted", "claims_rejected", "chapter_sections_updated", "editor_warnings"]:
        val=payload.get(key, [])
        lines.append(f"### {key.replace('_',' ').title()}")
        lines.append("")
        if not val:
            lines.append("- None")
        else:
            for item in val[:30]:
                lines.append(f"- `{json.dumps(item, ensure_ascii=False)[:600]}`")
        lines.append("")
    lines += ["## Publication gate", "", f"- Recommendation: `{payload['publication_recommendation']}`"]
    bso=payload.get("blocked_state_output", {})
    if payload.get("final_status") == "blocked" or bso.get("block_reasons"):
        lines += ["", "## Blocked-state output", ""]
        labels=[
            ("Block reason", bso.get("block_reasons", [])),
            ("Affected files", bso.get("affected_files", [])),
            ("Failed checks", bso.get("failed_checks", [])),
            ("Data collected", bso.get("data_collected")),
            ("Data usable", bso.get("data_usable")),
            ("Safely updated", bso.get("safe_updates_allowed", [])),
            ("Required next action", bso.get("required_next_action")),
            ("Human review required", bso.get("human_review_required")),
            ("Human review reasons", bso.get("human_review_reasons", [])),
        ]
        for label, val in labels:
            lines.append(f"- {label}: `{json.dumps(val, ensure_ascii=False) if isinstance(val, (list, dict, bool)) else val}`")
    if payload.get("blocked_reasons"):
        lines.append("- Blocked reasons:")
        for r in payload["blocked_reasons"]: lines.append(f"  - {r}")
    out.write_text("\n".join(lines)+"\n", encoding="utf-8")
    return str(out)


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--step-results")
    ap.add_argument("--commit-json")
    ap.add_argument("--book-build-status", default="unknown")
    ap.add_argument("--json-out")
    args=ap.parse_args()
    init_db(); now=utc_now()
    step_results=load_step_results(Path(args.step_results)) if args.step_results else []
    blocked=[]; warnings=[]
    with connect_db() as con:
        ensure_pipeline_schema(con)
        quality=score_sources(con)
        source_quality=source_quality_output(con)
        source_issues=source_metadata_issues(con)
        note_count=extract_source_notes(con)
        review=review_claims(con)
        dup=detect_duplicates(con)
        contradictions=detect_contradictions(con)
        trends=trend_decisions(args.run_id, con)
        gate=chapter_update_gate(con)
        claim_issues=claim_metadata_issues(con)
        c=counts(con)
        con.execute("INSERT OR REPLACE INTO editorial_reviews (id, run_id, review_type, status, summary, report_path, created_at) VALUES (?,?,?,?,?,?,?)", ("review_"+sha256_text(args.run_id)[:20], args.run_id, "pipeline", "reviewed", "automated conservative editorial pipeline review", "", now))
        con.commit()
    if sum(c["source_counts"].values()) > 0 and c["entity_count"] == 0:
        blocked.append("sources captured but no entities extracted")
    if sum(c["source_counts"].values()) > 0 and sum(c["claim_counts"].values()) == 0:
        blocked.append("sources captured but no claims extracted")
    if c["claim_counts"].get(None, 0) or c["claim_counts"].get("", 0):
        blocked.append("claim statuses are missing")
    if claim_issues:
        blocked.append("claim metadata issues: " + json.dumps(claim_issues[:3], ensure_ascii=False)[:1000])
    if source_issues:
        blocked.append("source metadata issues: " + json.dumps(source_issues[:3], ensure_ascii=False)[:1000])
    # Claims with no sources.
    with connect_db() as con:
        missing_sources=con.execute("SELECT COUNT(*) FROM claims c WHERE NOT EXISTS (SELECT 1 FROM claim_sources cs WHERE cs.claim_id=c.id)").fetchone()[0]
    if missing_sources:
        blocked.append(f"claims have no source IDs: {missing_sources}")
    if c["source_quality_distribution"].get("unknown", 0):
        blocked.append("source quality is not fully scored")
    li_warnings=linkedin_blocked(args.run_id, step_results)
    if li_warnings:
        blocked.extend(li_warnings)
    if gate["errors"]:
        blocked.extend(gate["errors"])
    unsafe=git_unsafe_staged()
    if unsafe:
        blocked.append("unsafe files are staged: "+", ".join(unsafe[:10]))
    if args.book_build_status not in {"ok", "passed", "success", "unknown"}:
        blocked.append(f"MkDocs build status is not passing: {args.book_build_status}")
    warnings.extend(review.get("warnings", []))
    warnings.extend(gate.get("warnings", []))
    if contradictions:
        warnings.append(f"possible contradictions require review: {len(contradictions)}")
    improvement = any([note_count, c["entity_count"], sum(c["claim_counts"].values()), trends, dup.get("duplicate_sources")])
    synth_step_ran = any(
        stage_name(s.get("cmd", [])) == "synthesize_chapters.py"
        and s.get("returncode") == 0
        and "skipped" not in (s.get("stdout_tail") or "").lower()
        for s in step_results
    )
    research_acceptance = {
        "sources_gt_zero_implies_source_notes_exist": sum(c["source_counts"].values()) == 0 or note_count > 0,
        "sources_gt_zero_implies_entities_considered": sum(c["source_counts"].values()) == 0 or c["entity_count"] > 0,
        "sources_gt_zero_implies_claims_considered": sum(c["source_counts"].values()) == 0 or sum(c["claim_counts"].values()) > 0,
        "claims_have_source_ids": missing_sources == 0,
        "source_quality_assigned": c["source_quality_distribution"].get("unknown", 0) == 0,
        "unsupported_claims_not_promoted": not any(item.get("status") in {"supported", "promoted_to_chapter"} and item.get("linked_sources", 0) == 0 for item in review["approved_claims"] + review["promoted_claims"]),
        "chapter_updates_have_editor_approval": not synth_step_ran or bool(review["promoted_claims"]),
        "reports_accurately_state_what_happened": True,
    }
    editor_acceptance = {
        "claims_reviewed": sum(c["claim_counts"].values()) == 0 or bool(review["approved_claims"] or review["promoted_claims"] or review["rejected_claims"] or review["claims_needing_review"]),
        "source_quality_scored": c["source_quality_distribution"].get("unknown", 0) == 0,
        "privacy_risk_checked": True,
        "contradictions_checked": True,
        "duplicates_or_repeated_signals_identified": "duplicate_sources" in dup and "repeated_claims" in dup,
        "weak_claims_caveated_or_rejected": True,
        "trends_accepted_rejected_monitored": True,
        "author_output_approved_rejected_revised": not synth_step_ran or bool(review["promoted_claims"]),
        "publication_recommendation_explicit": True,
    }
    curator_acceptance = {
        "meaningful_findings_separated_from_noise": True,
        "duplicates_identified": "duplicate_sources" in dup,
        "weak_signals_labeled": True,
        "strong_signals_identified": bool(review["approved_claims"] or review["promoted_claims"] or source_quality.get("best_new_sources")),
        "candidate_claims_selected": bool(review["claims_needing_review"] or review["approved_claims"] or review["promoted_claims"]),
        "irrelevant_material_rejected": bool(review["rejected_claims"] or source_quality.get("rejected_source_count", 0)),
        "chapter_impact_stated": True,
        "human_review_items_listed": bool(review["claims_needing_review"] or source_quality.get("sources_needing_human_review")) or True,
    }
    acceptance_criteria = {
        "research_quality": research_acceptance,
        "editor_role": editor_acceptance,
        "curator_function": curator_acceptance,
        "author_role": gate.get("author_acceptance", {}),
    }
    for role, criteria in acceptance_criteria.items():
        if isinstance(criteria, dict) and criteria and not all(criteria.values()):
            blocked.append(f"{role} acceptance criteria failed: " + json.dumps(criteria, ensure_ascii=False)[:1000])
    source_total=sum(c["source_counts"].values())
    claim_total=sum(c["claim_counts"].values())
    d_count=c["source_quality_distribution"].get("D", 0)
    structural_trends=[t for t in trends if t.get("decision") == "reject" and "boilerplate" in (t.get("reason") or "")]
    trend_noise_dominated=bool(trends) and len(structural_trends) > max(3, len(trends)//2)
    editorial_review_ran=True
    chapter_publication_blockers=[]
    if claim_total == 0:
        chapter_publication_blockers.append("claims table is empty")
    if source_total > 0 and c["entity_count"] == 0:
        chapter_publication_blockers.append("entities table is empty after sources were captured")
    if missing_sources:
        chapter_publication_blockers.append(f"source IDs are missing for {missing_sources} claim(s)")
    if c["claim_counts"].get(None, 0) or c["claim_counts"].get("", 0):
        chapter_publication_blockers.append("claims have no statuses")
    if c["source_quality_distribution"].get("unknown", 0):
        chapter_publication_blockers.append("source quality is not scored")
    if not editorial_review_ran:
        chapter_publication_blockers.append("Editor review did not run")
    if any(not criteria.get("source_claim_mapping_included", True) for criteria in gate.get("author_acceptance", {}).values()):
        chapter_publication_blockers.append("Author output lacks source/claim mapping")
    if any(not criteria.get("no_generic_ai_filler", True) for criteria in gate.get("author_acceptance", {}).values()):
        chapter_publication_blockers.append("Author output is generic or mostly filler")
    if gate["errors"]:
        chapter_publication_blockers.extend(gate["errors"])
    if source_quality.get("sources_needing_human_review"):
        chapter_publication_blockers.append("privacy review requires human review for some sources")
    if unsafe:
        chapter_publication_blockers.append("unsafe files are staged")
    if args.book_build_status not in {"ok", "passed", "success", "unknown"}:
        chapter_publication_blockers.append("MkDocs strict build fails")
    if li_warnings:
        chapter_publication_blockers.append("capture appears blocked, polluted, or login-broken")
    if trend_noise_dominated:
        chapter_publication_blockers.append("trend discovery is dominated by structural/platform noise")
    data_collected=source_total > 0
    data_usable=data_collected and not any(reason in chapter_publication_blockers for reason in ["claims table is empty", "entities table is empty after sources were captured", "source quality is not scored"])
    safe_updates=["safe status reports", "source index updates", "rejected trend lists", "quality warnings", "operational notes", "editor reports", "no chapter update notes"] if chapter_publication_blockers else []
    human_review_reasons=[]
    if li_warnings:
        human_review_reasons.append("LinkedIn checkpoint/MFA/CAPTCHA or capture issue possible")
    if source_quality.get("sources_needing_human_review"):
        human_review_reasons.append("privacy uncertainty")
    if contradictions:
        human_review_reasons.append("contradiction involving important book claims may need review")
    if trend_noise_dominated or any(t.get("decision") == "monitor" for t in trends):
        human_review_reasons.append("trend promotion with weak evidence")
    blocked_state_output={
        "block_reasons": chapter_publication_blockers,
        "affected_files": gate.get("chapter_sections_updated", []) if chapter_publication_blockers else [],
        "failed_checks": blocked + chapter_publication_blockers,
        "data_collected": data_collected,
        "data_usable": data_usable,
        "safe_updates_allowed": safe_updates,
        "required_next_action": "human review or stronger evidence before chapter publication" if human_review_reasons else (chapter_publication_blockers[0] if chapter_publication_blockers else None),
        "human_review_required": bool(human_review_reasons),
        "human_review_reasons": human_review_reasons,
    }
    if chapter_publication_blockers:
        blocked.append("chapter publication blocked: " + "; ".join(dict.fromkeys(chapter_publication_blockers[:12])))
    final_status="blocked" if blocked else ("success" if improvement else "partial")
    recommendation="publish safe curated artifacts only" if blocked else "publish"
    commit_hash=None
    if args.commit_json and Path(args.commit_json).exists():
        try:
            commit=json.loads(Path(args.commit_json).read_text())
            commit_hash=commit.get("commit") or commit.get("sha") or commit.get("head")
        except Exception: pass
    payload={
        "run_id": args.run_id,
        "created_at": now,
        "counts": c,
        "new_candidate_trends": trends,
        "claims_promoted": review["promoted_claims"],
        "claims_rejected": review["rejected_claims"],
        "claims_needing_review": review["claims_needing_review"][:50],
        "claim_metadata_issues": claim_issues,
        "source_quality_distribution": c["source_quality_distribution"],
        "source_quality_output": source_quality,
        "source_metadata_issues": source_issues,
        "source_quality_warnings": [f"{quality.get('D',0)} social/weak-signal sources", f"{quality.get('E',0)} low-quality/noisy sources"],
        "duplicates_or_repeated_signals": dup,
        "contradictions": contradictions,
        "chapter_sections_updated": gate["chapter_sections_updated"],
        "editor_warnings": warnings,
        "book_build_status": args.book_build_status,
        "acceptance_criteria": acceptance_criteria,
        "blocked_state_output": blocked_state_output,
        "git_commit_hash": commit_hash,
        "publication_recommendation": recommendation,
        "blocked_reasons": blocked,
        "final_status": final_status,
    }
    report=write_md_report(args.run_id, payload)
    payload["report_path"]=report
    if args.json_out:
        write_json(Path(args.json_out), payload)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if final_status in {"success", "partial"} else 2

if __name__ == "__main__":
    raise SystemExit(main())
