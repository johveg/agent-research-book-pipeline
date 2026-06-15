import importlib.util
import json
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "protected_mutation_guard.py"
DB = ROOT / ".var" / "book.sqlite"


def load_module():
    spec = importlib.util.spec_from_file_location("protected_mutation_guard", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def base_snapshot():
    return {
        "git_status_short": [],
        "git_diff_names": [],
        "db": {
            "counts": {"source_notes": 365, "claims": 181, "editorial_reviews": 10},
            "hashes": {
                "source_status_hash": "src",
                "claim_status_hash": "clm",
                "editorial_review_hash": "edr",
                "source_notes_hash": "notes",
            },
        },
        "path_hashes": {
            "data/source_registry.json": {"tree_hash": "registry"},
            "raw": {"tree_hash": "raw"},
            "docs/book": {"tree_hash": "book"},
            "docs/entities": {"tree_hash": "entities"},
            "docs/research/claims.md": {"tree_hash": "claimsmd"},
            "data/schema.sql": {"tree_hash": "schema"},
            "scripts/daily_book_worker.py": {"tree_hash": "worker"},
            ".var/book.sqlite": {"tree_hash": "dbfile"},
        },
    }


def changed(path, status="??"):
    s = base_snapshot()
    s["git_status_short"] = [f"{status} {path}"]
    s["git_diff_names"] = [path] if status.strip() != "??" else []
    return s


def test_snapshot_includes_db_counts_protected_hashes_git_diff_and_missing_raw(tmp_path):
    mod = load_module()
    copied = tmp_path / "book.sqlite"
    shutil.copy2(DB, copied)
    snap = mod.snapshot_workspace_state(root=ROOT, db_path=copied, protected_paths=["data/source_registry.json", "raw", "missing-raw-test"])
    assert snap["db"]["counts"]["source_notes"] >= 0
    assert snap["db"]["counts"]["claims"] >= 0
    assert "data/source_registry.json" in snap["path_hashes"]
    assert snap["path_hashes"]["missing-raw-test"]["exists"] is False
    assert isinstance(snap["git_diff_names"], list)
    snap2 = mod.snapshot_workspace_state(root=ROOT, db_path=copied, protected_paths=["data/source_registry.json", "raw", "missing-raw-test"])
    assert snap["db"] == snap2["db"]
    assert snap["path_hashes"] == snap2["path_hashes"]


def test_report_only_profile_allows_no_changes_and_new_reports_only():
    mod = load_module()
    before = base_snapshot()
    assert mod.compare_snapshots(before, before, "report_only")["ok"] is True
    after = changed("reports/editorial/new-report.json")
    result = mod.compare_snapshots(before, after, "report_only")
    assert result["ok"] is True
    assert "reports/editorial/new-report.json" in result["allowed_changed_paths"]


def test_config_only_and_control_plane_code_only_profiles_allow_expected_paths():
    mod = load_module()
    before = base_snapshot()
    cfg = mod.compare_snapshots(before, changed("config/closed_loop_state_machine.json", " M"), "config_only")
    assert cfg["ok"] is True
    code = base_snapshot()
    code["git_status_short"] = [
        "?? scripts/protected_mutation_guard.py",
        "?? tests/test_protected_mutation_guard.py",
        "?? reports/architecture/run35-protected-mutation-guard-evidence-map-20260614.md",
        "?? config/academic_book_quality_contract.json",
        "?? scripts/academic_book_quality_gate.py",
        "?? scripts/academic_book_structure_plan.py",
        "?? book/academic_structure_plan.md",
        "?? tests/test_academic_book_quality_gate.py",
    ]
    result = mod.compare_snapshots(before, code, "control_plane_code_only")
    assert result["ok"] is True
    assert not result["unexpected_changed_paths"]

    sqlite_after = base_snapshot()
    sqlite_after["path_hashes"][".var/book.sqlite"] = {"tree_hash": "physical-drift-without-logical-db-delta"}
    sqlite_result = mod.compare_snapshots(before, sqlite_after, "control_plane_code_only")
    assert sqlite_result["ok"] is True
    assert sqlite_result["sqlite_physical_hash_drift_allowed"] is True


def test_academic_manuscript_inventory_profile_allows_run49_reports_and_blocks_book_mutation():
    mod = load_module()
    before = base_snapshot()
    after = base_snapshot()
    after["git_status_short"] = [
        "?? scripts/academic_manuscript_inventory.py",
        "?? scripts/academic_chapter_conversion_plan.py",
        " M scripts/protected_mutation_guard.py",
        "?? tests/test_academic_manuscript_inventory.py",
        "?? tests/test_academic_chapter_conversion_plan.py",
        " M tests/test_protected_mutation_guard.py",
        "?? reports/editorial/run49-academic-manuscript-inventory.json",
        "?? reports/editorial/run49-chapter-conversion-plan.md",
        "?? reports/architecture/run49-academic-manuscript-inventory-evidence-map-20260615.md",
        "?? reports/telegram/run49-status.md",
    ]
    result = mod.compare_snapshots(before, after, "academic_manuscript_inventory_report_only")
    assert result["ok"] is True
    assert not result["unexpected_changed_paths"]

    blocked = mod.compare_snapshots(before, changed("docs/book/01-the-agent-loop.md", " M"), "academic_manuscript_inventory_report_only")
    assert blocked["ok"] is False
    assert "docs/book/01-the-agent-loop.md" in blocked["unexpected_changed_paths"]


def test_academic_introduction_profile_allows_run50_reports_and_blocks_book_mutation():
    mod = load_module()
    before = base_snapshot()
    after = base_snapshot()
    after["git_status_short"] = [
        "?? scripts/academic_introduction_input_packet.py",
        "?? scripts/academic_introduction_draft.py",
        "?? scripts/academic_introduction_developmental_review.py",
        " M scripts/academic_book_quality_gate.py",
        " M scripts/protected_mutation_guard.py",
        "?? tests/test_academic_introduction_input_packet.py",
        "?? tests/test_academic_introduction_draft.py",
        "?? tests/test_academic_introduction_developmental_review.py",
        " M tests/test_protected_mutation_guard.py",
        "?? reports/editorial/run50-introduction-thesis-draft.json",
        "?? reports/architecture/run50-introduction-thesis-draft-evidence-map-20260615.md",
        "?? reports/telegram/run50-status.md",
    ]
    result = mod.compare_snapshots(before, after, "academic_introduction_report_only")
    assert result["ok"] is True
    assert not result["unexpected_changed_paths"]

    blocked = mod.compare_snapshots(before, changed("docs/book/introduction.md", " M"), "academic_introduction_report_only")
    assert blocked["ok"] is False
    assert "docs/book/introduction.md" in blocked["unexpected_changed_paths"]


def test_protected_paths_fail_under_report_config_and_control_plane_profiles():
    mod = load_module()
    protected = [
        "data/source_registry.json",
        "docs/book/chapter.md",
        "raw/capture.json",
        "data/schema.sql",
        "scripts/daily_book_worker.py",
    ]
    for path in protected:
        for profile in ["report_only", "config_only", "control_plane_code_only"]:
            result = mod.compare_snapshots(base_snapshot(), changed(path, " M"), profile)
            assert result["ok"] is False, (path, profile)
            assert path in result["unexpected_changed_paths"]


def test_db_count_and_status_hash_deltas_fail_closed_for_non_db_profiles():
    mod = load_module()
    for table in ["source_notes", "claims", "editorial_reviews"]:
        after = base_snapshot()
        after["db"]["counts"][table] += 1
        result = mod.compare_snapshots(base_snapshot(), after, "control_plane_code_only")
        assert result["ok"] is False
        assert table in result["db_delta"]
    after = base_snapshot()
    after["db"]["hashes"]["source_status_hash"] = "changed"
    result = mod.compare_snapshots(base_snapshot(), after, "config_only")
    assert result["ok"] is False
    assert result["status_hash_delta"]["source_status_hash"] is True


def test_closed_loop_runner_shell_allows_sqlite_physical_hash_drift_only_when_logical_db_unchanged():
    mod = load_module()
    before = base_snapshot()
    after = base_snapshot()
    after["path_hashes"][".var/book.sqlite"] = {"tree_hash": "dbfile-physical-drift"}

    result = mod.compare_snapshots(before, after, "closed_loop_runner_shell")

    assert result["ok"] is True
    assert result["sqlite_physical_hash_drift_allowed"] is True
    assert result["protected_path_delta"][".var/book.sqlite"] is True

    after_count_delta = base_snapshot()
    after_count_delta["path_hashes"][".var/book.sqlite"] = {"tree_hash": "dbfile-physical-drift"}
    after_count_delta["db"]["counts"]["claims"] += 1
    assert mod.compare_snapshots(before, after_count_delta, "closed_loop_runner_shell")["ok"] is False

    after_status_delta = base_snapshot()
    after_status_delta["path_hashes"][".var/book.sqlite"] = {"tree_hash": "dbfile-physical-drift"}
    after_status_delta["db"]["hashes"]["claim_status_hash"] = "changed"
    result = mod.compare_snapshots(before, after_status_delta, "closed_loop_runner_shell")
    assert result["ok"] is False


def test_closed_loop_runner_shell_allows_run42_context_reports():
    mod = load_module()
    before = base_snapshot()
    after = changed("reports/editorial/citation-pipeline-test-20260612-constrained-authoring-context-run42.json")

    result = mod.compare_snapshots(before, after, "closed_loop_runner_shell")

    assert result["ok"] is True
    assert "reports/editorial/citation-pipeline-test-20260612-constrained-authoring-context-run42.json" in result["allowed_changed_paths"]


def test_db_write_source_notes_only_allows_only_source_notes_delta():
    mod = load_module()
    after = base_snapshot()
    after["db"]["counts"]["source_notes"] += 1
    after["db"]["hashes"]["source_notes_hash"] = "notes2"
    result = mod.compare_snapshots(base_snapshot(), after, "db_write_source_notes_only")
    assert result["ok"] is True
    after2 = base_snapshot()
    after2["db"]["counts"]["claims"] += 1
    assert mod.compare_snapshots(base_snapshot(), after2, "db_write_source_notes_only")["ok"] is False
    after3 = base_snapshot()
    after3["db"]["hashes"]["source_status_hash"] = "src2"
    assert mod.compare_snapshots(base_snapshot(), after3, "db_write_source_notes_only")["ok"] is False


def test_daily_worker_code_only_profile_allows_worker_tests_and_run40_reports_but_blocks_protected_runtime_paths():
    mod = load_module()
    before = base_snapshot()
    allowed_after = base_snapshot()
    allowed_after["git_status_short"] = [
        " M scripts/daily_book_worker.py",
        "?? tests/test_daily_book_worker_no_write_controls.py",
        " M scripts/scheduler_wrapper_contract.py",
        " M tests/test_scheduler_wrapper_contract.py",
        "?? reports/editorial/citation-pipeline-test-20260612-daily-worker-no-write-controls-run40.json",
        "?? reports/architecture/run40-daily-worker-no-write-controls-evidence-map-20260614.md",
    ]
    allowed_after["git_diff_names"] = [
        "scripts/daily_book_worker.py",
        "scripts/scheduler_wrapper_contract.py",
        "tests/test_scheduler_wrapper_contract.py",
    ]
    allowed_after["path_hashes"]["scripts/daily_book_worker.py"] = {"tree_hash": "worker-v2"}
    result = mod.compare_snapshots(before, allowed_after, "daily_worker_code_only")
    assert result["ok"] is True
    assert result["daily_worker_changed"] is True
    assert result["unexpected_changed_paths"] == []

    for path in [
        ".var/book.sqlite",
        "data/source_registry.json",
        "raw/capture.json",
        "docs/book/chapter.md",
        "docs/entities/acme.md",
        "docs/research/claims.md",
        "data/schema.sql",
    ]:
        assert mod.compare_snapshots(before, changed(path, " M"), "daily_worker_code_only")["ok"] is False

    human_after = base_snapshot()
    human_after["report_safety_scan"] = {"human_in_loop_dependency_added": True, "hard_flags_changed": {}}
    human_result = mod.compare_snapshots(before, human_after, "daily_worker_code_only")
    assert human_result["ok"] is False
    assert human_result["human_in_loop_dependency_added"] is True


def test_closed_loop_author_editor_code_only_profile_allows_run43_control_plane_and_blocks_runtime_paths():
    mod = load_module()
    before = base_snapshot()
    after = base_snapshot()
    after["git_status_short"] = [
        " M config/reasoning_models.json",
        "?? scripts/closed_loop_author_editor.py",
        "?? scripts/closed_loop_publish_packet_validator.py",
        " M scripts/model_profiles.py",
        " M scripts/protected_mutation_guard.py",
        "?? tests/test_closed_loop_author_editor.py",
        "?? tests/test_closed_loop_publish_packet_validator.py",
        "?? reports/editorial/citation-pipeline-test-20260612-author-editor-redteam-run43.json",
        "?? reports/architecture/run43-author-editor-redteam-evidence-map-20260614.md",
        "?? reports/telegram/run43-status.md",
    ]
    after["git_diff_names"] = [
        "config/reasoning_models.json",
        "scripts/model_profiles.py",
        "scripts/protected_mutation_guard.py",
    ]
    result = mod.compare_snapshots(before, after, "closed_loop_author_editor_code_only")
    assert result["ok"] is True
    assert result["unexpected_changed_paths"] == []

    for path in [
        ".var/book.sqlite",
        "data/source_registry.json",
        "raw/capture.json",
        "docs/book/chapter.md",
        "docs/entities/acme.md",
        "docs/research/claims.md",
        "data/schema.sql",
        "scripts/daily_book_worker.py",
    ]:
        assert mod.compare_snapshots(before, changed(path, " M"), "closed_loop_author_editor_code_only")["ok"] is False


def test_docs_book_write_permits_docs_book_target_and_run44_control_plane_but_blocks_other_protected_paths():
    mod = load_module()
    before = base_snapshot()
    after = base_snapshot()
    after["git_status_short"] = [
        " M docs/book/daily-pipeline-status.md",
        "?? reports/editorial/citation-pipeline-test-20260612-guarded-book-publication-run44.json",
        "?? reports/architecture/run44-guarded-book-publication-evidence-map-20260614.md",
        "?? reports/telegram/run44-status.md",
        "?? scripts/closed_loop_book_publisher.py",
        "?? scripts/closed_loop_publication_orchestrator.py",
        "?? tests/test_closed_loop_book_publisher.py",
        "?? tests/test_closed_loop_publication_orchestrator.py",
        " M scripts/protected_mutation_guard.py",
        " M tests/test_protected_mutation_guard.py",
    ]
    after["git_diff_names"] = [
        "docs/book/daily-pipeline-status.md",
        "scripts/protected_mutation_guard.py",
        "tests/test_protected_mutation_guard.py",
    ]
    after["path_hashes"]["docs/book"] = {"tree_hash": "book-v2"}
    result = mod.compare_snapshots(before, after, "docs_book_write")
    assert result["ok"] is True
    assert result["docs_book_changed"] is True
    assert result["unexpected_changed_paths"] == []

    sqlite_after = base_snapshot()
    sqlite_after["path_hashes"][".var/book.sqlite"] = {"tree_hash": "dbfile-physical-drift"}
    sqlite_result = mod.compare_snapshots(before, sqlite_after, "docs_book_write")
    assert sqlite_result["ok"] is True
    assert sqlite_result["sqlite_physical_hash_drift_allowed"] is True

    sqlite_logical_after = base_snapshot()
    sqlite_logical_after["path_hashes"][".var/book.sqlite"] = {"tree_hash": "dbfile-physical-drift"}
    sqlite_logical_after["db"]["counts"]["claims"] += 1
    assert mod.compare_snapshots(before, sqlite_logical_after, "docs_book_write")["ok"] is False

    for path in ["data/source_registry.json", "raw/capture.json", ".var/book.sqlite", "docs/entities/acme.md", "docs/research/claims.md", "data/schema.sql"]:
        assert mod.compare_snapshots(before, changed(path, " M"), "docs_book_write")["ok"] is False

    human_after = base_snapshot()
    human_after["report_safety_scan"] = {"human_in_loop_dependency_added": True, "hard_flags_changed": {}}
    assert mod.compare_snapshots(before, human_after, "docs_book_write")["ok"] is False


def test_production_daily_publish_profile_allows_intended_outputs_and_blocks_unsafe_surfaces():
    mod = load_module()
    before = base_snapshot()
    after = base_snapshot()
    for path in [
        "docs/book/daily-pipeline-status.md",
        "reports/editorial/citation-pipeline-test-20260612-production-execute-once-run45.json",
        "reports/architecture/run45-production-scheduler-evidence-map-20260614.md",
        "reports/telegram/run45-status.md",
        "logs/closed_loop/events.jsonl",
        "config/closed_loop_runtime.json",
        "config/schedules/closed-loop-production-daily.cron.example",
        "scripts/closed_loop_production_scheduler.py",
        "tests/test_closed_loop_production_scheduler.py",
        "tests/test_closed_loop_runtime_config.py",
    ]:
        after["git_status_short"].append(f" M {path}")
        after["git_diff_names"].append(path)
    after["path_hashes"]["docs/book"] = {"tree_hash": "book-v45"}
    result = mod.compare_snapshots(before, after, "production_daily_publish")
    assert result["ok"] is True
    assert result["docs_book_changed"] is True
    assert result["raw_changed"] is False

    raw_after = changed("raw/capture.json", " M")
    raw_after["path_hashes"]["raw"] = {"tree_hash": "raw-v45"}
    raw_after["report_safety_scan"] = {"raw_collection_performed": True}
    raw_result = mod.compare_snapshots(before, raw_after, "production_daily_publish")
    assert raw_result["ok"] is True
    assert raw_result["raw_changed"] is True

    registry_after = changed("data/source_registry.json", " M")
    registry_after["path_hashes"]["data/source_registry.json"] = {"tree_hash": "registry-v45"}
    registry_after["report_safety_scan"] = {"source_registry_export_performed": True}
    assert mod.compare_snapshots(before, registry_after, "production_daily_publish")["ok"] is True

    registry_hash_after = changed("data/source_registry.json", " M")
    registry_hash_after["path_hashes"]["data/source_registry.json"] = {"tree_hash": "registry-v45"}
    registry_hash_after["db"]["hashes"]["source_status_hash"] = "changed-by-source-registry-export"
    registry_hash_after["report_safety_scan"] = {"source_registry_export_performed": True}
    assert mod.compare_snapshots(before, registry_hash_after, "production_daily_publish")["ok"] is True

    registry_sqlite_after = changed("data/source_registry.json", " M")
    registry_sqlite_after["path_hashes"]["data/source_registry.json"] = {"tree_hash": "registry-v45"}
    registry_sqlite_after["path_hashes"][".var/book.sqlite"] = {"tree_hash": "db-physical-after-registry-export"}
    registry_sqlite_after["db"]["hashes"]["source_status_hash"] = "changed-by-source-registry-export"
    registry_sqlite_after["report_safety_scan"] = {"source_registry_export_performed": True}
    assert mod.compare_snapshots(before, registry_sqlite_after, "production_daily_publish")["ok"] is True

    mixed_reports = base_snapshot()
    for report_path in [
        "reports/editorial/production-daily-manual-20260615T171122Z-production-execute-once.json",
        "reports/editorial/production-scheduler-health-run47-after.json",
    ]:
        mixed_reports["git_status_short"].append(f"?? {report_path}")
        mixed_reports["git_diff_names"].append(report_path)
    assert mod.compare_snapshots(before, mixed_reports, "production_daily_publish")["unexpected_changed_paths"] == []

    db_after = base_snapshot()
    db_after["path_hashes"][".var/book.sqlite"] = {"tree_hash": "db-v45"}
    db_after["db"]["counts"]["source_notes"] += 1
    db_after["report_safety_scan"] = {"db_logical_delta_expected": True}
    assert mod.compare_snapshots(before, db_after, "production_daily_publish")["ok"] is True

    for path in ["data/schema.sql", "docs/entities/x.md", "docs/research/claims.md"]:
        assert mod.compare_snapshots(before, changed(path, " M"), "production_daily_publish")["ok"] is False


def test_production_daily_publish_blocks_missing_gates_and_unsafe_terms():
    mod = load_module()
    before = base_snapshot()
    after = changed("docs/book/chapter.md", " M")
    after["report_safety_scan"] = {"weak_local_fallback_used": True}
    assert mod.compare_snapshots(before, after, "production_daily_publish")["ok"] is False
    after = changed("docs/book/chapter.md", " M")
    after["report_safety_scan"] = {"gpt55_publication_gate_passed": False}
    assert mod.compare_snapshots(before, after, "production_daily_publish")["ok"] is False
    after = changed("docs/book/chapter.md", " M")
    after["report_safety_scan"] = {"citation_verifier_ok": False}
    assert mod.compare_snapshots(before, after, "production_daily_publish")["ok"] is False
    after = changed("docs/book/chapter.md", " M")
    after["report_safety_scan"] = {"human_in_loop_dependency_added": True}
    assert mod.compare_snapshots(before, after, "production_daily_publish")["ok"] is False


def test_production_ops_hardening_allows_ops_surfaces_and_blocks_publication_mutations():
    mod = load_module()
    before = base_snapshot()
    after = base_snapshot()
    allowed = [
        "scripts/production_daily_monitor.py",
        "scripts/closed_loop_production_scheduler.py",
        "scripts/git_push_with_hermes_key.sh",
        "scripts/protected_mutation_guard.py",
        "tests/test_production_daily_monitor.py",
        "tests/test_closed_loop_production_scheduler.py",
        "tests/test_git_push_with_hermes_key.py",
        "tests/test_protected_mutation_guard.py",
        "config/schedules/closed-loop-production-daily.md",
        "reports/editorial/production-ops-baseline-run46.json",
        "reports/editorial/production-monitor-run46.json",
        "reports/editorial/production-scheduler-health-run46.json",
        "reports/architecture/run46-production-ops-hardening-evidence-map-20260615.md",
        "reports/telegram/run46-status.md",
        "reports/telegram/production-monitor-latest.md",
        "reports/telegram/production-scheduler-health-run46.md",
    ]
    for path in allowed:
        after["git_status_short"].append(f" M {path}")
        after["git_diff_names"].append(path)
    result = mod.compare_snapshots(before, after, "production_ops_hardening")
    assert result["ok"] is True
    assert result["unexpected_changed_paths"] == []

    sqlite_after = base_snapshot()
    sqlite_after["path_hashes"][".var/book.sqlite"] = {"tree_hash": "db-physical-run46"}
    assert mod.compare_snapshots(before, sqlite_after, "production_ops_hardening")["ok"] is True

    db_logical = base_snapshot()
    db_logical["path_hashes"][".var/book.sqlite"] = {"tree_hash": "db-logical-run46"}
    db_logical["db"]["counts"]["claims"] += 1
    assert mod.compare_snapshots(before, db_logical, "production_ops_hardening")["ok"] is False

    for path in [
        "docs/book/06-operating-loops.md",
        "raw/web/x.json",
        "data/source_registry.json",
        ".var/book.sqlite",
        "docs/entities/x.md",
        "docs/research/claims.md",
        "data/schema.sql",
    ]:
        assert mod.compare_snapshots(before, changed(path, " M"), "production_ops_hardening")["ok"] is False

    unsafe = base_snapshot()
    unsafe["report_safety_scan"] = {"human_in_loop_dependency_added": True, "weak_local_fallback_allowed": True}
    assert mod.compare_snapshots(before, unsafe, "production_ops_hardening")["ok"] is False


def test_unknown_and_future_publication_profiles_fail_closed_without_gates():
    mod = load_module()
    assert mod.compare_snapshots(base_snapshot(), base_snapshot(), "unknown_profile")["ok"] is False
    assert mod.compare_snapshots(base_snapshot(), base_snapshot(), "schema_change")["ok"] is False
    assert mod.compare_snapshots(base_snapshot(), base_snapshot(), "daily_worker_change")["ok"] is False
    assert mod.compare_snapshots(base_snapshot(), base_snapshot(), "full_publication_gate")["ok"] is False

    mod = load_module()
    before = base_snapshot()
    after = base_snapshot()
    after["report_safety_scan"] = {
        "human_in_loop_dependency_added": True,
        "hard_flags_changed": {"author_allowed": True, "publication_approved": True, "chapter_update_allowed": True},
    }
    result = mod.compare_snapshots(before, after, "report_only")
    assert result["ok"] is False
    assert result["human_in_loop_dependency_added"] is True
    assert result["hard_flags_changed"]["author_allowed"] is True
    assert result["hard_flags_changed"]["publication_approved"] is True
    assert result["hard_flags_changed"]["chapter_update_allowed"] is True


def test_cli_snapshot_compare_writes_reports_without_no_write_side_effects(tmp_path):
    before_counts = db_counts()
    before_hash = DB.read_bytes()
    before = tmp_path / "before.json"
    after = tmp_path / "after.json"
    output = tmp_path / "guard.json"
    for path in [before, after]:
        res = subprocess.run([sys.executable, str(SCRIPT), "snapshot", "--output", str(path)], cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=180)
        assert res.returncode == 0, res.stderr + res.stdout
    res = subprocess.run([sys.executable, str(SCRIPT), "compare", "--before", str(before), "--after", str(after), "--profile", "report_only", "--output", str(output)], cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=180)
    assert res.returncode == 0, res.stderr + res.stdout
    report = json.loads(output.read_text())
    assert report["ok"] is True
    assert (tmp_path / "guard.md").exists()
    assert db_counts() == before_counts
    assert DB.read_bytes() == before_hash


def db_counts():
    con = sqlite3.connect(DB)
    try:
        return {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ["source_notes", "claims", "editorial_reviews"]}
    finally:
        con.close()
