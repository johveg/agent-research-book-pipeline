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

REQUIRED_BOOKLIKE_SIGNALS = [
    "central argument",
    "from prompt to loop",
    "operational pattern",
    "verification",
    "state",
    "escalation",
    "evidence limits",
    "references",
]


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def fetch_url(url: str, timeout: int = 30) -> str:
    req = Request(url, headers={"User-Agent": "Run59PublicChapterProof/1.0"})
    with urlopen(req, timeout=timeout) as response:  # noqa: S310 - explicit user-requested public URL proof
        return response.read().decode("utf-8", errors="replace")


def evaluate_public_chapter_text(text: str, expected_title: str) -> dict:
    norm = normalize(text)
    failed: list[str] = []
    forbidden_found = [phrase for phrase in FORBIDDEN_EVIDENCE_PHRASES if phrase in norm]
    required_missing = [phrase for phrase in REQUIRED_BOOKLIKE_SIGNALS if phrase not in norm]
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
        "failed_checks": failed,
        "checked_at_utc_iso": datetime.now(timezone.utc).isoformat(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prove a public/book chapter is reader-facing manuscript prose, not an evidence ledger.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--url")
    source.add_argument("--input-file")
    parser.add_argument("--expected-title", required=True)
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--output-md")
    args = parser.parse_args(argv)

    if args.url:
        text = fetch_url(args.url)
        source_value = args.url
        source_kind = "url"
    else:
        text = Path(args.input_file).read_text(encoding="utf-8")
        source_value = args.input_file
        source_kind = "file"

    result = evaluate_public_chapter_text(text, args.expected_title)
    result.update({"source": source_value, "source_kind": source_kind})
    out = Path(args.output_json)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path = Path(args.output_md) if args.output_md else out.with_suffix(".md")
    md_path.write_text(
        "# Public chapter proof\n\n"
        f"- source: `{source_value}`\n"
        f"- ok: `{str(result['ok']).lower()}`\n"
        f"- public_page_booklike: `{str(result['public_page_booklike']).lower()}`\n"
        f"- failed_checks: `{result['failed_checks']}`\n"
        f"- forbidden_phrases_found: `{result['forbidden_phrases_found']}`\n"
        f"- required_signals_missing: `{result['required_signals_missing']}`\n"
        f"- paragraph_count_ge_120_chars: `{result['paragraph_count_ge_120_chars']}`\n"
        f"- bullet_line_count: `{result['bullet_line_count']}`\n"
        f"- unique_citation_token_count: `{result['unique_citation_token_count']}`\n",
        encoding="utf-8",
    )
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
