import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN5_SOURCE = "reports/editorial/citation-pipeline-test-20260612-source-card-drafts-high-reasoning.json"
RUN5_SEMANTIC = "reports/editorial/citation-pipeline-test-20260612-semantic-object-drafts-high-reasoning.json"
DECISIONS = {"pass", "warn", "fail"}
LEGACY = {"ready_for_editor_review", "needs_revision", "blocked"}


def run_quality_gate(*args, env=None):
    full_env = os.environ.copy()
    if env:
        full_env.update(env)
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "llm_quality_gate.py"), *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        env=full_env,
    )


def db_bytes():
    p = ROOT / ".var" / "book.sqlite"
    return p.read_bytes() if p.exists() else None


def status_snapshots():
    p = ROOT / ".var" / "book.sqlite"
    con = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        return {
            "sources": [dict(r) for r in con.execute("SELECT id, quality_score, privacy_publication_status, duplicate_status FROM sources ORDER BY id LIMIT 25")],
            "claims": [dict(r) for r in con.execute("SELECT id, status, publication_decision, contradiction_status FROM claims ORDER BY id LIMIT 25")],
            "editorial_reviews": [dict(r) for r in con.execute("SELECT id, run_id, review_type, status, summary, report_path, created_at FROM editorial_reviews ORDER BY id LIMIT 25")],
        }
    finally:
        con.close()


def protected_bytes():
    paths = [
        *(ROOT / "docs" / "book").glob("*.md"),
        ROOT / "scripts" / "daily_book_worker.py",
        ROOT / "data" / "schema.sql",
    ]
    return {p.relative_to(ROOT): p.read_bytes() for p in sorted(paths)}


def make_mock_bridge(tmp_path, payload, exit_code=0, raw_stdout=None):
    p = tmp_path / "mock_quality_bridge.py"
    body = "#!/usr/bin/env python3\nimport json, sys\n"
    if raw_stdout is not None:
        body += "json.load(sys.stdin)\n"
        body += "sys.stdout.write(" + repr(raw_stdout) + ")\n"
        body += "sys.exit(" + str(exit_code) + ")\n"
    elif exit_code == 0:
        body += "req=json.load(sys.stdin)\n"
        body += "assert req.get('provider') == 'copilot'\n"
        body += "assert req.get('model') == 'gpt-5.5'\n"
        body += "print(json.dumps(" + repr(payload) + "))\n"
    else:
        body += "print(json.dumps(" + repr(payload) + "))\n"
        body += "sys.exit(" + str(exit_code) + ")\n"
    p.write_text(body, encoding="utf-8")
    p.chmod(0o755)
    return str(p)


def assert_review_shape(review):
    assert review["target_type"] in {"source_card", "semantic_object"}
    assert review["target_id"]
    assert review["source_id"]
    assert review["decision"] in DECISIONS
    assert review["legacy_decision"] in LEGACY
    assert review["downstream_eligibility"] in {"eligible_for_human_editor_review", "revise_before_editor_review", "ineligible"}
    assert review["recommended_next_stage"]
    assert isinstance(review["scores"], dict)
    assert isinstance(review["rule_results"], dict)
    assert isinstance(review["strengths"], list)
    assert isinstance(review["weaknesses"], list)
    assert isinstance(review["required_fixes"], list)
    assert isinstance(review["risk_flags"], list)
    assert review["review_summary"]
    assert review["author_allowed"] is False
    assert review["publication_approved"] is False
    assert review["advisory_only"] is True
    assert review["input_hash"]
    assert review["output_hash"]


