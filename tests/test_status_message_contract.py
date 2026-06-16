import importlib.util
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "status_message_contract.py"


def load_module():
    spec = importlib.util.spec_from_file_location("status_message_contract", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_timestamp_metadata_uses_machine_readable_epoch_and_iso_fields():
    mod = load_module()
    meta = mod.timestamp_metadata()
    assert isinstance(meta["emitted_at_unix_s"], int)
    assert isinstance(meta["emitted_at_unix_ms"], int)
    assert meta["emitted_at_unix_ms"] >= meta["emitted_at_unix_s"] * 1000
    assert re.match(r"^\d{4}-\d{2}-\d{2}T", meta["emitted_at_utc_iso"])
    assert meta["emitted_at_utc_iso"].endswith("Z") or meta["emitted_at_utc_iso"].endswith("+00:00")
    assert re.match(r"^\d{4}-\d{2}-\d{2}T.*[+-]\d{2}:\d{2}$", meta["emitted_at_oslo_iso"])
    assert meta["timezone"] == "Europe/Oslo"


def test_missing_required_operational_fields_fail_closed():
    mod = load_module()
    for missing in ["component", "run_id", "status", "severity"]:
        payload = {"component": "c", "run_id": "r", "status": "production_monitor_ok", "severity": "info"}
        payload.pop(missing)
        with pytest.raises(mod.StatusContractError):
            mod.normalize_status(payload)


def test_sensitive_strings_are_redacted():
    mod = load_module()
    text = "Authorization: Bearer abc.def.ghi token=secretvalue password: hunter2 TELEGRAM_BOT_TOKEN=123456:ABCdef"
    redacted = mod.redact_sensitive(text)
    assert "abc.def.ghi" not in redacted
    assert "secretvalue" not in redacted
    assert "hunter2" not in redacted
    assert "123456:ABCdef" not in redacted
    assert "[REDACTED]" in redacted


def test_default_target_channel_is_ops_and_non_ops_fails_closed():
    mod = load_module()
    assert mod.load_routing_config()["default_status_channel"] == "AL-Hermoine-OPS"
    payload = {"component": "production_daily_monitor", "run_id": "production-daily-20260616", "status": "production_monitor_ok", "severity": "info"}
    normalized = mod.normalize_status(payload)
    assert normalized["target_channel"] == "AL-Hermoine-OPS"
    with pytest.raises(mod.StatusContractError):
        mod.normalize_status(payload | {"target_channel": "telegram"})


def test_markdown_and_json_include_same_machine_metadata_block():
    mod = load_module()
    payload = {"component": "production_daily_monitor", "run_id": "production-daily-20260616", "status": "production_daily_missing_after_due", "severity": "failure", "disposition": "failed_closed", "repo": str(ROOT)}
    normalized = mod.normalize_status(payload)
    md = mod.render_markdown_status(normalized, title="Status")
    assert "```yaml\nstatus_metadata:" in md
    assert "emitted_at_unix_s:" in md
    assert "component: production_daily_monitor" in md
    rendered_json = json.loads(mod.render_json_status(normalized))
    assert rendered_json["status_metadata"]["target_channel"] == "AL-Hermoine-OPS"
    for key in ["emitted_at_unix_s", "emitted_at_unix_ms", "emitted_at_utc_iso", "emitted_at_oslo_iso", "component", "run_id", "status", "severity", "disposition"]:
        assert rendered_json[key] == normalized[key]
        assert rendered_json["status_metadata"][key] == normalized[key]
