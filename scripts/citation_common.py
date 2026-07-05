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
from urllib.parse import urlparse

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


def _display_name_for_reference(record: dict[str, Any]) -> str:
    publisher = (record.get("publisher") or "").strip()
    title = (record.get("title") or "").strip()
    source_type = (record.get("source_type") or "").strip()
    url = (record.get("canonical_url") or record.get("original_url") or "").strip()

    if publisher:
        return publisher
    if title:
        return title
    if source_type:
        return source_type
    if url:
        host = urlparse(url).netloc.replace("www.", "")
        return host or "Source"
    return "Source"


def citation_label(record: dict[str, Any]) -> str:
    name = _display_name_for_reference(record)
    url = (record.get("canonical_url") or record.get("original_url") or "").strip()
    if url:
        return f"[{name}]({url})"
    return name


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


def _normalize_legacy_reference_lines(text: str) -> tuple[str, bool]:
    references_header_re = re.compile(r"^##\s+references\s*$", re.I | re.M)
    number_line_re = re.compile(r"^\[(\d+)\]\s+(.*)$")
    markdown_link_re = re.compile(r"\[[^\]]+\]\(https?://[^)]+\)")
    url_re = re.compile(r"https?://[^\s),]+")

    lines = text.splitlines()
    header_idx = next((i for i, line in enumerate(lines) if references_header_re.match(line.strip())), None)
    if header_idx is None:
        return text, False

    changed = False
    for i in range(header_idx + 1, len(lines)):
        line = lines[i]
        if line.startswith("## "):
            break
        m = number_line_re.match(line.strip())
        if not m:
            continue
        number = m.group(1)
        body = m.group(2).strip()
        if markdown_link_re.search(body):
            continue
        url_match = None
        for candidate in url_re.findall(body):
            if candidate:
                url_match = candidate.rstrip('.,;)')
                if url_match:
                    break
        if not url_match:
            continue

        label = body.split(',', 1)[0].strip().strip('"“”')
        if not label:
            label = urlparse(url_match).netloc.replace("www.", "") or "Source"

        lines[i] = f"[{number}] [{label}]({url_match})"
        changed = True

    lines, spacing_changed = _space_reference_entries(lines, header_idx)
    normalized = "\n".join(lines)
    if text.endswith("\n") and not normalized.endswith("\n"):
        normalized += "\n"
    return normalized, changed or spacing_changed


