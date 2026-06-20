#!/usr/bin/env python3
"""Verify the research book workspace and latest run state."""
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from research_common import DB_PATH, ROOT, CONFIG_PATH

REQUIRED = ['README.md','mkdocs.yml','data/search_config.json','data/schema.sql','scripts/daily_book_worker.py','scripts/capture_web_daily.py','scripts/capture_linkedin_daily.py','scripts/discover_trends.py','scripts/update_book_pages.py','scripts/build_vector_db.py','docs/index.md','.github/workflows/pages.yml']
FORBIDDEN_PATTERNS = ['.env','cookie','token','secret','credential','.var/browser','browser-profile']

REPORT_SAFE_SECRET_SCAN_RE = r"reports/(editorial|telegram|architecture)/run[0-9]+-secrets-scan\.(json|md)$"


def is_unsafe_tracked_path(path: str) -> bool:
    import re
    low = path.lower()
    if path == '.env.example':
        return False
    if re.match(REPORT_SAFE_SECRET_SCAN_RE, low):
        return False
    return any(x in low for x in FORBIDDEN_PATTERNS)


def main() -> int:
    ap=argparse.ArgumentParser(); ap.add_argument('--latest', action='store_true'); args=ap.parse_args()
    errors=[]; warnings=[]
    for r in REQUIRED:
        if not (ROOT/r).exists(): errors.append(f'missing required path: {r}')
    try:
        cfg=json.loads(CONFIG_PATH.read_text())
        if not cfg.get('web_queries'): errors.append('no web queries configured')
        if not cfg.get('linkedin_queries'): errors.append('no linkedin queries configured')
    except Exception as e: errors.append(f'bad search_config.json: {e}')
    if DB_PATH.exists():
        try:
            con=sqlite3.connect(DB_PATH)
            for t in ['runs','sources','entities','claims','trend_terms']:
                con.execute(f'SELECT count(*) FROM {t}').fetchone()
        except Exception as e: errors.append(f'database check failed: {e}')
    else:
        warnings.append('runtime DB not initialized yet')
    state=ROOT/'logs/runs/state/latest.state'
    if args.latest and not state.exists(): warnings.append('no latest.state yet')
    # Ensure no obviously unsafe tracked paths
    import subprocess
    p=subprocess.run(['git','ls-files'], cwd=ROOT, text=True, capture_output=True)
    for line in p.stdout.splitlines():
        if is_unsafe_tracked_path(line): errors.append(f'unsafe tracked path: {line}')
    payload={'status':'ok' if not errors else 'error','errors':errors,'warnings':warnings,'db_path':str(DB_PATH)}
    print(json.dumps(payload, indent=2))
    return 0 if not errors else 1
if __name__=='__main__': raise SystemExit(main())
