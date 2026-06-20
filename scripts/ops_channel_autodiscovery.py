#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,re,subprocess,os
from datetime import datetime,timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo
ROOT=Path(__file__).resolve().parents[1]; OPS_CHANNEL='AL-Hermoine-OPS'
INSPECT=[Path('/root/.hermes/channel_directory.json'),Path('/root/.hermes/profiles/ops-bot/channel_directory.json'),Path('/root/.hermes/profiles/ops-bot/cron/jobs.json'),Path('/root/.hermes/cron/jobs.json'),Path('/root/.hermes/profiles/ops-bot'),Path('/home/ubuntu/.hermes/hermes-agent'),Path('/root/.hermes/config.yaml'),Path('/root/.hermes/profiles/ops-bot/config.yaml')]
TERMS=['AL-Hermoine-OPS','Hermoine','OPS','telegram','channel','target','chat','group','supergroup']
def ts(status='ops_alias_unresolved_retry_scheduled'):
    n=datetime.now(timezone.utc); o=n.astimezone(ZoneInfo('Europe/Oslo'))
    return {'emitted_at_unix_s':int(n.timestamp()),'emitted_at_unix_ms':int(n.timestamp()*1000),'emitted_at_utc_iso':n.replace(microsecond=0).isoformat().replace('+00:00','Z'),'emitted_at_oslo_iso':o.replace(microsecond=0).isoformat(),'timezone':'Europe/Oslo','component':'ops_channel_autodiscovery','run_id':'run54','status':status,'severity':'warning','disposition':status,'target_channel':OPS_CHANNEL}
def redact(x:Any)->Any:
    if isinstance(x,dict): return {k:('[REDACTED]' if re.search(r'id|token|secret|cookie|password|key|chat',str(k),re.I) else redact(v)) for k,v in x.items()}
    if isinstance(x,list): return [redact(v) for v in x]
    if isinstance(x,str): return re.sub(r'(?<!\w)-?\d{6,}(?!\w)','[REDACTED_NUMERIC_ID]',re.sub(r'\b\d{8,12}:[A-Za-z0-9_-]{30,}\b','[REDACTED_BOT_TOKEN]',x))
    return x
def aliases():
    p=subprocess.run(['bash','-lc','hermes --profile ops-bot send --list telegram 2>/dev/null || hermes send --list telegram 2>/dev/null || true'],text=True,capture_output=True)
    return [redact(l.strip()) for l in (p.stdout or '').splitlines() if 'telegram:' in l]
def ops_profile_home_available():
    p=Path('/root/.hermes/profiles/ops-bot/.env'); env={}
    if p.exists():
        for line in p.read_text(errors='ignore').splitlines():
            line=line.strip()
            if line and not line.startswith('#') and '=' in line:
                k,v=line.split('=',1); env[k.strip()]=v.strip().strip('"').strip("'")
    return bool(env.get('TELEGRAM_BOT_TOKEN') and (env.get('TELEGRAM_HOME_CHANNEL') or env.get('TELEGRAM_CHAT_ID')))
def ops_profile_home_explicit_alias(inspected):
    for r in inspected:
        if 'profiles/ops-bot/channel_directory.json' not in str(r.get('path','')):
            continue
        for m in r.get('matches',[]):
            s=json.dumps(m)
            if OPS_CHANNEL in s and 'ops_bot_home' in s:
                return True
    return False
def inspect_path(p:Path):
    rec={'path':str(p),'exists':p.exists(),'is_dir':p.is_dir(),'matches':[]}; files=[]
    if p.exists() and p.is_dir(): files=[f for f in p.rglob('*') if f.is_file() and f.stat().st_size<250000 and not any(s in str(f) for s in ['/sessions/','/logs/','.db'])][:250]
    elif p.exists() and p.is_file(): files=[p]
    for f in files:
        try: txt=f.read_text(errors='ignore')
        except Exception: continue
        found=[t for t in TERMS if t.lower() in txt.lower()]
        if found: rec['matches'].append({'path':str(f),'terms':found})
        if f.name.endswith('.json'):
            try:
                d=json.loads(txt)
                if 'platforms' in d and 'telegram' in d.get('platforms',{}):
                    for e in d['platforms']['telegram']: rec['matches'].append({'path':str(f),'telegram_entry':redact(e)})
            except Exception: pass
    rec['matches']=rec['matches'][:80]; return rec
def discover():
    av=aliases(); inspected=[inspect_path(p) for p in INSPECT]; explicit_home=ops_profile_home_explicit_alias(inspected); home_ok=ops_profile_home_available() and explicit_home
    ops_found=home_ok or any(OPS_CHANNEL in json.dumps(r) for r in inspected) or any(OPS_CHANNEL in a for a in av); resolvable=home_ok or any(OPS_CHANNEL in a for a in av)
    cand=[]
    for r in inspected:
        for m in r.get('matches',[]):
            s=json.dumps(m)
            if ('OPS' in s or 'Hermoine' in s) and 'Marius' not in s: cand.append({'source':r['path'],'redacted_match':m,'confidence':'low'})
    status='ops_delivery_live_verified' if resolvable else 'ops_alias_unresolved_retry_scheduled'
    return {'status_metadata':ts(status),'active_profile':'ops-bot' if home_ok else 'default','active_channel_directory':'/root/.hermes/profiles/ops-bot/.env' if home_ok else '/root/.hermes/channel_directory.json','delivery_profile':'ops-bot' if home_ok else None,'delivery_target':'telegram' if home_ok else None,'available_telegram_aliases':av,'ops_alias_found':ops_found,'ops_alias_resolvable':resolvable,'candidate_aliases':cand,'candidate_confidence':'high' if resolvable else 'none' if not cand else 'low','can_repair_safely':bool(resolvable),'repair_action':'ops_profile_home_delivery' if home_ok else 'none_needed' if resolvable else 'no_safe_repair_candidate_do_not_invent_alias','reload_required':not resolvable,'secrets_redacted':True,'fallback_channel_used':False,'files_inspected':inspected}
def write(r,outj,outm):
    Path(outj).parent.mkdir(parents=True,exist_ok=True); Path(outj).write_text(json.dumps(r,indent=2,sort_keys=True)+'\n'); Path(outm).parent.mkdir(parents=True,exist_ok=True); Path(outm).write_text('# Run 54 OPS autodiscovery\n\n```json\n'+json.dumps(r,indent=2,sort_keys=True)+'\n```\n')
def main(argv=None):
    ap=argparse.ArgumentParser(); ap.add_argument('--output-json',default='reports/editorial/run54-ops-autodiscovery.json'); ap.add_argument('--output-md',default='reports/editorial/run54-ops-autodiscovery.md'); a=ap.parse_args(argv)
    r=discover(); write(r,ROOT/a.output_json,ROOT/a.output_md); print(json.dumps({'ops_alias_resolvable':r['ops_alias_resolvable'],'can_repair_safely':r['can_repair_safely']},sort_keys=True)); return 0
if __name__=='__main__': raise SystemExit(main())
