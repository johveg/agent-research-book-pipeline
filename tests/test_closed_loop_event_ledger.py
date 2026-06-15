import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import closed_loop_event_ledger as ledger  # noqa: E402


def test_append_event_writes_jsonl_and_load_events_reads_it(tmp_path):
    path = tmp_path / "events.jsonl"

    event = ledger.append_event(
        path,
        run_id="run41",
        attempt_id="attempt-1",
        event_type="attempt_started",
        mode="preflight_only",
        disposition="safe_reports_only",
        status="started",
        payload={"hello": "world"},
        command_contract_hash="abc123",
    )

    assert path.exists()
    raw = [json.loads(line) for line in path.read_text().splitlines()]
    assert raw == [event]
    loaded = ledger.load_events(path)
    assert loaded == [event]
    assert event["event_id"]
    assert event["timestamp"]
    assert event["human_in_loop_dependency_added"] is False


def test_idempotency_key_is_deterministic():
    first = ledger.compute_idempotency_key("run41", "preflight_only", "safe_reports_only", "stage", "hash")
    second = ledger.compute_idempotency_key("run41", "preflight_only", "safe_reports_only", "stage", "hash")
    other = ledger.compute_idempotency_key("run41", "preflight_only", "safe_reports_only", "other", "hash")

    assert first == second
    assert first != other


def test_duplicate_detection_finds_identical_completed_attempt(tmp_path):
    path = tmp_path / "events.jsonl"
    key = ledger.compute_idempotency_key("run41", "preflight_only", "safe_reports_only", "attempt_completed", "hash")
    ledger.append_event(
        path,
        run_id="run41",
        attempt_id="attempt-1",
        event_type="attempt_completed",
        mode="preflight_only",
        disposition="safe_reports_only",
        status="completed",
        payload={},
        idempotency_key=key,
    )

    duplicate = ledger.detect_duplicate_event(
        ledger.load_events(path),
        run_id="run41",
        attempt_id="attempt-1",
        idempotency_key=key,
        completed_only=True,
    )

    assert duplicate is not None
    assert duplicate["event_type"] == "attempt_completed"


def test_record_helpers_write_required_event_types_and_false_human_loop(tmp_path):
    path = tmp_path / "events.jsonl"
    common = dict(
        ledger_path=path,
        run_id="run41",
        attempt_id="attempt-1",
        mode="preflight_only",
        disposition="safe_reports_only",
        command_contract_hash="hash",
    )

    ledger.record_attempt_started(**common, payload={})
    ledger.record_capability_probe(**common, ok=True, payload={"ok": True})
    ledger.record_mutation_guard_before(**common, payload={"snapshot": "before"})
    ledger.record_worker_preflight_execution(**common, status="started", payload={})
    ledger.record_worker_preflight_execution(**common, status="completed", payload={"returncode": 0})
    ledger.record_mutation_guard_after(**common, payload={"snapshot": "after"})
    ledger.record_mutation_guard_result(**common, ok=True, payload={"ok": True})
    ledger.record_attempt_completed(**common, payload={})
    ledger.record_attempt_failed(**common, payload={"reason": "test"})

    events = ledger.load_events(path)
    types = [event["event_type"] for event in events]
    assert types == [
        "attempt_started",
        "capability_probe_passed",
        "mutation_guard_before_snapshot",
        "worker_preflight_execution_started",
        "worker_preflight_execution_completed",
        "mutation_guard_after_snapshot",
        "mutation_guard_compare_passed",
        "attempt_completed",
        "attempt_failed",
    ]
    assert all(event["human_in_loop_dependency_added"] is False for event in events)


def test_write_event_ledger_report_summarizes_events(tmp_path):
    path = tmp_path / "events.jsonl"
    report = tmp_path / "ledger-report.md"
    ledger.record_attempt_started(
        ledger_path=path,
        run_id="run41",
        attempt_id="attempt-1",
        mode="preflight_only",
        disposition="safe_reports_only",
        command_contract_hash="hash",
        payload={},
    )

    summary = ledger.write_event_ledger_report(path, report)

    assert summary["event_count"] == 1
    assert summary["event_types"] == {"attempt_started": 1}
    assert report.exists()
    assert "attempt_started" in report.read_text()
