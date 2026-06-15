import copy
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "academic_book_quality_gate.py"
CONTRACT = ROOT / "config" / "academic_book_quality_contract.json"


def load_module():
    spec = importlib.util.spec_from_file_location("academic_book_quality_gate", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def packet(**updates):
    base = {
        "publish_packet_id": "pkt_quality_test",
        "target_file_suggestion": "docs/book/03-openclaw.md",
        "target_book_area": "OpenClaw",
        "update_type": "academic_chapter_update",
        "title": "OpenClaw as a closed-loop case",
        "summary": "Academic chapter candidate with thesis, definitions, argument, evidence, and limitations.",
        "proposed_markdown_delta": (
            "Purpose: This chapter explains why closed-loop publication systems require a separation between operational evidence and reader-facing argument.\n\n"
            "Definition: A closed-loop publication system is an automated pipeline that collects evidence, evaluates machine-readable claims, and applies only validated narrative changes. "
            "The central argument is that such systems become professionally useful only when evidence processing is translated into sustained explanatory prose rather than exposed as a ledger. "
            "The evidence indicates that OpenClaw and Hermes can be treated as a bounded case of tooling-mediated publication operations, with citations retained in internal reports and limitations stated in the chapter.\n\n"
            "Limitation: This discussion is limited to the documented tooling context and does not claim general runtime dependency or universal applicability."
        ),
        "claim_map": [{"claim": "Closed-loop publication systems require separation between evidence operations and reader-facing argument.", "evidence_refs": ["evidence_1"]}],
        "citation_map": {"evidence_1": ["reports/editorial/context.json"]},
        "evidence_refs": ["evidence_1"],
        "source_quality_summary": "Corroborated internal reports and public project context; limitations retained.",
        "required_caveats": ["Do not generalize beyond documented tooling context."],
        "forbidden_claims_checked": ["runtime dependency", "general operating environment"],
        "redteam_findings": {"approved": True},
        "machine_editor_findings": {"approved": True},
        "disposition": "publish_packet_machine_approved",
        "publication_readiness": {"ready_for_dry_run_patch": True, "ready_for_guarded_publication": True, "blocked": False},
        "idempotency_key": "idem_quality_test",
        "human_in_loop_dependency_added": False,
        "raw_text_publication_allowed": False,
        "docs_book_update_applied": False,
        "publication_deployed": False,
    }
    base.update(updates)
    return base


def evaluate(pkt):
    mod = load_module()
    return mod.evaluate_update(pkt, mod.load_contract(CONTRACT))


def test_evidence_stub_is_blocked_from_reader_facing_chapter():
    pkt = packet(
        update_type="evidence_stub",
        proposed_markdown_delta="Evidence: source:abc supports claim:xyz. Status: supported. See source mapping below.",
    )
    result = evaluate(pkt)
    assert result["decision"] == "blocked_evidence_stub_not_chapter_prose"
    assert result["academic_book_update_allowed"] is False
    assert result["safe_reports_only"] is True


def test_claim_source_id_heavy_text_is_blocked_from_main_chapter():
    pkt = packet(proposed_markdown_delta="claim:abc is supported by source:def and raw_capture_123. This is supported.")
    result = evaluate(pkt)
    assert result["academic_book_update_allowed"] is False
    assert "raw_or_internal_id_in_main_prose" in result["failed_checks"]


def test_internal_workflow_editorial_status_prose_is_blocked():
    pkt = packet(proposed_markdown_delta="Editor note: Author should update this chapter. Changelog: workflow status was weakly_supported and needs_review.")
    result = evaluate(pkt)
    assert result["decision"] == "blocked_evidence_stub_not_chapter_prose"
    assert "internal_editorial_or_workflow_language" in result["failed_checks"]


def test_social_discovery_only_evidence_is_blocked_from_academic_claims():
    pkt = packet(source_quality_summary="social signal only from discovery feed without corroboration", proposed_markdown_delta="Purpose: This chapter argues from a LinkedIn post. Definition: a signal is a post. The argument relies on this discovery-only evidence. Limitation: it may be weak.")
    result = evaluate(pkt)
    assert result["decision"] == "blocked_needs_literature_support"
    assert result["academic_book_update_allowed"] is False


def test_proper_academic_chapter_candidate_can_pass_as_candidate_only():
    result = evaluate(packet())
    assert result["decision"] == "academic_book_update_allowed"
    assert result["academic_book_update_allowed"] is True
    assert result["chapter_update_allowed"] is False
    for flag in ["author_allowed", "publication_approved", "eligible_for_claim_insertion", "eligible_for_authoring", "eligible_for_publication"]:
        assert result[flag] is False


def test_appendix_evidence_update_routes_appendix_only():
    result = evaluate(packet(update_type="appendix_evidence_update", target_file_suggestion="docs/book/source-quality-appendix.md"))
    assert result["decision"] == "appendix_only_allowed"
    assert result["appendix_only_allowed"] is True
    assert result["academic_book_update_allowed"] is False


def test_missing_config_and_missing_input_fail_closed(tmp_path):
    proc = subprocess.run([sys.executable, str(SCRIPT), "--input", str(tmp_path / "missing.json"), "--contract", str(CONTRACT), "--output-json", str(tmp_path / "out.json"), "--output-md", str(tmp_path / "out.md")], text=True, capture_output=True)
    assert proc.returncode == 2
    payload = json.loads((tmp_path / "out.json").read_text())
    assert payload["decision"] == "safe_reports_only"
    assert payload["safe_reports_only"] is True

    p = tmp_path / "packet.json"
    p.write_text(json.dumps(packet()))
    proc = subprocess.run([sys.executable, str(SCRIPT), "--input", str(p), "--contract", str(tmp_path / "missing_contract.json"), "--output-json", str(tmp_path / "out2.json"), "--output-md", str(tmp_path / "out2.md")], text=True, capture_output=True)
    assert proc.returncode == 2
    assert json.loads((tmp_path / "out2.json").read_text())["failed_closed"] is True


def test_report_only_execution_does_not_modify_protected_paths(tmp_path):
    pkt_path = tmp_path / "packet.json"
    out_json = tmp_path / "quality.json"
    out_md = tmp_path / "quality.md"
    pkt_path.write_text(json.dumps({"publish_packets": [packet()]}))
    protected = [ROOT / ".var/book.sqlite", ROOT / "data/source_registry.json", ROOT / "data/schema.sql", ROOT / "scripts/daily_book_worker.py"]
    before = {str(p): p.read_bytes() if p.exists() else b"" for p in protected}
    docs_before = {p: p.read_bytes() for p in (ROOT / "docs" / "book").glob("*.md")}
    raw_before = sorted(str(p.relative_to(ROOT)) for p in (ROOT / "raw").rglob("*") if p.is_file()) if (ROOT / "raw").exists() else []

    proc = subprocess.run([sys.executable, str(SCRIPT), "--input", str(pkt_path), "--contract", str(CONTRACT), "--output-json", str(out_json), "--output-md", str(out_md)], text=True, capture_output=True, cwd=ROOT)

    assert proc.returncode == 0
    assert out_json.exists() and out_md.exists()
    assert {str(p): p.read_bytes() if p.exists() else b"" for p in protected} == before
    assert {p: p.read_bytes() for p in (ROOT / "docs" / "book").glob("*.md")} == docs_before
    raw_after = sorted(str(p.relative_to(ROOT)) for p in (ROOT / "raw").rglob("*") if p.is_file()) if (ROOT / "raw").exists() else []
    assert raw_after == raw_before
