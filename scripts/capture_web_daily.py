#!/usr/bin/env python3
"""Daily public web-search capture using Brave Search plus sanitized page text."""
from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from research_common import RAW, brave_key, connect_db, init_db, sha256_text, slugify, strip_html, extract_title, utc_now, upsert_source, write_json

BRAVE_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"
USER_AGENT = "terefohealreboa-research-book/1.0 (+https://github.com/johveg/terefohealreboa)"


def brave_search(api_key: str, query: str, count: int = 10, freshness: str = "pd") -> dict[str, Any]:
    params = {"q": query, "count": count, "freshness": freshness, "safesearch": "moderate"}
    req = urllib.request.Request(
        BRAVE_ENDPOINT + "?" + urllib.parse.urlencode(params),
        headers={"Accept": "application/json", "Accept-Encoding": "identity", "X-Subscription-Token": api_key, "User-Agent": USER_AGENT},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def fetch_url(url: str) -> tuple[int, str, str]:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = resp.read(1_500_000).decode("utf-8", errors="replace")
            return resp.status, resp.headers.get_content_type(), body
    except Exception as e:
        return 0, "error", str(e)


def capture(query: str, run_id: str, count: int, freshness: str) -> dict[str, Any]:
    key = brave_key()
    if not key:
        return {"query": query, "status": "missing_brave_key", "items": []}
    now = utc_now()
    data = brave_search(key, query, count=count, freshness=freshness)
    results = ((data.get("web") or {}).get("results") or [])
    out_dir = RAW / "web" / run_id / slugify(query)
    out_dir.mkdir(parents=True, exist_ok=True)
    write_json(out_dir / "brave-metadata.json", {"query": query, "captured_at": now, "freshness": freshness, "result_count": len(results), "raw_brave": data})
    items=[]
    init_db()
    with connect_db() as con:
        for i,r in enumerate(results, start=1):
            url = r.get("url") or ""
            title = r.get("title") or ""
            status, ctype, body = fetch_url(url) if url else (0, "", "")
            text = strip_html(body)[:200_000] if status and "html" in ctype else (body[:20_000] if body else "")
            if not title and body:
                title = extract_title(body)
            item_id = f"{i:02d}-{slugify(title or url, 60)}"
            md_path = out_dir / f"{item_id}.md"
            meta_path = out_dir / f"{item_id}.json"
            md = f"# {title or url}\n\n- Query: `{query}`\n- URL: {url}\n- Captured: {now}\n- HTTP status: {status}\n- Content type: {ctype}\n\n## Search snippet\n\n{r.get('description','')}\n\n## Extracted text\n\n{text[:30000]}\n"
            md_path.write_text(md, encoding="utf-8")
            meta = {"query": query, "url": url, "title": title, "description": r.get("description"), "captured_at": now, "http_status": status, "content_type": ctype, "markdown_path": str(md_path.relative_to(out_dir.parents[2])), "content_hash": sha256_text(text)}
            write_json(meta_path, meta)
            src_id = upsert_source(con, source_type="web", query=query, url=url, title=title, publisher=urllib.parse.urlparse(url).netloc, captured_at=now, archived_path=str(md_path.relative_to(out_dir.parents[2])), content_hash=meta["content_hash"], run_id=run_id, visibility="public_web")
            items.append({"source_id": src_id, **meta})
        con.commit()
    return {"query": query, "status": "ok", "items": items, "out_dir": str(out_dir)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--query", action="append", required=True)
    ap.add_argument("--count", type=int, default=10)
    ap.add_argument("--freshness", default="pd")
    ap.add_argument("--json-out")
    args = ap.parse_args()
    payload={"run_id": args.run_id, "captured_at": utc_now(), "captures": [capture(q,args.run_id,args.count,args.freshness) for q in args.query]}
    if args.json_out:
        write_json(Path(args.json_out), payload)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 2 if any(c["status"] != "ok" for c in payload["captures"]) else 0

if __name__ == "__main__":
    raise SystemExit(main())
