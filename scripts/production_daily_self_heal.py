#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/'scripts'))
from ops_delivery_outbox import OPS_CHANNEL, enqueue, meta
LOCK=Path('/tmp/terefo_production_daily_self_heal.lock')
def run_monitor(repo,timezone,expect):
    p=subprocess.run(['python3','scripts/production_daily_monitor.py','--repo',repo,'--timezone',timezone,'--expect-schedule-time',expect,'--json'],cwd=repo,text=True,capture_output=True)
    try: return json.loads(p.stdout)
    except Exception: return {'status':'production_daily_failed_closed','error':'monitor_json_invalid','stdout_tail':p.stdout[-500:],'stderr_tail':p.stderr[-500:]}
def write_md(path,report):
    Path(path).parent.mkdir(parents=True,exist_ok=True); Path(path).write_text('# Run 54 production self-heal status\n\n```json\n'+json.dumps(report,indent=2,sort_keys=True)+'\n```\n')
def self_heal(repo=str(ROOT),timezone='Europe/Oslo',expect='05:30',target_channel=OPS_CHANNEL,output_json='reports/editorial/run54-production-self-heal.json',output_md='reports/editorial/run54-production-self-heal.md',telegram_status='reports/telegram/run54-production-self-heal-status.md'):
    if target_channel!=OPS_CHANNEL: raise ValueError('no_fallback_channel_allowed')
    rp=Path(repo); before=run_monitor(str(rp),timezone,expect); status=before.get('status'); action='none'; after=before; rc=None
    if LOCK.exists(): disp='production_self_heal_failed_closed'; action='lock_prevented_overlap'
    elif status=='production_daily_completed': disp='production_self_heal_not_needed'; action='none_completed'
    elif status=='production_daily_missing_not_due_yet': disp='production_self_heal_not_due'; action='none_not_due'
    elif status=='production_daily_missing_after_due':
        try:
            LOCK.write_text('locked')
            proc=subprocess.run(['bash','scripts/run_production_daily_cron.sh'],cwd=rp,text=True,capture_output=True,timeout=1800)
            rc=proc.returncode; action='wrapper_executed_once'; after=run_monitor(str(rp),timezone,expect); disp='production_self_heal_executed' if after.get('status')=='production_daily_completed' else 'production_self_heal_failed_closed'
        finally:
            try: LOCK.unlink()
            except FileNotFoundError: pass
    else: disp='production_self_heal_failed_closed'; action='no_infinite_retry_failed_closed'
    severity='success' if disp in {'production_self_heal_not_needed','production_self_heal_executed','production_self_heal_not_due'} else 'failed_closed'
    report={'status_metadata':meta('production_daily_self_heal','run54',disp,severity,disp),'before_monitor':before,'after_monitor':after,'action':action,'wrapper_returncode':rc,'target_channel':OPS_CHANNEL,'fallback_channel_used':False,'final_disposition':disp}
    (rp/output_json).parent.mkdir(parents=True,exist_ok=True); (rp/output_json).write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    (rp/output_md).parent.mkdir(parents=True,exist_ok=True); (rp/output_md).write_text('# Run 54 production daily self-heal\n\n```json\n'+json.dumps(report,indent=2,sort_keys=True)+'\n```\n')
    write_md(rp/telegram_status,report)
    enqueue(rp/telegram_status,rp/output_json,'production_daily_self_heal','run54',disp,severity,disp,rp/'reports/ops/outbox/ops_delivery_outbox.jsonl',rp/'reports/ops/outbox/ops_delivery_outbox_state.json')
    return report
def main(argv=None):
    ap=argparse.ArgumentParser(); ap.add_argument('--repo',default=str(ROOT)); ap.add_argument('--timezone',default='Europe/Oslo'); ap.add_argument('--expect-schedule-time',default='05:30'); ap.add_argument('--target-channel',default=OPS_CHANNEL); ap.add_argument('--output-json',default='reports/editorial/run54-production-self-heal.json'); ap.add_argument('--output-md',default='reports/editorial/run54-production-self-heal.md'); ap.add_argument('--telegram-status',default='reports/telegram/run54-production-self-heal-status.md')
    a=ap.parse_args(argv); r=self_heal(a.repo,a.timezone,a.expect_schedule_time,a.target_channel,a.output_json,a.output_md,a.telegram_status); print(json.dumps({'final_disposition':r['final_disposition'],'monitor_status':r['before_monitor'].get('status')},sort_keys=True)); return 0 if r['final_disposition']!='production_self_heal_failed_closed' else 2
if __name__=='__main__': raise SystemExit(main())
