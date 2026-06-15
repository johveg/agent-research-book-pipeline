import hashlib
import importlib.util
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "scheduler_wrapper_contract.py"
DB = ROOT / ".var" / "book.sqlite"
PRELIGHT = ROOT / "reports" / "editorial" / "citation-pipeline-test-20260612-daily-worker-closed-loop-preflight-run36.json"

PROTECTED_FILES = [
    ROOT / "data" / "source_registry.json",
    ROOT / "docs" / "research" / "claims.md",
    ROOT / "data" / "schema.sql",
    ROOT / "scripts" / "daily_book_worker.py",
]
PROTECTED_DIRS = [ROOT / "raw", ROOT / "docs" / "book", ROOT / "docs" / "entities"]


def load_module():
    spec = importlib.util.spec_from_file_location("scheduler_wrapper_contract", SCRIPT)
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


def test_profile_mapping_and_future_fail_closed_modes():
    mod = load_module()
    assert mod.select_verification_profile("report_only_daily", "safe_reports_only")["profile"] == "report_only"
    assert mod.select_verification_profile("config_update", "config_only")["profile"] == "config_only"
    assert mod.select_verification_profile("control_plane_code", "control_plane_code_only")["profile"] == "control_plane_code_only"

    source = mod.select_verification_profile("source_note_write", "caveat_only")
    assert source["profile"] == "db_write_source_notes_only"
    assert source["ok"] is False
    assert source["future_disabled"] is True

    for mode in ["claim_write", "docs_book_write", "publication", "unknown"]:
        result = mod.select_verification_profile(mode, "safe_reports_only")
        assert result["ok"] is False
        assert result["profile"] is None
        assert result["fail_closed"] is True

    assert mod.select_verification_profile("report_only_daily", "unknown")["ok"] is False


def test_daily_worker_command_contract_is_safe_and_execution_disabled_by_default():
    mod = load_module()
    contract = mod.build_daily_worker_command_contract(
        run_id="citation-pipeline-test-20260612",
        daily_worker=ROOT / "scripts" / "daily_book_worker.py",
        execute_safe_command=False,
    )
    argv = contract["argv"]
    assert "--no-commit" in argv
    assert "--skip-capture" in argv
    assert "--allow-chapter-updates" not in argv
    assert contract["execution_enabled"] is False
    assert contract["blocks_capture"] is True
    assert contract["blocks_commit"] is True
    assert contract["blocks_push"] is True
    assert contract["blocks_docs_book_mutation"] is True
    assert contract["blocks_source_registry_mutation"] is True
    assert contract["would_execute"] is False


def test_report_only_daily_no_write_capability_gate_blocks_current_worker():
    mod = load_module()
    contract = mod.build_daily_worker_command_contract(
        run_id="citation-pipeline-test-20260612",
        daily_worker=ROOT / "scripts" / "daily_book_worker.py",
        execute_safe_command=False,
    )
    analysis = mod.analyze_daily_worker_no_write_capabilities(
        mode="report_only_daily",
        selected_profile="report_only",
        command_contract=contract,
        preflight_report=mod.load_json(PRELIGHT),
    )
    assert analysis["execution_allowed"] is False
    assert analysis["execution_capability_decision"] == "blocked_missing_no_write_capabilities"
    assert analysis["required_no_write_capabilities"] == mod.required_no_write_capabilities_for_mode("report_only_daily")
    assert "disable_capture" in analysis["supported_no_write_capabilities"]
    assert "disable_commit" in analysis["supported_no_write_capabilities"]
    assert "disable_push" in analysis["supported_no_write_capabilities"]
    assert "disable_vector_index_build" in analysis["supported_no_write_capabilities"]
    assert "disable_docs_book_update" in analysis["supported_no_write_capabilities"]
    for missing in [
        "disable_entity_extraction",
        "disable_claim_extraction",
        "disable_docs_entities_update",
        "disable_docs_research_claims_update",
        "disable_source_registry_export",
        "disable_run_table_db_write_or_classify",
    ]:
        assert missing in analysis["missing_no_write_capabilities"]
        assert f"missing_no_write_capability:{missing}" in analysis["execution_block_reasons"]
    assert analysis["daily_worker_supported_no_write_flags"] == ["--no-commit", "--skip-capture", "--skip-vector"]
    assert analysis["daily_worker_missing_no_write_flags"]
    assert analysis["daily_worker_write_surfaces_from_preflight"]


