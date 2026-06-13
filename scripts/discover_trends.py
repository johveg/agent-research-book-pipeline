#!/usr/bin/env python3
"""Discover candidate trending phrases from the latest captured Markdown sources."""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from research_common import RAW, REPORTS, connect_db, init_db, load_config, sha256_text, utc_now, write_json

STOP = set('''a an and are as at be by for from has have in into is it its of on or that the this to was were with you your our their they them we will can about after all also more most new now how what when where who why not but if than then there these those using use via over under between within without ai linkedin openclaw hermes loop engineering engineer agents agent'''.split())
STRUCTURAL = set('''https http www com urn hashtag query search result results captured visible text url href profile miniprofileurn feed post follow followers comment like share source sources markdown metadata archive captured_at published_at t01'''.split())


def words(text: str):
    return [w.lower() for w in re.findall(r"[A-Za-z][A-Za-z0-9+.#-]{2,}", text)]


def ngrams(tokens, n):
    for i in range(len(tokens)-n+1):
        g=tokens[i:i+n]
        if any(x in STOP or x in STRUCTURAL for x in g):
            continue
        yield " ".join(g)


def meaningful(term: str) -> bool:
    parts=[p for p in re.split(r"\W+", term.lower()) if p]
    if not parts:
        return False
    if any(p in STRUCTURAL for p in parts):
        return False
    return any(p not in STOP and len(p) > 3 for p in parts)


def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument('--run-id', required=True)
    ap.add_argument('--json-out')
    args=ap.parse_args()
    cfg=load_config().get('trend_discovery', {})
    min_count=int(cfg.get('min_count',2))
    max_terms=int(cfg.get('max_terms',30))
    root_paths=[RAW/'web'/args.run_id, RAW/'linkedin'/args.run_id]
    docs=[]
    for root in root_paths:
        if root.exists():
            docs.extend(p for p in root.rglob('*.md'))
    text='\n'.join(p.read_text(errors='ignore') for p in docs)
    toks=[w for w in words(text) if w not in STOP and w not in STRUCTURAL and len(w)>2]
    counts=Counter(toks)
    phrase_counts=Counter()
    doc_hits=defaultdict(set)
    for p in docs:
        doc_text=p.read_text(errors='ignore')
        doc_toks=[w for w in words(doc_text) if w not in STOP and w not in STRUCTURAL and len(w)>2]
        unique_terms=set(doc_toks)
        for n in [2,3]:
            unique_terms.update(ngrams(doc_toks,n))
        for term in unique_terms:
            if meaningful(term):
                doc_hits[term].add(str(p))
    for n in [2,3]:
        phrase_counts.update(ngrams(toks,n))
    candidates=[]
    for term,count,typ in [(k,v,'word') for k,v in counts.items()] + [(k,v,'phrase') for k,v in phrase_counts.items()]:
        doc_count=len(doc_hits.get(term, set()))
        if count >= min_count and doc_count >= 2 and meaningful(term):
            candidates.append({'term':term,'count':count,'doc_count':doc_count,'term_type':typ})
    candidates=sorted(candidates, key=lambda x:(-x['doc_count'], -x['count'], x['term']))[:max_terms]
    now=utc_now()
    out_md=REPORTS/'discovery'/f'{args.run_id}-trend-discovery.md'
    out_json=REPORTS/'discovery'/f'{args.run_id}-trend-discovery.json'
    md=['# Trend discovery', '', f'- Run: `{args.run_id}`', f'- Generated: {now}', '', '## Candidate terms/phrases', '']
    for c in candidates:
        md.append(f"- **{c['term']}** — {c['count']} mentions across {c.get('doc_count', 0)} sources ({c['term_type']})")
    md.append('\n## Use\n\nThese are candidates for human review before adding new recurring search terms. LinkedIn/social captures are discovery signal only, not independent confirmation.\n')
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
