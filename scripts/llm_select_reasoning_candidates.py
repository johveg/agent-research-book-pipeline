#!/usr/bin/env python3
"""Run 7 report-only selector for better high-reasoning source candidates.

Reads existing SQLite/source metadata read-only and ranks sources that are more
publication-suitable than the weak/privacy-blocked Run 5 sample. It never writes
SQLite, docs/book, raw captures, statuses, schema, daily-worker wiring, commit
allowlists, claims, narrative packets, or chapter prose.
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from editorial_common import source_text  # noqa: E402
from research_common import DB_PATH, ROOT as REPO_ROOT, sha256_text, write_json  # noqa: E402

MODE = "reasoning_candidate_selection_report_only"
BOOK_TERMS = {
    "hermes": ["hermes", "assistant", "tool", "telegram"],
    "openclaw": ["openclaw", "browser", "desktop", "local control"],
    "autonomous_agents": ["autonomous agent", "ai agent", "agentic", "coding agent"],
    "loop_engineering": ["loop engineering", "loop engineer", "self-running", "feedback loop"],
    "context_memory_architecture": ["context", "memory", "rag", "retrieval", "semantic"],
    "agentic_workflows": ["workflow", "orchestration", "mcp", "automation"],
    "ai_infrastructure": ["infrastructure", "model", "eval", "deployment", "provider"],
    "operator_model": ["operator", "governance", "human", "review", "control"],
    "source_citation_pipeline": ["source", "citation", "claim", "evidence", "verification"],
}
CHAPTER_MAP = [
    ("01-the-agent-loop", ["agent", "workflow", "orchestration", "loop"]),
    ("02-hermes", ["hermes", "assistant", "telegram", "tool"]),
    ("03-openclaw", ["openclaw", "browser", "desktop"]),
    ("04-loop-engineering", ["loop engineering", "loop engineer", "self-running"]),
    ("05-context-memory-architecture", ["context", "memory", "rag", "semantic", "retrieval"]),
    ("06-operating-loops", ["operator", "governance", "verification", "safety", "eval"]),
]
QUALITY_RANK = {"A": 5, "B": 4, "C": 3, "D": 1, "E": 0, "unknown": 2, "": 2, None: 2}
MIN_QUALITY = {"A": 5, "B": 4, "C": 3, "D": 1, "E": 0, "unknown": 2}
SOURCE_TYPE_RANK = {"web": 18, "paper": 20, "docs": 20, "blog": 16, "news": 14, "linkedin_search_result": -30}
RAW_ID_RE = re.compile(r"\b(?:src|claim)_[0-9a-f]{8,}\b")


class CandidateSelectionError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def repo_relative(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def clean_text(text: Any, max_len: int = 180) -> str:
    text = re.sub(r"https?://\S+", "[url]", str(text or ""))
    text = RAW_ID_RE.sub("[internal-id]", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > max_len:
        return text[: max_len - 1].rstrip() + "…"
    return text


def connect_readonly(db_path: Path = DB_PATH) -> sqlite3.Connection:
    con = sqlite3.connect(f"file:{db_path.resolve()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA query_only = ON")
    return con


def table_columns(con: sqlite3.Connection, table: str) -> set[str]:
    return {r[1] for r in con.execute(f"PRAGMA table_info({table})")}


def fetch_all_sources(con: sqlite3.Connection) -> list[sqlite3.Row]:
    wanted = [
        "id", "source_type", "query", "url", "title", "publisher", "author", "published_at", "captured_at",
        "archived_path", "content_hash", "reliability_tier", "visibility", "run_id", "quality_score", "quality_notes",
        "summary", "relevant_entities", "extracted_candidate_claims", "duplicate_status", "privacy_publication_status", "publication_notes",
    ]
    cols = [c for c in wanted if c in table_columns(con, "sources")]
    if not cols:
        raise CandidateSelectionError("sources table has no recognized columns")
    order = "captured_at DESC" if "captured_at" in cols else "id DESC"
    return con.execute(f"SELECT {', '.join(cols)} FROM sources ORDER BY {order}").fetchall()


def safe_lower(*parts: Any) -> str:
    return " ".join(str(p or "") for p in parts).lower()


def expected_chapters(text: str) -> list[str]:
    low = text.lower()
    scored = [(name, sum(1 for t in terms if t in low)) for name, terms in CHAPTER_MAP]
    return [name for name, score in sorted(scored, key=lambda x: x[1], reverse=True) if score > 0][:3] or ["needs_editor_mapping"]


def theme_hits(text: str) -> list[str]:
    low = text.lower()
    hits = []
    for name, terms in BOOK_TERMS.items():
        if any(t in low for t in terms):
            hits.append(name)
    return hits


def source_value(row: sqlite3.Row, key: str, default: Any = "") -> Any:
    return row[key] if key in row.keys() and row[key] is not None else default


def score_source(row: sqlite3.Row, *, min_quality: str = "C", prefer_public: bool = True, exclude_human_review: bool = True) -> dict[str, Any]:
    source_id = str(source_value(row, "id"))
    source_type = str(source_value(row, "source_type", "unknown"))
    quality = str(source_value(row, "quality_score", "unknown") or "unknown")
    privacy = str(source_value(row, "privacy_publication_status", "unknown") or "unknown")
    title = clean_text(source_value(row, "title"), 160)
    publisher = clean_text(source_value(row, "publisher"), 100)
    canonical = bool(source_value(row, "url"))
    summary = clean_text(source_value(row, "summary"), 260)
    query = clean_text(source_value(row, "query"), 180)
    relevant = clean_text(source_value(row, "relevant_entities"), 160)
    text = source_text(row, max_len=1400)
    combined = safe_lower(title, publisher, summary, query, relevant, text)
    hits = theme_hits(combined)
    chapters = expected_chapters(combined)
    score = 0
    reasons: list[str] = []
    risks: list[str] = []

    qrank = QUALITY_RANK.get(quality, QUALITY_RANK.get(quality.upper(), 2))
    score += qrank * 10
    reasons.append(f"quality_score {quality}")
    if qrank < MIN_QUALITY.get(min_quality, 3):
        score -= 40
        risks.append(f"below_min_quality_{min_quality}")
    if quality == "D":
        score -= 35
        risks.append("quality_score D")

    st_rank = SOURCE_TYPE_RANK.get(source_type, 3)
    score += st_rank
    if source_type == "linkedin_search_result":
        risks.append("linkedin_search_result")
    else:
        reasons.append(f"stronger source_type {source_type}")

    if privacy == "human_review":
        score -= 45
        risks.append("human_review privacy status")
    elif privacy in {"publishable_metadata_only", "publishable", "public"}:
        score += 20
        reasons.append(f"lower-risk privacy status {privacy}")
    elif privacy in {"reject", "private"}:
        score -= 50
        risks.append(f"privacy status {privacy}")

    if canonical:
        score += 10
        reasons.append("canonical URL available")
    else:
        score -= 10
        risks.append("missing canonical URL")
    if title and publisher:
        score += 8
        reasons.append("clear title and publisher")
    else:
        risks.append("thin title/publisher metadata")
    if len(text) >= 180 or len(summary) >= 80:
        score += 8
        reasons.append("enough sanitized text/summary for semantic extraction")
    else:
        score -= 20
        risks.append("thin safe text")
    if hits:
        score += 7 * len(hits)
        reasons.append("book theme hits: " + ", ".join(hits[:5]))
    else:
        score -= 8
        risks.append("weak book-theme relevance")

    skip_reasons = []
    if exclude_human_review and privacy == "human_review":
        skip_reasons.append("human_review privacy status excluded")
    if prefer_public and source_type == "linkedin_search_result":
        skip_reasons.append("linkedin_search_result deprioritized below public web sources")
    if qrank < MIN_QUALITY.get(min_quality, 3):
        skip_reasons.append(f"quality_score {quality} below min_quality {min_quality}")
    if not canonical:
        skip_reasons.append("canonical URL missing")
    decision = "selected" if not skip_reasons and score > 0 else "skipped"
    reason = "; ".join(reasons if decision == "selected" else skip_reasons + risks + reasons)
    return {
        "source_id": source_id,
        "selection_score": int(score),
        "selection_decision": decision,
        "selection_reason": clean_text(reason, 500),
        "source_type": source_type,
        "quality_score": quality,
        "privacy_publication_status": privacy,
        "canonical_url_available": canonical,
        "title": title,
        "publisher": publisher,
        "risk_flags": risks,
        "expected_chapter_targets": chapters,
        "theme_hits": hits,
        "why_better_than_run5_sample": "Public/non-human-review source with canonical URL and quality above D; avoids Run 5 do_not_use/reject/human_review pattern." if decision == "selected" else "Not better enough for Run 7 selection.",
        "source_text_hash": sha256_text(text or ""),
    }


def select_candidates(con: sqlite3.Connection, limit: int, *, min_quality: str = "C", prefer_public_sources: bool = False, exclude_human_review: bool = False) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[sqlite3.Row], list[sqlite3.Row], dict[str, Any]]:
    rows = fetch_all_sources(con)
    scored = [(score_source(r, min_quality=min_quality, prefer_public=prefer_public_sources, exclude_human_review=exclude_human_review), r) for r in rows]
    selected_pairs = [(s, r) for s, r in scored if s["selection_decision"] == "selected"]
    selected_pairs.sort(key=lambda x: (x[0]["selection_score"], x[0]["canonical_url_available"]), reverse=True)
    selected_pairs = selected_pairs[:limit]
    selected_ids = {s["source_id"] for s, _ in selected_pairs}
    skipped_pairs = [(s, r) for s, r in scored if s["source_id"] not in selected_ids]
    skipped_pairs.sort(key=lambda x: x[0]["selection_score"])
    skipped = [s for s, _ in skipped_pairs[: max(25, limit * 5)]]
    selected = [s for s, _ in selected_pairs]
    distributions = {
        "quality_score": dict(Counter(str(source_value(r, "quality_score", "unknown") or "unknown") for r in rows)),
        "privacy_publication_status": dict(Counter(str(source_value(r, "privacy_publication_status", "unknown") or "unknown") for r in rows)),
        "source_type": dict(Counter(str(source_value(r, "source_type", "unknown") or "unknown") for r in rows)),
    }
    return selected, skipped, [r for _, r in selected_pairs], rows, distributions


def build_payload(args: argparse.Namespace) -> dict[str, Any]:
    with connect_readonly() as con:
        selected, skipped, _rows, all_rows, distributions = select_candidates(
            con,
            args.limit,
            min_quality=args.min_quality,
            prefer_public_sources=args.prefer_public_sources,
            exclude_human_review=args.exclude_human_review,
        )
    return {
        "run_id": args.run_id,
        "generated_at": utc_now(),
        "mode": MODE,
        "total_sources_inspected": len(all_rows),
        "selected_count": len(selected),
        "selected_sources": selected,
        "skipped_sources": skipped,
        "skipped_reason_counts": dict(Counter(flag for s in skipped for flag in s.get("risk_flags", []))),
        "quality_distribution": distributions["quality_score"],
        "privacy_distribution": distributions["privacy_publication_status"],
        "source_type_distribution": distributions["source_type"],
        "materially_better_than_run5_sample": bool(selected) and all(s["source_type"] != "linkedin_search_result" and s["privacy_publication_status"] != "human_review" and s["quality_score"] != "D" and s["canonical_url_available"] for s in selected),
        "comparison_to_run5_sample": {
            "run5_pattern": "linkedin_search_result, quality_score=D, privacy_publication_status=human_review, recommended_use=do_not_use, evidence_strength=reject",
            "run7_selected_pattern": "web/public metadata, min-quality threshold, canonical URLs, lower privacy risk, stronger book-theme relevance",
        },
        "db_modified": False,
        "db_write_scope": "none",
        "chapters_modified": False,
        "statuses_modified": False,
        "schema_modified": False,
        "daily_worker_modified": False,
        "commit_allowlist_modified": False,
        "raw_private_material_written": False,
        "long_source_excerpt_written": False,
        "claims_inserted": 0,
        "publication_approval_granted": False,
    }


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [f"# Reasoning candidate selection: {payload['run_id']}", "", "## Summary", ""]
    lines += [
        f"- Total sources inspected: {payload['total_sources_inspected']}",
        f"- Selected sources: {payload['selected_count']}",
        f"- Materially better than Run 5 sample: {payload['materially_better_than_run5_sample']}",
        f"- DB modified: {payload['db_modified']}",
        "",
        "## Selected candidates",
        "",
        "| source_id | score | source_type | quality | privacy | title | chapter targets | reason |",
        "|---|---:|---|---|---|---|---|---|",
    ]
    for s in payload["selected_sources"]:
        lines.append("| " + " | ".join([
            s["source_id"], str(s["selection_score"]), s["source_type"], s["quality_score"], s["privacy_publication_status"], clean_text(s["title"], 70).replace("|", "\\|"), ", ".join(s["expected_chapter_targets"]), clean_text(s["selection_reason"], 100).replace("|", "\\|"),
        ]) + " |")
    lines += ["", "## Distributions", "", f"- Quality: `{payload['quality_distribution']}`", f"- Privacy: `{payload['privacy_distribution']}`", f"- Source type: `{payload['source_type_distribution']}`", "", "## Safety", "", "- Report-only advisory selection; no DB/status/docs/schema/worker/allowlist changes.", ""]
    return "\n".join(lines)


def write_reports(payload: dict[str, Any], output_dir: Path) -> dict[str, str]:
    output_dir = output_dir if output_dir.is_absolute() else REPO_ROOT / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    md = output_dir / f"{payload['run_id']}-reasoning-candidate-selection.md"
    js = output_dir / f"{payload['run_id']}-reasoning-candidate-selection.json"
    write_json(js, payload)
    md.write_text(render_markdown(payload), encoding="utf-8")
    return {"markdown": repo_relative(md), "json": repo_relative(js)}


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Select better public sources for Run 7 high-reasoning regeneration.")
    p.add_argument("--run-id", default="latest")
    p.add_argument("--limit", type=int, default=5)
    p.add_argument("--output-dir", default="reports/editorial")
    p.add_argument("--prefer-public-sources", action="store_true")
    p.add_argument("--exclude-human-review", action="store_true")
    p.add_argument("--min-quality", default="C", choices=["A", "B", "C", "D", "E", "unknown"])
    args = p.parse_args(argv)
    if args.limit < 0:
        raise CandidateSelectionError("--limit must be non-negative")
    return args


def main(argv: list[str] | None = None) -> int:
    try:
        args = parse_args(argv or sys.argv[1:])
        payload = build_payload(args)
        outputs = write_reports(payload, Path(args.output_dir))
        print(json.dumps({"status": "ok", "run_id": payload["run_id"], "selected_count": payload["selected_count"], "outputs": outputs, "db_modified": False}, indent=2, sort_keys=True))
        return 0
    except CandidateSelectionError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
