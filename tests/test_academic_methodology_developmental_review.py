import importlib.util
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def load():
    spec=importlib.util.spec_from_file_location('academic_methodology_developmental_review',ROOT/'scripts/academic_methodology_developmental_review.py'); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
def test_review_validation_good_report_only():
    m=load(); d={'provider':'copilot','model':'gpt-5.5','bridge':'hermes_cli','weak_local_fallback_used':False,'safety_flags':m.SAFETY,'publication_consideration_recommendation':'safe_reports_only','purpose_clear':True,'boundaries_clear':True,'privacy_handling_clear':True,'automation_limits_clear':True,'overclaiming_avoided':True,'gpt55_used':True}
    r=m.validate(d); assert r['ok'] is True; assert r['publication_allowed'] is False; assert r['docs_book_update_allowed'] is False
def test_review_rejects_publication_flags_and_invalid_recommendation():
    m=load(); flags=dict(m.SAFETY); flags['publication_approved']=True
    d={'provider':'copilot','model':'gpt-5.5','bridge':'hermes_cli','weak_local_fallback_used':False,'safety_flags':flags,'publication_consideration_recommendation':'publish_now'}
    r=m.validate(d); assert r['ok'] is False; assert r['safety_flags']['publication_approved'] is False
def test_quality_gate_report_only(tmp_path):
    m=load(); q=m.quality_gate({'ok':True},{'ok':True},tmp_path/'q.json',tmp_path/'q.md')
    assert q['classification']=='methodology_update'; assert q['docs_book_update_allowed'] is False