def test_build_report_embeds_no_write_capability_gate_and_blocks_execution():
    mod = load_module()
    report = mod.build_report(
        run_id="citation-pipeline-test-20260612",
        daily_worker=ROOT / "scripts" / "daily_book_worker.py",
        state_machine_config=ROOT / "config" / "closed_loop_state_machine.json",
        transition_engine=ROOT / "scripts" / "closed_loop_transition_engine.py",
        mutation_guard=ROOT / "scripts" / "protected_mutation_guard.py",
        daily_worker_preflight=PRELIGHT,
        mode="report_only_daily",
        disposition="safe_reports_only",
        output_dir=ROOT / "reports" / "editorial",
        report_suffix="run39",
        dry_run=True,
        execute_safe_command=False,
    )
    assert report["execution_allowed"] is False
    assert report["execution_performed"] is False
    assert report["execution_capability_decision"] == "blocked_missing_no_write_capabilities"
    assert report["execution_block_reasons"]
    assert report["missing_no_write_capabilities"]
    assert report["supported_no_write_capabilities"]
    assert report["required_no_write_capabilities"] == mod.required_no_write_capabilities_for_mode("report_only_daily")
    assert report["daily_worker_command_contract"]["execution_enabled"] is False
    assert report["daily_worker_command_contract"]["would_execute"] is False
    assert report["human_in_loop_dependency_added"] is False
    assert report["safety_flags"]["author_allowed"] is False
    assert report["safety_flags"]["publication_approved"] is False
    assert report["safety_flags"]["chapter_update_allowed"] is False


def test_run39_report_naming_uses_scheduler_no_write_capability(tmp_path):
    mod = load_module()
    report = mod.build_report(
        run_id="citation-pipeline-test-20260612",
        daily_worker=ROOT / "scripts" / "daily_book_worker.py",
        state_machine_config=ROOT / "config" / "closed_loop_state_machine.json",
        transition_engine=ROOT / "scripts" / "closed_loop_transition_engine.py",
        mutation_guard=ROOT / "scripts" / "protected_mutation_guard.py",
        daily_worker_preflight=PRELIGHT,
        mode="report_only_daily",
        disposition="safe_reports_only",
        output_dir=tmp_path,
        report_suffix="run39",
        dry_run=True,
    )
    paths = mod.write_reports(report, tmp_path, "run39")
    assert paths["json"].endswith("citation-pipeline-test-20260612-scheduler-no-write-capability-run39.json")
    assert paths["markdown"].endswith("citation-pipeline-test-20260612-scheduler-no-write-capability-run39.md")
    assert (tmp_path / "citation-pipeline-test-20260612-scheduler-no-write-capability-run39.json").exists()


def test_commit_and_push_are_blocked_by_guard_diff_secrets_deltas_and_hard_flags():
    mod = load_module()
    ok_guard = {
        "ok": True,
        "unexpected_changed_paths": [],
        "db_delta": {},
        "status_hash_delta": {},
        "docs_book_changed": False,
        "human_in_loop_dependency_added": False,
        "hard_flags_changed": {
            "author_allowed": False,
            "publication_approved": False,
            "chapter_update_allowed": False,
        },
    }
    policy = mod.evaluate_commit_push_policy(ok_guard, selected_profile="report_only")
    assert policy["commit_allowed"] is False
    assert policy["push_allowed"] is False
    assert "report_only_contract_blocks_commit" in policy["commit_block_reasons"]

    cases = [
        ({**ok_guard, "ok": False}, "mutation_guard_failed"),
        ({**ok_guard, "unexpected_changed_paths": ["docs/book/x.md"]}, "unexpected_protected_or_scope_changes"),
        ({**ok_guard, "db_delta": {"claims": {"before": 1, "after": 2}}}, "db_delta_outside_selected_profile"),
        ({**ok_guard, "status_hash_delta": {"claim": {"before": "a", "after": "b"}}}, "status_hash_delta_outside_selected_profile"),
        ({**ok_guard, "docs_book_changed": True}, "docs_book_changed_under_non_publication_profile"),
        ({**ok_guard, "human_in_loop_dependency_added": True}, "human_in_loop_dependency_added"),
        ({**ok_guard, "hard_flags_changed": {"author_allowed": True}}, "hard_flag_true"),
    ]
    for guard, reason in cases:
        p = mod.evaluate_commit_push_policy(guard, selected_profile="report_only")
        assert p["commit_allowed"] is False
        assert p["push_allowed"] is False
        assert reason in p["commit_block_reasons"]
        assert reason in p["push_block_reasons"]

    p = mod.evaluate_commit_push_policy(ok_guard, selected_profile="report_only", git_diff_check_ok=False)
    assert "git_diff_check_failed" in p["commit_block_reasons"]
    assert "git_diff_check_failed" in p["push_block_reasons"]
    p = mod.evaluate_commit_push_policy(ok_guard, selected_profile="report_only", secrets_detected=True)
    assert "secrets_detected" in p["commit_block_reasons"]
    assert "secrets_detected" in p["push_block_reasons"]


