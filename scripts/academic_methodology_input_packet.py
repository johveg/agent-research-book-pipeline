#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,re
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
FALSE_FLAGS={'author_allowed':False,'publication_approved':False,'eligible_for_claim_insertion':False,'eligible_for_authoring':False,'eligible_for_publication':False,'chapter_update_allowed':False}
def wc(t): return len(re.findall(r"\b[\w’'-]+\b",t or ''))
def load(p): return json.loads((ROOT/p).read_text())
def build_packet():
    required=['reports/editorial/run50-introduction-thesis-draft.json','reports/editorial/run50-introduction-developmental-review.json','reports/editorial/run49-academic-manuscript-inventory.json','reports/editorial/run49-chapter-conversion-plan.json','config/academic_book_quality_contract.json','book/academic_structure_plan.md']
    missing=[p for p in required if not (ROOT/p).exists()]
    if missing: return {'ok':False,'status':'methodology_input_packet_failed_closed','missing_inputs':missing,'safety_flags':FALSE_FLAGS}
    intro=load(required[0]); review=load(required[1]); inventory=load(required[2]); plan=load(required[3]); contract=load(required[4]); structure=(ROOT/required[5]).read_text()
    packet={'ok':True,'run_id':'run54','status':'methodology_input_packet_created','target_channel':'AL-Hermoine-OPS','created_at':datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00','Z'),'provider':'copilot','model':'gpt-5.5','bridge':'hermes_cli','reasoning_profile':'closed_loop_editorial','strict_json':True,'weak_local_fallback':False,'inputs':required,'introduction_summary':{k:intro.get(k) for k in ['draft_status','central_thesis','scope_statement','limitations','draft_word_count']},'developmental_review_summary':{k:review.get(k) for k in ['review_status','publication_consideration_recommendation','required_changes_before_publication']},'inventory_status':inventory.get('status') or inventory.get('final_disposition'),'conversion_plan_status':plan.get('status') or plan.get('final_disposition'),'quality_contract_keys':sorted(contract.keys()),'academic_structure_plan_word_count':wc(structure),'methodology_sections_required':['purpose of methodology','evidence sources and boundaries','source collection process','inclusion/exclusion criteria','source quality categories','claim extraction and claim status model','editorial review and safety gates','privacy and raw-capture handling','social/LinkedIn discovery-only policy','automation limits','reproducibility limits','bias and limitations','relationship between internal pipeline evidence and public book claims','what the method cannot prove','how future chapters should use evidence'],'safety_flags':FALSE_FLAGS,'publication_allowed':False,'docs_book_update_allowed':False}
    return packet
def write(report,outj,outm):
    Path(outj).parent.mkdir(parents=True,exist_ok=True); Path(outj).write_text(json.dumps(report,indent=2,sort_keys=True)+'\n'); Path(outm).parent.mkdir(parents=True,exist_ok=True); Path(outm).write_text('# Run 54 methodology input packet\n\n```json\n'+json.dumps(report,indent=2,sort_keys=True)+'\n```\n')
def main(argv=None):
    ap=argparse.ArgumentParser(); ap.add_argument('--output-json',default='reports/editorial/run54-methodology-input-packet.json'); ap.add_argument('--output-md',default='reports/editorial/run54-methodology-input-packet.md'); a=ap.parse_args(argv)
    r=build_packet(); write(r,ROOT/a.output_json,ROOT/a.output_md); print(json.dumps({'ok':r['ok'],'status':r['status']},sort_keys=True)); return 0 if r['ok'] else 2
if __name__=='__main__': raise SystemExit(main())
