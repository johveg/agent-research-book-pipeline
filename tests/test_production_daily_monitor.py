import importlib.util
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "production_daily_monitor.py"


def load_module():
    spec = importlib.util.spec_from_file_location("production_daily_monitor", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def make_repo(tmp_path, run_id="production-daily-20260616"):
    (tmp_path / "reports" / "editorial").mkdir(parents=True)
    (tmp_path / "reports" / "telegram").mkdir(parents=True)
    (tmp_path / "logs" / "runs").mkdir(parents=True)
    (tmp_path / "logs" / "closed_loop").mkdir(parents=True)
    return tmp_path


def test_today_before_0530_missing_is_not_due_yet(tmp_path):
    mod = load_module()
    repo = make_repo(tmp_path)
    now = datetime(2026, 6, 16, 5, 20, tzinfo=ZoneInfo("Europe/Oslo"))
    report = mod.monitor(repo=repo, date="2026-06-16", timezone_name="Europe/Oslo", expect_schedule_time="05:30", now=now)
    assert report["expected_run_id"] == "production-daily-20260616"
    assert report["status"] == "production_daily_missing_not_due_yet"
    assert report["ok"] is True


def test_today_at_0530_missing_is_after_due_or_running_grace(tmp_path):
    mod = load_module()
    repo = make_repo(tmp_path)
    now = datetime(2026, 6, 16, 5, 30, tzinfo=ZoneInfo("Europe/Oslo"))
    report = mod.monitor(repo=repo, date="2026-06-16", timezone_name="Europe/Oslo", expect_schedule_time="05:30", now=now)
    assert report["status"] in {"production_daily_missing_after_due", "production_daily_running"}


def test_today_after_0530_missing_is_after_due(tmp_path):
    mod = load_module()
    repo = make_repo(tmp_path)
    now = datetime(2026, 6, 16, 6, 20, tzinfo=ZoneInfo("Europe/Oslo"))
    report = mod.monitor(repo=repo, date="2026-06-16", timezone_name="Europe/Oslo", expect_schedule_time="05:30", now=now)
    assert report["status"] == "production_daily_missing_after_due"
    assert report["ok"] is False


def test_0720_missing_is_after_due_not_not_due(tmp_path):
    mod = load_module()
    repo = make_repo(tmp_path)
    now = datetime(2026, 6, 16, 7, 20, tzinfo=ZoneInfo("Europe/Oslo"))
    report = mod.monitor(repo=repo, date="2026-06-16", timezone_name="Europe/Oslo", expect_schedule_time="05:30", now=now)
    assert report["status"] == "production_daily_missing_after_due"


def test_stale_future_next_run_after_due_does_not_create_false_not_due(tmp_path):
    mod = load_module()
    repo = make_repo(tmp_path)
    stale = repo / "reports" / "editorial" / "production-daily-20260615-schedule-install-run45.json"
    stale.write_text(json.dumps({"next_expected_run_time": "2026-06-17T05:30:00+01:00/+02:00 Europe/Oslo"}))
    now = datetime(2026, 6, 16, 7, 20, tzinfo=ZoneInfo("Europe/Oslo"))

    report = mod.monitor(repo=repo, date="2026-06-16", timezone_name="Europe/Oslo", expect_schedule_time="05:30", now=now)

    assert report["schedule_due"] is True
    assert report["status"] == "production_daily_missing_after_due"
    assert report["ok"] is False
    assert "ignored_stale_future_recorded_next_run_due_already_reached" in report["warnings"]


def test_completed_report_is_completed(tmp_path):
    mod = load_module()
    repo = make_repo(tmp_path)
    run_id = "production-daily-20260616"
    (repo / "logs" / "runs" / f"{run_id}.log").write_text("log\n")
    (repo / "logs" / "runs" / f"{run_id}.cron.out").write_text("out\n")
    (repo / "logs" / "runs" / f"{run_id}.cron.err").write_text("")
    report_path = repo / "reports" / "editorial" / f"{run_id}-production-execute-once.json"
    report_path.write_text(json.dumps({
        "run_id": run_id, "status": "production_daily_completed", "severity": "success", "disposition": "production_daily_completed", "final_disposition": "production_daily_completed",
        "run_started_at_unix_s": 1781674200, "run_finished_at_unix_s": 1781674300, "duration_seconds": 100,
        "emitted_at_unix_s": 1781674300, "emitted_at_unix_ms": 1781674300000, "emitted_at_utc_iso": "2026-06-17T03:31:40Z", "emitted_at_oslo_iso": "2026-06-17T05:31:40+02:00",
        "target_channel": "AL-Hermoine-OPS", "fallback_channel_used": False, "production_execution_attempted": True, "production_execution_completed": True, "failed_closed_reason": None,
        "wrapper_invocation_id": "wrapper", "git_branch": "main", "git_commit": "abc123", "production_daily_completed": True
    }))
    (repo / "reports" / "editorial" / f"{run_id}-production-execute-once.md").write_text("# report\n")
    (repo / "reports" / "telegram" / "production-daily-latest.md").write_text("# status\n")
    report = mod.monitor(repo=repo, run_id=run_id, timezone_name="Europe/Oslo")
    assert report["status"] == "production_daily_completed"
    assert report["ok"] is True
    assert report["production_report_json_exists"] is True


def test_report_exists_but_log_missing_is_failed_closed(tmp_path):
    mod = load_module()
    repo = make_repo(tmp_path)
    run_id = "production-daily-20260616"
    report_path = repo / "reports" / "editorial" / f"{run_id}-production-execute-once.json"
    report_path.write_text(json.dumps({"final_disposition": "production_daily_completed", "production_daily_completed": True}))
    (repo / "reports" / "editorial" / f"{run_id}-production-execute-once.md").write_text("# report\n")
    (repo / "reports" / "telegram" / "production-daily-latest.md").write_text("# status\n")
    report = mod.monitor(repo=repo, run_id=run_id, timezone_name="Europe/Oslo")
    assert report["status"] == "production_daily_failed_closed"
    assert report["ok"] is False
    assert any("missing_required_artifact:logs/runs" in w for w in report["warnings"])


def test_failed_report_is_failed_closed(tmp_path):
    mod = load_module()
    repo = make_repo(tmp_path)
    run_id = "production-daily-20260616"
    (repo / "reports" / "editorial" / f"{run_id}-production-execute-once.json").write_text(json.dumps({"final_disposition": "production_daily_failed_closed"}))
    report = mod.monitor(repo=repo, run_id=run_id, timezone_name="Europe/Oslo")
    assert report["status"] == "production_daily_failed_closed"
    assert report["ok"] is False


def test_stale_running_log_older_than_max_age(tmp_path):
    mod = load_module()
    repo = make_repo(tmp_path)
    run_id = "production-daily-20260616"
    log = repo / "logs" / "runs" / f"{run_id}.log"
    log.write_text("started\n")
    old = datetime(2026, 6, 16, 5, 30, tzinfo=ZoneInfo("Europe/Oslo")).timestamp()
    import os
    os.utime(log, (old, old))
    now = datetime(2026, 6, 16, 9, 0, tzinfo=ZoneInfo("Europe/Oslo"))
    report = mod.monitor(repo=repo, run_id=run_id, timezone_name="Europe/Oslo", now=now, max_age_minutes=180)
    assert report["status"] == "production_daily_stale"
    assert report["ok"] is False


def test_fixed_run_id_is_rejected_for_production_monitor(tmp_path):
    mod = load_module()
    repo = make_repo(tmp_path)
    report = mod.monitor(repo=repo, run_id="citation-pipeline-test-20260612", timezone_name="Europe/Oslo")
    assert report["status"] == "production_monitor_failed_closed"
    assert report["ok"] is False
    assert "fixed_run_id_not_allowed" in report["warnings"]


def test_manual_production_daily_run_id_is_accepted_and_completed(tmp_path):
    mod = load_module()
    repo = make_repo(tmp_path)
    run_id = "production-daily-manual-20260615T171122Z"
    (repo / "logs" / "runs" / f"{run_id}.log").write_text("log\n")
    (repo / "logs" / "runs" / f"{run_id}.cron.out").write_text("out\n")
    (repo / "logs" / "runs" / f"{run_id}.cron.err").write_text("")
    (repo / "reports" / "editorial" / f"{run_id}-production-execute-once.json").write_text(
        json.dumps({
            "run_id": run_id, "status": "production_daily_completed", "severity": "success", "disposition": "production_daily_completed", "final_disposition": "production_daily_completed",
            "run_started_at_unix_s": 1781674200, "run_finished_at_unix_s": 1781674300, "duration_seconds": 100,
            "emitted_at_unix_s": 1781674300, "emitted_at_unix_ms": 1781674300000, "emitted_at_utc_iso": "2026-06-17T03:31:40Z", "emitted_at_oslo_iso": "2026-06-17T05:31:40+02:00",
            "target_channel": "AL-Hermoine-OPS", "fallback_channel_used": False, "production_execution_attempted": True, "production_execution_completed": True, "failed_closed_reason": None,
            "wrapper_invocation_id": "wrapper", "git_branch": "main", "git_commit": "abc123", "production_daily_completed": True
        })
    )
    (repo / "reports" / "editorial" / f"{run_id}-production-execute-once.md").write_text("# report\n")
    (repo / "reports" / "telegram" / "production-daily-latest.md").write_text("# status\n")

    report = mod.monitor(repo=repo, run_id=run_id, timezone_name="Europe/Oslo")

    assert report["status"] == "production_daily_completed"
    assert report["ok"] is True
    assert report["old_fixed_run_id_ignored"] is True


def test_monitor_detects_crontab_production_command(monkeypatch, tmp_path):
    mod = load_module()
    repo = make_repo(tmp_path)
    monkeypatch.setattr(mod, "read_crontab", lambda: "CRON_TZ=Europe/Oslo\n30 5 * * * /home/hermoine/terefohealreboa/scripts/run_production_daily_cron.sh")
    report = mod.monitor(repo=repo, run_id="production-daily-20260616", timezone_name="Europe/Oslo")
    assert report["crontab_production_daily_command_found"] is True
    assert "run_production_daily_cron.sh" in report["schedule_command"]


def test_monitor_includes_timestamp_contract_and_ops_channel(tmp_path):
    mod = load_module()
    repo = make_repo(tmp_path)
    out = tmp_path / "telegram.md"
    report = mod.monitor(repo=repo, run_id="production-daily-20260616", timezone_name="Europe/Oslo", telegram_status=out)
    text = out.read_text()
    assert report["target_channel"] == "AL-Hermoine-OPS"
    assert "status_metadata:" in text
    assert "target_channel: AL-Hermoine-OPS" in text


def test_monitor_writes_telegram_fallback_and_json_valid(tmp_path):
    mod = load_module()
    repo = make_repo(tmp_path)
    out = tmp_path / "telegram.md"
    report = mod.monitor(repo=repo, run_id="production-daily-20260616", timezone_name="Europe/Oslo", telegram_status=out)
    assert out.exists()
    json.dumps(report)
    assert "production-daily-20260616" in out.read_text()


def test_cli_json_output(tmp_path):
    repo = make_repo(tmp_path)
    proc = subprocess.run([
        sys.executable, str(SCRIPT), "--repo", str(repo), "--run-id", "production-daily-20260616", "--timezone", "Europe/Oslo", "--json"
    ], text=True, capture_output=True, cwd=ROOT)
    assert proc.returncode in {0, 2}
    payload = json.loads(proc.stdout)
    assert payload["expected_run_id"] == "production-daily-20260616"
    assert payload["target_channel"] == "AL-Hermoine-OPS"
    assert payload["status_metadata"]["target_channel"] == "AL-Hermoine-OPS"
    for key in ["emitted_at_unix_s", "emitted_at_unix_ms", "emitted_at_utc_iso", "emitted_at_oslo_iso", "status", "severity", "disposition"]:
        assert key in payload
        assert payload["status_metadata"][key] == payload[key]
