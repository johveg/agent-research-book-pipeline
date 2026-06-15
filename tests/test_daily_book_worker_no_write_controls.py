import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import daily_book_worker as worker  # noqa: E402


REQUIRED_CAPABILITY_KEYS = {
    "supports_skip_capture",
    "supports_skip_entity_extraction",
    "supports_skip_claim_extraction",
    "supports_skip_docs_entities_update",
    "supports_skip_docs_claims_update",
    "supports_skip_source_registry_export",
    "supports_skip_run_table_update",
    "supports_skip_vector",
    "supports_no_commit",
    "supports_no_push",
    "supports_no_docs_book_update_without_gate",
    "supports_preflight_only",
    "preflight_only_no_write",
    "capability_probe_no_write",
    "human_in_loop_dependency_added",
    "author_allowed",
    "publication_approved",
    "eligible_for_claim_insertion",
    "eligible_for_authoring",
    "eligible_for_publication",
    "chapter_update_allowed",
}


class FakeConnection:
    def __init__(self):
        self.executed = []
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, *args, **kwargs):
        self.executed.append((args, kwargs))
        return self

    def commit(self):
        self.committed = True


def _configure_worker(monkeypatch, tmp_path):
    logs = tmp_path / "logs"
    reports = tmp_path / "reports"
    config = tmp_path / "search_config.json"
    config.write_text(json.dumps({"web_queries": [], "linkedin_queries": []}))
    monkeypatch.setattr(worker, "LOGS", logs)
    monkeypatch.setattr(worker, "REPORTS", reports)
    monkeypatch.setattr(worker, "CONFIG_PATH", config)
    monkeypatch.setattr(worker, "ROOT", tmp_path)
    monkeypatch.setattr(worker, "MKDOCS_PY", sys.executable)
    monkeypatch.setattr(worker, "utc_now", lambda: "2026-06-15T00:00:00Z")
    monkeypatch.setattr(worker, "docs_book_dirty_files", lambda: [])

    calls = []
    connection = FakeConnection()

    def fake_run(cmd, log):
        calls.append(cmd)
        name = Path(cmd[1] if len(cmd) > 1 else cmd[0]).name
        if name == "editorial_pipeline_report.py":
            out = Path(cmd[cmd.index("--json-out") + 1])
            out.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "final_status": "success",
                "counts": {"source_counts": {}, "entity_count": 0, "claim_counts": {}},
                "new_candidate_trends": [],
                "claims_promoted": [],
                "claims_rejected": [],
                "chapter_sections_updated": [],
                "editor_warnings": [],
                "publication_recommendation": "do_not_publish_chapter_updates",
                "blocked_state_output": {
                    "chapter_update_allowed": False,
                    "chapter_update_skipped_reason": "allow_chapter_updates_flag_absent",
                    "publication_approved": False,
                    "eligible_for_claim_insertion": False,
                    "eligible_for_authoring": False,
                    "eligible_for_publication": False,
                },
            }
            out.write_text(json.dumps(payload))
            return {"cmd": cmd, "returncode": 0, "stdout_tail": json.dumps(payload), "stderr_tail": ""}
        return {"cmd": cmd, "returncode": 0, "stdout_tail": "ok", "stderr_tail": ""}

    monkeypatch.setattr(worker, "init_db", lambda: None)
    monkeypatch.setattr(worker, "connect_db", lambda: connection)
    monkeypatch.setattr(worker, "run", fake_run)
    commit_calls = []
    monkeypatch.setattr(worker, "git_commit_push", lambda *args, **kwargs: commit_calls.append((args, kwargs)) or {"committed": True})
    return calls, commit_calls, connection, logs, reports


def _command_names(calls):
    return [Path(c[1] if len(c) > 1 else c[0]).name for c in calls]


def test_print_capabilities_json_emits_valid_json_exits_zero_and_has_hard_flags_false(monkeypatch, capsys):
    forbidden_calls = []
    for name in ["init_db", "connect_db", "git_commit_push", "write_steps", "build_daily_summary"]:
        monkeypatch.setattr(worker, name, lambda *args, _name=name, **kwargs: forbidden_calls.append(_name) or pytest.fail(f"{_name} must not run in capability probe"))
    monkeypatch.setattr(worker, "run", lambda *args, **kwargs: pytest.fail("subprocess steps must not run in capability probe"))
    monkeypatch.setattr(sys, "argv", ["daily_book_worker.py", "--print-capabilities-json"])

    assert worker.main() == 0
    payload = json.loads(capsys.readouterr().out)

    assert set(payload) >= REQUIRED_CAPABILITY_KEYS
    for key in REQUIRED_CAPABILITY_KEYS:
        if key.startswith("supports_") or key == "capability_probe_no_write":
            assert payload[key] is True
    for key in [
        "human_in_loop_dependency_added",
        "author_allowed",
        "publication_approved",
        "eligible_for_claim_insertion",
        "eligible_for_authoring",
        "eligible_for_publication",
        "chapter_update_allowed",
    ]:
        assert payload[key] is False
    assert forbidden_calls == []


