#!/usr/bin/env python3
"""Citation/source-origin helpers for the Terefo Heal Reboa book pipeline.

The source registry is the citation authority. Vector/chunk/search IDs may carry
source_id, but publication must resolve source_id -> registry metadata -> reader
citation. Raw src_/claim_ identifiers are allowed only inside structured internal
citation tokens before this resolver runs.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from research_common import DATA, DOCS, RAW, connect_db, init_db, utc_now, write_json

REGISTRY_PATH = DATA / "source_registry.json"
TOKEN_RE = re.compile(r"\{\{\s*cite\s*:\s*(src_[a-f0-9]{20}|claim_[a-f0-9]{20})\s*\}\}")
BACKTICK_ID_RE = re.compile(r"`(src_[a-f0-9]{20}|claim_[a-f0-9]{20})`")
BARE_ID_RE = re.compile(r"(?<![A-Za-z0-9_])(src_[a-f0-9]{20}|claim_[a-f0-9]{20})(?![A-Za-z0-9_])")
RAW_ID_RE = re.compile(r"(?<![A-Za-z0-9_])(src_[a-f0-9]{20}|claim_[a-f0-9]{20})(?![A-Za-z0-9_])")


def _safe_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _raw_capture_path(archived_path: str | None) -> str | None:
    if not archived_path:
        return None
    candidate = RAW / archived_path
    return str(candidate.relative_to(DATA.parent)) if candidate.exists() else None


def source_row_to_registry_record(row: Any) -> dict[str, Any]:
    archived = _safe_str(row["archived_path"])
    url = _safe_str(row["url"])
    return {
        "source_id": row["id"],
        "title": _safe_str(row["title"]) or url or row["id"],
        "author": _safe_str(row["author"]),
        "publisher": _safe_str(row["publisher"]),
        "canonical_url": url,
        "original_url": url,
        "source_type": _safe_str(row["source_type"]) or "unknown",
        "captured_at": _safe_str(row["captured_at"]),
        "published_at": _safe_str(row["published_at"]),
        "archive_path": archived,
        "raw_capture_path": _raw_capture_path(archived),
        "quality_score": _safe_str(row["quality_score"]) or _safe_str(row["reliability_tier"]) or "unknown",
        "privacy_publication_status": _safe_str(row["privacy_publication_status"]) or _safe_str(row["visibility"]) or "unknown",
        "content_hash": _safe_str(row["content_hash"]),
        "run_id": _safe_str(row["run_id"]),
        "search_query": _safe_str(row["query"]),
        "extraction_method": "pipeline_capture_to_sqlite_sources",
        "summary": _safe_str(row["summary"]),
        "duplicate_status": _safe_str(row["duplicate_status"]) or "unknown",
        "quality_notes": _safe_str(row["quality_notes"]),
        "publication_notes": _safe_str(row["publication_notes"]),
    }


def export_source_registry(path: Path = REGISTRY_PATH) -> dict[str, Any]:
    """Export the canonical source registry from the SQLite sources table."""
    init_db()
    with connect_db() as con:
        rows = con.execute("SELECT * FROM sources ORDER BY id").fetchall()
    records = [source_row_to_registry_record(row) for row in rows]
    payload = {
        "schema_version": 1,
        "generated_at": utc_now(),
        "authority": "SQLite sources table exported by scripts/export_source_registry.py",
        "records": records,
    }
    write_json(path, payload)
    return payload


def load_source_registry(path: Path = REGISTRY_PATH) -> dict[str, dict[str, Any]]:
    if not path.exists():
        export_source_registry(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {rec["source_id"]: rec for rec in payload.get("records", []) if rec.get("source_id")}


def resolve_claim_sources(claim_id: str) -> list[str]:
    init_db()
    with connect_db() as con:
        rows = con.execute(
            """
            SELECT source_id FROM claim_sources
            WHERE claim_id=?
            ORDER BY source_id
            """,
            (claim_id,),
        ).fetchall()
    return [row["source_id"] for row in rows]


def citation_label(record: dict[str, Any]) -> str:
    title = record.get("title") or "Untitled source"
    publisher = record.get("publisher") or record.get("source_type") or "unknown publisher"
    author = record.get("author")
    date = record.get("published_at") or record.get("captured_at") or "unknown date"
    url = record.get("canonical_url") or record.get("original_url")
    quality = record.get("quality_score") or "unknown"
    source_id = record.get("source_id")
    bits = []
    if author:
        bits.append(str(author))
    bits.append(f"“{title}”")
    bits.append(str(publisher))
    bits.append(str(date))
    if url:
        bits.append(str(url))
    bits.append(f"quality {quality}")
    # Do not expose internal source IDs in public book pages. Traceability is
    # preserved in data/source_registry.json.
    return ", ".join(bits) + "."


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(DATA.parent))
    except ValueError:
        return str(path)


def _source_is_publishable(record: dict[str, Any]) -> bool:
    privacy = (record.get("privacy_publication_status") or "").lower()
    return bool(record.get("source_id")) and bool(record.get("title")) and privacy != "human_review"


def _ids_to_source_ids(identifier: str) -> list[str]:
    if identifier.startswith("src_"):
        return [identifier]
    if identifier.startswith("claim_"):
        return resolve_claim_sources(identifier)
    return []


def resolve_text_citations(text: str, registry: dict[str, dict[str, Any]] | None = None) -> tuple[str, dict[str, Any]]:
    """Resolve citation tokens/raw IDs in a markdown document.

    Raw IDs are accepted as legacy input so existing generated pages can be
    normalized, but generator output should prefer {{cite:...}} tokens.
    """
    registry = registry or load_source_registry()
    citation_numbers: dict[str, int] = {}
    unresolved: list[dict[str, Any]] = []

    def cite_for_identifier(identifier: str) -> str:
        source_ids = _ids_to_source_ids(identifier)
        if not source_ids:
            unresolved.append({"identifier": identifier, "reason": "no linked source ids"})
            return ""
        labels: list[str] = []
        for source_id in source_ids:
            record = registry.get(source_id)
            if not record:
                unresolved.append({"identifier": identifier, "source_id": source_id, "reason": "missing source registry record"})
                continue
            if not _source_is_publishable(record):
                unresolved.append({"identifier": identifier, "source_id": source_id, "reason": "source origin metadata not publishable"})
                continue
            if source_id not in citation_numbers:
                citation_numbers[source_id] = len(citation_numbers) + 1
            labels.append(f"[{citation_numbers[source_id]}]")
        return "".join(labels)

    text = TOKEN_RE.sub(lambda m: cite_for_identifier(m.group(1)), text)
    text = BACKTICK_ID_RE.sub(lambda m: cite_for_identifier(m.group(1)), text)
    text = BARE_ID_RE.sub(lambda m: cite_for_identifier(m.group(1)), text)
    text = text.replace("[unresolved citation]", "")

    # Replace an existing generated reference section to keep reruns idempotent.
    text = re.sub(r"\n## References\n\n.*\Z", "", text, flags=re.S).rstrip() + "\n"
    if citation_numbers:
        references = ["", "## References", ""]
        for source_id, number in sorted(citation_numbers.items(), key=lambda item: item[1]):
            references.append(f"[{number}] {citation_label(registry[source_id])}")
        text += "\n".join(references) + "\n"

    return text, {
        "citation_count": len(citation_numbers),
        "source_ids": sorted(citation_numbers, key=citation_numbers.get),
        "unresolved": unresolved,
    }


def resolve_book_pages(book_dir: Path | None = None, registry_path: Path = REGISTRY_PATH) -> dict[str, Any]:
    book_dir = book_dir or (DOCS / "book")
    registry = load_source_registry(registry_path)
    files: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    for path in sorted(book_dir.glob("*.md")):
        original = path.read_text(encoding="utf-8", errors="ignore")
        resolved, info = resolve_text_citations(original, registry)
        if resolved != original:
            path.write_text(resolved, encoding="utf-8")
        rel = display_path(path)
        files.append({"path": rel, **info, "changed": resolved != original})
        for item in info["unresolved"]:
            unresolved.append({"path": rel, **item})
    return {"status": "ok" if not unresolved else "blocked", "files": files, "unresolved": unresolved}


def scan_publication_citation_issues(book_dir: Path | None = None) -> dict[str, Any]:
    book_dir = book_dir or (DOCS / "book")
    raw_id_hits: list[dict[str, Any]] = []
    unresolved_hits: list[dict[str, Any]] = []
    for path in sorted(book_dir.glob("*.md")):
        text = path.read_text(encoding="utf-8", errors="ignore")
        rel = display_path(path)
        for idx, line in enumerate(text.splitlines(), start=1):
            if RAW_ID_RE.search(line) or TOKEN_RE.search(line):
                raw_id_hits.append({"path": rel, "line": idx, "text": line.strip()[:300]})
            if "[unresolved citation]" in line:
                unresolved_hits.append({"path": rel, "line": idx, "text": line.strip()[:300]})
    return {
        "status": "ok" if not raw_id_hits and not unresolved_hits else "blocked",
        "raw_id_hits": raw_id_hits,
        "unresolved_hits": unresolved_hits,
    }