def test_quality_gate_no_llm_structural_mode_writes_corrected_reports_and_is_safe(tmp_path):
    before_db = db_bytes()
    before_statuses = status_snapshots()
    before_protected = protected_bytes()

    result = run_quality_gate("--run-id", "latest", "--limit", "10", "--output-dir", str(tmp_path), "--no-llm")

    assert result.returncode == 0, result.stderr + result.stdout
    json_path = tmp_path / "citation-pipeline-test-20260612-quality-gate-corrected.json"
    md_path = tmp_path / "citation-pipeline-test-20260612-quality-gate-corrected.md"
    assert json_path.exists()
    assert md_path.exists()
    payload = json.loads(json_path.read_text())

    assert payload["mode"] == "quality_gate_report_only"
    assert payload["llm_used"] is False
    assert payload["quality_gate_llm_used"] is False
    assert payload["reasoning_status"] == "no_llm_structural_only"
    assert payload["provider"] == "none"
    assert payload["model"] == "none"
    assert payload["bridge"] == "none"
    assert payload["decision_vocabulary"] == ["pass", "warn", "fail"]
    assert payload["decision_mapping"] == {"ready_for_editor_review": "pass", "needs_revision": "warn", "blocked": "fail"}
    assert payload["source_cards_reviewed"] == len(payload["source_card_reviews"])
    assert payload["semantic_objects_reviewed"] == len(payload["semantic_object_reviews"])
    assert payload["source_cards_reviewed"] >= 1
    assert payload["semantic_objects_reviewed"] >= 1
    assert payload["downstream_eligible_count"] == payload["decision_counts"].get("pass", 0)
    for key in ["db_modified", "chapters_modified", "statuses_modified", "schema_modified", "daily_worker_modified", "commit_allowlist_modified"]:
        assert payload[key] is False
    assert payload["raw_or_vector_authority_used"] is False
    assert payload["narrative_packets_created"] is False
    assert payload["chapter_prose_generated"] is False
    assert payload["publication_approval_granted"] is False
    assert payload["long_source_excerpt_written"] is False

    for review in payload["source_card_reviews"] + payload["semantic_object_reviews"]:
        assert_review_shape(review)
    assert "Correction/audit" in md_path.read_text()

    assert db_bytes() == before_db
    assert status_snapshots() == before_statuses
    assert protected_bytes() == before_protected


def test_quality_gate_live_mocked_uses_gpt55_metadata_and_report_only(tmp_path):
    bridge = make_mock_bridge(tmp_path, {"reviews": [], "overall_summary": "Mock GPT reviewer returned no changes; keep preflight findings."})
    before_db = db_bytes()
    before_statuses = status_snapshots()
    before_protected = protected_bytes()

    result = run_quality_gate(
        "--run-id", "latest", "--limit", "10", "--output-dir", str(tmp_path), "--require-high-reasoning",
        env={"TEREFO_HIGH_REASONING_BRIDGE_COMMAND": bridge, "TEREFO_LLM_PROVIDER": "copilot", "TEREFO_LLM_REASONING_MODEL": "gpt-5.5"},
    )

    assert result.returncode == 0, result.stderr + result.stdout
    payload = json.loads((tmp_path / "citation-pipeline-test-20260612-quality-gate-corrected.json").read_text())
    assert payload["llm_used"] is True
    assert payload["quality_gate_llm_used"] is True
    assert payload["provider"] == "copilot"
    assert payload["model"] == "gpt-5.5"
    assert payload["bridge"] == "hermes_cli"
    assert payload["reasoning_status"] == "high_reasoning_used"
    assert payload["high_reasoning_bridge"]["ok"] is True
    assert payload["db_modified"] is False
    for review in payload["source_card_reviews"] + payload["semantic_object_reviews"]:
        assert_review_shape(review)
        assert review["reviewer_model"] == "gpt-5.5"
    assert db_bytes() == before_db
    assert status_snapshots() == before_statuses
    assert protected_bytes() == before_protected


def test_quality_gate_invalid_gpt55_json_fails_closed_no_reports_or_db_write(tmp_path):
    bridge = make_mock_bridge(tmp_path, {}, raw_stdout="not json")
    before_db = db_bytes()
    result = run_quality_gate(
        "--run-id", "latest", "--limit", "1", "--output-dir", str(tmp_path), "--require-high-reasoning",
        env={"TEREFO_HIGH_REASONING_BRIDGE_COMMAND": bridge},
    )
    assert result.returncode == 2
    assert "high-reasoning bridge failed" in result.stderr
    assert db_bytes() == before_db
    assert not (tmp_path / "citation-pipeline-test-20260612-quality-gate-corrected.json").exists()


