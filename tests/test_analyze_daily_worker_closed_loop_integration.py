import hashlib
import importlib.util
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "analyze_daily_worker_closed_loop_integration.py"
DB = ROOT / ".var" / "book.sqlite"
PROTECTED_FILES = [
    ROOT / "data" / "source_registry.json",
    ROOT / "docs" / "research" / "claims.md",
    ROOT / "data" / "schema.sql",
    ROOT / "scripts" / "daily_book_worker.py",
]
PROTECTED_DIRS = [ROOT / "raw", ROOT / "docs" / "book", ROOT / "docs" / "entities"]


def load_module():
    spec = importlib.util.spec_from_file_location("analyze_daily_worker_closed_loop_integration", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def db_counts():
    con = sqlite3.connect(DB)
    try:
        return {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ["source_notes", "claims", "editorial_reviews"]}
    finally:
        con.close()


def status_hashes():
    con = sqlite3.connect(DB)
    try:
        queries = {
            "source": "SELECT id, quality_score, privacy_publication_status, duplicate_status FROM sources ORDER BY id",
            "claim": "SELECT id, status, publication_decision, contradiction_status FROM claims ORDER BY id",
            "editorial": "SELECT id, run_id, review_type, status, summary, report_path, created_at FROM editorial_reviews ORDER BY id",
        }
        out = {}
        for name, sql in queries.items():
            out[name] = hashlib.sha256(json.dumps(con.execute(sql).fetchall(), sort_keys=True, default=str).encode()).hexdigest()
        return out
    finally:
        con.close()


def file_hash(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def tree_hash(path: Path):
    if not path.exists():
        return None
    files = {}
    for item in sorted(p for p in path.rglob("*") if p.is_file()):
        files[str(item.relative_to(path))] = file_hash(item)
    return hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()


def protected_snapshot():
    return {
        "files": {str(p.relative_to(ROOT)): file_hash(p) for p in PROTECTED_FILES},
        "dirs": {str(p.relative_to(ROOT)): tree_hash(p) for p in PROTECTED_DIRS},
        "db_bytes": file_hash(DB),
        "db_counts": db_counts(),
        "status_hashes": status_hashes(),
    }


def test_build_report_inspects_required_files_and_maps_risks():
    mod = load_module()
    report = mod.build_report(
        run_id="citation-pipeline-test-20260612",
        daily_worker=ROOT / "scripts" / "daily_book_worker.py",
        state_machine_config=ROOT / "config" / "closed_loop_state_machine.json",
        transition_engine=ROOT / "scripts" / "closed_loop_transition_engine.py",
        mutation_guard=ROOT / "scripts" / "protected_mutation_guard.py",
    )
    inspected = set(report["inspected_files"])
    assert "scripts/daily_book_worker.py" in inspected
    assert "scripts/closed_loop_transition_engine.py" in inspected
    assert "scripts/protected_mutation_guard.py" in inspected
    assert "config/closed_loop_state_machine.json" in inspected
    assert "config/reasoning_models.json" in inspected
    assert "scripts/update_closed_loop_promotion_contract.py" in inspected
    assert "scripts/verify_book_workspace.py" in inspected
    assert "scripts/verify_editorial_roles.py" in inspected
    assert "scripts/verify_book_citations.py" in inspected
    assert report["daily_worker_write_surfaces"]
    assert report["db_mutation_risk_map"]
    assert report["protected_paths_risk_map"]


def test_report_recommends_integration_points_and_verification_profiles():
    mod = load_module()
    report = mod.build_report(
        run_id="citation-pipeline-test-20260612",
        daily_worker=ROOT / "scripts" / "daily_book_worker.py",
        state_machine_config=ROOT / "config" / "closed_loop_state_machine.json",
        transition_engine=ROOT / "scripts" / "closed_loop_transition_engine.py",
        mutation_guard=ROOT / "scripts" / "protected_mutation_guard.py",
    )
    assert report["state_machine_integration_points"]
    assert report["transition_engine_integration_points"]
    assert report["mutation_guard_integration_points"]
    profiles = report["recommended_verification_profiles"]
    assert profiles["report_only_daily_runs"] == "report_only"
    assert profiles["config_only_contract_updates"] == "config_only"
    assert profiles["control_plane_code_changes"] == "control_plane_code_only"
    assert profiles["future_source_note_writes"] == "db_write_source_notes_only"
    assert profiles["future_docs_book_updates"] == "docs_book_write"
    assert profiles["future_publication"] == "full_publication_gate"


def test_safety_flags_and_no_human_dependency_are_fail_closed_false():
    mod = load_module()
    report = mod.build_report(
        run_id="citation-pipeline-test-20260612",
        daily_worker=ROOT / "scripts" / "daily_book_worker.py",
        state_machine_config=ROOT / "config" / "closed_loop_state_machine.json",
        transition_engine=ROOT / "scripts" / "closed_loop_transition_engine.py",
        mutation_guard=ROOT / "scripts" / "protected_mutation_guard.py",
    )
    assert report["report_only"] is True
    assert report["llm_used"] is False
    assert report["changed_daily_worker"] is False
    assert report["changed_db"] is False
    assert report["changed_docs_book"] is False
    assert report["human_in_loop_dependency_added"] is False
    flags = report["safety_flags"]
    assert flags["author_allowed"] is False
    assert flags["publication_approved"] is False
    assert flags["eligible_for_claim_insertion"] is False
    assert flags["eligible_for_authoring"] is False
    assert flags["eligible_for_publication"] is False
    assert flags["chapter_update_allowed"] is False
    assert "human_review_required" not in json.dumps(report).lower()


def test_cli_writes_expected_reports_and_does_not_modify_protected_state(tmp_path):
    before = protected_snapshot()
    cmd = [
        sys.executable,
        str(SCRIPT),
        "--run-id",
        "citation-pipeline-test-20260612",
        "--daily-worker",
        "scripts/daily_book_worker.py",
        "--state-machine-config",
        "config/closed_loop_state_machine.json",
        "--transition-engine",
        "scripts/closed_loop_transition_engine.py",
        "--mutation-guard",
        "scripts/protected_mutation_guard.py",
        "--output-dir",
        str(tmp_path),
        "--report-suffix",
        "run36",
    ]
    res = subprocess.run(cmd, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=180)
    assert res.returncode == 0, res.stderr + res.stdout
    json_path = tmp_path / "citation-pipeline-test-20260612-daily-worker-closed-loop-preflight-run36.json"
    md_path = tmp_path / "citation-pipeline-test-20260612-daily-worker-closed-loop-preflight-run36.md"
    assert json_path.exists()
    assert md_path.exists()
    report = json.loads(json_path.read_text())
    assert report["changed_source_notes"] is False
    assert report["claims_inserted"] == 0
    assert report["editorial_reviews_inserted"] == 0
    assert report["source_status_changed"] is False
    assert report["claim_status_changed"] is False
    assert report["editorial_status_changed"] is False
    assert report["changed_source_registry"] is False
    assert report["changed_raw_captures"] is False
    assert report["changed_docs_book"] is False
    assert report["changed_schema"] is False
    assert report["changed_daily_worker"] is False
    assert protected_snapshot() == before
