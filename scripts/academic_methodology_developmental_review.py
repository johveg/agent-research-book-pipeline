#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,subprocess,sys
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
FALSE_FLAGS={'author_allowed':False,'publication_approved':False,'eligible_for_claim_insertion':False,'eligible_for_authoring':False,'eligible_for_publication':False,'chapter_update_allowed':False}
SAFETY={'advisory_only':True,'review_only':True,'report_only':True,**FALSE_FLAGS}
def fail(err): return {'ok':False,'run_id':'run54','review_status':'methodology_developmental_review_failed_closed','gpt55_used':False,'provider':'copilot','model':'gpt-5.5','bridge':'hermes_cli','reasoning_profile':'closed_loop_editorial','strict_json':True,'weak_local_fallback_used':False,'errors':err,'publication_consideration_recommendation':'safe_reports_only','safety_flags':SAFETY,'generated_at':datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00','Z')}
def validate(d):
    errs=[]
    if d.get('provider')!='copilot' or d.get('model')!='gpt-5.5' or d.get('bridge')!='hermes_cli': errs.append('wrong_provider_model_bridge')
    if d.get('weak_local_fallback_used') is not False: errs.append('weak_local_fallback_used_refused')
    flags=d.get('safety_flags') if isinstance(d.get('safety_flags'),dict) else {}
    for k,v in SAFETY.items():
        if flags.get(k) is not v: errs.append('missing_or_invalid_safety_flag:'+k)
    rec=d.get('publication_consideration_recommendation') or 'safe_reports_only'
    if rec not in {'safe_reports_only','revise_before_publication','candidate_for_guarded_publication_consideration'}: errs.append('invalid_recommendation')
    for k in ['purpose_clear','boundaries_clear','privacy_handling_clear','automation_limits_clear','overclaiming_avoided']:
        val=d.get(k); val=val.get('status') if isinstance(val,dict) else val
        if not isinstance(val,bool): errs.append('missing_boolean:'+k)
        else: d[k]=val
    if errs: return fail(errs)
    d=dict(d); d['ok']=True; d['review_status']='methodology_developmental_review_completed'; d['publication_consideration_recommendation']=rec; d['safety_flags']=SAFETY; d['publication_allowed']=False; d['docs_book_update_allowed']=False; return d
def call_bridge(prompt,timeout=360):
    p=subprocess.run([sys.executable,'scripts/hermes_high_reasoning_json.py','--prompt',prompt,'--schema-name','run54_methodology_review','--provider','copilot','--model','gpt-5.5','--reasoning-profile','closed_loop_editorial','--timeout-seconds',str(timeout)],cwd=ROOT,text=True,capture_output=True,timeout=timeout+30)
    if p.returncode!=0: raise RuntimeError('gpt55_bridge_failed_closed')
    data=json.loads(p.stdout); return data.get('parsed_json') if isinstance(data.get('parsed_json'),dict) else data
def write(r,outj,outm):
    Path(outj).parent.mkdir(parents=True,exist_ok=True); Path(outj).write_text(json.dumps(r,indent=2,sort_keys=True,ensure_ascii=False)+'\n'); Path(outm).parent.mkdir(parents=True,exist_ok=True); Path(outm).write_text('# Run 54 methodology developmental review\n\n```json\n'+json.dumps(r,indent=2,sort_keys=True,ensure_ascii=False)+'\n```\n')
def quality_gate(review,draft,outj,outm):
    ok=bool(review.get('ok') and draft.get('ok'))
    r={'ok':ok,'run_id':'run54','status':'methodology_quality_gate_completed' if ok else 'methodology_quality_gate_failed_closed','classification':'methodology_update' if ok else 'safe_reports_only','publication_approved':False,'docs_book_update_allowed':False,'chapter_update_allowed':False,'safety_flags':FALSE_FLAGS,'publication_recommendation':'safe_reports_only'}
    write(r,outj,outm); return r
def main(argv=None):
    ap=argparse.ArgumentParser(); ap.add_argument('--draft',default='reports/editorial/run54-methodology-draft.json'); ap.add_argument('--output-json',default='reports/editorial/run54-methodology-developmental-review.json'); ap.add_argument('--output-md',default='reports/editorial/run54-methodology-developmental-review.md'); ap.add_argument('--quality-json',default='reports/editorial/run54-methodology-quality-gate.json'); ap.add_argument('--quality-md',default='reports/editorial/run54-methodology-quality-gate.md'); ap.add_argument('--timeout-seconds',type=int,default=360); a=ap.parse_args(argv)
    try:
        draft=json.loads((ROOT/a.draft).read_text()); prompt=json.dumps({'task':'Developmentally review report-only methodology draft. Return strict JSON only.','provider':'copilot','model':'gpt-5.5','bridge':'hermes_cli','strict_json':True,'weak_local_fallback':False,'required_safety_flags':SAFETY,'draft':draft},ensure_ascii=False); raw=call_bridge(prompt,a.timeout_seconds); r=validate(raw)
    except Exception as e: r=fail([str(e)]); draft={}
    write(r,ROOT/a.output_json,ROOT/a.output_md); q=quality_gate(r,draft,ROOT/a.quality_json,ROOT/a.quality_md); print(json.dumps({'ok':r.get('ok'),'review_status':r.get('review_status'),'quality_gate_ok':q.get('ok')},sort_keys=True)); return 0 if r.get('ok') else 2
if __name__=='__main__': raise SystemExit(main())
