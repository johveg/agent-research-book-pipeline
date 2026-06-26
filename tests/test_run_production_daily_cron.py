import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run_production_daily_cron.sh"


def test_wrapper_exists_executable_and_uses_safe_shell_contract():
    assert SCRIPT.exists()
    assert os.access(SCRIPT, os.X_OK)
    text = SCRIPT.read_text()
    assert "set -euo pipefail" in text
    assert "cd /home/hermoine/agent-research-book-pipeline" in text
    assert "TZ=Europe/Oslo" in text
    assert "RUN_ID=\"production-daily-$(TZ=Europe/Oslo date +%Y%m%d)\"" in text
    assert "${LOG_DIR}/${RUN_ID}.log" in text
    assert "${LOG_DIR}/${RUN_ID}.cron.out" in text
    assert "${LOG_DIR}/${RUN_ID}.cron.err" in text
    assert "WRAPPER_INVOCATION_ID" in text
    assert "RUN_STARTED_AT_UNIX_S" in text
    assert "run_finished_at_unix_s" in text
    assert "PYTHONPATH" in text
    assert "flock" in text
    assert "closed_loop_production_scheduler.py" in text
    assert "--wrapper-invocation-id" in text
    assert "--run-started-at-unix-s" in text
    assert "--install-schedule-after-success" not in text
    assert "reports/telegram/production-daily-latest.md" in text
    assert "AL-Hermoine-OPS" in text
    assert "telegram:Marius" not in text


def test_wrapper_dry_run_reports_command_without_execution():
    proc = subprocess.run([str(SCRIPT), "--dry-run"], cwd=ROOT, text=True, capture_output=True)
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "production-daily-" in proc.stdout
    assert "closed_loop_production_scheduler.py" in proc.stdout
    assert "dry_run" in proc.stdout
