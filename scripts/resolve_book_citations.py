#!/usr/bin/env python3
"""Resolve book citation tokens/internal IDs into reader-facing numbered citations."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from citation_common import REGISTRY_PATH, resolve_book_pages
from research_common import DOCS


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--book-dir", default=str(DOCS / "book"), help="Directory containing generated book markdown pages")
    ap.add_argument("--registry", default=str(REGISTRY_PATH), help="Canonical source registry JSON")
    ap.add_argument("--json-out", help="Optional path for resolver report JSON")
    args = ap.parse_args()
    result = resolve_book_pages(Path(args.book_dir), Path(args.registry))
    if args.json_out:
        Path(args.json_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json_out).write_text(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["status"] == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())
