import json
from scripts.academic_chapter_draft import validate_draft_payload, parse_strict_json, build_report_only_draft

def test_invalid_json_fails_closed():
    result=parse_strict_json('{not json')
    assert result['failed_closed'] is True

def test_missing_safety_flags_fail_closed():
    payload={'draft_status':'manuscript_draft_created','draft_markdown':'# Title\n\nProse [1].\n\n## References\n[1] x','word_count':10}
    assert validate_draft_payload(payload)['ok'] is False

def test_internal_editorial_and_evidence_headings_fail():
    payload=build_report_only_draft({'chapter_thesis':'x','allowed_claims':[]})
    payload['draft_markdown']='# X\n\n## Current evidence status\nBullet 1 maps to supported claim.'
    assert validate_draft_payload(payload)['ok'] is False

def test_overclaim_and_weak_fallback_fail():
    payload=build_report_only_draft({'chapter_thesis':'x','allowed_claims':[]})
    payload['draft_markdown']='# X\n\nPrompt engineering is dead and loop engineering is an industry consensus. [1]\n\n## References\n[1] x'
    assert validate_draft_payload(payload)['ok'] is False
    payload=build_report_only_draft({'chapter_thesis':'x','allowed_claims':[]})
    payload['model_metadata']['weak_local_fallback_used']=True
    assert validate_draft_payload(payload)['ok'] is False
