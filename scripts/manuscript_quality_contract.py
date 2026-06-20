#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT=ROOT/'config/manuscript_quality_contract.json'
HARD_FLAGS=['author_allowed','publication_approved','eligible_for_claim_insertion','eligible_for_authoring','eligible_for_publication','chapter_update_allowed']

def load_contract(path=DEFAULT_CONTRACT):
    p=Path(path)
    if not p.exists(): raise FileNotFoundError(str(p))
    return json.loads(p.read_text())

def hard_safety_flags_false(flags):
    return all(flags.get(k) is False for k in HARD_FLAGS)

def _contains_any(text, phrases):
    low=text.lower()
    return [p for p in phrases if p.lower() in low]

def evaluate_chapter_text(text, contract=None, publication_requested=False):
    contract=contract or load_contract()
    failed=[]
    forbidden=_contains_any(text, contract.get('forbidden_reader_facing_phrases',[]))
    if forbidden: failed.append('forbidden_reader_facing_phrase')
    if re.search(r'\b(claim|source)_[A-Za-z0-9_\-]+\b|\bsrc_[A-Za-z0-9_\-]+\b|raw_capture_\w+', text): failed.append('internal_id_exposed')
    headings=re.findall(r'^##\s+(.+)$', text, re.M)
    paras=[p.strip() for p in re.split(r'\n\s*\n', text) if p.strip() and not p.strip().startswith('#')]
    if not text.lstrip().startswith('# '): failed.append('missing_chapter_title')
    if len(paras)<1: failed.append('insufficient_paragraph_argument')
    if not re.search(r'\[\d+\]', text): failed.append('missing_integrated_citations')
    if '## References' not in text and '## references' not in text.lower(): failed.append('missing_references')
    if not re.search(r'limitation|limited|cautious|not settled|does not establish|emerging', text, re.I): failed.append('missing_limitations_or_caveat')
    over=[]
    low=text.lower()
    for phrase in contract.get('blocked_overclaims',[]):
        if phrase.lower() in low and not re.search(r'does not claim|do not claim|not (a |an )?'+re.escape(phrase.lower())+'|does not establish|rather than settled|not settled', low):
            over.append(phrase)
    if over: failed.append('uncaveated_overclaim')
    bullet_lines=[l for l in text.splitlines() if l.startswith('- ')]
    if len(bullet_lines)>max(4, len(paras)): failed.append('raw_evidence_bullets_dominate')
    passed=not failed
    return {
        'manuscript_contract_passed':passed,
        'failed_checks':sorted(set(failed)),
        'forbidden_phrases_found':forbidden,
        'publication_candidate':passed and publication_requested,
        'docs_book_update_allowed':passed and publication_requested,
        'safety_flags':{k:False for k in HARD_FLAGS},
    }

def main(argv=None):
    ap=argparse.ArgumentParser(); ap.add_argument('--input',required=True); ap.add_argument('--contract',default=str(DEFAULT_CONTRACT)); ap.add_argument('--output-json'); ap.add_argument('--output-md'); ap.add_argument('--publication-requested',action='store_true')
    a=ap.parse_args(argv)
    try:
        contract=load_contract(a.contract); text=Path(a.input).read_text(); out=evaluate_chapter_text(text,contract,a.publication_requested); rc=0 if out['manuscript_contract_passed'] else 2
    except Exception as e:
        out={'manuscript_contract_passed':False,'failed_closed':True,'error':str(e),'docs_book_update_allowed':False,'publication_candidate':False,'safety_flags':{k:False for k in HARD_FLAGS}}; rc=2
    if a.output_json: Path(a.output_json).write_text(json.dumps(out,indent=2,sort_keys=True))
    if a.output_md: Path(a.output_md).write_text('# Manuscript quality contract evaluation\n\n```json\n'+json.dumps(out,indent=2,sort_keys=True)+'\n```\n')
    print(json.dumps(out,indent=2,sort_keys=True)); return rc
if __name__=='__main__': raise SystemExit(main())
