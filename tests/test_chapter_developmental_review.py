from scripts.chapter_developmental_review import validate_review_payload, build_deterministic_review

def test_review_recommendation_allowlist_and_flags():
    payload=build_deterministic_review({'manuscript_quality_passed':True},{'evidence_safety_passed':True}, '# Chapter\n\nProse')
    assert validate_review_payload(payload)['ok'] is True
    payload['recommendation']='manual_approval_required'
    assert validate_review_payload(payload)['ok'] is False

def test_gpt_review_cannot_authorize_publication_flags():
    payload=build_deterministic_review({'manuscript_quality_passed':True},{'evidence_safety_passed':True}, '# Chapter\n\nProse')
    payload['safety_flags']['publication_approved']=True
    assert validate_review_payload(payload)['ok'] is False
