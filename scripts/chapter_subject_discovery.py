#!/usr/bin/env python3
"""Human-approved new chapter subject discovery.

This report-only gate inspects newly discovered terms/trends, compares them to the
configured manuscript chapters, and proposes possible new chapter subjects for
human approval. It never writes docs/book and never approves publication.
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config" / "chapter_discovery_topics.json"
DEFAULT_CONTRACT = ROOT / "config" / "book_manuscript_production_contract.json"
REPORTS = ROOT / "reports"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: str | Path, default: Any = None) -> Any:
    p = Path(path)
    if not p.exists():
        return default
    return json.loads(p.read_text(encoding="utf-8"))


def write_json(path: str | Path, obj: Any) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def slugify(text: str) -> str:
    words = re.findall(r"[a-z0-9]+", text.lower())
    return "-".join(words[:6]) or "new-subject"


def tokens(value: Any) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, (list, tuple, set)):
        text = " ".join(str(x) for x in value)
    else:
        text = str(value)
    return {t for t in re.findall(r"[a-z0-9]+", text.lower()) if len(t) >= 3}


def chapter_tokens(chapter_id: str, chapter: dict[str, Any]) -> set[str]:
    out = tokens(chapter_id.replace("_", " "))
    for key in ("title", "topics", "role", "target_path"):
        out |= tokens(chapter.get(key))
    return out


def candidate_term(candidate: dict[str, Any]) -> str:
    return str(candidate.get("term") or candidate.get("title") or candidate.get("subject") or "").strip()


def candidate_is_worth_proposing(candidate: dict[str, Any], min_doc_count: int = 2) -> bool:
    term = candidate_term(candidate)
    if not term:
        return False
    if len(tokens(term)) < 2:
        return False
    try:
        return int(candidate.get("doc_count", candidate.get("count", 0))) >= min_doc_count
    except Exception:
        return False


def fits_existing_chapter(term: str, chapters: dict[str, Any]) -> tuple[str | None, int]:
    term_tokens = tokens(term)
    best_id: str | None = None
    best_score = 0
    for chapter_id, chapter in chapters.items():
        if not isinstance(chapter, dict):
            continue
        score = len(term_tokens & chapter_tokens(chapter_id, chapter))
        if score > best_score:
            best_id, best_score = chapter_id, score
    return best_id, best_score


def sufficient_existing_fit(term: str, score: int) -> bool:
    term_token_count = max(1, len(tokens(term)))
    if score <= 0:
        return False
    if term_token_count <= 2:
        return score >= 1
    return score >= 2


def research_pair_for(term: str) -> dict[str, str]:
    quoted = f'"{term}"'
    return {
        "linkedin_query": quoted,
        "web_query": f'{quoted} AI agents',
    }


def already_decided(slug: str, config: dict[str, Any]) -> bool:
    for key in ("approved_subjects", "rejected_subjects", "monitor_only_subjects"):
        for item in config.get(key, []) if isinstance(config.get(key), list) else []:
            if item.get("chapter_id") == slug.replace("-", "_") or item.get("slug") == slug:
                return True
    return False


def build_subject_proposals(contract: dict[str, Any], trends: dict[str, Any], run_id: str = "manual", config: dict[str, Any] | None = None) -> dict[str, Any]:
    config = config or {}
    chapters = contract.get("chapters") if isinstance(contract.get("chapters"), dict) else {}
    candidates = trends.get("candidates") or trends.get("new_candidate_trends") or trends.get("trends") or []
    proposals: list[dict[str, Any]] = []
    ignored: list[dict[str, Any]] = []
    min_doc_count = int(config.get("min_doc_count", 2)) if isinstance(config, dict) else 2

    for candidate in candidates if isinstance(candidates, list) else []:
        if not isinstance(candidate, dict):
            continue
        term = candidate_term(candidate)
        if not candidate_is_worth_proposing(candidate, min_doc_count=min_doc_count):
            ignored.append({"term": term, "reason": "below_subject_discovery_threshold"})
            continue
        existing_id, score = fits_existing_chapter(term, chapters)
        if sufficient_existing_fit(term, score):
            ignored.append({"term": term, "reason": "fits_existing_chapter", "existing_chapter_id": existing_id, "matched_topic_count": score})
            continue
        slug = slugify(term)
        if already_decided(slug, config):
            ignored.append({"term": term, "reason": "already_decided"})
            continue
        pair = research_pair_for(term)
        proposals.append({
            "candidate_chapter_id": slug.replace("-", "_"),
            "candidate_title": term.title(),
            "candidate_target_path": f"docs/book/{slug}.md",
            "term": term,
            "source_count": candidate.get("count"),
            "doc_count": candidate.get("doc_count"),
            "evidence_strength": "discovery_signal_only",
            "status": "pending_human_approval",
            "human_approval_required": True,
            "recommended_action": "ask_human_approval_before_research_lane",
            "research_pair": pair,
            "approval_options": ["approve_new_chapter", "merge_into_existing_chapter", "monitor_only", "reject"],
            "write_docs_book_now": False,
        })

    return {
        "ok": True,
        "run_id": run_id,
        "generated_at_utc": utc_now(),
        "mode": "human_approved_chapter_subject_discovery",
        "human_approval_required": bool(proposals),
        "proposal_count": len(proposals),
        "proposals": proposals,
        "ignored_candidates": ignored,
        "docs_book_changed": False,
        "publication_approved": False,
        "chapter_update_allowed": False,
        "auto_publish_new_chapters_without_approval": False,
    }


def render_md(report: dict[str, Any]) -> str:
    lines = [
        "# Chapter subject discovery proposals",
        "",
        f"- Run: `{report.get('run_id')}`",
        f"- Generated: `{report.get('generated_at_utc')}`",
        f"- Human approval required: `{report.get('human_approval_required')}`",
        f"- Proposal count: `{report.get('proposal_count')}`",
        f"- Docs/book changed: `{report.get('docs_book_changed')}`",
        "",
        "## Proposals",
        "",
    ]
    if not report.get("proposals"):
        lines.append("No new chapter subjects require approval in this run.")
    for p in report.get("proposals", []):
        lines += [
            f"### {p.get('candidate_title')}",
            "",
            f"- candidate_chapter_id: `{p.get('candidate_chapter_id')}`",
            f"- target_path: `{p.get('candidate_target_path')}`",
            f"- status: `{p.get('status')}`",
            f"- recommended_action: `{p.get('recommended_action')}`",
            f"- LinkedIn query: `{p.get('research_pair', {}).get('linkedin_query')}`",
            f"- Web query: `{p.get('research_pair', {}).get('web_query')}`",
            "- approval_options: `approve_new_chapter`, `merge_into_existing_chapter`, `monitor_only`, `reject`",
            "",
        ]
    lines += [
        "## Ignored candidates",
        "",
    ]
    for item in report.get("ignored_candidates", [])[:25]:
        lines.append(f"- `{item.get('term')}` — {item.get('reason')}")
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--contract", default=str(DEFAULT_CONTRACT))
    ap.add_argument("--trends-json", required=True)
    ap.add_argument("--config", default=str(DEFAULT_CONFIG))
    ap.add_argument("--output-json")
    ap.add_argument("--output-md")
    args = ap.parse_args()

    contract = load_json(args.contract, {}) or {}
    trends = load_json(args.trends_json, {}) or {}
    config = load_json(args.config, {}) or {}
    report = build_subject_proposals(contract, trends, run_id=args.run_id, config=config)
    out_json = Path(args.output_json) if args.output_json else REPORTS / "editorial" / f"{args.run_id}-chapter-subject-discovery.json"
    out_md = Path(args.output_md) if args.output_md else REPORTS / "editorial" / f"{args.run_id}-chapter-subject-discovery.md"
    write_json(out_json, report)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text(render_md(report), encoding="utf-8")
    print(json.dumps(report, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