def _space_reference_entries(lines: list[str], header_idx: int) -> tuple[list[str], bool]:
    spaced: list[str] = []
    changed = False
    reference_line_re = re.compile(r"^\[(\d+)\]\s+")

    for i, line in enumerate(lines):
        if i > header_idx and line.startswith("## "):
            spaced.extend(lines[i:])
            break
        if i > header_idx and reference_line_re.match(line.strip()) and spaced:
            previous = spaced[-1].strip()
            if reference_line_re.match(previous):
                spaced.append("")
                changed = True
        spaced.append(line)
    else:
        return spaced, changed
    return spaced, changed


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

    # Replace an existing generated reference section only when this pass has
    # resolved raw citation tokens. If a page already contains reader-facing
    # numeric citations and references, a no-token resolver pass must be
    # idempotent and must not delete the bibliography.
    references_normalized = False
    if citation_numbers:
        text = re.sub(r"\n## References\n\n.*\Z", "", text, flags=re.S).rstrip() + "\n"
        references = ["", "## References", ""]
        for source_id, number in sorted(citation_numbers.items(), key=lambda item: item[1]):
            references.append(f"[{number}] {citation_label(registry[source_id])}")
            references.append("")
        text += "\n".join(references).rstrip() + "\n"
    else:
        text, references_normalized = _normalize_legacy_reference_lines(text)

    return text, {
        "citation_count": len(citation_numbers),
        "source_ids": sorted(citation_numbers, key=citation_numbers.get),
        "unresolved": unresolved,
        "references_normalized": references_normalized,
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
    citation_reference_mismatch_hits: list[dict[str, Any]] = []
    legacy_reference_style_hits: list[dict[str, Any]] = []
    prose_citation_re = re.compile(r"\[(\d+)\]")
    reference_line_re = re.compile(r"^\[(\d+)\]\s+")
    markdown_link_re = re.compile(r"\[[^\]]+\]\(https?://[^)]+\)")
    url_re = re.compile(r"https?://[^\s),]+")
    timestamp_re = re.compile(r"\b\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\b")
    quality_re = re.compile(r"\bquality\s+[A-Z]\b", re.I)

    for path in sorted(book_dir.glob("*.md")):
        text = path.read_text(encoding="utf-8", errors="ignore")
        lines = text.splitlines()
        rel = display_path(path)

        for idx, line in enumerate(lines, start=1):
            if RAW_ID_RE.search(line) or TOKEN_RE.search(line):
                raw_id_hits.append({"path": rel, "line": idx, "text": line.strip()[:300]})
            if "[unresolved citation]" in line:
                unresolved_hits.append({"path": rel, "line": idx, "text": line.strip()[:300]})

        references_header_idx = next((i for i, line in enumerate(lines) if line.strip().lower() == "## references"), None)
        prose_lines = lines[:references_header_idx] if references_header_idx is not None else lines
        reference_lines = lines[references_header_idx + 1 :] if references_header_idx is not None else []

        prose_numbers = sorted({int(match.group(1)) for line in prose_lines for match in prose_citation_re.finditer(line)})
        reference_numbers_all = [int(match.group(1)) for line in reference_lines for match in reference_line_re.finditer(line)]
        reference_numbers = sorted(set(reference_numbers_all))
        duplicate_reference_numbers = sorted({n for n in reference_numbers_all if reference_numbers_all.count(n) > 1})

        missing_reference_numbers = sorted(set(prose_numbers) - set(reference_numbers))
        orphan_reference_numbers = sorted(set(reference_numbers) - set(prose_numbers))

        if missing_reference_numbers or orphan_reference_numbers or duplicate_reference_numbers:
            citation_reference_mismatch_hits.append(
                {
                    "path": rel,
                    "has_references_section": references_header_idx is not None,
                    "prose_citation_numbers": prose_numbers,
                    "reference_numbers": reference_numbers,
                    "missing_reference_numbers": missing_reference_numbers,
                    "orphan_reference_numbers": orphan_reference_numbers,
                    "duplicate_reference_numbers": duplicate_reference_numbers,
                }
            )

        for offset, line in enumerate(reference_lines):
            idx = ((references_header_idx + 2) if references_header_idx is not None else 1) + offset
            ref_match = reference_line_re.match(line)
            if not ref_match:
                continue
            body = line.strip()
            style_failures: list[str] = []
            has_link = bool(markdown_link_re.search(body))
            has_url = bool(url_re.search(body))
            if has_url and not has_link:
                style_failures.append("missing_markdown_hyperlink")
            if timestamp_re.search(body):
                style_failures.append("contains_timestamp")
            if quality_re.search(body):
                style_failures.append("contains_quality_label")
            if offset + 1 < len(reference_lines) and reference_line_re.match(reference_lines[offset + 1]):
                style_failures.append("missing_blank_line_after_reference")
            if style_failures:
                legacy_reference_style_hits.append(
                    {
                        "path": rel,
                        "line": idx,
                        "text": body[:300],
                        "style_failures": style_failures,
                    }
                )

    blocked = bool(raw_id_hits or unresolved_hits or citation_reference_mismatch_hits or legacy_reference_style_hits)
    return {
        "status": "ok" if not blocked else "blocked",
        "raw_id_hits": raw_id_hits,
        "unresolved_hits": unresolved_hits,
        "citation_reference_mismatch_hits": citation_reference_mismatch_hits,
        "legacy_reference_style_hits": legacy_reference_style_hits,
    }
