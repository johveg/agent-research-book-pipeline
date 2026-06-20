#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,os,re,subprocess,urllib.parse,urllib.request
from datetime import datetime,timezone
from pathlib import Path
from zoneinfo import ZoneInfo
ROOT=Path(__file__).resolve().parents[1]; OPS_CHANNEL='AL-Hermoine-OPS'; OPS_PROFILE_HOME=Path('/root/.hermes/profiles/ops-bot')
DEFAULT_OUTBOX=ROOT/'reports/ops/outbox/ops_delivery_outbox.jsonl'; DEFAULT_STATE=ROOT/'reports/ops/outbox/ops_delivery_outbox_state.json'; DEFAULT_ATTEMPTS=ROOT/'reports/ops/outbox/ops_delivery_attempts.jsonl'
SECRET=[
    re.compile(r'-----BEGIN [A-Z ]*PRIVATE KEY-----',re.I),
    re.compile('(?i)' + 'authorization' + r'\s*:\s*' + 'bearer' + r'\s+\S+'),
    re.compile('(?i)(' + 'api[_-]?key|' + 'password|' + 'oauth[_-]?secret|' + 'cookie' + r')\s*[=:]\s*\S+'),
    re.compile(r'\b\d{8,12}:[A-Za-z0-9_-]{30,}\b'),
]
def meta(component='ops_delivery_outbox',run_id='run54',status='ops_delivery_degraded_queued',severity='warning',disposition='ops_delivery_degraded_queued'):
    n=datetime.now(timezone.utc); o=n.astimezone(ZoneInfo('Europe/Oslo'))
    return {'emitted_at_unix_s':int(n.timestamp()),'emitted_at_unix_ms':int(n.timestamp()*1000),'emitted_at_utc_iso':n.replace(microsecond=0).isoformat().replace('+00:00','Z'),'emitted_at_oslo_iso':o.replace(microsecond=0).isoformat(),'timezone':'Europe/Oslo','component':component,'run_id':run_id,'status':status,'severity':severity,'disposition':disposition,'target_channel':OPS_CHANNEL}
