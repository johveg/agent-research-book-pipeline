import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "hermes_high_reasoning_json.py"


def make_fake_command(tmp_path, body, sleep=None):
    p = tmp_path / "fake_hermes.py"
    lines = ["#!/usr/bin/env python3", "import sys, time"]
    if sleep:
        lines.append(f"time.sleep({sleep})")
    lines.append(body)
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    p.chmod(0o755)
    return str(p)


def run_helper(tmp_path, fake_command, *args, timeout="5"):
    env = os.environ.copy()
    env.update({
        "TEREFO_LLM_COMMAND": fake_command,
        "TEREFO_LLM_TIMEOUT_SECONDS": timeout,
        "TEREFO_LLM_PROVIDER": "copilot",
        "TEREFO_LLM_REASONING_MODEL": "gpt-5.5",
        "TEREFO_LLM_TOOLSETS": "safe",
        "TEREFO_LLM_SOURCE_TAG": "tool",
    })
    return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=ROOT, env=env, text=True, capture_output=True)


def test_canary_parses_valid_json_from_mocked_hermes(tmp_path):
    fake = make_fake_command(tmp_path, "print('{\"ok\":true,\"model\":\"gpt-5.5\",\"reasoning\":\"available\"}')")
    res = run_helper(tmp_path, fake, "--canary", "--json-only", "--output-dir", str(tmp_path))
    assert res.returncode == 0, res.stderr + res.stdout
    payload = json.loads(res.stdout)
    assert payload["ok"] is True
    assert payload["llm_used"] is True
    assert payload["reasoning_status"] == "high_reasoning_used"
    assert payload["parsed_json"] == {"ok": True, "model": "gpt-5.5", "reasoning": "available"}
    assert payload["stdout_json_valid"] is True
    assert "secret" not in res.stdout.lower()


def test_invalid_json_fails_closed(tmp_path):
    fake = make_fake_command(tmp_path, "print('not json')")
    res = run_helper(tmp_path, fake, "--canary", "--json-only", "--output-dir", str(tmp_path))
    assert res.returncode != 0
    payload = json.loads(res.stdout)
    assert payload["ok"] is False
    assert payload["stdout_json_valid"] is False
    assert "invalid_json" in payload["error"]


def test_nonzero_exit_fails_closed_and_redacts_secret_like_values(tmp_path):
    fake = make_fake_command(tmp_path, "print('token=sk-abc123', file=sys.stderr); sys.exit(7)")
    res = run_helper(tmp_path, fake, "--canary", "--json-only", "--output-dir", str(tmp_path))
    assert res.returncode != 0
    payload = json.loads(res.stdout)
    assert payload["ok"] is False
    assert payload["exit_code"] == 7
    assert "sk-abc123" not in json.dumps(payload)
    assert "[REDACTED]" in json.dumps(payload)


def test_timeout_fails_closed(tmp_path):
    fake = make_fake_command(tmp_path, "print('{\"ok\":true}')", sleep=2)
    res = run_helper(tmp_path, fake, "--canary", "--json-only", "--output-dir", str(tmp_path), timeout="1")
    assert res.returncode != 0
    payload = json.loads(res.stdout)
    assert payload["ok"] is False
    assert payload["timed_out"] is True
