#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,re
from pathlib import Path
FORBIDDEN=['Current evidence status','Source/claim mapping','Bullet 1 maps','Editor notes','Changelog','Editorial policy','status supported','status weakly_supported','quality A','quality B','claim record','source tokens']

def evaluate_manuscript(text):
    failed=[]
    paras=[p.strip() for p in re.split(r'\n\s*\n',text) if p.strip() and not p.startswith('#')]
    if len(paras)<2: failed.append('insufficient_paragraph_level_argument')
    if not re.search(r'argu|thesis|central', text, re.I): failed.append('missing_coherent_thesis')
    if not re.search(r'\[\d+\]', text): failed.append('missing_integrated_citations')
    if '## References' not in text: failed.append('missing_references')
    if not re.search(r'limited|limitation|cautious|not settled|does not claim|not sufficient', text, re.I): failed.append('missing_limitations')
    body = text.split('## References',1)[0]
    if any(f.lower() in body.lower() for f in FORBIDDEN): failed.append('internal_metadata_or_evidence_machinery')
    if re.search(r'\b(claim|source)_[\w-]+\b|\bsrc_[\w-]+\b|raw_capture_\w+', text): failed.append('internal_id_exposed')
    bullets=[l for l in text.splitlines() if l.startswith('- ')]
    if len(bullets)>4: failed.append('raw_evidence_bullets_as_main_body')
    low=text.lower()
    if 'prompt engineering is dead' in low or ('industry consensus' in low and 'not sufficient to claim' not in low and 'does not claim' not in low): failed.append('overclaiming')
    passed=not failed
    return {'manuscript_quality_passed':passed,'failed_checks':sorted(set(failed)),'publication_candidate':passed,'docs_book_update_allowed':passed,'appendix_required':False,'evidence_mapping_externalized': 'Source/claim mapping' not in text,'safety_flags':{'publication_approved':False,'chapter_update_allowed':False}}

def main(argv=None):
    ap=argparse.ArgumentParser(); ap.add_argument('--draft-md',required=True); ap.add_argument('--quality-contract',required=True); ap.add_argument('--academic-contract',required=True); ap.add_argument('--output-json',required=True); ap.add_argument('--output-md',required=True)
    a=ap.parse_args(argv)
    try:
        text=Path(a.draft_md).read_text(); out=evaluate_manuscript(text); rc=0 if out['manuscript_quality_passed'] else 2
    except Exception as e:
        out={'manuscript_quality_passed':False,'failed_closed':True,'error':str(e),'failed_checks':['missing_input_or_contract'],'publication_candidate':False,'docs_book_update_allowed':False}; rc=2
    Path(a.output_json).parent.mkdir(parents=True,exist_ok=True); Path(a.output_json).write_text(json.dumps(out,indent=2,sort_keys=True))
    Path(a.output_md).write_text('# Manuscript quality gate\n\n```json\n'+json.dumps(out,indent=2,sort_keys=True)+'\n```\n')
    print(json.dumps(out,indent=2,sort_keys=True)); return rc
if __name__=='__main__': raise SystemExit(main())
