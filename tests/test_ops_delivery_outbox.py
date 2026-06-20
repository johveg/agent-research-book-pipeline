import importlib.util,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def load():
    spec=importlib.util.spec_from_file_location('ops_delivery_outbox',ROOT/'scripts/ops_delivery_outbox.py'); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
def msg(tmp_path,text='hello'):
    md=tmp_path/'m.md'; js=tmp_path/'m.json'; md.write_text(text); js.write_text(json.dumps({'x':text})); return md,js
def test_enqueue_writes_jsonl_and_state_metadata(tmp_path):
    m=load(); md,js=msg(tmp_path); out=tmp_path/'out.jsonl'; st=tmp_path/'state.json'
    e=m.enqueue(md,js,outbox=out,state_path=st)
    assert out.exists() and st.exists(); data=json.loads(st.read_text())
    assert e['target_channel']=='AL-Hermoine-OPS'; assert data['queued_count']==1; assert e['fallback_channel_used'] is False
    assert 'emitted_at_unix_s' in e
def test_unresolved_target_queues_no_fallback(monkeypatch,tmp_path):
    m=load(); monkeypatch.setattr(m,'alias_resolves',lambda:False); md,js=msg(tmp_path); out=tmp_path/'out.jsonl'; st=tmp_path/'state.json'; att=tmp_path/'att.jsonl'
    m.enqueue(md,js,outbox=out,state_path=st); s=m.attempt_delivery(out,st,att,live=True)
    assert s['queued_count']==1; assert json.loads(out.read_text().splitlines()[0])['delivery_state']=='retry_scheduled'; assert s['fallback_channel_used'] is False
    assert 'Marius' not in out.read_text()
def test_duplicate_enqueue_idempotent(tmp_path):
    m=load(); md,js=msg(tmp_path); out=tmp_path/'out.jsonl'; st=tmp_path/'state.json'
    a=m.enqueue(md,js,outbox=out,state_path=st); b=m.enqueue(md,js,outbox=out,state_path=st)
    assert a['message_id_local']==b['message_id_local']; assert len(out.read_text().splitlines())==1
def test_delivered_requires_confirmation(tmp_path):
    m=load(); md,js=msg(tmp_path); out=tmp_path/'out.jsonl'; st=tmp_path/'state.json'; e=m.enqueue(md,js,outbox=out,state_path=st)
    import pytest
    with pytest.raises(ValueError): m.mark(e['message_id_local'],'delivered',outbox=out,state_path=st)
    s=m.mark(e['message_id_local'],'delivered',confirmation={'ok':True},outbox=out,state_path=st); assert s['delivered_count']==1
def test_secrets_refused(tmp_path):
    m=load(); md,js=msg(tmp_path,'Authorization: ' + 'Bearer ' + 'abcdef1234567890abcdef1234567890')
    import pytest
    with pytest.raises(ValueError): m.enqueue(md,js,outbox=tmp_path/'o',state_path=tmp_path/'s')
def test_validate_target_channel_and_no_fallback(tmp_path):
    m=load(); md,js=msg(tmp_path); out=tmp_path/'out.jsonl'; st=tmp_path/'state.json'; m.enqueue(md,js,outbox=out,state_path=st)
    r=m.validate(out,st); assert r['ok'] is True; assert r['state']['target_channel']=='AL-Hermoine-OPS'


def test_ops_profile_home_delivery_is_resolvable_and_delivered(monkeypatch,tmp_path):
    m=load()
    monkeypatch.setattr(m, 'alias_resolves', lambda: True)
    monkeypatch.setattr(m, 'send_via_ops_bot_home', lambda text: {'ok': True, 'message_id': 44, 'chat_type': 'private', 'bot_username': 'al_hermoine_ops_bot', 'fallback_channel_used': False})
    md,js=msg(tmp_path,'ops profile home delivery')
    out=tmp_path/'out.jsonl'; st=tmp_path/'state.json'; att=tmp_path/'att.jsonl'
    e=m.enqueue(md,js,outbox=out,state_path=st)
    s=m.attempt_delivery(out,st,att,live=True)
    assert s['delivered_count']==1
    rec=json.loads(out.read_text().splitlines()[0])
    assert rec['delivery_state']=='delivered'
    assert rec['delivery_confirmation']['bot_username']=='al_hermoine_ops_bot'
    assert rec['fallback_channel_used'] is False
    assert 'Marius' not in out.read_text()
