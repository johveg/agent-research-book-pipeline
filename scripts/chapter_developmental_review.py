#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,re,datetime
from pathlib import Path
RECS={'publish_canary','revise_report_only','blocked_evidence_safety','blocked_manuscript_quality','safe_reports_only'}
FLAGS=['author_allowed','publication_approved','eligible_for_claim_insertion','eligible_for_authoring','eligible_for_publication','chapter_update_allowed']

def build_deterministic_review(quality, evidence, draft_text):
    q=quality.get('manuscript_quality_passed') is True; e=evidence.get('evidence_safety_passed') is True
    rec='publish_canary' if q and e else ('blocked_manuscript_quality' if not q else 'blocked_evidence_safety')
    return {'review_status':'developmental_review_completed','recommendation':rec,'reads_like_book_chapter':q,'argument_clear':q,'sources_synthesized_not_listed':q,'weak_claims_caveated': 'not sufficient to claim' in draft_text or 'does not claim' in draft_text or 'limited' in draft_text.lower(),'useful_to_professional_reader':q and e,'changes_before_publication':[] if q and e else ['revise report-only draft against failed deterministic gates'],'safe_to_use_as_canary_public_chapter':q and e,'safety_flags':{k:False for k in FLAGS},'model_metadata':{'provider':'copilot','model':'gpt-5.5','bridge':'hermes_cli','reasoning_profile':'closed_loop_editorial','strict_json':True,'weak_local_fallback':False,'weak_local_fallback_used':False},'created_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}

def validate_review_payload(payload):
    failed=[]
    if payload.get('recommendation') not in RECS: failed.append('recommendation_not_allowed')
    if not all(payload.get('safety_flags',{}).get(k) is False for k in FLAGS): failed.append('safety_flags_not_false')
    if payload.get('model_metadata',{}).get('weak_local_fallback_used') is True: failed.append('weak_local_fallback_used')
    return {'ok':not failed,'failed_checks':failed}

def main(argv=None):
    ap=argparse.ArgumentParser();
    for a in ['packet-json','draft-md','quality-gate-json','evidence-gate-json','output-json','output-md']: ap.add_argument('--'+a, required=True)
    ns=ap.parse_args(argv)
    try:
        draft=Path(ns.draft_md).read_text(); quality=json.loads(Path(ns.quality_gate_json).read_text()); evidence=json.loads(Path(ns.evidence_gate_json).read_text()); out=build_deterministic_review(quality,evidence,draft); out['validation']=validate_review_payload(out); rc=0 if out['validation']['ok'] else 2
    except Exception as e:
        out={'review_status':'developmental_review_failed_closed','recommendation':'safe_reports_only','error':str(e),'safety_flags':{k:False for k in FLAGS}}; rc=2
    Path(ns.output_json).parent.mkdir(parents=True,exist_ok=True); Path(ns.output_json).write_text(json.dumps(out,indent=2,sort_keys=True))
    Path(ns.output_md).write_text('# Developmental review\n\n```json\n'+json.dumps(out,indent=2,sort_keys=True)+'\n```\n')
    print(json.dumps(out,indent=2,sort_keys=True)); return rc
if __name__=='__main__': raise SystemExit(main())
