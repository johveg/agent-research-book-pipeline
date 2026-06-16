import importlib.util,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def load(n):
    spec=importlib.util.spec_from_file_location(n,ROOT/'scripts'/f'{n}.py'); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
def test_marius_dm_never_accepted_as_ops(monkeypatch):
    m=load('ops_channel_autodiscovery'); monkeypatch.setattr(m,'aliases',lambda:['telegram:Marius (dm)'])
    monkeypatch.setattr(m,'INSPECT',[]); r=m.discover()
    assert r['ops_alias_resolvable'] is False; assert r['can_repair_safely'] is False; assert 'Marius' not in json.dumps(r['candidate_aliases'])
def test_safe_alias_discovery_marks_resolvable(monkeypatch):
    m=load('ops_channel_autodiscovery'); monkeypatch.setattr(m,'aliases',lambda:['telegram:AL-Hermoine-OPS'])
    monkeypatch.setattr(m,'INSPECT',[]); r=m.discover()
    assert r['ops_alias_resolvable'] is True; assert r['can_repair_safely'] is True
    assert 'emitted_at_unix_s' in r['status_metadata']
def test_no_secret_leakage_redacts_ids():
    m=load('ops_channel_autodiscovery'); red=m.redact({'chat_id':'-1001234567890','name':'OPS'})
    assert red['chat_id']=='[REDACTED]'
def test_unresolved_alias_retry_not_manual_stop(monkeypatch):
    m=load('ops_channel_autodiscovery'); monkeypatch.setattr(m,'aliases',lambda:[]); monkeypatch.setattr(m,'INSPECT',[])
    r=m.discover(); assert r['repair_action']=='no_safe_repair_candidate_do_not_invent_alias'; assert r['status_metadata']['disposition']=='ops_alias_unresolved_retry_scheduled'
