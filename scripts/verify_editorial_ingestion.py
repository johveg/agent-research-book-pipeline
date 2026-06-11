#!/usr/bin/env python3
"""Verify that source collection has been editorially ingested into safe book pages."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from research_common import DOCS, ROOT, connect_db, init_db
from editorial_common import ensure_editorial_schema

BOOK_PAGES = [
    "book/preface.md",
    "book/01-the-agent-loop.md",
    "book/02-hermes.md",
    "book/03-openclaw.md",
    "book/04-loop-engineering.md",
    "book/05-context-memory-architecture.md",
    "book/06-operating-loops.md",
    "book/open-questions.md",
]
PLACEHOLDER_BITS = [
    "will be curated here",
    "no claim records have been extracted yet",
]


def tracked_or_staged_raw() -> tuple[list[str], list[str]]:
    tracked = [
        p for p in subprocess.run(["git", "ls-files", "raw"], cwd=ROOT, text=True, capture_output=True).stdout.splitlines()
        if p != "raw/.gitkeep"
    ]
    status = subprocess.run(["git", "status", "--short"], cwd=ROOT, text=True, capture_output=True).stdout.splitlines()
    staged_raw = []
    for line in status:
        path = line[3:]
        code = line[:2]
        if not path.startswith("raw/"):
            continue
        # Deletions are allowed when intentionally untracking historical raw captures.
        # raw/.gitkeep is the only allowed staged raw addition.
        if code.strip() == "D" or path == "raw/.gitkeep":
            continue
        staged_raw.append(line)
    return tracked, staged_raw


def page_is_stub(path: Path) -> bool:
    if not path.exists():
        return True
    text = path.read_text(encoding="utf-8", errors="ignore")
    body_lines = [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.startswith("#")]
    if len(body_lines) < 4:
        return True
    if any(bit in text.lower() for bit in PLACEHOLDER_BITS) and "Current evidence status" not in text:
        return True
    return False


def main() -> int:
    init_db()
    errors = []
    warnings = []
    with connect_db() as con:
        ensure_editorial_schema(con)
        sources = con.execute("SELECT count(*) FROM sources").fetchone()[0]
        entities = con.execute("SELECT count(*) FROM entities").fetchone()[0]
        claims = con.execute("SELECT count(*) FROM claims").fetchone()[0]
        missing_claim_sources = con.execute(
            "SELECT count(*) FROM claims c WHERE NOT EXISTS (SELECT 1 FROM claim_sources cs WHERE cs.claim_id = c.id)"
        ).fetchone()[0]
    if sources > 0 and entities == 0:
        errors.append("sources > 0 but entities = 0")
    if sources > 0 and claims == 0:
        errors.append("sources > 0 but claims = 0")
    if missing_claim_sources:
        errors.append(f"claims without source IDs: {missing_claim_sources}")
    entity_index = DOCS / "entities" / "index.md"
    if not entity_index.exists() or "Source count" not in entity_index.read_text(encoding="utf-8", errors="ignore"):
        errors.append("docs/entities/index.md missing or not populated")
    claims_page = DOCS / "research" / "claims.md"
    if not claims_page.exists() or "Candidate claims" not in claims_page.read_text(encoding="utf-8", errors="ignore"):
        errors.append("docs/research/claims.md missing candidate/supported grouping")
    stub_pages = [p for p in BOOK_PAGES if page_is_stub(DOCS / p)]
    if sources > 0 and stub_pages:
        errors.append("book pages still look like stubs: " + ", ".join(stub_pages))
    for rel in ["entities/index.md", "research/claims.md", *BOOK_PAGES]:
        path = DOCS / rel
        text = path.read_text(encoding="utf-8", errors="ignore") if path.exists() else ""
        if any(bit in text.lower() for bit in PLACEHOLDER_BITS) and "Current evidence status" not in text:
            warnings.append(f"placeholder-like content remains in {rel}")
    tracked_raw, staged_raw = tracked_or_staged_raw()
    if staged_raw:
        errors.append("raw files are staged unintentionally: " + "; ".join(staged_raw[:10]))
    if tracked_raw:
        warnings.append(f"raw/ has {len(tracked_raw)} tracked files; review whether sanitized enough to keep committed")
    payload = {"status": "ok" if not errors else "error", "errors": errors, "warnings": warnings}
    print(json.dumps(payload, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
