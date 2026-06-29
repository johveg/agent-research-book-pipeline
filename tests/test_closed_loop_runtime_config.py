import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "closed_loop_runtime.json"


def load_config():
    return json.loads(CONFIG.read_text())


def test_runtime_config_enables_production_daily_closed_loop():
    cfg = load_config()
    assert cfg["closed_loop_enabled"] is True
    assert cfg["production_daily_enabled"] is True
    assert cfg["daily_schedule_enabled"] is True


def test_runtime_config_has_no_routine_human_or_weak_fallback_dependency():
    cfg = load_config()
    assert cfg["human_in_loop_required"] is False
    assert cfg["weak_local_fallback_allowed"] is False


def test_runtime_config_requires_gpt55_for_authoring_and_publication_gate():
    cfg = load_config()
    assert cfg["gpt55_required_for_author_editor_redteam"] is True
    assert cfg["gpt55_required_for_publication_gate"] is True
    assert cfg["model_gate"] == {
        "provider": "copilot",
        "model": "gpt-5.5",
        "bridge": "hermes_cli",
        "reasoning_profile": "closed_loop_editorial",
        "strict_json": True,
        "weak_local_fallback": False,
    }


def test_runtime_config_requires_verification_and_event_driven_bounded_updates():
    cfg = load_config()
    assert cfg["mutation_guard_required"] is True
    assert cfg["citation_verification_required"] is True
    assert cfg["mkdocs_strict_required"] is True
    assert cfg["event_driven_book_production_enabled"] is True
    assert cfg["max_substantive_book_updates_per_run"] >= 1
    assert cfg["max_existing_chapter_updates_per_window"] >= 1
    assert cfg["max_new_seed_chapters_per_window"] >= 1
    assert cfg["daily_status_fallback_enabled"] is True
    assert cfg["allow_daily_status_only_update"] is True


def test_runtime_config_blocks_high_risk_paths_without_profile():
    cfg = load_config()
    assert "raw/" in cfg["blocked_paths"]
    assert "data/schema.sql" in cfg["blocked_paths"]
    for path in ["data/source_registry.json", "docs/entities/", "docs/research/claims.md", ".var/book.sqlite"]:
        assert path in cfg["blocked_unless_explicit_profile"]