def test_build_report_contains_required_report_only_fields_and_blocks_writes():
    mod = load_module()
    report = mod.build_report(
        run_id="citation-pipeline-test-20260612",
        daily_worker=ROOT / "scripts" / "daily_book_worker.py",
        state_machine_config=ROOT / "config" / "closed_loop_state_machine.json",
        transition_engine=ROOT / "scripts" / "closed_loop_transition_engine.py",
        mutation_guard=ROOT / "scripts" / "protected_mutation_guard.py",
        daily_worker_preflight=PRELIGHT,
        mode="report_only_daily",
        disposition="safe_reports_only",
        output_dir=ROOT / "reports" / "editorial",
        report_suffix="run37",
        dry_run=True,
        execute_safe_command=False,
    )
    assert report["report_only"] is True
    assert report["dry_run"] is True
    assert report["llm_used"] is False
    assert report["provider"] is None
    assert report["model"] is None
    assert report["bridge"] is None
    assert report["model_profile"] is None
    assert report["selected_verification_profile"] == "report_only"
    assert report["daily_worker_command_would_execute"] is False
    assert report["execution_enabled"] is False
    assert report["execution_performed"] is False
    assert report["commit_allowed"] is False
    assert report["push_allowed"] is False
    assert report["protected_write_surfaces_blocked"] is True
    assert report["db_write_surfaces_blocked"] is True
    assert report["docs_book_write_blocked"] is True
    assert report["source_registry_write_blocked"] is True
    assert report["raw_capture_write_blocked"] is True
    assert report["schema_change_blocked"] is True
    assert report["daily_worker_change_blocked"] is True
    assert report["human_in_loop_dependency_added"] is False
    assert report["changed_db"] is False
    assert report["changed_source_notes"] is False
    assert report["changed_source_registry"] is False
    assert report["changed_raw_captures"] is False
    assert report["changed_docs_book"] is False
    assert report["changed_schema"] is False
    assert report["changed_daily_worker"] is False
    assert report["claims_inserted"] == 0
    assert report["editorial_reviews_inserted"] == 0
    assert report["source_status_changed"] is False
    assert report["claim_status_changed"] is False
    assert report["editorial_status_changed"] is False
    assert report["safety_flags"]["author_allowed"] is False
    assert report["safety_flags"]["publication_approved"] is False
    assert report["safety_flags"]["chapter_update_allowed"] is False
    assert "human_review_required" not in json.dumps(report).lower()


def test_cli_dry_run_writes_reports_and_does_not_modify_protected_state(tmp_path):
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
        "--daily-worker-preflight",
        str(PRELIGHT.relative_to(ROOT)),
        "--mode",
        "report_only_daily",
        "--disposition",
        "safe_reports_only",
        "--output-dir",
        str(tmp_path),
        "--report-suffix",
        "run37",
        "--dry-run",
    ]
    res = subprocess.run(cmd, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=180)
    assert res.returncode == 0, res.stderr + res.stdout
    json_path = tmp_path / "citation-pipeline-test-20260612-scheduler-wrapper-contract-run37.json"
    md_path = tmp_path / "citation-pipeline-test-20260612-scheduler-wrapper-contract-run37.md"
    assert json_path.exists()
    assert md_path.exists()
    report = json.loads(json_path.read_text())
    assert report["execution_performed"] is False
    assert report["daily_worker_command_would_execute"] is False
    assert report["commit_allowed"] is False
    assert report["push_allowed"] is False
    assert report["changed_source_notes"] is False
    assert report["claims_inserted"] == 0
    assert report["editorial_reviews_inserted"] == 0
    assert report["source_status_changed"] is False
    assert report["claim_status_changed"] is False
    assert report["editorial_status_changed"] is False
    assert protected_snapshot() == before


