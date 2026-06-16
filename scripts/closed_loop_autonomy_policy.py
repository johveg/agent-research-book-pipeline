#!/usr/bin/env python3
from __future__ import annotations
import argparse,json
from datetime import datetime,timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo
OPS_CHANNEL='AL-Hermoine-OPS'
HARD_KEYS=['secrets_detected','protected_mutation_unexpected','docs_book_changed_without_publication_gate','source_claim_editorial_status_mutation_without_gate','data_schema_changed','weak_local_fallback_attempted','fallback_telegram_channel_used','gpt55_unavailable_for_required_reasoning_stage','invalid_required_report_json']
def ts(status='safe_reports_only',severity='info',disposition='safe_reports_only'):
    n=datetime.now(timezone.utc); o=n.astimezone(ZoneInfo('Europe/Oslo'))
    return {'emitted_at_unix_s':int(n.timestamp()),'emitted_at_unix_ms':int(n.timestamp()*1000),'emitted_at_utc_iso':n.replace(microsecond=0).isoformat().replace('+00:00','Z'),'emitted_at_oslo_iso':o.replace(microsecond=0).isoformat(),'timezone':'Europe/Oslo','component':'closed_loop_autonomy_policy','run_id':'run54','status':status,'severity':severity,'disposition':disposition,'target_channel':OPS_CHANNEL}
def evaluate_policy(state:dict[str,Any])->dict[str,Any]:
    hard=[k for k in HARD_KEYS if state.get(k) is True]
    degr=[]
    if state.get('ops_alias_resolved') is False:
        if state.get('outbox_available') and state.get('ops_status_queued'): degr.append('ops_alias_unresolved_but_status_queued')
        else: hard.append('ops_alias_unresolved_without_durable_outbox')
    if state.get('telegram_live_send_failed_closed') and not state.get('fallback_channel_used'): degr.append('telegram_live_send_failed_closed_no_fallback')
    if state.get('production_daily_status') in {'production_daily_completed','production_self_heal_not_needed','production_self_heal_not_due'}: degr.append('production_daily_completed_self_heal_not_needed')
    if state.get('methodology_report_only'): degr.append('methodology_draft_report_only')
    if state.get('outbox_available'): degr.append('status_outbox_available')
    if state.get('methodology_draft_requested') and state.get('gpt55_available') is False and not state.get('deterministic_alternative_exists'): hard.append('gpt55_unavailable_for_required_reasoning_stage')
    hard=sorted(set(hard)); degr=sorted(set(degr)); degraded=bool(degr) and not hard
    status='blocked_unsafe' if hard else ('ops_delivery_degraded_queued' if degraded else 'safe_reports_only')
    return {'status_metadata':ts(status,'failed_closed' if hard else 'warning' if degraded else 'info',status),'continue_allowed':not hard,'publication_allowed':False,'commit_allowed':not hard and not state.get('verification_gates_failed',False),'degraded_mode':degraded,'degradation_reasons':degr,'hard_stop_reasons':hard,'required_next_machine_action':'stop_failed_closed' if hard else 'continue_report_only_and_retry_ops_delivery' if degraded else 'run_remaining_verification_gates','human_required':False,'manual_action_required':False,'optional_manual_action':state.get('optional_manual_action'),'healthy':not hard and not degraded and bool(state.get('verification_gates_pass'))}
def main(argv=None):
    ap=argparse.ArgumentParser(); ap.add_argument('--state-json'); ap.add_argument('--output-json'); ap.add_argument('--output-md'); a=ap.parse_args(argv)
    state=json.loads(Path(a.state_json).read_text()) if a.state_json else {}; r=evaluate_policy(state)
    if a.output_json: Path(a.output_json).parent.mkdir(parents=True,exist_ok=True); Path(a.output_json).write_text(json.dumps(r,indent=2,sort_keys=True)+'\n')
    if a.output_md: Path(a.output_md).parent.mkdir(parents=True,exist_ok=True); Path(a.output_md).write_text('# Closed-loop autonomy policy\n\n```json\n'+json.dumps(r,indent=2,sort_keys=True)+'\n```\n')
    print(json.dumps({'continue_allowed':r['continue_allowed'],'degraded_mode':r['degraded_mode'],'hard_stop_reasons':r['hard_stop_reasons']},sort_keys=True)); return 0 if r['continue_allowed'] else 2
if __name__=='__main__': raise SystemExit(main())
