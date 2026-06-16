import importlib.util
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def load():
    spec=importlib.util.spec_from_file_location('production_daily_self_heal',ROOT/'scripts/production_daily_self_heal.py'); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
def test_completed_no_action(monkeypatch,tmp_path):
    m=load(); monkeypatch.setattr(m,'run_monitor',lambda *a:{'status':'production_daily_completed'}); monkeypatch.setattr(m,'ROOT',tmp_path)
    r=m.self_heal(repo=str(tmp_path),output_json='r.json',output_md='r.md',telegram_status='t.md')
    assert r['final_disposition']=='production_self_heal_not_needed'; assert r['action']=='none_completed'; assert r['fallback_channel_used'] is False
def test_missing_not_due_no_action(monkeypatch,tmp_path):
    m=load(); monkeypatch.setattr(m,'run_monitor',lambda *a:{'status':'production_daily_missing_not_due_yet'})
    r=m.self_heal(repo=str(tmp_path),output_json='r.json',output_md='r.md',telegram_status='t.md')
    assert r['final_disposition']=='production_self_heal_not_due'
def test_missing_after_due_runs_wrapper_once(monkeypatch,tmp_path):
    m=load(); calls=[]
    def mon(*a): return {'status':'production_daily_missing_after_due'} if not calls else {'status':'production_daily_completed'}
    monkeypatch.setattr(m,'run_monitor',mon)
    class P: returncode=0
    monkeypatch.setattr(m.subprocess,'run',lambda *a,**k:(calls.append(a),P())[1])
    r=m.self_heal(repo=str(tmp_path),output_json='r.json',output_md='r.md',telegram_status='t.md')
    assert r['final_disposition']=='production_self_heal_executed'; assert len(calls)==1
def test_failed_closed_no_infinite_loop(monkeypatch,tmp_path):
    m=load(); monkeypatch.setattr(m,'run_monitor',lambda *a:{'status':'production_daily_failed_closed'})
    r=m.self_heal(repo=str(tmp_path),output_json='r.json',output_md='r.md',telegram_status='t.md')
    assert r['action']=='no_infinite_retry_failed_closed'
def test_lock_prevents_overlap(monkeypatch,tmp_path):
    m=load(); m.LOCK=tmp_path/'lock'; m.LOCK.write_text('x'); monkeypatch.setattr(m,'run_monitor',lambda *a:{'status':'production_daily_missing_after_due'})
    r=m.self_heal(repo=str(tmp_path),output_json='r.json',output_md='r.md',telegram_status='t.md')
    assert r['action']=='lock_prevented_overlap'
def test_no_fallback_channel():
    m=load(); import pytest
    with pytest.raises(ValueError): m.self_heal(target_channel='telegram:Marius')
