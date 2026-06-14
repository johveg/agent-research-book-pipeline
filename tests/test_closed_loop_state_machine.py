import hashlib
import importlib.util
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "closed_loop_state_machine.py"
CONFIG = ROOT / "config" / "closed_loop_state_machine.json"
RUN21 = ROOT / "reports" / "editorial" / "citation-pipeline-test-20260612-packet-redteam-gate-run21.json"
DB = ROOT / ".var" / "book.sqlite"

REQUIRED_STATES = {
    "raw_discovery_signal",
    "source_card_draft",
    "semantic_object_draft",
    "source_support_reviewed",
    "corroboration_needed",
    "source_context_unclear",
    "review_note_persisted",
    "downstream_manifest_eligible",
    "caveat_only_cluster_candidate",
    "support_cluster_candidate",
    "cluster_quality_reviewed",
    "caveat_only_packet_candidate",
    "packet_redteam_reviewed",
    "draft_input_candidate",
    "author_draft_candidate",
    "draft_redteam_reviewed",
    "chapter_update_candidate",
    "safe_reports_only",
    "excluded_from_pipeline",
    "contradiction_review_required",
    "blocked_for_publication_by_policy",
}
REQUIRED_DISPOSITIONS = {
    "auto_quarantine",
    "discovery_only",
    "needs_more_sources",
    "caveat_only",
    "exclude_from_pipeline",
    "contradiction_review_required",
    "safe_reports_only",
    "eligible_for_review_note_persistence",
    "eligible_for_clustering",
    "caveat_only_cluster_candidate",
    "eligible_for_packet_candidate",
    "caveat_only_author_input_ready",
    "blocked_for_publication_by_policy",
    "source_context_unclear",
}
REQUIRED_TRANSITIONS = {
    ("source_support_reviewed", "review_note_persisted"),
    ("review_note_persisted", "downstream_manifest_eligible"),
    ("downstream_manifest_eligible", "caveat_only_cluster_candidate"),
    ("caveat_only_cluster_candidate", "caveat_only_packet_candidate"),
    ("caveat_only_packet_candidate", "draft_input_candidate"),
    ("draft_input_candidate", "author_draft_candidate"),
    ("author_draft_candidate", "draft_redteam_reviewed"),
    ("draft_redteam_reviewed", "chapter_update_candidate"),
}


def load_module():
    spec = importlib.util.spec_from_file_location("closed_loop_state_machine", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def db_counts(path: Path):
    con = sqlite3.connect(path)
    try:
        return {
            "source_notes": con.execute("SELECT COUNT(*) FROM source_notes").fetchone()[0],
            "claims": con.execute("SELECT COUNT(*) FROM claims").fetchone()[0],
            "editorial_reviews": con.execute("SELECT COUNT(*) FROM editorial_reviews").fetchone()[0],
        }
    finally:
        con.close()


def run_cli(tmp_path: Path):
    db_copy = tmp_path / "book.sqlite"
    shutil.copy2(DB, db_copy)
    out = tmp_path / "reports"
    env = os.environ.copy()
    env["TEREFO_BOOK_DB_PATH"] = str(db_copy)
    before = db_counts(db_copy)
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--run-id",
            "citation-pipeline-test-20260612",
            "--packet-redteam-report",
            str(RUN21),
            "--output-dir",
            str(out),
            "--report-suffix",
            "run22a-test",
        ],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    after = db_counts(db_copy)
    assert before == after
    payload = json.loads((out / "citation-pipeline-test-20260612-closed-loop-state-machine-run22a-test.json").read_text())
    return payload


def test_state_machine_config_loads_and_has_required_vocabulary():
    mod = load_module()
    cfg = mod.load_state_machine_config(CONFIG)
    mod.validate_state_machine_config(cfg)
    assert REQUIRED_STATES <= set(cfg["states"])
    assert REQUIRED_DISPOSITIONS <= set(cfg["automated_dispositions"])
    transitions = {(t["from_state"], t["to_state"]) for t in cfg["transitions"]}
    assert REQUIRED_TRANSITIONS <= transitions
    assert cfg["hard_invariants"]["author_allowed_until_explicit_authoring_gate"] is False
    assert cfg["hard_invariants"]["publication_approved_until_explicit_publication_gate"] is False


def test_invalid_config_fails_closed(tmp_path):
    mod = load_module()
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"states": ["packet_redteam_reviewed"], "transitions": []}))
    with pytest_raises(Exception):
        mod.validate_state_machine_config(mod.load_state_machine_config(bad))


def pytest_raises(exc_type):
    import pytest
    return pytest.raises(exc_type)


