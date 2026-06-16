import importlib.util,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def load(n):
    spec=importlib.util.spec_from_file_location(n,ROOT/'scripts'/f'{n}.py'); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
def test_controller_unresolved_alias_queues_retry(monkeypatch,tmp_path):
    m=load('ops_delivery_controller')
    monkeypatch.setattr(m,'discover',lambda:{'ops_alias_resolvable':False,'files_inspected':[],'available_telegram_aliases':['telegram:Marius'],'can_repair_safely':False})
    monkeypatch.setattr(m,'write_discovery',lambda *a,**k: None)
    out=tmp_path/'out.jsonl'; st=tmp_path/'state.json'; oj=tmp_path/'r.json'; om=tmp_path/'r.md'
    r=m.controller(outbox=str(out),state=str(st),output_json=str(oj),output_md=str(om))
    assert r['final_disposition']=='ops_delivery_degraded_queued'; assert r['retry_scheduled'] is True
    assert r['fallback_channel_used'] is False; assert 'Marius' not in json.dumps(r['outbox_entry'])
def test_controller_requires_ops_target():
    m=load('ops_delivery_controller'); import pytest
    with pytest.raises(ValueError): m.controller(target_channel='telegram:Marius')
def test_controller_output_has_metadata(monkeypatch,tmp_path):
    m=load('ops_delivery_controller'); monkeypatch.setattr(m,'discover',lambda:{'ops_alias_resolvable':False,'files_inspected':[]}) ; monkeypatch.setattr(m,'write_discovery',lambda *a,**k: None)
    r=m.controller(outbox=str(tmp_path/'o'),state=str(tmp_path/'s'),output_json=str(tmp_path/'r.json'),output_md=str(tmp_path/'r.md'))
    assert 'emitted_at_unix_s' in r['status_metadata']
