#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/'scripts'))
from ops_delivery_outbox import OPS_CHANNEL, enqueue, meta
LOCK=Path('/tmp/terefo_production_daily_self_heal.lock')

def run_monitor(repo,timezone,expect,run_id=None):
    cmd=['python3','scripts/production_daily_monitor.py','--repo',repo,'--timezone',timezone,'--expect-schedule-time',expect,'--json']
    if run_id: cmd += ['--run-id', run_id]
    p=subprocess.run(cmd,cwd=repo,text=True,capture_output=True)
    try: return json.loads(p.stdout)
    except Exception: return {'status':'production_daily_failed_closed','error':'monitor_json_invalid','stdout_tail':p.stdout[-500:],'stderr_tail':p.stderr[-500:]}

def write_md(path,report):
    Path(path).parent.mkdir(parents=True,exist_ok=True); Path(path).write_text('# Production daily self-heal status\n\n```json\n'+json.dumps(report,indent=2,sort_keys=True)+'\n```\n')

def retry_count_for(run_id:str,outbox_path:Path)->int:
    if not outbox_path.exists(): return 0
    count=0
    for line in outbox_path.read_text(errors='ignore').splitlines():
        if run_id in line and 'production_daily_self_heal' in line:
            count += 1
    return count

def self_heal(repo=str(ROOT),timezone='Europe/Oslo',expect='05:30',target_channel=OPS_CHANNEL,run_id=None,output_json='reports/editorial/run55-production-self-heal.json',output_md='reports/editorial/run55-production-self-heal.md',telegram_status='reports/telegram/run55-production-self-heal-status.md',retry_limit=1):
    if target_channel!=OPS_CHANNEL: raise ValueError('no_fallback_channel_allowed')
    rp=Path(repo); outbox=rp/'reports/ops/outbox/ops_delivery_outbox.jsonl'; state=rp/'reports/ops/outbox/ops_delivery_outbox_state.json'
    before=run_monitor(str(rp),timezone,expect,run_id); status=before.get('status'); action='none'; after=before; rc=None; stdout_tail=''; stderr_tail=''
    retry_count=retry_count_for(run_id or before.get('expected_run_id','production-daily-unknown'), outbox)
    executable_statuses={'production_daily_missing_after_due','production_daily_failed_closed'}
    failed_reasons=before.get('contract_validation',{}).get('failed_closed_reasons',[]) if isinstance(before.get('contract_validation'),dict) else []
    recoverable_failed_closed = status=='production_daily_failed_closed' and any(('missing_required_artifact:logs/runs' in str(r) or 'missing_required_field:run_started_at_unix_s' in str(r) or 'missing_required_field:run_finished_at_unix_s' in str(r)) for r in failed_reasons)
    if LOCK.exists():
        disp='production_execution_failed_closed'; action='lock_prevented_overlap'; reason='lock_prevented_overlap'
    elif status=='production_daily_completed':
        disp='production_self_heal_not_needed'; action='none_completed'; reason=None
    elif status=='production_daily_missing_not_due_yet':
        disp='production_self_heal_not_due'; action='none_not_due'; reason='not_due'
    elif status=='production_daily_failed_closed' and retry_count == 0 and not recoverable_failed_closed:
        disp='production_execution_failed_closed'; action='no_infinite_retry_failed_closed'; reason='retry_marker_required_for_failed_closed_recovery'
    elif status in executable_statuses and retry_count >= retry_limit:
        disp='production_execution_failed_closed'; action='retry_limit_exceeded'; reason='retry_limit_exceeded'
    elif status in executable_statuses:
        try:
            LOCK.write_text('locked')
            env=None
            if run_id:
                env=dict(__import__('os').environ); env['TEREFO_PRODUCTION_RUN_ID']=run_id
            proc=subprocess.run(['bash','scripts/run_production_daily_cron.sh'],cwd=rp,text=True,capture_output=True,timeout=1800,env=env)
            rc=proc.returncode; stdout_tail=getattr(proc,'stdout','')[-4000:]; stderr_tail=getattr(proc,'stderr','')[-4000:]; action='wrapper_executed_once'
            after=run_monitor(str(rp),timezone,expect,run_id)
            disp='production_execution_recovered' if after.get('status')=='production_daily_completed' else 'production_execution_failed_closed'
            reason=None if disp=='production_execution_recovered' else after.get('status')
        finally:
            try: LOCK.unlink()
            except FileNotFoundError: pass
    else: disp='production_execution_failed_closed'; action='unsupported_monitor_status_no_infinite_retry'; reason=status
    severity='success' if disp in {'production_self_heal_not_needed','production_execution_recovered'} else 'failed_closed'
    report={'status_metadata':meta('production_daily_self_heal','run55',disp,severity,disp),'run_id':'run55','production_run_id':run_id or before.get('expected_run_id'),'before_monitor':before,'after_monitor':after,'action':action,'wrapper_returncode':rc,'wrapper_stdout_tail':stdout_tail,'wrapper_stderr_tail':stderr_tail,'retry_count_before':retry_count,'retry_limit':retry_limit,'target_channel':OPS_CHANNEL,'fallback_channel_used':False,'failed_closed_reason':reason,'final_disposition':disp}
    (rp/output_json).parent.mkdir(parents=True,exist_ok=True); (rp/output_json).write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    (rp/output_md).parent.mkdir(parents=True,exist_ok=True); (rp/output_md).write_text('# Run 55 production daily self-heal\n\n```json\n'+json.dumps(report,indent=2,sort_keys=True)+'\n```\n')
    write_md(rp/telegram_status,report)
    enqueue(rp/telegram_status,rp/output_json,'production_daily_self_heal','run55',disp,severity,disp,outbox,state)
    return report

def main(argv=None):
    ap=argparse.ArgumentParser(); ap.add_argument('--repo',default=str(ROOT)); ap.add_argument('--timezone',default='Europe/Oslo'); ap.add_argument('--expect-schedule-time',default='05:30'); ap.add_argument('--target-channel',default=OPS_CHANNEL); ap.add_argument('--run-id'); ap.add_argument('--output-json',default='reports/editorial/run55-production-self-heal.json'); ap.add_argument('--output-md',default='reports/editorial/run55-production-self-heal.md'); ap.add_argument('--telegram-status',default='reports/telegram/run55-production-self-heal-status.md'); ap.add_argument('--retry-limit',type=int,default=1)
    a=ap.parse_args(argv); r=self_heal(a.repo,a.timezone,a.expect_schedule_time,a.target_channel,a.run_id,a.output_json,a.output_md,a.telegram_status,a.retry_limit); print(json.dumps({'final_disposition':r['final_disposition'],'monitor_status':r['before_monitor'].get('status')},sort_keys=True)); return 0 if r['final_disposition'] in {'production_self_heal_not_needed','production_execution_recovered'} else 2
if __name__=='__main__': raise SystemExit(main())