def test_print_capabilities_json_does_not_write_runtime_surfaces(monkeypatch, tmp_path, capsys):
    logs = tmp_path / "logs"
    reports = tmp_path / "reports"
    raw = tmp_path / "raw"
    docs_book = tmp_path / "docs" / "book"
    docs_entities = tmp_path / "docs" / "entities"
    docs_claims = tmp_path / "docs" / "research" / "claims.md"
    source_registry = tmp_path / "data" / "source_registry.json"
    for path in [logs, reports, raw, docs_book, docs_entities, docs_claims.parent, source_registry.parent]:
        path.mkdir(parents=True, exist_ok=True)
    docs_claims.write_text("before\n")
    source_registry.write_text("{}\n")
    monkeypatch.setattr(worker, "LOGS", logs)
    monkeypatch.setattr(worker, "REPORTS", reports)
    monkeypatch.setattr(worker, "ROOT", tmp_path)
    monkeypatch.setattr(sys, "argv", ["daily_book_worker.py", "--print-capabilities-json"])

    assert worker.main() == 0
    json.loads(capsys.readouterr().out)

    assert list(logs.rglob("*")) == []
    assert list(reports.rglob("*")) == []
    assert list(raw.rglob("*")) == []
    assert list(docs_book.rglob("*")) == []
    assert list(docs_entities.rglob("*")) == []
    assert docs_claims.read_text() == "before\n"
    assert source_registry.read_text() == "{}\n"


def test_skip_flags_prevent_corresponding_daily_worker_steps(monkeypatch, tmp_path):
    calls, commit_calls, connection, logs, _reports = _configure_worker(monkeypatch, tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "daily_book_worker.py",
            "run40-skip-flags",
            "--skip-capture",
            "--skip-entity-extraction",
            "--skip-claim-extraction",
            "--skip-docs-entities-update",
            "--skip-docs-claims-update",
            "--skip-source-registry-export",
            "--skip-run-table-update",
            "--skip-vector",
            "--no-commit",
        ],
    )

    assert worker.main() == 0

    command_names = _command_names(calls)
    assert "extract_entities.py" not in command_names
    assert "extract_claims.py" not in command_names
    assert "update_entity_pages.py" not in command_names
    assert "update_claims_page.py" not in command_names
    assert "export_source_registry.py" not in command_names
    assert "build_vector_db.py" not in command_names
    assert commit_calls == []
    assert connection.executed == []
    assert connection.committed is False
    steps = json.loads((logs / "runs" / "run40-skip-flags-steps.json").read_text())["steps"]
    step_names = [Path(s["cmd"][1] if len(s["cmd"]) > 1 else s["cmd"][0]).name for s in steps]
    assert "extract_entities.py" in step_names
    assert "extract_claims.py" in step_names
    assert "update_entity_pages.py" in step_names
    assert "update_claims_page.py" in step_names
    assert "export_source_registry.py" in step_names


def test_no_commit_prevents_commit_and_push(monkeypatch, tmp_path):
    _calls, commit_calls, _connection, _logs, _reports = _configure_worker(monkeypatch, tmp_path)
    monkeypatch.setattr(sys, "argv", ["daily_book_worker.py", "run40-no-commit", "--skip-capture", "--skip-vector", "--skip-run-table-update", "--no-commit"])

    assert worker.main() == 0

    assert commit_calls == []


def test_without_skip_run_table_update_writes_runs_table(monkeypatch, tmp_path):
    _calls, _commit_calls, connection, _logs, _reports = _configure_worker(monkeypatch, tmp_path)
    monkeypatch.setattr(sys, "argv", ["daily_book_worker.py", "run40-run-table", "--skip-capture", "--skip-vector", "--no-commit"])

    assert worker.main() == 0

    assert any("INSERT OR REPLACE INTO runs" in args[0] for args, _kwargs in connection.executed)
    assert connection.committed is True


def test_preflight_only_exits_zero_and_does_not_mutate_runtime_surfaces(monkeypatch, tmp_path, capsys):
    calls, commit_calls, connection, logs, reports = _configure_worker(monkeypatch, tmp_path)
    monkeypatch.setattr(sys, "argv", ["daily_book_worker.py", "run41-preflight", "--preflight-only"])

    assert worker.main() == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["preflight_only"] is True
    assert payload["run_id"] == "run41-preflight"
    assert calls == []
    assert commit_calls == []
    assert connection.executed == []
    assert connection.committed is False
    assert not logs.exists() or list(logs.rglob("*")) == []
    assert not reports.exists() or list(reports.rglob("*")) == []


def test_preflight_only_does_not_commit_or_push(monkeypatch, tmp_path):
    _calls, commit_calls, _connection, _logs, _reports = _configure_worker(monkeypatch, tmp_path)
    monkeypatch.setattr(sys, "argv", ["daily_book_worker.py", "run41-preflight", "--preflight-only", "--no-commit"])

    assert worker.main() == 0

    assert commit_calls == []
