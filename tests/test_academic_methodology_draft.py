import importlib.util
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def load():
    spec=importlib.util.spec_from_file_location('academic_methodology_draft',ROOT/'scripts/academic_methodology_draft.py'); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
def good_text():
    para='This methodology explains how evidence boundaries, source collection process, inclusion and exclusion criteria, source quality categories, claim extraction and claim status model, editorial review and safety gates, privacy and raw-capture handling, social/LinkedIn discovery-only policy, automation limits, reproducibility limits, bias and limitations, relationship between internal pipeline evidence and public book claims, what the method cannot prove, and how future chapters should use evidence are handled in a bounded report-only system. '
    return para*30
def test_validate_good_methodology_report_only():
    m=load(); d={'provider':'copilot','model':'gpt-5.5','bridge':'hermes_cli','weak_local_fallback_used':False,'safety_flags':m.SAFETY,'draft_markdown':good_text(),'gpt55_used':True}
    r=m.validate(d); assert r['ok'] is True; assert r['draft_status']=='methodology_draft_report_only_created'; assert r['publication_allowed'] is False
def test_validate_rejects_weak_fallback_and_ids():
    m=load(); d={'provider':'local','model':'x','bridge':'other','weak_local_fallback_used':True,'safety_flags':{},'draft_markdown':'claim:abc '+good_text()}
    r=m.validate(d); assert r['ok'] is False; assert 'weak_local_fallback_used_refused' in r['errors']; assert r['safety_flags']['publication_approved'] is False