def test_mutation_guard_command_builders_and_runner_invocation(tmp_path):
    mod = load_module()
    before = tmp_path / "before.json"
    after = tmp_path / "after.json"
    guard_report = tmp_path / "guard.json"
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if cmd[2] == "snapshot":
            Path(cmd[cmd.index("--output") + 1]).write_text('{"snapshot": true}')
            return subprocess.CompletedProcess(cmd, 0, stdout='{"ok": true}', stderr="")
        assert cmd[2] == "compare"
        guard_report.write_text(json.dumps({"ok": True, "failed_checks": [], "unexpected_changed_paths": []}))
        return subprocess.CompletedProcess(cmd, 0, stdout='{"ok": true}', stderr="")

    result = mod.run_mutation_guard_flow(
        mutation_guard="scripts/protected_mutation_guard.py",
        selected_profile="report_only",
        before_snapshot=before,
        after_snapshot=after,
        mutation_guard_report=guard_report,
        runner=fake_run,
    )

    assert [call[2] for call in calls] == ["snapshot", "snapshot", "compare"]
    assert calls[0] == mod.build_mutation_guard_snapshot_command("scripts/protected_mutation_guard.py", before)
    assert calls[1] == mod.build_mutation_guard_snapshot_command("scripts/protected_mutation_guard.py", after)
    assert calls[2] == mod.build_mutation_guard_compare_command("scripts/protected_mutation_guard.py", before, after, "report_only", guard_report)
    assert result["executed"] is True
    assert result["ok"] is True
    assert result["failed_checks"] == []
    assert result["unexpected_changed_paths"] == []


def test_run_mutation_guard_embeds_ok_and_does_not_execute_daily_worker(tmp_path):
    mod = load_module()
    before = tmp_path / "before.json"
    after = tmp_path / "after.json"
    guard_report = tmp_path / "guard.json"

    def fake_run(cmd, **kwargs):
        assert "daily_book_worker.py" not in " ".join(map(str, cmd))
        if cmd[2] == "snapshot":
            Path(cmd[cmd.index("--output") + 1]).write_text('{"snapshot": true}')
        else:
            guard_report.write_text(json.dumps({"ok": True, "failed_checks": [], "unexpected_changed_paths": []}))
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    guard = mod.run_mutation_guard_flow(
        "scripts/protected_mutation_guard.py", "report_only", before, after, guard_report, runner=fake_run
    )
    report = mod.build_report(
        run_id="citation-pipeline-test-20260612",
        daily_worker=ROOT / "scripts" / "daily_book_worker.py",
        state_machine_config=ROOT / "config" / "closed_loop_state_machine.json",
        transition_engine=ROOT / "scripts" / "closed_loop_transition_engine.py",
        mutation_guard=ROOT / "scripts" / "protected_mutation_guard.py",
        daily_worker_preflight=PRELIGHT,
        mode="report_only_daily",
        disposition="safe_reports_only",
        output_dir=tmp_path,
        report_suffix="run38",
        dry_run=True,
        mutation_guard_execution=guard,
    )
    assert report["mutation_guard_executed"] is True
    assert report["mutation_guard_ok"] is True
    assert report["mutation_guard_failed_checks"] == []
    assert report["mutation_guard_unexpected_changed_paths"] == []
    assert report["execution_performed"] is False
    assert report["commit_allowed"] is False
    assert report["push_allowed"] is False
    assert "report_only_contract_blocks_commit" in report["commit_block_reasons"]
    assert "report_only_contract_blocks_push" in report["push_block_reasons"]


