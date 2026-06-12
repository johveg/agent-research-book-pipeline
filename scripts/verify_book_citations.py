#!/usr/bin/env python3
"""Publication gate: book pages must not expose unresolved internal source IDs."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from citation_common import scan_publication_citation_issues
from research_common import DOCS


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--book-dir", default=str(DOCS / "book"))
    ap.add_argument("--json-out")
    args = ap.parse_args()
    result = scan_publication_citation_issues(Path(args.book_dir))
    if args.json_out:
        Path(args.json_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json_out).write_text(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["status"] == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())
