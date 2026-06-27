#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

FORBIDDEN_EVIDENCE_PHRASES = [
    "current evidence status",
    "source/claim mapping",
    "bullet 1 maps to",
    "maps to supported claim",
    "maps to caveated weak claim",
    "status supported",
    "status weakly_supported",
    "quality a",
    "quality b",
    "generated author output",
    "editor notes",
    "changelog",
    "editorial policy",
    "claim record",
    "source tokens",
]

GENERIC_BOOKLIKE_SIGNALS = [
    "central argument",
    "evidence limits",
    "references",
]

CHAPTER_SPECIFIC_SIGNALS = {
    "agent_loop": [
        "from prompt to loop",
        "operational pattern",
        "verification",
        "state",
        "escalation",
    ],
}

REQUIRED_BOOKLIKE_SIGNALS = GENERIC_BOOKLIKE_SIGNALS + CHAPTER_SPECIFIC_SIGNALS["agent_loop"]


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def fetch_url(url: str, timeout: int = 30) -> str:
    req = Request(url, headers={"User-Agent": "Run59PublicChapterProof/1.0"})
    with urlopen(req, timeout=timeout) as response:  # noqa: S310 - explicit user-requested public URL proof
        return response.read().decode("utf-8", errors="replace")


def chapter_title_from_target(path: str, configured_title: str | None = None) -> str:
    if configured_title:
        return configured_title
    stem = Path(path).stem.replace("-", " ").replace("_", " ").strip()
    if stem and stem[:2].isdigit():
        stem = stem[2:].strip()
    return stem.title() if stem else "Chapter"


def required_signals_for_chapter(chapter_id: str | None = None) -> list[str]:
    if chapter_id:
        return GENERIC_BOOKLIKE_SIGNALS + CHAPTER_SPECIFIC_SIGNALS.get(chapter_id, [])
    return REQUIRED_BOOKLIKE_SIGNALS


def evaluate_public_chapter_text(text: str, expected_title: str, chapter_id: str | None = None) -> dict:
    norm = normalize(text)
    required_signals = required_signals_for_chapter(chapter_id)
    failed: list[str] = []
    forbidden_found = [phrase for phrase in FORBIDDEN_EVIDENCE_PHRASES if phrase in norm]
    required_missing = [phrase for phrase in required_signals if phrase not in norm]
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if len(p.strip()) > 120]
    bullet_lines = [line for line in text.splitlines() if line.lstrip().startswith(("- ", "* "))]
    citation_tokens = re.findall(r"\[\d+\]", text)

    if expected_title.lower() not in norm:
        failed.append("expected_title_missing")
    if forbidden_found:
        failed.append("evidence_ledger_language_present")
    if required_missing:
        failed.append("booklike_required_signals_missing")
    if len(paragraphs) < 4:
        failed.append("insufficient_sustained_prose")
    if len(bullet_lines) > 2:
        failed.append("bullet_density_too_high")
    if len(set(citation_tokens)) < 3:
        failed.append("citation_tokens_missing_or_too_sparse")

    return {
        "ok": not failed,
        "public_page_booklike": not failed,
        "expected_title": expected_title,
        "forbidden_phrases_found": forbidden_found,
        "required_signals_missing": required_missing,
        "paragraph_count_ge_120_chars": len(paragraphs),
        "bullet_line_count": len(bullet_lines),
        "unique_citation_token_count": len(set(citation_tokens)),
        "required_signals": required_signals,
        "failed_checks": failed,
        "checked_at_utc_iso": datetime.now(timezone.utc).isoformat(),
    }


def evaluate_all_local_book_chapters(*, repo_root: Path, contract_json: Path) -> dict:
    contract = json.loads(contract_json.read_text(encoding="utf-8"))
    chapters = contract.get("chapters", {})
    results: dict[str, dict] = {}
    failed: list[str] = []
    missing: list[str] = []
    for chapter_id, spec in sorted(chapters.items()):
        target = spec.get("target_path")
        title = chapter_title_from_target(str(target or ""), spec.get("title"))
        if not target:
            result = {
                "ok": False,
                "public_page_booklike": False,
                "expected_title": title,
                "failed_checks": ["target_path_missing"],
            }
        else:
            path = repo_root / target
            if not path.exists():
                result = {
                    "ok": False,
                    "public_page_booklike": False,
                    "expected_title": title,
                    "source": str(path),
                    "source_kind": "file",
                    "failed_checks": ["chapter_file_missing"],
                }
                missing.append(chapter_id)
            else:
                result = evaluate_public_chapter_text(path.read_text(encoding="utf-8"), title, chapter_id=chapter_id)
                result.update({"source": str(path), "source_kind": "file", "target_path": target})
        results[chapter_id] = result
        if not result.get("ok"):
            failed.append(chapter_id)
    return {
        "ok": not failed,
        "source_kind": "all_local_book_chapters",
        "contract_json": str(contract_json),
        "repo_root": str(repo_root),
        "total_chapters": len(chapters),
        "passed_chapters": [c for c in sorted(chapters) if c not in failed],
        "failed_chapters": failed,
        "missing_chapters": missing,
        "chapter_results": results,
        "public_page_booklike": not failed,
        "checked_at_utc_iso": datetime.now(timezone.utc).isoformat(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prove public/book chapters are reader-facing manuscript prose, not evidence ledgers.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--url")
    source.add_argument("--input-file")
    source.add_argument("--all-local-book-chapters", action="store_true")
    parser.add_argument("--expected-title")
    parser.add_argument("--contract-json", default="config/book_manuscript_production_contract.json")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--output-md")
    parser.add_argument("--chapter-id")
    args = parser.parse_args(argv)

    if args.all_local_book_chapters:
        result = evaluate_all_local_book_chapters(repo_root=Path(args.repo_root), contract_json=Path(args.contract_json))
        source_value = str(args.contract_json)
    elif args.url:
        if not args.expected_title:
            parser.error("--expected-title is required with --url")
        text = fetch_url(args.url)
        source_value = args.url
        result = evaluate_public_chapter_text(text, args.expected_title, chapter_id=args.chapter_id)
        result.update({"source": source_value, "source_kind": "url"})
    else:
        if not args.expected_title:
            parser.error("--expected-title is required with --input-file")
        text = Path(args.input_file).read_text(encoding="utf-8")
        source_value = args.input_file
        result = evaluate_public_chapter_text(text, args.expected_title, chapter_id=args.chapter_id)
        result.update({"source": source_value, "source_kind": "file"})
    out = Path(args.output_json)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path = Path(args.output_md) if args.output_md else out.with_suffix(".md")
    md_path.write_text(
        "# Public chapter proof\n\n"
        f"- source: `{source_value}`\n"
        f"- ok: `{str(result['ok']).lower()}`\n"
        f"- public_page_booklike: `{str(result['public_page_booklike']).lower()}`\n"
        f"- failed_checks: `{result.get('failed_checks', [])}`\n"
        f"- failed_chapters: `{result.get('failed_chapters', [])}`\n"
        f"- total_chapters: `{result.get('total_chapters', 1)}`\n"
        f"- forbidden_phrases_found: `{result.get('forbidden_phrases_found', [])}`\n"
        f"- required_signals_missing: `{result.get('required_signals_missing', [])}`\n"
        f"- paragraph_count_ge_120_chars: `{result.get('paragraph_count_ge_120_chars', 'n/a')}`\n"
        f"- bullet_line_count: `{result.get('bullet_line_count', 'n/a')}`\n"
        f"- unique_citation_token_count: `{result.get('unique_citation_token_count', 'n/a')}`\n",
        encoding="utf-8",
    )
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
