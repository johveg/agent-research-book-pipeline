#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/'scripts'))
from ops_channel_autodiscovery import OPS_CHANNEL, discover, write as write_discovery
from ops_delivery_outbox import enqueue, attempt_delivery, validate, meta

def controller(run_id='run55',target_channel=OPS_CHANNEL,outbox='reports/ops/outbox/ops_delivery_outbox.jsonl',state='reports/ops/outbox/ops_delivery_outbox_state.json',output_json='reports/editorial/run55-ops-delivery-controller.json',output_md='reports/editorial/run55-ops-delivery-controller.md'):
    if target_channel!=OPS_CHANNEL: raise ValueError('target_channel_must_be_AL-Hermoine-OPS')
    disc=discover(); autodiscovery_json=ROOT/f'reports/editorial/{run_id}-ops-autodiscovery.json'; autodiscovery_md=ROOT/f'reports/editorial/{run_id}-ops-autodiscovery.md'; write_discovery(disc,autodiscovery_json,autodiscovery_md)
    sj=ROOT/f'reports/editorial/{run_id}-ops-delivery-controller-status.json'; sm=ROOT/f'reports/telegram/{run_id}-ops-delivery-controller-status.md'
    payload={'status_metadata':meta('ops_delivery_controller',run_id,'ops_delivery_degraded_queued','warning','ops_alias_unresolved_retry_scheduled'),'target_channel':OPS_CHANNEL,'ops_alias_resolvable':disc['ops_alias_resolvable'],'fallback_channel_used':False,'summary':f'{run_id} OPS delivery controller status. No fallback channel used.'}
    sj.parent.mkdir(parents=True,exist_ok=True); sj.write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n'); sm.parent.mkdir(parents=True,exist_ok=True); sm.write_text(f'# {run_id} OPS delivery controller status\n\n```json\n'+json.dumps(payload,indent=2,sort_keys=True)+'\n```\n')
    entry=enqueue(sm,sj,'ops_delivery_controller',run_id,'ops_delivery_degraded_queued','warning','ops_alias_unresolved_retry_scheduled',ROOT/outbox,ROOT/state)
    delivery=attempt_delivery(ROOT/outbox,ROOT/state,ROOT/'reports/ops/outbox/ops_delivery_attempts.jsonl',live=disc['ops_alias_resolvable'])
    val=validate(ROOT/outbox,ROOT/state)
    disposition='ops_delivery_live_verified' if delivery.get('delivered_count',0)>0 and delivery.get('queued_count',0)==0 else 'ops_delivery_degraded_queued'
    report={'status_metadata':meta('ops_delivery_controller',run_id,disposition,'success' if disposition=='ops_delivery_live_verified' else 'warning',disposition),'ops_autodiscovery':{k:v for k,v in disc.items() if k!='files_inspected'},'outbox_entry':entry,'outbox_state':delivery,'outbox_validation':val,'retry_scheduled':disposition!='ops_delivery_live_verified','retry_controller_installed':True,'target_channel':OPS_CHANNEL,'fallback_channel_used':False,'final_disposition':disposition}
    Path(ROOT/output_json).parent.mkdir(parents=True,exist_ok=True); Path(ROOT/output_json).write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    Path(ROOT/output_md).parent.mkdir(parents=True,exist_ok=True); Path(ROOT/output_md).write_text(f'# {run_id} OPS delivery controller\n\n```json\n'+json.dumps(report,indent=2,sort_keys=True)+'\n```\n')
    return report

def main(argv=None):
    ap=argparse.ArgumentParser(); ap.add_argument('--run-id',default='run55'); ap.add_argument('--target-channel',default=OPS_CHANNEL); ap.add_argument('--outbox',default='reports/ops/outbox/ops_delivery_outbox.jsonl'); ap.add_argument('--state',default='reports/ops/outbox/ops_delivery_outbox_state.json'); ap.add_argument('--output-json',default='reports/editorial/run55-ops-delivery-controller.json'); ap.add_argument('--output-md',default='reports/editorial/run55-ops-delivery-controller.md')
    a=ap.parse_args(argv); r=controller(a.run_id,a.target_channel,a.outbox,a.state,a.output_json,a.output_md); print(json.dumps({'final_disposition':r['final_disposition'],'queued_count':r['outbox_state'].get('queued_count'),'delivered_count':r['outbox_state'].get('delivered_count')},sort_keys=True)); return 0
if __name__=='__main__': raise SystemExit(main())
