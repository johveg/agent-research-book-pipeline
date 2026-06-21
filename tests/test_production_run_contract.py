import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "production_run_contract.py"


def load_module():
    spec = importlib.util.spec_from_file_location("production_run_contract", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def make_repo(tmp_path, run_id="production-daily-20260617", with_log=True, with_cron=True, json_payload=None):
    (tmp_path / "logs" / "runs").mkdir(parents=True)
    (tmp_path / "reports" / "editorial").mkdir(parents=True)
    (tmp_path / "reports" / "telegram").mkdir(parents=True)
    if with_log:
        (tmp_path / "logs" / "runs" / f"{run_id}.log").write_text("started\nfinished\n")
    if with_cron:
        (tmp_path / "logs" / "runs" / f"{run_id}.cron.out").write_text("out\n")
        (tmp_path / "logs" / "runs" / f"{run_id}.cron.err").write_text("")
    payload = {
        "run_id": run_id,
        "status": "production_daily_completed",
        "severity": "success",
        "disposition": "production_daily_completed",
        "final_disposition": "production_daily_completed",
        "run_started_at_unix_s": 1781674200,
        "run_finished_at_unix_s": 1781674300,
        "duration_seconds": 100,
        "emitted_at_unix_s": 1781674300,
        "emitted_at_unix_ms": 1781674300000,
        "emitted_at_utc_iso": "2026-06-17T03:31:40Z",
        "emitted_at_oslo_iso": "2026-06-17T05:31:40+02:00",
        "target_channel": "AL-Hermoine-OPS",
        "fallback_channel_used": False,
        "production_execution_attempted": True,
        "production_execution_completed": True,
        "failed_closed_reason": None,
        "wrapper_invocation_id": "wrapper-abc",
        "git_branch": "main",
        "git_commit": "abc123",
    }
    if json_payload:
        payload.update(json_payload)
    (tmp_path / "reports" / "editorial" / f"{run_id}-production-execute-once.json").write_text(json.dumps(payload))
    (tmp_path / "reports" / "editorial" / f"{run_id}-production-execute-once.md").write_text("# report\n")
    (tmp_path / "reports" / "telegram" / "production-daily-latest.md").write_text("# status\n")
    return tmp_path


def test_reports_without_log_are_failed_closed(tmp_path):
    mod = load_module()
    repo = make_repo(tmp_path, with_log=False)
    result = mod.validate_run_contract(repo, "production-daily-20260617")
    assert result["status"] == "production_daily_failed_closed"
    assert "missing_required_artifact:logs/runs/production-daily-20260617.log" in result["failed_closed_reasons"]
    assert result["completed"] is False


def test_reports_with_null_start_finish_are_failed_closed(tmp_path):
    mod = load_module()
    repo = make_repo(tmp_path, json_payload={"run_started_at_unix_s": None, "run_finished_at_unix_s": None})
    result = mod.validate_run_contract(repo, "production-daily-20260617")
    assert result["status"] == "production_daily_failed_closed"
    assert "missing_required_field:run_started_at_unix_s" in result["failed_closed_reasons"]
    assert "missing_required_field:run_finished_at_unix_s" in result["failed_closed_reasons"]


def test_completed_requires_all_required_artifacts(tmp_path):
    mod = load_module()
    repo = make_repo(tmp_path)
    result = mod.validate_run_contract(repo, "production-daily-20260617")
    assert result["status"] == "production_daily_completed"
    assert result["completed"] is True
    assert result["failed_closed_reasons"] == []


def test_cron_out_err_alone_are_insufficient(tmp_path):
    mod = load_module()
    repo = make_repo(tmp_path, with_log=False)
    (repo / "reports" / "editorial" / "production-daily-20260617-production-execute-once.json").unlink()
    (repo / "reports" / "editorial" / "production-daily-20260617-production-execute-once.md").unlink()
    result = mod.validate_run_contract(repo, "production-daily-20260617")
    assert result["status"] == "production_daily_failed_closed"
    assert result["completed"] is False
    assert any(r.startswith("missing_required_artifact:reports/editorial") for r in result["failed_closed_reasons"])


def test_failed_closed_is_eligible_for_self_heal_if_due_and_retry_limit_not_exceeded(tmp_path):
    mod = load_module()
    repo = make_repo(tmp_path, with_log=False)
    result = mod.validate_run_contract(repo, "production-daily-20260617", due=True, retry_count=0, retry_limit=1)
    assert result["status"] == "production_daily_failed_closed"
    assert result["self_heal_eligible"] is True


def test_no_fake_success_accepted(tmp_path):
    mod = load_module()
    repo = make_repo(tmp_path, json_payload={"production_execution_attempted": False, "production_execution_completed": True})
    result = mod.validate_run_contract(repo, "production-daily-20260617")
    assert result["status"] == "production_daily_failed_closed"
    assert "completed_without_attempt" in result["failed_closed_reasons"]
    assert result["completed"] is False


def test_successful_wrapper_run_accepts_json_contract_paths_when_shell_logs_not_committed(tmp_path):
    mod = load_module()
    run_id = "production-daily-manual-20260621T044656Z"
    repo = make_repo(tmp_path, run_id=run_id, with_cron=False, json_payload={
        "log_path": f"logs/runs/{run_id}.log",
        "cron_out_path": f"logs/runs/{run_id}.cron.out",
        "cron_err_path": f"logs/runs/{run_id}.cron.err",
    })

    result = mod.validate_run_contract(repo, run_id)

    assert result["status"] == "production_daily_completed"
    assert result["completed"] is True
    assert result["failed_closed_reasons"] == []


def test_successful_run_may_have_null_failed_closed_reason(tmp_path):
    mod = load_module()
    repo = make_repo(tmp_path, json_payload={"failed_closed_reason": None})

    result = mod.validate_run_contract(repo, "production-daily-20260617")

    assert result["status"] == "production_daily_completed"
    assert "missing_required_field:failed_closed_reason" not in result["failed_closed_reasons"]
