import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "closed_loop_book_publisher.py"


def load_module():
    spec = importlib.util.spec_from_file_location("publisher", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def packet(disposition="publish_packet_machine_approved", update_type="existing_chapter_delta", target="docs/book/03-openclaw.md"):
    blocked = disposition in {"safe_reports_only", "publish_packet_blocked", "needs_more_sources", "quarantine", "contradiction_review_required", "publish_daily_no_safe_promotions"}
    return {
        "publish_packet_id": "pkt_run44_test",
        "source_packet_ids": ["src_a", "src_b"],
        "input_context_ids": ["ctx_run44"],
        "target_book_area": "OpenClaw",
        "target_file_suggestion": target,
        "update_type": update_type,
        "title": "Guarded canary",
        "summary": "A machine-gated canary update.",
        "proposed_markdown_delta": "\n\n## Guarded publication canary\n\nMachine gates approved a narrowly scoped canary update with citations.\n",
        "claim_map": [{"claim": "Machine gates approved a narrowly scoped canary update.", "evidence_refs": ["ev1"]}],
        "citation_map": {"ev1": ["reports/editorial/source-report.json"]},
        "evidence_refs": ["ev1"],
        "source_quality_summary": "Two safe internal evidence references.",
        "required_caveats": ["This canary is scoped to existing evidence."],
        "forbidden_claims_checked": ["runtime dependency", "general operating environment"],
        "redteam_findings": {"approved": not blocked, "privacy_raw_leakage_risk": "low"},
        "machine_editor_findings": {"approved": not blocked, "all_claims_cited": True},
        "disposition": disposition,
        "publication_readiness": {"ready_for_dry_run_patch": not blocked, "ready_for_guarded_publication": disposition == "publish_packet_machine_approved", "blocked": blocked},
        "idempotency_key": "idem_run44_test",
        "human_in_loop_dependency_added": False,
        "raw_text_publication_allowed": False,
        "docs_book_update_applied": False,
        "publication_deployed": False,
    }


def write_packets(tmp_path, packets):
    path = tmp_path / "packets.json"
    path.write_text(json.dumps({"publish_packets": packets}, indent=2), encoding="utf-8")
    return path


def copy_book(tmp_path):
    docs = tmp_path / "docs" / "book"
    shutil.copytree(ROOT / "docs" / "book", docs)
    return docs


def test_rejects_safe_reports_only_and_no_publication_packet():
    mod = load_module()
    for disp, typ in [("safe_reports_only", "no_publication"), ("publish_daily_no_safe_promotions", "no_publication")]:
        result = mod.select_publishable_packets([packet(disp, typ)], max_packets=1)
        assert result["selected"] == []
        assert result["rejected"][0]["reason"] in {"blocked_disposition", "no_publication_update"}


def test_rejects_missing_evidence_citation_human_dependency_raw_leakage_and_unsupported_disposition():
    mod = load_module()
    cases = []
    p = packet(); p.pop("evidence_refs"); cases.append(p)
    p = packet(); p.pop("citation_map"); cases.append(p)
    p = packet(); p["human_in_loop_dependency_added"] = True; cases.append(p)
    p = packet(); p["proposed_markdown_delta"] = "RAW_CAPTURE: copied material"; cases.append(p)
    p = packet(); p["disposition"] = "publish_now"; cases.append(p)
    for p in cases:
        result = mod.select_publishable_packets([p], max_packets=1)
        assert result["selected"] == []
        assert result["rejected"], p


def test_accepts_machine_approved_and_caveat_only_with_complete_evidence():
    mod = load_module()
    for disp in ["publish_packet_machine_approved", "caveat_only_publish_packet"]:
        p = packet(disp)
        if disp == "caveat_only_publish_packet":
            p["publication_readiness"] = {"ready_for_dry_run_patch": True, "ready_for_guarded_publication": False, "blocked": False}
        result = mod.select_publishable_packets([p], max_packets=1)
        assert [x["publish_packet_id"] for x in result["selected"]] == ["pkt_run44_test"]


def test_academic_quality_gate_routes_evidence_stub_away_from_chapter_publication():
    mod = load_module()
    p = packet(update_type="evidence_stub")
    p["proposed_markdown_delta"] = "Evidence: source:abc supports claim:def. Status: supported. Source mapping follows."
    result = mod.select_publishable_packets([p], max_packets=1)
    assert result["selected"] == []
    assert result["rejected"][0]["reason"].startswith("academic_quality_gate:")


def test_dry_run_does_not_modify_docs_book(tmp_path):
    docs = copy_book(tmp_path)
    target = docs / "03-openclaw.md"
    before = target.read_text(encoding="utf-8")
    mod = load_module()
    report = mod.publish_packets([packet(target="docs/book/03-openclaw.md")], docs_root=docs, apply=False, max_packets=1, run_id="run44")
    assert report["docs_book_update_applied"] is False
    assert target.read_text(encoding="utf-8") == before


def test_apply_modifies_only_target_docs_book_file_and_writes_report(tmp_path):
    docs = copy_book(tmp_path)
    target = docs / "03-openclaw.md"
    other = docs / "02-hermes.md"
    before_other = other.read_bytes()
    out_json = tmp_path / "publication.json"
    out_md = tmp_path / "publication.md"
    res = subprocess.run([
        sys.executable, str(SCRIPT), "--publish-packets", str(write_packets(tmp_path, [packet()])),
        "--docs-root", str(docs), "--apply", "--max-packets", "1", "--run-id", "run44",
        "--output-json", str(out_json), "--output-md", str(out_md)
    ], cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
    assert res.returncode == 0, res.stderr + res.stdout
    assert "Guarded publication canary" in target.read_text(encoding="utf-8")
    assert other.read_bytes() == before_other
    report = json.loads(out_json.read_text())
    assert report["publication_applied"] is True
    assert out_md.exists()


def test_apply_refuses_more_than_max_packets(tmp_path):
    docs = copy_book(tmp_path)
    mod = load_module()
    r = mod.publish_packets([packet(), packet()], docs_root=docs, apply=True, max_packets=1, run_id="run44")
    assert r["publication_applied"] is False
    assert "max_packets_exceeded" in r["failed_checks"]


def test_daily_no_safe_promotions_status_update_can_be_applied_safely(tmp_path):
    docs = copy_book(tmp_path)
    mod = load_module()
    report = mod.apply_daily_status(docs_root=docs, run_id="citation-pipeline-test-20260612", packets_considered=3, reason="No substantive packet passed machine gates.", apply=True)
    status_file = docs / "daily-pipeline-status.md"
    assert report["daily_status_fallback_applied"] is True
    text = status_file.read_text(encoding="utf-8")
    assert "Daily pipeline status" in text
    assert "No substantive packet passed machine gates" in text
    assert "external market" not in text.lower()


def test_publisher_never_touches_protected_non_book_paths(tmp_path):
    docs = copy_book(tmp_path)
    protected = [ROOT / ".var/book.sqlite", ROOT / "data/source_registry.json", ROOT / "data/schema.sql", ROOT / "docs/research/claims.md"]
    before = {str(p): p.read_bytes() for p in protected if p.exists()}
    mod = load_module()
    mod.publish_packets([packet()], docs_root=docs, apply=True, max_packets=1, run_id="run44")
    after = {str(p): p.read_bytes() for p in protected if p.exists()}
    assert after == before