def test_mutation_guard_failure_modes_fail_closed(tmp_path):
    mod = load_module()
    before = tmp_path / "before.json"
    after = tmp_path / "after.json"
    guard_report = tmp_path / "guard.json"

    def run_without_before(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    result = mod.run_mutation_guard_flow("scripts/protected_mutation_guard.py", "report_only", before, after, guard_report, runner=run_without_before)
    assert result["ok"] is False
    assert "before_snapshot_missing" in result["failed_checks"]

    before.unlink(missing_ok=True)
    after.unlink(missing_ok=True)
    guard_report.unlink(missing_ok=True)

    def run_without_after(cmd, **kwargs):
        if cmd[2] == "snapshot" and not before.exists():
            before.write_text("{}")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    result = mod.run_mutation_guard_flow("scripts/protected_mutation_guard.py", "report_only", before, after, guard_report, runner=run_without_after)
    assert result["ok"] is False
    assert "after_snapshot_missing" in result["failed_checks"]

    before.write_text("{}")
    after.write_text("{}")
    guard_report.unlink(missing_ok=True)

    def run_missing_report(cmd, **kwargs):
        if cmd[2] == "snapshot":
            Path(cmd[cmd.index("--output") + 1]).write_text("{}")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    result = mod.run_mutation_guard_flow("scripts/protected_mutation_guard.py", "report_only", before, after, guard_report, runner=run_missing_report)
    assert result["ok"] is False
    assert "mutation_guard_report_missing" in result["failed_checks"]

    before.unlink(missing_ok=True)
    after.unlink(missing_ok=True)
    guard_report.unlink(missing_ok=True)

    def run_subprocess_failure(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 9, stdout="", stderr="boom")

    result = mod.run_mutation_guard_flow("scripts/protected_mutation_guard.py", "report_only", before, after, guard_report, runner=run_subprocess_failure)
    assert result["ok"] is False
    assert "before_snapshot_subprocess_failed" in result["failed_checks"]


def test_mutation_guard_ok_false_unexpected_paths_and_human_loop_block_policy(tmp_path):
    mod = load_module()
    base_guard = {
        "executed": True,
        "ok": False,
        "profile_used": "report_only",
        "before_snapshot": str(tmp_path / "before.json"),
        "after_snapshot": str(tmp_path / "after.json"),
        "report_path": str(tmp_path / "guard.json"),
        "failed_checks": ["unexpected_changed_paths"],
        "unexpected_changed_paths": ["docs/book/chapter.md"],
        "report": {
            "ok": False,
            "unexpected_changed_paths": ["docs/book/chapter.md"],
            "failed_checks": ["unexpected_changed_paths"],
            "human_in_loop_dependency_added": True,
            "hard_flags_changed": {"author_allowed": True},
            "db_delta": {},
            "status_hash_delta": {},
        },
    }
    report = mod.build_report(
        run_id="citation-pipeline-test-20260612",
        daily_worker=ROOT / "scripts" / "daily_book_worker.py",
        state_machine_config=ROOT / "config" / "closed_loop_state_machine.json",
        transition_engine=ROOT / "scripts" / "closed_loop_transition_engine.py",
        mutation_guard=ROOT / "scripts" / "protected_mutation_guard.py",
        daily_worker_preflight=PRELIGHT,
        mode="report_only_daily",
        disposition="safe_reports_only",
        output_dir=tmp_path,
        report_suffix="run38",
        dry_run=True,
        mutation_guard_execution=base_guard,
    )
    assert report["mutation_guard_ok"] is False
    assert report["commit_allowed"] is False
    assert report["push_allowed"] is False
    assert "mutation_guard_failed" in report["commit_block_reasons"]
    assert "unexpected_protected_or_scope_changes" in report["commit_block_reasons"]
    assert "human_in_loop_dependency_added" in report["commit_block_reasons"]
    assert "hard_flag_true" in report["commit_block_reasons"]
    assert report["human_in_loop_dependency_added"] is False


def test_cli_run_mutation_guard_writes_both_reports_and_preserves_protected_state(tmp_path):
    before_state = protected_snapshot()
    before_snapshot = tmp_path / "before.json"
    after_snapshot = tmp_path / "after.json"
    guard_report = tmp_path / "guard.json"
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
        "--daily-worker-preflight",
        str(PRELIGHT.relative_to(ROOT)),
        "--mode",
        "report_only_daily",
        "--disposition",
        "safe_reports_only",
        "--output-dir",
        str(tmp_path),
        "--report-suffix",
        "run38",
        "--dry-run",
        "--run-mutation-guard",
        "--before-snapshot",
        str(before_snapshot),
        "--after-snapshot",
        str(after_snapshot),
        "--mutation-guard-report",
        str(guard_report),
    ]
    res = subprocess.run(cmd, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=180)
    assert res.returncode == 0, res.stderr + res.stdout
    report_path = tmp_path / "citation-pipeline-test-20260612-scheduler-wrapper-contract-run38.json"
    assert report_path.exists()
    assert guard_report.exists()
    assert before_snapshot.exists()
    assert after_snapshot.exists()
    report = json.loads(report_path.read_text())
    assert report["mutation_guard_executed"] is True
    assert report["mutation_guard_ok"] is True
    assert report["selected_verification_profile"] == "report_only"
    assert report["execution_allowed"] is False
    assert report["execution_capability_decision"] == "blocked_missing_no_write_capabilities"
    assert report["execution_block_reasons"]
    assert report["execution_performed"] is False
    assert report["daily_worker_command_contract"]["blocks_capture"] is True
    assert report["daily_worker_command_contract"]["blocks_docs_book_mutation"] is True
    assert "--no-commit" in report["daily_worker_command_contract"]["argv"]
    assert protected_snapshot() == before_state
