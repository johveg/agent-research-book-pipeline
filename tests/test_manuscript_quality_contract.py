import json
from pathlib import Path
from scripts.manuscript_quality_contract import load_contract, evaluate_chapter_text, hard_safety_flags_false
ROOT=Path(__file__).resolve().parents[1]

def test_current_evidence_led_chapter_fails_manuscript_contract():
    contract=load_contract(ROOT/'config/manuscript_quality_contract.json')
    text="# 1. The Agent Loop\n\n## Current evidence status\n\n- status supported claim.\n\n## Source/claim mapping\n\nBullet 1 maps to supported claim; source tokens: [1].\n\n## Editor notes\nGenerated Author output.\n"
    result=evaluate_chapter_text(text, contract, publication_requested=True)
    assert result['manuscript_contract_passed'] is False
    assert 'forbidden_reader_facing_phrase' in result['failed_checks']
    assert result['docs_book_update_allowed'] is False

def test_narrative_chapter_with_citations_passes():
    contract=load_contract(ROOT/'config/manuscript_quality_contract.json')
    text='# 1. The Agent Loop\n\nThe central argument of this chapter is that tool-using agents should be studied as loops rather than isolated prompt responses. This framing does not make loop engineering a settled discipline; it treats the term as emerging practitioner discourse. [1]\n\n## 1.1 From Prompt to Loop\n\nA prompt-response exchange is episodic, while an agent loop connects a goal, context, action, verification, state, and reporting. The available sources support this as a useful framing for professional analysis, although the evidence remains limited. [1] [2]\n\n## 1.2 Limitations and Transition\n\nThe present source base is strongest for practitioner framing and weaker for broad field-wide adoption claims. The next chapter therefore uses this loop vocabulary cautiously.\n\n## References\n\n[1] Example source.\n[2] Example source.\n'
    result=evaluate_chapter_text(text, contract, publication_requested=True)
    assert result['manuscript_contract_passed'] is True
    assert result['publication_candidate'] is True

def test_internal_editorial_phrases_and_mapping_fail():
    contract=load_contract(ROOT/'config/manuscript_quality_contract.json')
    text='# X\n\n## Source/claim mapping\n\nBullet 1 maps to supported claim with source tokens. status supported quality A.'
    result=evaluate_chapter_text(text, contract, publication_requested=True)
    assert result['manuscript_contract_passed'] is False
    assert result['docs_book_update_allowed'] is False

def test_weak_claims_allowed_only_when_caveated():
    contract=load_contract(ROOT/'config/manuscript_quality_contract.json')
    bad='# X\n\nLoop engineering is an industry consensus and prompt engineering is dead. [1]\n\n## References\n[1] x'
    assert evaluate_chapter_text(bad, contract)['manuscript_contract_passed'] is False
    good='# X\n\nSome practitioner sources describe loop engineering as emerging discourse, but the evidence is limited and does not establish industry consensus. [1]\n\n## Limitations\nThe claim remains caveated.\n\n## References\n[1] x'
    assert evaluate_chapter_text(good, contract)['manuscript_contract_passed'] is True

def test_safety_flags_false_required():
    assert hard_safety_flags_false({k:False for k in ['author_allowed','publication_approved','eligible_for_claim_insertion','eligible_for_authoring','eligible_for_publication','chapter_update_allowed']})
    assert not hard_safety_flags_false({'author_allowed': True})
