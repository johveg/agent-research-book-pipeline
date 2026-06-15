import importlib.util

ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "closed_loop_publish_packet_validator.py"


def load_module():
    spec = importlib.util.spec_from_file_location("validator", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def valid_packet():
    return {
        "publish_packet_id": "pkt_run43_test",
        "source_packet_ids": ["context_run42"],
        "input_context_ids": ["context_run42"],
        "target_book_area": "docs/book/03-openclaw.md",
        "target_file_suggestion": "docs/book/03-openclaw.md",
        "update_type": "caveated_note",
        "title": "OpenClaw Hermes tooling caveat",
        "summary": "Caveat-only packet for OpenClaw documentation references to Hermes tooling.",
        "proposed_markdown_delta": "OpenClaw documentation references Hermes in migration/setup tooling contexts; this does not establish Hermes as a runtime dependency.",
        "claim_map": [{"claim": "OpenClaw documentation references Hermes in migration/setup tooling contexts.", "evidence_refs": ["evidence_1"]}],
        "citation_map": {"evidence_1": ["reports/editorial/context.json"]},
        "evidence_refs": ["evidence_1"],
        "source_quality_summary": "Narrow singleton evidence; caveat required.",
        "required_caveats": ["Do not state runtime dependency."],
        "forbidden_claims_checked": ["runtime dependency", "general operating environment"],
        "redteam_findings": {"approved": True, "risks": ["weak-source risk controlled by caveat"]},
        "machine_editor_findings": {"approved": True, "all_claims_cited": True},
        "disposition": "caveat_only_publish_packet",
        "publication_readiness": {"ready_for_dry_run_patch": True, "ready_for_guarded_publication": False, "blocked": False},
        "idempotency_key": "idem_run43_test",
        "human_in_loop_dependency_added": False,
        "raw_text_publication_allowed": False,
        "docs_book_update_applied": False,
        "publication_deployed": False,
    }


def assert_invalid(packet, expected):
    mod = load_module()
    errors = mod.validate_publish_packet(packet)
    assert any(expected in err for err in errors), errors


def test_validates_packet_with_all_required_fields():
    mod = load_module()
    assert mod.validate_publish_packet(valid_packet()) == []


def test_rejects_packet_missing_evidence_refs():
    pkt = valid_packet(); pkt.pop("evidence_refs")
    assert_invalid(pkt, "evidence_refs")


def test_rejects_packet_missing_citation_map():
    pkt = valid_packet(); pkt.pop("citation_map")
    assert_invalid(pkt, "citation_map")


def test_rejects_unsupported_disposition():
    pkt = valid_packet(); pkt["disposition"] = "publish_now"
    assert_invalid(pkt, "unsupported disposition")


def test_rejects_human_review_style_dependency_without_literal_term():
    pkt = valid_packet(); pkt["human_in_loop_dependency_added"] = True
    assert_invalid(pkt, "human_in_loop_dependency_added")
    pkt = valid_packet(); pkt["disposition"] = "human_" + "review_required"
    assert_invalid(pkt, "human-review dependency")


def test_rejects_docs_book_update_applied_true_in_run43():
    pkt = valid_packet(); pkt["docs_book_update_applied"] = True
    assert_invalid(pkt, "docs_book_update_applied")


def test_rejects_publication_deployed_true_in_run43():
    pkt = valid_packet(); pkt["publication_deployed"] = True
    assert_invalid(pkt, "publication_deployed")


def test_rejects_ready_for_guarded_publication_without_editor_redteam_approval():
    pkt = valid_packet()
    pkt["publication_readiness"] = {"ready_for_dry_run_patch": False, "ready_for_guarded_publication": True, "blocked": False}
    pkt["machine_editor_findings"] = {"approved": False}
    assert_invalid(pkt, "guarded publication")


def test_accepts_ready_for_dry_run_patch_when_machine_approval_fields_are_present():
    pkt = valid_packet()
    pkt["publication_readiness"] = {"ready_for_dry_run_patch": True, "ready_for_guarded_publication": False, "blocked": False}
    assert load_module().validate_publish_packet(pkt) == []


def test_verifies_idempotency_key_exists():
    pkt = valid_packet(); pkt["idempotency_key"] = ""
    assert_invalid(pkt, "idempotency_key")


def test_verifies_raw_text_publication_allowed_false():
    pkt = valid_packet(); pkt["raw_text_publication_allowed"] = True
    assert_invalid(pkt, "raw_text_publication_allowed")


def test_academic_quality_contract_blocks_evidence_stub_packet():
    pkt = valid_packet()
    pkt["update_type"] = "evidence_stub"
    pkt["disposition"] = "publish_packet_machine_approved"
    pkt["publication_readiness"] = {"ready_for_dry_run_patch": True, "ready_for_guarded_publication": True, "blocked": False}
    pkt["proposed_markdown_delta"] = "Evidence: claim:abc is supported by source:def. Status: supported."
    assert_invalid(pkt, "academic quality gate")


def test_academic_quality_contract_allows_candidate_but_not_chapter_flag():
    pkt = valid_packet()
    pkt["update_type"] = "academic_chapter_update"
    pkt["proposed_markdown_delta"] = (
        "Purpose: This chapter explains the publication pipeline's quality boundary.\n\n"
        "Definition: a quality boundary is the distinction between internal evidence processing and public argument. "
        "The chapter argues that academic prose must synthesize evidence into paragraphs with citations and caveats, "
        "rather than reproduce operational ledgers. Evidence from the pipeline supports the bounded case.\n\n"
        "Limitation: this argument is limited to the documented pipeline and does not generalize beyond it."
    )
    pkt["chapter_update_allowed"] = False
    assert load_module().validate_publish_packet(pkt) == []