def has_secret(t): return any(p.search(t or '') for p in SECRET)
def entries(outbox=DEFAULT_OUTBOX):
    p=Path(outbox); p.parent.mkdir(parents=True,exist_ok=True)
    return [] if not p.exists() else [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
def save(es,outbox=DEFAULT_OUTBOX): Path(outbox).parent.mkdir(parents=True,exist_ok=True); Path(outbox).write_text(''.join(json.dumps(e,sort_keys=True,ensure_ascii=False)+'\n' for e in es))
def state(es,state=DEFAULT_STATE):
    counts={s:sum(1 for e in es if e.get('delivery_state')==s) for s in ['queued','delivered','failed_closed_target_not_resolvable','retry_scheduled']}
    obj={'status_metadata':meta(status='outbox_state',severity='info',disposition='outbox_state'),'target_channel':OPS_CHANNEL,'queued_count':counts['queued']+counts['retry_scheduled']+counts['failed_closed_target_not_resolvable'],'delivered_count':counts['delivered'],'counts_by_state':counts,'pending_message_ids':[e['message_id_local'] for e in es if e.get('delivery_state')!='delivered'],'fallback_channel_used':False,'entry_count':len(es)}
    Path(state).parent.mkdir(parents=True,exist_ok=True); Path(state).write_text(json.dumps(obj,indent=2,sort_keys=True)+'\n'); return obj
def attempt_log(obj,attempts=DEFAULT_ATTEMPTS):
    Path(attempts).parent.mkdir(parents=True,exist_ok=True)
    with Path(attempts).open('a') as f: f.write(json.dumps(obj,sort_keys=True)+'\n')
def _profile_env(profile_home=OPS_PROFILE_HOME):
    env={}
    p=Path(profile_home)/'.env'
    if p.exists():
        for line in p.read_text(errors='ignore').splitlines():
            line=line.strip()
            if not line or line.startswith('#') or '=' not in line: continue
            k,v=line.split('=',1); env[k.strip()]=v.strip().strip('"').strip("'")
    return {**os.environ, **env}

def _telegram_api(token, method, data=None):
    url=f'https://api.telegram.org/bot{token}/{method}'
    body=urllib.parse.urlencode(data).encode() if data else None
    req=urllib.request.Request(url,data=body) if body else urllib.request.Request(url)
    with urllib.request.urlopen(req,timeout=20) as r: return json.loads(r.read().decode())

def send_via_ops_bot_home(text, profile_home=OPS_PROFILE_HOME):
    env=_profile_env(profile_home); token=env.get('TELEGRAM_BOT_TOKEN'); chat=env.get('TELEGRAM_HOME_CHANNEL') or env.get('TELEGRAM_CHAT_ID')
    if not token or not chat: return {'ok':False,'error':'ops_profile_missing_token_or_home_channel','fallback_channel_used':False}
    me=_telegram_api(token,'getMe'); sent=_telegram_api(token,'sendMessage',{'chat_id':chat,'text':text,'disable_notification':'true'})
    res=sent.get('result',{})
    return {'ok':bool(sent.get('ok')),'message_id':res.get('message_id'),'chat_type':res.get('chat',{}).get('type'),'bot_username':me.get('result',{}).get('username'),'bot_first_name':me.get('result',{}).get('first_name'),'delivery_profile':'ops-bot','delivery_target':'telegram','fallback_channel_used':False,'chat_id_redacted':'[REDACTED]'}

def alias_resolves():
    env=_profile_env();
    if env.get('TELEGRAM_BOT_TOKEN') and (env.get('TELEGRAM_HOME_CHANNEL') or env.get('TELEGRAM_CHAT_ID')):
        return True
    p=subprocess.run(['bash','-lc','hermes --profile ops-bot send --list telegram 2>/dev/null || hermes send --list telegram 2>/dev/null || true'],text=True,capture_output=True)
    return OPS_CHANNEL in (p.stdout or '')
def enqueue(message_md_path,message_json_path,component='run54_autonomy_acceleration',run_id='run54',status='safe_reports_only',severity='info',disposition='safe_reports_only',outbox=DEFAULT_OUTBOX,state_path=DEFAULT_STATE):
    md=Path(message_md_path); js=Path(message_json_path); text=(md.read_text(errors='ignore') if md.exists() else '')+'\n'+(js.read_text(errors='ignore') if js.exists() else '')
    if has_secret(text): raise ValueError('secret_pattern_detected_refusing_outbox_enqueue')
    ch=hashlib.sha256((text+OPS_CHANNEL+component+run_id+status).encode()).hexdigest(); es=entries(outbox)
    for e in es:
        if e.get('content_hash')==ch: state(es,state_path); return e
    m=meta(component,run_id,status,severity,disposition); mid='ops-'+hashlib.sha256((ch+str(m['emitted_at_unix_ms'])).encode()).hexdigest()[:16]
    e={**m,'message_id_local':mid,'created_at_unix_s':m['emitted_at_unix_s'],'created_at_unix_ms':m['emitted_at_unix_ms'],'created_at_utc_iso':m['emitted_at_utc_iso'],'created_at_oslo_iso':m['emitted_at_oslo_iso'],'message_md_path':str(md),'message_json_path':str(js),'delivery_state':'queued','attempt_count':0,'last_attempt_at_unix_s':None,'last_error':None,'fallback_channel_used':False,'content_hash':ch,'redaction_status':'secret_scan_passed_no_sensitive_values_stored'}
    es.append(e); save(es,outbox); state(es,state_path); return e
def attempt_delivery(outbox=DEFAULT_OUTBOX,state_path=DEFAULT_STATE,attempts=DEFAULT_ATTEMPTS,live=False):
    es=entries(outbox); resolvable=alias_resolves(); ids=[]
    for e in es:
        if e.get('delivery_state')=='delivered': continue
        e['attempt_count']=int(e.get('attempt_count') or 0)+1; e['last_attempt_at_unix_s']=int(datetime.now(timezone.utc).timestamp())
        if not resolvable: e['delivery_state']='retry_scheduled'; e['last_error']='failed_closed_target_not_resolvable'
        elif live:
            body='OPS status via @al_hermoine_ops_bot\n\n'+(Path(e.get('message_md_path','')).read_text(errors='ignore') if e.get('message_md_path') and Path(e.get('message_md_path')).exists() else e.get('message_id_local',''))
            conf=send_via_ops_bot_home(body)
            if conf.get('ok') and conf.get('message_id'):
                e['delivery_state']='delivered'; e['last_error']=None; e['delivery_confirmation']=conf
            else:
                e['delivery_state']='retry_scheduled'; e['last_error']=conf.get('error','ops_bot_home_delivery_failed'); e['delivery_confirmation']=conf
        else: e['delivery_state']='retry_scheduled'; e['last_error']='live_delivery_disabled'
        ids.append(e['message_id_local']); attempt_log({'message_id_local':e['message_id_local'],'alias_resolvable':resolvable,'live':live,'result_state':e['delivery_state'],'last_error':e.get('last_error'),'fallback_channel_used':False,**meta(status='ops_delivery_attempt',disposition=e['delivery_state'])},attempts)
    save(es,outbox); st=state(es,state_path); st['attempted_message_ids']=ids; st['ops_alias_resolvable']=resolvable; return st
def mark(message_id,new_state,confirmation=None,error=None,outbox=DEFAULT_OUTBOX,state_path=DEFAULT_STATE):
    es=entries(outbox); found=False
    for e in es:
        if e.get('message_id_local')==message_id:
            found=True
            if new_state=='delivered' and not confirmation: raise ValueError('delivered_requires_explicit_confirmation')
            e['delivery_state']=new_state; e['last_error']=error; e['delivery_confirmation']=confirmation
    if not found: raise KeyError(message_id)
    save(es,outbox); return state(es,state_path)
def validate(outbox=DEFAULT_OUTBOX,state_path=DEFAULT_STATE):
    es=entries(outbox); errs=[]; seen=set()
    for e in es:
        if e.get('target_channel')!=OPS_CHANNEL: errs.append('wrong_target_channel')
        if e.get('fallback_channel_used') is not False: errs.append('fallback_channel_used')
        if e.get('content_hash') in seen: errs.append('duplicate_content_hash')
        seen.add(e.get('content_hash'))
        if has_secret(json.dumps(e)): errs.append('secret_pattern_detected')
    return {'ok':not errs,'errors':sorted(set(errs)),'state':state(es,state_path)}
def main(argv=None):
    ap=argparse.ArgumentParser(); sub=ap.add_subparsers(dest='cmd',required=True)
    def common(p): p.add_argument('--outbox',default=str(DEFAULT_OUTBOX)); p.add_argument('--state',default=str(DEFAULT_STATE)); p.add_argument('--attempts',default=str(DEFAULT_ATTEMPTS))
    p=sub.add_parser('enqueue'); common(p); p.add_argument('--message-md-path',required=True); p.add_argument('--message-json-path',required=True); p.add_argument('--component',default='run54_autonomy_acceleration'); p.add_argument('--run-id',default='run54'); p.add_argument('--status',default='safe_reports_only'); p.add_argument('--severity',default='info'); p.add_argument('--disposition',default='safe_reports_only')
    for n in ['list','status','validate','attempt-delivery','flush-if-resolvable']: common(sub.add_parser(n))
    p=sub.add_parser('mark-delivered'); common(p); p.add_argument('--message-id-local',required=True); p.add_argument('--confirmation',required=True)
    p=sub.add_parser('mark-failed-closed'); common(p); p.add_argument('--message-id-local',required=True); p.add_argument('--error',default='failed_closed')
    a=ap.parse_args(argv)
    if a.cmd=='enqueue': r=enqueue(a.message_md_path,a.message_json_path,a.component,a.run_id,a.status,a.severity,a.disposition,a.outbox,a.state)
    elif a.cmd=='list': r={'entries':entries(a.outbox)}
    elif a.cmd=='status': r=state(entries(a.outbox),a.state)
    elif a.cmd=='validate': r=validate(a.outbox,a.state)
    elif a.cmd in {'attempt-delivery','flush-if-resolvable'}: r=attempt_delivery(a.outbox,a.state,a.attempts,live=True)
    elif a.cmd=='mark-delivered': r=mark(a.message_id_local,'delivered',json.loads(a.confirmation),outbox=a.outbox,state_path=a.state)
    else: r=mark(a.message_id_local,'failed_closed_target_not_resolvable',error=a.error,outbox=a.outbox,state_path=a.state)
    print(json.dumps(r,indent=2,sort_keys=True)); return 0 if r.get('ok',True) is not False else 2
if __name__=='__main__': raise SystemExit(main())
