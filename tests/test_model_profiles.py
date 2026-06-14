import hashlib
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_snapshot(path: Path):
    return {str(p.relative_to(ROOT)): sha(p) for p in sorted(path.rglob("*")) if p.is_file()}


def db_counts_and_status_hashes():
    con = sqlite3.connect(f"file:{(ROOT/'.var/book.sqlite').resolve()}?mode=ro", uri=True)
    try:
        counts = {
            "claims": con.execute("SELECT COUNT(*) FROM claims").fetchone()[0],
            "editorial_reviews": con.execute("SELECT COUNT(*) FROM editorial_reviews").fetchone()[0],
            "source_notes": con.execute("SELECT COUNT(*) FROM source_notes").fetchone()[0],
        }
        status = {}
        for name, query in {
            "sources": "SELECT id, quality_score, privacy_publication_status, duplicate_status FROM sources ORDER BY id",
            "claims": "SELECT id, status, publication_decision, contradiction_status FROM claims ORDER BY id",
            "editorial_reviews": "SELECT id, run_id, review_type, status, summary, report_path, created_at FROM editorial_reviews ORDER BY id",
        }.items():
            rows = con.execute(query).fetchall()
            status[name] = hashlib.sha256(json.dumps(rows, sort_keys=True, default=str).encode()).hexdigest()
        return counts, status
    finally:
        con.close()


def test_loads_editorial_reasoning_profile():
    from model_profiles import load_model_profile

    profile = load_model_profile("editorial_reasoning")
    assert profile["provider"] == "copilot"
    assert profile["model"] == "gpt-5.5"
    assert profile["bridge"] == "hermes_cli"
    assert profile["reasoning_effort"] == "high"
    assert profile["task_class"] == "editorial_reasoning"
    assert profile["allow_weak_fallback"] is False
    assert profile["allow_local_fallback"] is False
    assert profile["strict_json_required"] is True


def test_loads_coding_agent_profile():
    from model_profiles import load_model_profile

    profile = load_model_profile("coding_agent")
    assert profile["provider"] == "codex"
    assert profile["model"] == "gpt-5.3-codex"
    assert profile["bridge"] == "codex_cli"
    assert profile["task_class"] == "coding"
    assert profile["allow_weak_fallback"] is False
    assert profile["allow_local_fallback"] is False
    assert profile["strict_json_required"] is False


def test_loads_closed_loop_editorial_profile_with_dispositions():
    from model_profiles import load_model_profile

    profile = load_model_profile("closed_loop_editorial")
    assert profile["provider"] == "copilot"
    assert profile["model"] == "gpt-5.5"
    assert profile["strict_json_required"] is True
    assert profile["allow_weak_fallback"] is False
    assert profile["allow_local_fallback"] is False
    dispositions = set(profile["allowed_dispositions"])
    assert "auto_quarantine" in dispositions
    assert "discovery_only" in dispositions
    assert "needs_more_sources" in dispositions
    assert "eligible_for_review_note_persistence" in dispositions
    assert "blocked_for_publication_by_policy" in dispositions
    assert "source_context_unclear" in dispositions


def test_missing_config_fails_closed_unless_explicit_provider_model(tmp_path):
    from model_profiles import ModelProfileError, resolve_model_profile

    missing = tmp_path / "missing.json"
    with pytest.raises(ModelProfileError):
        resolve_model_profile("editorial_reasoning", config_path=missing)

    explicit = resolve_model_profile(None, provider="copilot", model="gpt-5.5", config_path=missing)
    assert explicit["provider"] == "copilot"
    assert explicit["model"] == "gpt-5.5"
    assert explicit["profile_name"] == "explicit_cli"


def test_missing_profile_fails_closed():
    from model_profiles import ModelProfileError, load_model_profile

    with pytest.raises(ModelProfileError):
        load_model_profile("does_not_exist")


