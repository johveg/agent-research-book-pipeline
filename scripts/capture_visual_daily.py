#!/usr/bin/env python3
"""Optional PixelRAG/pixelshot visual evidence capture for harvested web sources.

This script is deliberately a supplement to text harvest: it records screenshots/tiles as
supplemental visual evidence and never mutates docs/book or publication state.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import urllib.parse
from pathlib import Path
from typing import Any

import research_common as rc
from research_common import slugify, utc_now, upsert_source, write_json


def raw_root() -> Path:
    return Path(os.environ.get("TEREFO_RAW_DIR", str(rc.RAW)))


def db_path() -> Path:
    return Path(os.environ.get("TEREFO_DB_PATH", str(rc.DB_PATH)))


def pixelshot_bin() -> str:
    configured = os.environ.get("TEREFO_PIXELSHOT_BIN", "").strip()
    if configured:
        return configured
    project_pixelshot = rc.ROOT / ".venv-pixelrag" / "bin" / "pixelshot"
    if project_pixelshot.exists():
        return str(project_pixelshot)
    return "pixelshot"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def connect_db_override():
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    import sqlite3

    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def load_urls(args: argparse.Namespace) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for url in args.url or []:
        items.append({"url": url, "query": args.query or "", "title": ""})
    if args.from_web_capture_json:
        data = json.loads(Path(args.from_web_capture_json).read_text())
        for capture in data.get("captures", []):
            query = capture.get("query") or args.query or ""
            for item in capture.get("items", []):
                url = item.get("url") or ""
                if url and item.get("http_status") not in (0, "0"):
                    items.append({"url": url, "query": query, "title": item.get("title") or ""})
    seen: set[str] = set()
    deduped: list[dict[str, str]] = []
    for item in items:
        url = item["url"]
        if url not in seen:
            seen.add(url)
            deduped.append(item)
    return deduped[: max(args.max_urls, 0)]


def find_tiles(out_dir: Path) -> list[Path]:
    return sorted([p for p in out_dir.rglob("*") if p.is_file() and p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}])


def capture_one(item: dict[str, str], run_id: str, pixelshot: str) -> dict[str, Any]:
    url = item["url"]
    parsed = urllib.parse.urlparse(url)
    base_slug = slugify(parsed.netloc + "-" + (parsed.path.strip("/") or "home"), 90)
    out_dir = raw_root() / "visual" / run_id / base_slug
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [pixelshot, url, "--output", str(out_dir)]
    proc = subprocess.run(cmd, text=True, capture_output=True, timeout=90)
    tiles = find_tiles(out_dir)
    now = utc_now()
    tile_hashes = {str(p.relative_to(raw_root())): sha256_file(p) for p in tiles}
    content_hash = hashlib.sha256((url + json.dumps(tile_hashes, sort_keys=True)).encode("utf-8")).hexdigest()
    meta = {
        "run_id": run_id,
        "source_type": "visual_web",
        "url": url,
        "query": item.get("query") or "",
        "title": item.get("title") or "",
        "captured_at": now,
        "capture_tool": "pixelshot",
        "capture_command": ["pixelshot", url, "--output", str(out_dir.relative_to(raw_root()))],
        "returncode": proc.returncode,
        "status": "ok" if proc.returncode == 0 and tiles else "capture_failed",
        "tile_count": len(tiles),
        "tiles": list(tile_hashes),
        "tile_hashes": tile_hashes,
        "stdout_tail": proc.stdout[-1000:],
        "stderr_tail": proc.stderr[-1000:],
        "content_hash": content_hash,
        "visibility": "supplemental_visual_evidence",
        "archived_path": str((out_dir / "visual-metadata.json").relative_to(raw_root())),
    }
    write_json(out_dir / "visual-metadata.json", meta)
    if meta["status"] == "ok":
        with connect_db_override() as con:
            src_id = upsert_source(
                con,
                source_type="visual_web",
                query=meta["query"],
                url=url,
                title=meta["title"],
                publisher=parsed.netloc,
                captured_at=now,
                archived_path=meta["archived_path"],
                content_hash=content_hash,
                run_id=run_id,
                visibility="supplemental_visual_evidence",
                reliability_tier="visual_supplement",
            )
            con.commit()
        meta["source_id"] = src_id
    return meta


def emit(path: str | None, payload: dict[str, Any]) -> None:
    if path:
        write_json(Path(path), payload)
    print(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--url", action="append")
    ap.add_argument("--query", default="")
    ap.add_argument("--from-web-capture-json")
    ap.add_argument("--max-urls", type=int, default=5)
    enabled = ap.add_mutually_exclusive_group()
    enabled.add_argument("--enabled", action="store_true")
    enabled.add_argument("--disabled", action="store_true")
    ap.add_argument("--json-out")
    args = ap.parse_args()

    if args.disabled or not args.enabled:
        payload = {
            "run_id": args.run_id,
            "captured_at": utc_now(),
            "visual_capture_enabled": False,
            "status": "disabled",
            "items": [],
        }
        emit(args.json_out, payload)
        return 0

    pixelshot = pixelshot_bin()
    if shutil.which(pixelshot) is None and not Path(pixelshot).exists():
        payload = {
            "run_id": args.run_id,
            "captured_at": utc_now(),
            "visual_capture_enabled": True,
            "status": "pixelshot_missing",
            "pixelshot_bin": pixelshot,
            "items": [],
        }
        emit(args.json_out, payload)
        return 2

    urls = load_urls(args)
    items = [capture_one(item, args.run_id, pixelshot) for item in urls]
    status = "ok" if all(item.get("status") == "ok" for item in items) else "partial"
    payload = {
        "run_id": args.run_id,
        "captured_at": utc_now(),
        "visual_capture_enabled": True,
        "status": status,
        "mode": "pixelshot",
        "item_count": len(items),
        "items": items,
    }
    emit(args.json_out, payload)
    return 0 if status == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())
