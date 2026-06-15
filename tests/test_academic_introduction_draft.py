import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "academic_introduction_draft.py"


def load_module():
    spec = importlib.util.spec_from_file_location("academic_introduction_draft", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def valid_packet(tmp_path: Path) -> Path:
    p = tmp_path / "packet.json"
    p.write_text(json.dumps({
        "ok": True,
        "proposed_working_title": "Engineering Governable Agent Loops",
        "proposed_audience": ["engineers", "technical leaders"],
        "proposed_thesis_candidates": ["Agent loops should be treated as governable engineering systems rather than isolated prompts."],
        "proposed_contribution_candidates": ["A bounded framework for discussing loop engineering as an emerging practitioner label."],
        "scope_statement_candidates": ["The book examines practitioner observations, local case material, and supported claims."],
        "exclusion_candidates": ["It does not claim field consensus."],
        "limitation_candidates": ["The evidence base is incomplete and literature support remains necessary."],
        "publication_safety_flags": {
            "author_allowed": False,
            "publication_approved": False,
            "eligible_for_claim_insertion": False,
            "eligible_for_authoring": False,
            "eligible_for_publication": False,
            "chapter_update_allowed": False,
        },
    }), encoding="utf-8")
    return p


def valid_contract(tmp_path: Path) -> Path:
    p = tmp_path / "contract.json"
    p.write_text(json.dumps({"hard_safety_flags": {
        "author_allowed": False,
        "publication_approved": False,
        "eligible_for_claim_insertion": False,
        "eligible_for_authoring": False,
        "eligible_for_publication": False,
        "chapter_update_allowed": False,
    }}), encoding="utf-8")
    return p


def valid_draft(word_count=1300):
    prose = " ".join(["This chapter argues that agent loops are emerging practitioner systems requiring governable engineering treatment, while the evidence remains bounded and incomplete."] * (word_count // 18 + 1))
    return {
        "run_id": "run50",
        "title": "Draft Introduction",
        "draft_type": "report_only_introduction_draft",
        "draft_status": "introduction_draft_created",
        "gpt55_used": True,
        "provider": "copilot",
        "model": "gpt-5.5",
        "bridge": "hermes_cli",
        "reasoning_profile": "closed_loop_editorial",
        "weak_local_fallback_used": False,
        "introduction_title": "Engineering Governable Agent Loops",
        "target_audience": "Engineers and technical leaders",
        "central_thesis": "Agent loops should be treated as governable engineering systems rather than isolated prompts.",
        "problem_statement": "Current practice often lacks bounded language for engineering and governing agent loops.",
        "contribution_statement": "The draft offers a cautious framework for inquiry and professional practice.",
        "scope_statement": "The scope is practitioner observation, local case material, and supported claims.",
        "exclusions": ["No field consensus claim"],
        "evidence_basis": "Existing manuscript pages and report-only inventory.",
        "limitations": ["Literature and methodology support remain incomplete."],
        "how_to_read_this_book": "Read as a staged argument with caveats.",
        "draft_markdown": prose,
        "chapter_outline": ["Purpose", "Thesis", "Scope"],
        "key_terms_to_define": ["agent loop", "loop engineering"],
        "literature_support_needed": ["software engineering governance"],
        "methodology_support_needed": ["case selection"],
        "claims_not_made": ["Loop engineering is not claimed as an established discipline."],
        "caveats": ["Do not overgeneralize."],
        "do_not_publish_reasons": ["Report-only Run 50 draft."],
        "recommended_next_stage": "Run 51 guarded revision/publication consideration.",
        "safety_flags": {
            "advisory_only": True,
            "draft_only": True,
            "report_only": True,
            "author_allowed": False,
            "publication_approved": False,
            "eligible_for_claim_insertion": False,
            "eligible_for_authoring": False,
            "eligible_for_publication": False,
            "chapter_update_allowed": False,
        },
    }


def test_validate_draft_accepts_valid_strict_json():
    mod = load_module()
    result = mod.validate_draft_payload(valid_draft())
    assert result["draft_status"] == "introduction_draft_created"
    assert result["safety_flags"]["publication_approved"] is False


def test_invalid_json_and_missing_safety_flags_fail_closed():
    mod = load_module()
    for raw in ["not json", json.dumps({"draft_markdown": "short"})]:
        result = mod.parse_and_validate_gpt_output(raw)
        assert result["ok"] is False
        assert result["draft_status"] == "introduction_draft_failed_closed"


def test_true_publication_flag_fails_closed():
    mod = load_module()
    bad = valid_draft()
    bad["safety_flags"]["publication_approved"] = True
    result = mod.parse_and_validate_gpt_output(json.dumps(bad))
    assert result["ok"] is False
    assert "publication_approved" in " ".join(result["errors"])


def test_draft_quality_failures():
    mod = load_module()
    cases = [
        (dict(valid_draft(), draft_markdown="too short"), "draft_word_count_out_of_bounds"),
        (dict(valid_draft(), draft_markdown=("claim_abc " * 1300)), "claim_or_source_id_in_draft"),
        (dict(valid_draft(), draft_markdown=("Author role " * 1300)), "internal_workflow_language_in_draft"),
        (dict(valid_draft(), draft_markdown=("This book proves loop engineering is an established discipline. " * 250)), "overclaiming_pattern"),
        (dict(valid_draft(), draft_markdown=("According to Smith (2024), cautious bounded discussion continues. " * 250)), "invented_citation_marker"),
    ]
    for payload, expected in cases:
        result = mod.parse_and_validate_gpt_output(json.dumps(payload))
        assert result["ok"] is False
        assert any(expected in e for e in result["errors"])


def test_weak_local_fallback_refused():
    mod = load_module()
    payload = valid_draft()
    payload["weak_local_fallback_used"] = True
    result = mod.parse_and_validate_gpt_output(json.dumps(payload))
    assert result["ok"] is False
    assert any("weak_local_fallback" in e for e in result["errors"])


def test_cli_missing_gpt_fails_closed_without_writing_book(tmp_path):
    packet = valid_packet(tmp_path)
    contract = valid_contract(tmp_path)
    out_json = tmp_path / "draft.json"
    out_md = tmp_path / "draft.md"
    proc = subprocess.run([
        sys.executable, str(SCRIPT),
        "--input-packet", str(packet),
        "--quality-contract", str(contract),
        "--output-json", str(out_json),
        "--output-md", str(out_md),
        "--bridge-script", str(tmp_path / "missing_bridge.py"),
    ], text=True, capture_output=True)
    assert proc.returncode == 2
    data = json.loads(out_json.read_text(encoding="utf-8"))
    assert data["draft_status"] == "introduction_draft_failed_closed"
    assert data["weak_local_fallback_used"] is False
