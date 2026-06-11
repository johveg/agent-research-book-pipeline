#!/usr/bin/env python3
"""Authenticated LinkedIn search-result capture via existing CDP browser.

Read-only: opens fresh LinkedIn content searches, expands visible text, scrolls until plateau,
and archives only sanitized visible search-result metadata. It does not open posts/profiles.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
from pathlib import Path

from research_common import RAW, connect_db, init_db, sha256_text, slugify, utc_now, upsert_source, write_json

BLOCK_TERMS = ["captcha", "checkpoint", "security verification", "sign in", "join linkedin", "verify", "unusual activity"]


def search_url(query: str) -> str:
    params = {
        "datePosted": '["past-24h"]',
        "keywords": query,
        "origin": "FACETED_SEARCH",
        "sortBy": '["date_posted"]',
    }
    return "https://www.linkedin.com/search/results/content/?" + urllib.parse.urlencode(params)


def detect_blocked(page) -> str | None:
    url = page.url.lower()
    title = (page.title() or "").lower()
    body = (page.locator("body").inner_text(timeout=5000) or "").lower()[:5000]
    hay = " ".join([url, title, body])
    for t in BLOCK_TERMS:
        if t in hay:
            return t
    if "/login" in url or "/checkpoint" in url:
        return url
    return None


def extract_posts(page) -> list[dict]:
    js = r'''
    () => {
      const cards = Array.from(document.querySelectorAll('li, div.feed-shared-update-v2, div[data-urn*="activity"], div.update-components-text')).slice(0, 300);
      const out = [];
      const seen = new Set();
      for (const el of cards) {
        const txt = (el.innerText || '').replace(/\s+/g, ' ').trim();
        if (!txt || txt.length < 40) continue;
        let a = el.querySelector('a[href*="/in/"], a[href*="/company/"], a[href*="/feed/update/"], a[href*="/posts/"]');
        let href = a ? a.href : '';
        let urn = el.getAttribute('data-urn') || '';
        let key = (urn || href || txt.slice(0,150));
        if (seen.has(key)) continue;
        seen.add(key);
        out.push({text: txt.slice(0, 6000), href, urn});
      }
      return out;
    }
    '''
    return page.evaluate(js)


def capture_one(page, query: str, run_id: str, max_scrolls: int) -> dict:
    now = utc_now()
    url = search_url(query)
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(4000)
    blocked = detect_blocked(page)
    if blocked:
        return {"query": query, "status": "blocked_or_login", "reason": blocked, "url": page.url, "items": []}
    out_dir = RAW / "linkedin" / run_id / slugify(query)
    out_dir.mkdir(parents=True, exist_ok=True)
    last_count = 0
    stable = 0
    for _ in range(max_scrolls):
        # Expand visible text only; ignore failures/localized variants are best-effort.
        for txt in ["see more", "…see more", "more", "vis mer", "se mer"]:
            try:
                page.get_by_text(txt, exact=False).click(timeout=800)
            except Exception:
                pass
        posts = extract_posts(page)
        if len(posts) <= last_count:
            stable += 1
        else:
            stable = 0
            last_count = len(posts)
        if stable >= 4:
            break
        page.mouse.wheel(0, 1800)
        page.wait_for_timeout(1500)
    posts = extract_posts(page)
    init_db()
    items=[]
    with connect_db() as con:
        for i,p in enumerate(posts, start=1):
            sid_hash = sha256_text((p.get("urn") or "") + (p.get("href") or "") + p.get("text", ""))[:20]
            md_path = out_dir / f"{i:03d}-{sid_hash}.md"
            meta_path = out_dir / f"{i:03d}-{sid_hash}.json"
            md_path.write_text(f"# LinkedIn search result {i}\n\n- Query: `{query}`\n- Captured: {now}\n- URL: {p.get('href','')}\n- URN: {p.get('urn','')}\n\n## Visible text\n\n{p.get('text','')}\n", encoding="utf-8")
            meta = {"query": query, "captured_at": now, "href": p.get("href"), "urn": p.get("urn"), "text_hash": sha256_text(p.get("text", "")), "markdown_path": str(md_path.relative_to(out_dir.parents[2]))}
            write_json(meta_path, meta)
            source_id=upsert_source(con, source_type="linkedin_search_result", query=query, url=p.get("href"), title=(p.get("text") or "")[:140], captured_at=now, archived_path=str(md_path.relative_to(out_dir.parents[2])), content_hash=meta["text_hash"], run_id=run_id, visibility="authenticated_search_result_visible_text")
            items.append({"source_id": source_id, **meta})
        con.commit()
    write_json(out_dir / "metadata-sanitized.json", {"query": query, "captured_at": now, "url": url, "result_count": len(items), "limitation": "Authenticated LinkedIn search-results page only; posts/profiles/comments were not opened.", "items": items})
    return {"query": query, "status": "ok", "count": len(items), "out_dir": str(out_dir), "items": items}


def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--query", action="append", required=True)
    ap.add_argument("--cdp", default="http://127.0.0.1:9222")
    ap.add_argument("--max-scrolls", type=int, default=60)
    ap.add_argument("--json-out")
    args=ap.parse_args()
    from playwright.sync_api import sync_playwright
    payload={"run_id": args.run_id, "captured_at": utc_now(), "captures": []}
    with sync_playwright() as p:
        browser=p.chromium.connect_over_cdp(args.cdp)
        context=browser.contexts[0] if browser.contexts else browser.new_context()
        page=context.pages[0] if context.pages else context.new_page()
        for q in args.query:
            payload["captures"].append(capture_one(page,q,args.run_id,args.max_scrolls))
        # Do not close the persistent browser; closing CDP connection is fine.
        browser.close()
    if args.json_out:
        write_json(Path(args.json_out), payload)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 2 if any(c["status"] != "ok" for c in payload["captures"]) else 0

if __name__ == "__main__":
    raise SystemExit(main())
