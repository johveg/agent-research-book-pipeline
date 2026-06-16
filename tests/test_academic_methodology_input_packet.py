import importlib.util,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def load(n):
    spec=importlib.util.spec_from_file_location(n,ROOT/'scripts'/f'{n}.py'); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
def test_methodology_input_packet_missing_inputs_fail_closed(monkeypatch,tmp_path):
    m=load('academic_methodology_input_packet'); monkeypatch.setattr(m,'ROOT',tmp_path)
    r=m.build_packet(); assert r['ok'] is False and r['safety_flags']['publication_approved'] is False
def test_methodology_input_packet_existing_inputs_report_only():
    m=load('academic_methodology_input_packet'); r=m.build_packet()
    assert r['ok'] is True; assert r['provider']=='copilot' and r['model']=='gpt-5.5'; assert r['weak_local_fallback'] is False
    assert r['publication_allowed'] is False and r['docs_book_update_allowed'] is False
