#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,re,subprocess,sys
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
FALSE_FLAGS={'author_allowed':False,'publication_approved':False,'eligible_for_claim_insertion':False,'eligible_for_authoring':False,'eligible_for_publication':False,'chapter_update_allowed':False}
SAFETY={'advisory_only':True,'draft_only':True,'report_only':True,**FALSE_FLAGS}
REQ=['purpose of methodology','evidence sources and boundaries','source collection process','inclusion/exclusion criteria','source quality categories','claim extraction and claim status model','editorial review and safety gates','privacy and raw-capture handling','social/LinkedIn discovery-only policy','automation limits','reproducibility limits','bias and limitations','relationship between internal pipeline evidence and public book claims','what the method cannot prove','how future chapters should use evidence']
def wc(t): return len(re.findall(r"\b[\w’'-]+\b",t or ''))
def fail(err): return {'ok':False,'run_id':'run54','draft_status':'methodology_draft_failed_closed','gpt55_used':False,'provider':'copilot','model':'gpt-5.5','bridge':'hermes_cli','reasoning_profile':'closed_loop_editorial','strict_json':True,'weak_local_fallback_used':False,'errors':err,'draft_word_count':0,'safety_flags':SAFETY,'generated_at':datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00','Z')}
def validate(d):
    errs=[]; text=str(d.get('draft_markdown') or '')
    if d.get('provider')!='copilot' or d.get('model')!='gpt-5.5' or d.get('bridge')!='hermes_cli': errs.append('wrong_provider_model_bridge')
    if d.get('weak_local_fallback_used') is not False: errs.append('weak_local_fallback_used_refused')
    flags=d.get('safety_flags') if isinstance(d.get('safety_flags'),dict) else {}
    for k,v in SAFETY.items():
        if flags.get(k) is not v: errs.append('missing_or_invalid_safety_flag:'+k)
    n=wc(text)
    if n<1500 or n>3000: errs.append(f'draft_word_count_out_of_bounds:{n}')
    if re.search(r'\b(?:claim|source|src|raw_capture|evidence)[_:][A-Za-z0-9_.:-]+',text,re.I): errs.append('raw_id_in_main_prose')
    if re.search(r'\[[0-9]+\]|\([A-Z][A-Za-z-]+,\s*(?:19|20)\d{2}\)',text): errs.append('invented_citation_marker')
    low=text.lower()
    for s in ['methodology','evidence','privacy','automation','limitations','future chapters']:
        if s not in low: errs.append('missing_required_topic:'+s)
    if errs: return fail(errs)
    d=dict(d); d['ok']=True; d['draft_status']='methodology_draft_report_only_created'; d['draft_word_count']=n; d['safety_flags']=SAFETY; d['publication_allowed']=False; d['docs_book_update_allowed']=False; return d
def build_prompt(packet):
    return json.dumps({'task':'Draft a report-only methodology chapter/appendix for an academic/professional book. Return strict JSON only.','provider':'copilot','model':'gpt-5.5','bridge':'hermes_cli','reasoning_profile':'closed_loop_editorial','strict_json':True,'weak_local_fallback':False,'word_count_bounds':[1500,3000],'required_sections':REQ,'required_safety_flags':SAFETY,'must_not':['publish','authorize docs/book update','invent citations','use raw claim/source IDs','overclaim'],'input_packet':packet},ensure_ascii=False)
def call_bridge(prompt,timeout=360):
    p=subprocess.run([sys.executable,'scripts/hermes_high_reasoning_json.py','--prompt',prompt,'--schema-name','run54_methodology_draft','--provider','copilot','--model','gpt-5.5','--reasoning-profile','closed_loop_editorial','--timeout-seconds',str(timeout)],cwd=ROOT,text=True,capture_output=True,timeout=timeout+30)
    if p.returncode!=0: raise RuntimeError('gpt55_bridge_failed_closed')
    data=json.loads(p.stdout); return data.get('parsed_json') if isinstance(data.get('parsed_json'),dict) else data
def write(r,outj,outm):
    Path(outj).parent.mkdir(parents=True,exist_ok=True); Path(outj).write_text(json.dumps(r,indent=2,sort_keys=True,ensure_ascii=False)+'\n'); Path(outm).parent.mkdir(parents=True,exist_ok=True); Path(outm).write_text('# Run 54 methodology draft\n\n- ok: `'+str(r.get('ok'))+'`\n- draft_status: `'+str(r.get('draft_status'))+'`\n- GPT-5.5 used: `'+str(r.get('gpt55_used'))+'`\n- word count: `'+str(r.get('draft_word_count'))+'`\n\n## Draft\n\n'+str(r.get('draft_markdown') or '')+'\n')
def main(argv=None):
    ap=argparse.ArgumentParser(); ap.add_argument('--input-packet',default='reports/editorial/run54-methodology-input-packet.json'); ap.add_argument('--output-json',default='reports/editorial/run54-methodology-draft.json'); ap.add_argument('--output-md',default='reports/editorial/run54-methodology-draft.md'); ap.add_argument('--timeout-seconds',type=int,default=360); a=ap.parse_args(argv)
    try:
        packet=json.loads((ROOT/a.input_packet).read_text()); raw=call_bridge(build_prompt(packet),a.timeout_seconds); r=validate(raw)
    except Exception as e: r=fail([str(e)])
    write(r,ROOT/a.output_json,ROOT/a.output_md); print(json.dumps({'ok':r.get('ok'),'draft_status':r.get('draft_status'),'draft_word_count':r.get('draft_word_count')},sort_keys=True)); return 0 if r.get('ok') else 2
if __name__=='__main__': raise SystemExit(main())
