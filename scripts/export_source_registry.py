#!/usr/bin/env python3
"""Export canonical machine-readable source registry from the SQLite source database."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from citation_common import REGISTRY_PATH, export_source_registry


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(REGISTRY_PATH), help="Output registry JSON path")
    args = ap.parse_args()
    payload = export_source_registry(Path(args.out))
    print(json.dumps({
        "status": "ok",
        "path": args.out,
        "records": len(payload.get("records", [])),
        "generated_at": payload.get("generated_at"),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
