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
HYPE_WORDS = ["revolutionary", "game-changing", "unlock", "unleash", "transformative", "disruptive", "paradigm shift", "next-generation", "groundbreaking", "frictionless", "magical"]
GENERIC_TREND_BITS = {"https", "http", "urn", "hashtag", "query", "search", "result", "results", "linkedin", "visible", "captured", "source", "sources"}
SOCIAL_TYPES = {"linkedin_search_result", "social", "post"}


def source_quality(row) -> str:
    st=(row["source_type"] or "").lower()
    vis=(row["visibility"] or "").lower()
    url=(row["url"] or "").lower()
    pub=(row["publisher"] or "").lower()
    title=(row["title"] or "").lower()
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


def ensure_pipeline_schema(con):
    ensure_editorial_schema(con)
    src_cols={r[1] for r in con.execute("PRAGMA table_info(sources)")}
    if "quality_score" not in src_cols:
        con.execute("ALTER TABLE sources ADD COLUMN quality_score TEXT DEFAULT 'unknown'")
    if "quality_notes" not in src_cols:
        con.execute("ALTER TABLE sources ADD COLUMN quality_notes TEXT")
    claim_cols={r[1] for r in con.execute("PRAGMA table_info(claims)")}
    if "editor_notes" not in claim_cols:
        con.execute("ALTER TABLE claims ADD COLUMN editor_notes TEXT")
    if "reviewed_at" not in claim_cols:
        con.execute("ALTER TABLE claims ADD COLUMN reviewed_at TEXT")
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
    for row in con.execute("SELECT * FROM sources"):
        q=source_quality(row)
        counts[q]+=1
        con.execute("UPDATE sources SET quality_score=?, reliability_tier=?, quality_notes=? WHERE id=?", (q, q, f"auto_scored_{q}", row["id"]))
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
             SUM(CASE WHEN s.quality_score='D' THEN 1 ELSE 0 END) AS social_sources,
             SUM(CASE WHEN s.quality_score='E' THEN 1 ELSE 0 END) AS low_sources
      FROM claims c
      LEFT JOIN claim_sources cs ON cs.claim_id=c.id
      LEFT JOIN sources s ON s.id=cs.source_id
      GROUP BY c.id
    """).fetchall()
    for c in claims:
        status=c["status"] or "candidate"
        linked=c["linked_sources"] or 0; strong=c["strong_sources"] or 0; social=c["social_sources"] or 0; low=c["low_sources"] or 0
        text=(c["claim_text"] or "")
        notes=[]
        if linked == 0:
            status="rejected"; notes.append("rejected: no source IDs")
        elif strong >= 1 and linked >= 1 and status not in {"promoted_to_chapter", "supported"}:
            status="needs_review"; notes.append("has A/B support but needs human/editor review before promotion")
        elif social >= linked and strong == 0:
            status="weakly_supported"; notes.append("social/search-result evidence only; caveat required")
        elif low >= linked:
            status="rejected"; notes.append("only low-quality/noisy sources")
        elif status == "candidate":
            status="needs_review"; notes.append("candidate requires editor review")
        if any(w in text.lower() for w in HYPE_WORDS):
            notes.append("hype language present")
            if status in {"supported", "promoted_to_chapter"}: status="needs_review"
        con.execute("UPDATE claims SET status=?, editor_notes=?, reviewed_at=? WHERE id=?", (status, "; ".join(notes), now, c["id"]))
        item={"id": c["id"], "text": text, "status": status, "linked_sources": linked, "strong_sources": strong, "social_sources": social, "low_sources": low, "notes": notes}
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


def chapter_update_gate(con):
    errors=[]; warnings=[]; updated=[]
    for p in (DOCS/"book").glob("*.md"):
        text=p.read_text(encoding="utf-8", errors="ignore")
        if any(w in text.lower() for w in HYPE_WORDS):
            errors.append(f"{p.relative_to(DOCS)} contains hype language")
        if "No supported or high-confidence claims" in text:
            continue
        bullets=[ln for ln in text.splitlines() if ln.startswith("- ")]
        if bullets and not re.search(r"`(claim_[a-f0-9]{20}|src_[a-f0-9]{20})`", text):
            errors.append(f"{p.relative_to(DOCS)} has claim-like bullets without claim/source mapping")
        if "Last generated" in text:
            updated.append(str(p.relative_to(DOCS)))
    return {"chapter_sections_updated": updated, "errors": errors, "warnings": warnings}


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
    lines += ["## Required run output", ""]
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
        note_count=extract_source_notes(con)
        review=review_claims(con)
        dup=detect_duplicates(con)
        contradictions=detect_contradictions(con)
        trends=trend_decisions(args.run_id, con)
        gate=chapter_update_gate(con)
        c=counts(con)
        con.execute("INSERT OR REPLACE INTO editorial_reviews (id, run_id, review_type, status, summary, report_path, created_at) VALUES (?,?,?,?,?,?,?)", ("review_"+sha256_text(args.run_id)[:20], args.run_id, "pipeline", "reviewed", "automated conservative editorial pipeline review", "", now))
        con.commit()
    if sum(c["source_counts"].values()) > 0 and c["entity_count"] == 0:
        blocked.append("sources captured but no entities extracted")
    if sum(c["source_counts"].values()) > 0 and sum(c["claim_counts"].values()) == 0:
        blocked.append("sources captured but no claims extracted")
    if c["claim_counts"].get(None, 0) or c["claim_counts"].get("", 0):
        blocked.append("claim statuses are missing")
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
        "source_quality_distribution": c["source_quality_distribution"],
        "source_quality_warnings": [f"{quality.get('D',0)} social/weak-signal sources", f"{quality.get('E',0)} low-quality/noisy sources"],
        "duplicates_or_repeated_signals": dup,
        "contradictions": contradictions,
        "chapter_sections_updated": gate["chapter_sections_updated"],
        "editor_warnings": warnings,
        "book_build_status": args.book_build_status,
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
