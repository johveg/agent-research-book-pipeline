#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,re
from pathlib import Path

def evaluate_evidence_safety(packet, text):
    failed=[]; unsupported=[]; caveat=[]
    refs=set(re.findall(r'^\[(\d+)\]', text, re.M)); used=set(re.findall(r'\[(\d+)\]', text))
    if not used: failed.append('no_citations_used')
    if not used.issubset(refs): failed.append('citation_token_without_reference')
    if re.search(r'\b(claim|source)_[\w-]+\b|\bsrc_[\w-]+\b|raw_capture_\w+', text.split('## References',1)[0]): failed.append('internal_id_exposed')
    low=text.lower()
    if 'linkedin' in low and 'discovery signal' not in low: failed.append('social_signal_used_as_confirmation')
    if 'industry consensus' in low and 'not sufficient to claim' not in low and 'does not claim' not in low: failed.append('unsupported_industry_consensus')
    if 'prompt engineering is dead' in low: failed.append('unsupported_prompt_death_claim')
    if 'memory architecture' in low and not re.search(r'cautious|limited|requires better|stronger', low): caveat.append('memory_context_architecture')
    # simple support heuristic: cited paragraphs are supported/caveated by packet.
    for para in [p for p in re.split(r'\n\s*\n',text.split('## References',1)[0]) if p.strip() and not p.startswith('#')]:
        if re.search(r'\[\d+\]', para): continue
        if len(para.split())>25: unsupported.append(para[:120])
    if unsupported: failed.append('factual_paragraph_without_citation')
    passed=not failed
    return {'evidence_safety_passed':passed,'failed_checks':sorted(set(failed)),'unsupported_claims':unsupported,'caveat_required':caveat,'references_valid':'citation_token_without_reference' not in failed,'publication_candidate':passed}

def main(argv=None):
    ap=argparse.ArgumentParser();
    for a in ['packet-json','draft-md','source-registry','claims','output-json','output-md']: ap.add_argument('--'+a, required=True)
    ns=ap.parse_args(argv)
    try:
        packet=json.loads(Path(ns.packet_json).read_text()); text=Path(ns.draft_md).read_text(); out=evaluate_evidence_safety(packet,text); rc=0 if out['evidence_safety_passed'] else 2
    except Exception as e:
        out={'evidence_safety_passed':False,'failed_closed':True,'error':str(e),'failed_checks':['missing_input'],'unsupported_claims':[],'caveat_required':[],'references_valid':False,'publication_candidate':False}; rc=2
    Path(ns.output_json).parent.mkdir(parents=True,exist_ok=True); Path(ns.output_json).write_text(json.dumps(out,indent=2,sort_keys=True))
    Path(ns.output_md).write_text('# Evidence safety gate\n\n```json\n'+json.dumps(out,indent=2,sort_keys=True)+'\n```\n')
    print(json.dumps(out,indent=2,sort_keys=True)); return rc
if __name__=='__main__': raise SystemExit(main())
