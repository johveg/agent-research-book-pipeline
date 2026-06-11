#!/usr/bin/env python3
"""Discover candidate trending phrases from the latest captured Markdown sources."""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

from research_common import RAW, REPORTS, connect_db, init_db, load_config, sha256_text, utc_now, write_json

STOP = set('''a an and are as at be by for from has have in into is it its of on or that the this to was were with you your our their they them we will can about after all also more most new now how what when where who why not but if than then there these those using use via over under between within without ai linkedin openclaw hermes loop engineering engineer agents agent'''.split())


def words(text: str):
    return [w.lower() for w in re.findall(r"[A-Za-z][A-Za-z0-9+.#-]{2,}", text)]


def ngrams(tokens, n):
    for i in range(len(tokens)-n+1):
        g=tokens[i:i+n]
        if any(x in STOP for x in g):
            continue
        yield " ".join(g)


def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument('--run-id', required=True)
    ap.add_argument('--json-out')
    args=ap.parse_args()
    cfg=load_config().get('trend_discovery', {})
    min_count=int(cfg.get('min_count',2))
    max_terms=int(cfg.get('max_terms',30))
    root_paths=[RAW/'web'/args.run_id, RAW/'linkedin'/args.run_id]
    text='\n'.join(p.read_text(errors='ignore') for root in root_paths if root.exists() for p in root.rglob('*.md'))
    toks=[w for w in words(text) if w not in STOP and len(w)>2]
    counts=Counter(toks)
    phrase_counts=Counter()
    for n in [2,3]: phrase_counts.update(ngrams(toks,n))
    candidates=[]
    for term,count,typ in [(k,v,'word') for k,v in counts.items()] + [(k,v,'phrase') for k,v in phrase_counts.items()]:
        if count >= min_count:
            candidates.append({'term':term,'count':count,'term_type':typ})
    candidates=sorted(candidates, key=lambda x:(-x['count'], x['term']))[:max_terms]
    now=utc_now()
    out_md=REPORTS/'discovery'/f'{args.run_id}-trend-discovery.md'
    out_json=REPORTS/'discovery'/f'{args.run_id}-trend-discovery.json'
    md=['# Trend discovery', '', f'- Run: `{args.run_id}`', f'- Generated: {now}', '', '## Candidate terms/phrases', '']
    for c in candidates:
        md.append(f"- **{c['term']}** — {c['count']} mentions ({c['term_type']})")
    md.append('\n## Use\n\nThese are candidates for human review before adding new recurring search terms.\n')
    out_md.write_text('\n'.join(md), encoding='utf-8')
    write_json(out_json, {'run_id':args.run_id,'generated_at':now,'candidates':candidates})
    init_db()
    with connect_db() as con:
        for c in candidates:
            tid='trend_'+sha256_text(c['term'])[:20]
            con.execute('INSERT OR REPLACE INTO trend_terms (id, term, term_type, count, first_seen_at, last_seen_at, status, evidence_path, run_id) VALUES (?,?,?,?,?,?,?,?,?)',
                        (tid,c['term'],c['term_type'],c['count'],now,now,'candidate',str(out_md),args.run_id))
        con.commit()
    payload={'run_id':args.run_id,'markdown':str(out_md),'json':str(out_json),'candidates':candidates}
    if args.json_out: write_json(Path(args.json_out), payload)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0
if __name__=='__main__': raise SystemExit(main())