def test_quality_gate_refuses_weak_provider_without_fallback(tmp_path):
    before_db = db_bytes()
    result = run_quality_gate(
        "--run-id", "latest", "--limit", "1", "--output-dir", str(tmp_path), "--require-high-reasoning",
        env={"TEREFO_LLM_PROVIDER": "local", "TEREFO_LLM_REASONING_MODEL": "small"},
    )
    assert result.returncode == 2
    assert "copilot" in result.stderr or "weak/local fallback refused" in result.stderr
    assert db_bytes() == before_db
    assert not (tmp_path / "citation-pipeline-test-20260612-quality-gate-corrected.json").exists()


def test_quality_gate_fail_closed_when_input_is_not_high_reasoning(tmp_path):
    bad_source = tmp_path / "source.json"
    bad_semantic = tmp_path / "semantic.json"
    bad_source.write_text(json.dumps({"run_id": "bad-run", "llm_used": False, "reasoning_status": "no_llm_structural_only", "source_cards": []}))
    bad_semantic.write_text(json.dumps({"run_id": "bad-run", "llm_used": False, "reasoning_status": "no_llm_structural_only", "semantic_objects": []}))
    before_db = db_bytes()

    result = run_quality_gate(
        "--run-id", "bad-run", "--source-card-report", str(bad_source), "--semantic-object-report", str(bad_semantic), "--output-dir", str(tmp_path / "out"), "--no-llm",
    )

    assert result.returncode == 2
    assert "high-reasoning" in result.stderr.lower()
    assert db_bytes() == before_db


def test_quality_gate_detects_schema_quality_and_linkage_issues(tmp_path):
    source = tmp_path / "source.json"
    semantic = tmp_path / "semantic.json"
    source.write_text(json.dumps({
        "run_id": "quality-test", "llm_used": True, "reasoning_status": "high_reasoning_used", "provider": "copilot", "model": "gpt-5.5",
        "source_cards": [{"card_id": "card-1", "source_id": "src_1", "run_id": "quality-test", "advisory_only": True, "llm_used": True, "confidence": "high", "recommended_use": "do_not_use", "evidence_strength": "reject", "privacy_publication_status": "human_review", "risk_flags": ["privacy_review_required"], "do_not_publish_reason": "Privacy review required.", "safe_summary": "Short summary.", "main_thesis": "Short thesis.", "card_output_hash": "hash-card"}],
    }))
    semantic.write_text(json.dumps({
        "run_id": "quality-test", "llm_used": True, "reasoning_status": "high_reasoning_used", "provider": "copilot", "model": "gpt-5.5",
        "semantic_objects": [{"semantic_object_id": "obj-1", "object_type": "interpretation", "source_id": "src_1", "source_card_id": "missing-card", "source_note_id": "note_1", "run_id": "quality-test", "text": "Short semantic text.", "advisory_only": True, "author_allowed": False, "publication_approved": False, "paraphrase_only": True, "evidence_basis": "source_card_draft", "evidence_strength": "strong", "recommended_use": "semantic_candidate", "risk_flags": [], "do_not_publish_reason": "Needs review.", "llm_used": True, "confidence": "high", "object_output_hash": "hash-object"}],
    }))

    result = run_quality_gate(
        "--run-id", "quality-test", "--source-card-report", str(source), "--semantic-object-report", str(semantic), "--output-dir", str(tmp_path / "out"), "--no-llm",
    )

    assert result.returncode == 0, result.stderr + result.stdout
    payload = json.loads((tmp_path / "out" / "quality-test-quality-gate-corrected.json").read_text())
    assert payload["decision_counts"]["fail"] >= 1
    assert payload["semantic_object_reviews"][0]["decision"] == "fail"
    assert payload["semantic_object_reviews"][0]["legacy_decision"] == "blocked"
    assert any("source_card_id not found" in issue for issue in payload["semantic_object_reviews"][0]["required_fixes"])
    assert payload["recommendation"]["next_allowed_stage"] == "revise_high_reasoning_drafts"