def test_transition_guards_for_early_persistence_and_manifest_steps():
    mod = load_module()
    cfg = mod.load_state_machine_config(CONFIG)
    good = {
        "advisory_only": True,
        "author_allowed": False,
        "publication_approved": False,
        "recommended_next_stage": "eligible_for_review_note_persistence",
        "support_decision": "partially_supported",
        "corroboration_decision": "partially_corroborated",
        "contradiction": False,
        "do_not_use": False,
    }
    allowed = mod.validate_transition("source_support_reviewed", "review_note_persisted", good, cfg)
    assert allowed["allowed"] is True
    bad = {**good, "author_allowed": True}
    blocked = mod.validate_transition("source_support_reviewed", "review_note_persisted", bad, cfg)
    assert blocked["allowed"] is False
    assert "author_allowed_false" in blocked["failed_guards"]

    manifest_ctx = {
        "source_note_exists": True,
        "note_type": "source_support_rereview_draft",
        "provenance_complete": True,
        "author_allowed": False,
        "publication_approved": False,
    }
    assert mod.validate_transition("review_note_persisted", "downstream_manifest_eligible", manifest_ctx, cfg)["allowed"] is True
    blocked = mod.validate_transition("review_note_persisted", "downstream_manifest_eligible", {**manifest_ctx, "provenance_complete": False}, cfg)
    assert blocked["allowed"] is False
    assert "provenance_complete" in blocked["failed_guards"]


def test_cluster_packet_and_draft_input_transitions_require_caveats_and_redteam_readiness():
    mod = load_module()
    cfg = mod.load_state_machine_config(CONFIG)
    packet_ctx = {
        "quality_gate_decision": "caveat_only_packet_candidate_ready",
        "required_caveat_exists": True,
        "do_not_say_exists": True,
        "author_allowed": False,
        "publication_approved": False,
    }
    assert mod.validate_transition("caveat_only_cluster_candidate", "caveat_only_packet_candidate", packet_ctx, cfg)["allowed"] is True
    assert mod.validate_transition("caveat_only_cluster_candidate", "caveat_only_packet_candidate", {**packet_ctx, "required_caveat_exists": False}, cfg)["allowed"] is False

    draft_ctx = {
        "redteam_decision": "caveat_only_author_input_ready",
        "author_allowed": False,
        "publication_approved": False,
        "eligible_for_authoring": False,
        "eligible_for_publication": False,
        "chapter_update_allowed": False,
    }
    allowed = mod.validate_transition("caveat_only_packet_candidate", "draft_input_candidate", draft_ctx, cfg)
    assert allowed["allowed"] is True
    assert draft_ctx["author_allowed"] is False
    assert draft_ctx["publication_approved"] is False
    for unsafe_key in ["author_allowed", "publication_approved", "eligible_for_authoring", "chapter_update_allowed"]:
        blocked = mod.validate_transition("caveat_only_packet_candidate", "draft_input_candidate", {**draft_ctx, unsafe_key: True}, cfg)
        assert blocked["allowed"] is False
        assert f"{unsafe_key}_false" in blocked["failed_guards"]


def test_context_unclear_and_contradiction_route_away_from_authoring():
    mod = load_module()
    assert mod.classify_report_object({"closed_loop_disposition": "source_context_unclear"})["current_state"] == "source_context_unclear"
    assert mod.classify_report_object({"closed_loop_disposition": "contradiction_review_required"})["current_state"] == "contradiction_review_required"


def test_current_run21_packet_allows_future_draft_input_only(tmp_path):
    payload = run_cli(tmp_path)
    assert payload["current_object_count"] == 1
    assert payload["allowed_for_future_run_count"] == 1
    assert payload["blocked_count"] == 0
    assert payload["transition_decision_counts"] == {"allowed_for_future_run": 1}
    assert payload["proposed_next_state_counts"] == {"draft_input_candidate": 1}
    item = payload["transition_manifest"][0]
    assert item["object_id"] == "packet_run20_caveat_only_cluster_4e8554045cfaf827bc68bcc5"
    assert item["current_state"] == "packet_redteam_reviewed"
    assert item["proposed_next_state"] == "draft_input_candidate"
    assert item["transition_decision"] == "allowed_for_future_run"
    assert item["allowed_future_run"] == "build_caveat_only_author_draft_input"
    assert item["author_allowed"] is False
    assert item["publication_approved"] is False
    assert item["eligible_for_authoring"] is False
    assert item["eligible_for_publication"] is False
    assert item["chapter_update_allowed"] is False


def test_report_only_cli_does_not_modify_protected_files_or_db(tmp_path):
    protected = [
        ROOT / "data" / "source_registry.json",
        ROOT / "data" / "schema.sql",
        ROOT / "scripts" / "daily_book_worker.py",
        ROOT / "docs" / "book" / "preface.md",
        ROOT / "docs" / "research" / "claims.md",
    ]
    before_hashes = {str(p): sha(p) for p in protected}
    payload = run_cli(tmp_path)
    after_hashes = {str(p): sha(p) for p in protected}
    assert before_hashes == after_hashes
    assert payload["changed_db"] is False
    assert payload["changed_source_notes"] is False
    assert payload["changed_source_registry"] is False
    assert payload["changed_raw_captures"] is False
    assert payload["changed_docs_book"] is False
    assert payload["changed_schema"] is False
    assert payload["changed_daily_worker"] is False
    assert payload["claims_inserted"] == 0
    assert payload["editorial_reviews_inserted"] == 0
    assert payload["source_status_changed"] is False
    assert payload["claim_status_changed"] is False
    assert payload["editorial_status_changed"] is False