def test_invalid_profile_missing_provider_or_model_fails_closed(tmp_path):
    from model_profiles import ModelProfileError, load_model_profile

    cfg = tmp_path / "bad.json"
    cfg.write_text(json.dumps({
        "profiles": {
            "broken": {
                "provider": "copilot",
                "bridge": "hermes_cli",
                "reasoning_effort": "high",
                "task_class": "editorial_reasoning",
                "allow_weak_fallback": False,
                "allow_local_fallback": False,
                "strict_json_required": True,
            }
        },
        "defaults": {"editorial_reasoning": "broken"},
    }), encoding="utf-8")
    with pytest.raises(ModelProfileError):
        load_model_profile("broken", config_path=cfg)


def test_explicit_provider_model_cli_args_remain_backward_compatible(tmp_path):
    fake = tmp_path / "fake_hermes.py"
    fake.write_text(
        "#!/usr/bin/env python3\n"
        "import json,sys\n"
        "print(json.dumps({'ok': True, 'model': 'gpt-5.5', 'reasoning': 'available'}))\n",
        encoding="utf-8",
    )
    fake.chmod(0o755)
    env = os.environ.copy()
    env.update({
        "TEREFO_LLM_COMMAND": str(fake),
        "TEREFO_LLM_TIMEOUT_SECONDS": "5",
        "TEREFO_LLM_TOOLSETS": "safe",
        "TEREFO_LLM_SOURCE_TAG": "tool",
    })
    res = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "hermes_high_reasoning_json.py"),
            "--canary",
            "--json-only",
            "--output-dir",
            str(tmp_path),
            "--provider",
            "copilot",
            "--model",
            "gpt-5.5",
        ],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
    )
    assert res.returncode == 0, res.stderr + res.stdout
    payload = json.loads(res.stdout)
    assert payload["provider"] == "copilot"
    assert payload["model"] == "gpt-5.5"
    assert payload["stdout_json_valid"] is True


def test_reasoning_profile_cli_metadata_and_strict_json(tmp_path):
    fake = tmp_path / "fake_hermes.py"
    fake.write_text(
        "#!/usr/bin/env python3\n"
        "import json,sys\n"
        "print(json.dumps({'ok': True, 'model': 'gpt-5.5', 'reasoning': 'available'}))\n",
        encoding="utf-8",
    )
    fake.chmod(0o755)
    env = os.environ.copy()
    env.update({"TEREFO_LLM_COMMAND": str(fake), "TEREFO_LLM_TIMEOUT_SECONDS": "5"})
    res = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "hermes_high_reasoning_json.py"),
            "--canary",
            "--json-only",
            "--output-dir",
            str(tmp_path),
            "--reasoning-profile",
            "editorial_reasoning",
        ],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
    )
    assert res.returncode == 0, res.stderr + res.stdout
    payload = json.loads(res.stdout)
    assert payload["provider"] == "copilot"
    assert payload["model"] == "gpt-5.5"
    assert payload["model_profile"] == "editorial_reasoning"
    assert payload["strict_json_required"] is True
    assert payload["weak_local_fallback_refused"] is True


def test_profile_loading_and_helper_do_not_modify_protected_artifacts(tmp_path):
    from model_profiles import load_model_profile

    before_counts, before_status = db_counts_and_status_hashes()
    before_registry = sha(ROOT / "data" / "source_registry.json")
    before_raw = tree_snapshot(ROOT / "raw")
    before_book = tree_snapshot(ROOT / "docs" / "book")
    before_schema = sha(ROOT / "data" / "schema.sql")
    before_worker = sha(ROOT / "scripts" / "daily_book_worker.py")

    assert load_model_profile("editorial_reasoning")["model"] == "gpt-5.5"
    assert load_model_profile("coding_agent")["model"] == "gpt-5.3-codex"
    assert load_model_profile("closed_loop_editorial")["model"] == "gpt-5.5"

    assert db_counts_and_status_hashes() == (before_counts, before_status)
    assert sha(ROOT / "data" / "source_registry.json") == before_registry
    assert tree_snapshot(ROOT / "raw") == before_raw
    assert tree_snapshot(ROOT / "docs" / "book") == before_book
    assert sha(ROOT / "data" / "schema.sql") == before_schema
    assert sha(ROOT / "scripts" / "daily_book_worker.py") == before_worker
