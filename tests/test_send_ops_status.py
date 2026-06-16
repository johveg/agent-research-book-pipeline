import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "send_ops_status.py"
CONTRACT = ROOT / "scripts" / "status_message_contract.py"


def load_module():
    spec = importlib.util.spec_from_file_location("send_ops_status", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def status_file(tmp_path):
    path = tmp_path / "status.json"
    path.write_text(json.dumps({"component": "production_daily_monitor", "run_id": "production-daily-20260616", "status": "production_monitor_ok", "severity": "info", "disposition": "production_monitor_ok"}))
    return path


def test_dry_run_normalizes_to_ops_channel_and_does_not_send(tmp_path):
    mod = load_module()
    sent = []
    report = mod.send_ops_status(status_file(tmp_path), component=None, run_id=None, status=None, severity=None, ops_channel="AL-Hermoine-OPS", dry_run=True, sender=lambda *a, **k: sent.append((a, k)))
    assert report["ok"] is True
    assert report["dry_run"] is True
    assert report["target_channel"] == "AL-Hermoine-OPS"
    assert sent == []


def test_missing_ops_channel_fails_closed(tmp_path):
    mod = load_module()
    with pytest.raises(mod.StatusContractError):
        mod.send_ops_status(status_file(tmp_path), ops_channel="telegram", dry_run=True)


def test_status_metadata_is_injected_and_written(tmp_path):
    mod = load_module()
    out_json = tmp_path / "normalized.json"
    out_md = tmp_path / "normalized.md"
    report = mod.send_ops_status(status_file(tmp_path), ops_channel="AL-Hermoine-OPS", dry_run=True, write_normalized_json=out_json, write_normalized_md=out_md)
    payload = json.loads(out_json.read_text())
    assert report["ok"] is True
    assert isinstance(payload["emitted_at_unix_s"], int)
    assert "status_metadata:" in out_md.read_text()


def test_secrets_are_redacted(tmp_path):
    mod = load_module()
    path = tmp_path / "status.json"
    path.write_text(json.dumps({"component": "c", "run_id": "r", "status": "ops_routing_repaired", "severity": "success", "summary": "password: hunter2 token=secret"}))
    out = tmp_path / "normalized.md"
    mod.send_ops_status(path, ops_channel="AL-Hermoine-OPS", dry_run=True, write_normalized_md=out)
    text = out.read_text()
    assert "hunter2" not in text
    assert "secret" not in text
    assert "[REDACTED]" in text


def test_no_default_home_channel_route_in_cli_dry_run(tmp_path):
    out_json = tmp_path / "normalized.json"
    proc = subprocess.run([
        sys.executable, str(SCRIPT), "--status-file", str(status_file(tmp_path)), "--ops-channel", "AL-Hermoine-OPS", "--dry-run", "--write-normalized-json", str(out_json)
    ], cwd=ROOT, text=True, capture_output=True)
    assert proc.returncode == 0, proc.stderr + proc.stdout
    payload = json.loads(out_json.read_text())
    assert payload["target_channel"] == "AL-Hermoine-OPS"
    assert payload["target_channel"] not in {"telegram", "origin", "local"}
