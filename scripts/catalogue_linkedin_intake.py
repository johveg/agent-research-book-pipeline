#!/usr/bin/env python3
"""Append sanitized LinkedIn intake records to the book content catalogue."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CATALOGUE = ROOT / "data" / "linkedin_content_catalogue.jsonl"

CHAPTER_HINTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("hermes", ("hermes", "agent", "assistant", "memory", "tool", "gateway", "telegram")),
    ("autonomous-research-pipeline", ("research", "pipeline", "catalog", "catalogue", "source", "evidence", "capture")),
    ("observability-for-agents", ("observability", "monitor", "ops", "trace", "status", "alert", "telemetry")),
    ("multi-agent-workflows", ("multi-agent", "multi agent", "orchestration", "worker", "delegate", "team")),
    ("mcp-tools", ("mcp", "tool server", "connector", "integration")),
    ("agent-runtime-security", ("security", "safety", "privacy", "credential", "token", "auth")),
    ("computer-use-agents", ("browser", "computer use", "desktop", "screenshot", "vision")),
)


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def stable_id(*parts: str) -> str:
    h = hashlib.sha256("\n".join(p for p in parts if p).encode("utf-8")).hexdigest()
    return "linkedin_intake_" + h[:20]


def load_json(path: Path | None) -> dict[str, Any]:
    if not path:
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("metadata JSON must be an object")
    return data


def as_text(value: Any) -> str:
    return value if isinstance(value, str) else ""


def summarize(text: str, limit: int = 600) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def chapter_candidates(text: str) -> list[str]:
    haystack = text.lower()
    scored: list[tuple[int, str]] = []
    for chapter, terms in CHAPTER_HINTS:
        score = sum(1 for term in terms if term in haystack)
        if score:
            scored.append((score, chapter))
    return [chapter for _, chapter in sorted(scored, reverse=True)[:4]]


def score_from_candidates(candidates: list[str], text: str) -> int:
    if not text.strip():
        return 0
    return min(5, max(1, len(candidates) + (1 if len(text) > 400 else 0)))


def build_entry(args: argparse.Namespace) -> dict[str, Any]:
    metadata = load_json(Path(args.metadata) if args.metadata else None)
    post = metadata.get("post") if isinstance(metadata.get("post"), dict) else {}
    author = metadata.get("author") if isinstance(metadata.get("author"), dict) else {}
    comments = metadata.get("comments") if isinstance(metadata.get("comments"), dict) else {}
    media = metadata.get("media") if isinstance(metadata.get("media"), list) else []

    input_url = args.url or as_text(metadata.get("input_url")) or as_text(metadata.get("canonical_url"))
    canonical_url = as_text(metadata.get("canonical_url")) or input_url
    title = args.title or as_text(post.get("headline")) or as_text(metadata.get("title")) or "LinkedIn intake"
    post_text = args.text or as_text(post.get("article_body")) or as_text(metadata.get("post_text"))
    summary = args.summary or summarize(post_text)
    combined = "\n".join([title, summary, post_text, args.notes or ""])
    candidates = chapter_candidates(combined)
    book_score = score_from_candidates(candidates, combined)
    hermione_terms = ("hermes", "assistant", "agent", "memory", "tool", "gateway", "telegram", "ops", "autonomous")
    hermione_score = min(5, sum(1 for term in hermione_terms if term in combined.lower()))

    media_summary = args.media_summary or (
        f"{len(media)} media item(s) visible in archived metadata" if media else "No visible media captured or media not exposed."
    )
    visible_comment_summary = args.comment_summary or (
        f"{comments.get('count_visible_in_guest_html')} guest-visible comment(s)." if comments.get("count_visible_in_guest_html") is not None else "Comments not visible or not captured."
    )
    limitations = list(args.limitation or [])
    if not limitations:
        limitations.append("LinkedIn post is social/discovery evidence until corroborated.")
    if not media:
        limitations.append("LinkedIn may hide media or video assets from this capture path.")

    archive_dir = args.archive_dir or (str(Path(args.metadata).parent) if args.metadata else "")
    entry = {
        "schema_version": 1,
        "intake_id": stable_id(input_url, canonical_url, summary),
        "ingested_at": utc_now(),
        "source_platform": "linkedin",
        "input_url": input_url,
        "canonical_url": canonical_url,
        "activity_id": as_text(metadata.get("activity_id")) or as_text(post.get("activity_id")),
        "archive_dir": archive_dir,
        "title": title,
        "author": args.author or as_text(author.get("name")) or as_text(post.get("author")),
        "post_text_summary": summary,
        "visible_comment_summary": visible_comment_summary,
        "media_summary": media_summary,
        "book_relevance": {
            "score": book_score,
            "candidate_chapters": candidates,
            "claim_or_example": args.claim_or_example or summarize(combined, 240),
            "evidence_strength": args.evidence_strength,
        },
        "hermione_relevance": {
            "score": hermione_score,
            "why": args.hermione_relevance or ("Relevant to Hermione's agent/tooling practice." if hermione_score else "No direct Hermione relevance detected yet."),
            "suggested_change": args.suggested_change or "",
        },
        "limitations": limitations,
        "status": args.status,
        "notes": args.notes or "",
    }
    return entry


def append_jsonl(path: Path, entry: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--catalogue", default=str(DEFAULT_CATALOGUE))
    p.add_argument("--metadata", help="Archived LinkedIn metadata JSON path")
    p.add_argument("--url", default="")
    p.add_argument("--archive-dir", default="")
    p.add_argument("--title", default="")
    p.add_argument("--author", default="")
    p.add_argument("--text", default="")
    p.add_argument("--summary", default="")
    p.add_argument("--comment-summary", default="")
    p.add_argument("--media-summary", default="")
    p.add_argument("--claim-or-example", default="")
    p.add_argument("--hermione-relevance", default="")
    p.add_argument("--suggested-change", default="")
    p.add_argument("--notes", default="")
    p.add_argument("--limitation", action="append")
    p.add_argument("--evidence-strength", default="discovery-only", choices=["strong", "moderate", "weak", "discovery-only"])
    p.add_argument("--status", default="catalogued")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    entry = build_entry(args)
    if not entry["input_url"]:
        raise SystemExit("--url or metadata input_url/canonical_url is required")
    append_jsonl(Path(args.catalogue), entry)
    print(json.dumps({"ok": True, "catalogue": args.catalogue, "intake_id": entry["intake_id"], "candidate_chapters": entry["book_relevance"]["candidate_chapters"]}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
