import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "closed_loop_production_scheduler.py"


def load_module():
    spec = importlib.util.spec_from_file_location("closed_loop_production_scheduler", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def good_config(**overrides):
    cfg = {
        "closed_loop_enabled": True,
        "production_daily_enabled": True,
        "daily_schedule_enabled": True,
        "raw_collection_enabled": True,
        "extraction_enabled": True,
        "evidence_promotion_enabled": True,
        "author_editor_redteam_enabled": True,
        "guarded_book_publication_enabled": True,
        "daily_status_fallback_enabled": True,
        "commit_push_enabled_after_gates": True,
        "telegram_status_enabled": True,
        "human_in_loop_required": False,
        "weak_local_fallback_allowed": False,
        "gpt55_required_for_author_editor_redteam": True,
        "gpt55_required_for_publication_gate": True,
        "mutation_guard_required": True,
        "citation_verification_required": True,
        "mkdocs_strict_required": True,
        "max_substantive_book_updates_per_run": 1,
        "allow_daily_status_only_update": True,
        "allowed_book_targets": ["docs/book/"],
        "blocked_paths": ["raw/", "data/schema.sql"],
        "blocked_unless_explicit_profile": ["data/source_registry.json", "docs/entities/", "docs/research/claims.md", ".var/book.sqlite"],
        "default_disposition_on_failure": "production_daily_failed_closed",
        "default_disposition_on_no_safe_promotions": "publish_daily_no_safe_promotions",
        "model_gate": {"provider": "copilot", "model": "gpt-5.5", "bridge": "hermes_cli", "reasoning_profile": "closed_loop_editorial", "strict_json": True, "weak_local_fallback": False},
    }
    cfg.update(overrides)
    return cfg


def test_validate_runtime_config_accepts_safe_production_config():
    mod = load_module()
    errors = mod.validate_runtime_config(good_config())
    assert errors == []


def test_validate_runtime_config_fails_closed_for_disabled_or_human_or_weak_fallback():
    mod = load_module()
    for override in [
        {"closed_loop_enabled": False},
        {"production_daily_enabled": False},
        {"human_in_loop_required": True},
        {"weak_local_fallback_allowed": True},
        {"gpt55_required_for_author_editor_redteam": False},
        {"gpt55_required_for_publication_gate": False},
    ]:
        assert mod.validate_runtime_config(good_config(**override))


def test_model_gate_requires_copilot_gpt55_strict_no_fallback():
    mod = load_module()
    assert mod.model_gate_errors(good_config()) == []
    bad = good_config(model_gate={"provider": "local", "model": "gpt-4", "bridge": "other", "reasoning_profile": "cheap", "strict_json": False, "weak_local_fallback": True})
    errors = mod.model_gate_errors(bad)
    assert "provider must be copilot" in errors
    assert "model must be gpt-5.5" in errors
    assert any("weak" in e for e in errors)


def test_build_schedule_artifact_is_installable_but_not_fake_installed(tmp_path):
    mod = load_module()
    out = tmp_path / "closed-loop-production-daily.cron.example"
    md = tmp_path / "closed-loop-production-daily.md"
    report = mod.write_schedule_artifacts(run_id="run45", cron_path=out, md_path=md, runtime_config="config/closed_loop_runtime.json")
    assert report["schedule_installed"] is False
    assert report["schedule_installable"] is True
    assert report["schedule_timezone"] == "Europe/Oslo"
    assert "30 5 * * *" in out.read_text()
    assert "closed_loop_production_scheduler.py" in report["schedule_command"]
    assert "crontab" in report["install_command"]


def test_execute_once_starts_ledger_probes_worker_invokes_daily_runner_and_orchestrator(monkeypatch, tmp_path):
    mod = load_module()
    calls = []
    monkeypatch.setattr(mod, "run_cmd", lambda cmd, **kw: calls.append(cmd) or {"returncode": 0, "stdout": '{"ok": true}', "stderr": ""})
    monkeypatch.setattr(mod, "append_event", lambda *a, **kw: {"event_type": kw.get("event_type", "event")})
    monkeypatch.setattr(mod, "db_counts", lambda: {"source_notes": 1, "claims": 2, "editorial_reviews": 3})
    report = mod.execute_once(
        run_id="run45",
        config=good_config(),
        output_json=tmp_path / "exec.json",
        output_md=tmp_path / "exec.md",
        telegram_status=tmp_path / "telegram.md",
        allow_raw_collection=True,
        allow_extraction=True,
        allow_evidence_promotion=True,
        allow_author_editor_redteam=True,
        allow_guarded_book_publication=True,
        allow_daily_status_fallback=True,
        send_telegram_status=True,
    )
    flat = "\n".join(" ".join(map(str, c)) for c in calls)
    assert "daily_book_worker.py" in flat or "closed_loop_daily_runner.py" in flat
    assert "closed_loop_publication_orchestrator.py" in flat
    assert report["event_ledger_attempt_started"] is True
    assert report["daily_worker_capability_probe_ok"] is True
    assert report["publication_orchestrator_invoked"] is True
    assert report["telegram_status_written"] is True


def test_execute_once_fails_closed_when_runtime_invalid(tmp_path):
    mod = load_module()
    report = mod.execute_once(
        run_id="run45",
        config=good_config(production_daily_enabled=False),
        output_json=tmp_path / "exec.json",
        output_md=tmp_path / "exec.md",
        telegram_status=tmp_path / "telegram.md",
    )
    assert report["final_disposition"] == "production_daily_failed_closed"
    assert report["production_daily_completed"] is False


def test_evaluate_gates_requires_verifiers_mkdocs_and_mutation_guard():
    mod = load_module()
    report = {"workspace_verifier_ok": True, "editorial_verifier_ok": True, "citation_verifier_ok": True, "mkdocs_strict_ok": True, "mutation_guard_ok": True, "publication_status": "substantive_canary_applied"}
    assert mod.evaluate_final_gates(report)["ok"] is True
    for key in ["citation_verifier_ok", "mkdocs_strict_ok", "mutation_guard_ok"]:
        bad = dict(report); bad[key] = False
        assert mod.evaluate_final_gates(bad)["ok"] is False


def test_no_human_dependency_terms_in_scheduler_source():
    text = SCRIPT.read_text() if SCRIPT.exists() else ""
    for term in ["human_" + "review_required", "requires_" + "human_review", "manual_" + "approval_required", "editor_" + "must_review"]:
        assert term not in text.lower()


def test_cli_writes_execute_once_reports(tmp_path):
    cfg = tmp_path / "runtime.json"
    cfg.write_text(json.dumps(good_config()))
    out_json = tmp_path / "out.json"
    out_md = tmp_path / "out.md"
    telegram = tmp_path / "telegram.md"
    proc = subprocess.run([
        sys.executable, str(SCRIPT), "--run-id", "run45", "--runtime-config", str(cfg), "--mode", "production_daily", "--execute-once", "--allow-daily-status-fallback", "--output-json", str(out_json), "--output-md", str(out_md), "--telegram-status", str(telegram), "--simulate"
    ], cwd=ROOT, text=True, capture_output=True)
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(out_json.read_text())
    assert payload["final_disposition"] in {"production_daily_completed", "production_daily_failed_closed"}
    assert telegram.exists()


def test_status_only_reports_runtime_schedule_latest_and_push_helper_without_mutation(monkeypatch, tmp_path):
    mod = load_module()
    cfg = tmp_path / "runtime.json"
    cfg.write_text(json.dumps(good_config()))
    latest = tmp_path / "production-daily-20260616-production-execute-once.json"
    latest.write_text(json.dumps({"final_disposition": "production_daily_completed"}))
    monkeypatch.setattr(mod, "ROOT", tmp_path)
    monkeypatch.setattr(mod, "run_cmd", lambda cmd, **kw: {"returncode": 0, "stdout": "30 5 * * * production-daily-%Y%m%d closed_loop_production_scheduler.py\n", "stderr": ""} if cmd[:2] == ["bash", "-lc"] else {"returncode": 0, "stdout": "abc123 HEAD\n", "stderr": ""})
    monkeypatch.setattr(mod, "find_latest_production_report", lambda repo: latest)
    report = mod.production_status_report(cfg, tmp_path / "health.json", tmp_path / "health.md", tmp_path / "telegram.md")
    assert report["mode"] == "production_status"
    assert report["status_only"] is True
    assert report["raw_collection_performed"] is False
    assert report["extraction_performed"] is False
    assert report["gpt55_used"] is False
    assert report["docs_book_update_performed"] is False
    assert report["runtime_config_present"] is True
    assert report["production_daily_enabled"] is True
    assert report["human_in_loop_required"] is False
    assert report["weak_local_fallback_allowed"] is False
    assert report["crontab_schedule_found"] is True
    assert report["latest_production_daily_disposition"] == "production_daily_completed"
    assert report["git_push_helper_path"].endswith("scripts/git_push_with_hermes_key.sh")


def test_status_only_refuses_human_or_weak_fallback(tmp_path):
    mod = load_module()
    cfg = tmp_path / "runtime.json"
    cfg.write_text(json.dumps(good_config(human_in_loop_required=True, weak_local_fallback_allowed=True)))
    report = mod.production_status_report(cfg, tmp_path / "health.json", tmp_path / "health.md", tmp_path / "telegram.md")
    assert report["ok"] is False
    assert "human_in_loop_required_must_be_false" in report["runtime_config_validation_errors"]
    assert "weak_local_fallback_allowed_must_be_false" in report["runtime_config_validation_errors"]


def test_cli_status_only_writes_health_reports(tmp_path):
    cfg = tmp_path / "runtime.json"
    cfg.write_text(json.dumps(good_config()))
    out_json = tmp_path / "health.json"
    out_md = tmp_path / "health.md"
    telegram = tmp_path / "telegram.md"
    proc = subprocess.run([
        sys.executable, str(SCRIPT), "--runtime-config", str(cfg), "--mode", "production_status", "--status-only", "--output-json", str(out_json), "--output-md", str(out_md), "--telegram-status", str(telegram)
    ], cwd=ROOT, text=True, capture_output=True)
    assert proc.returncode in {0, 2}
    payload = json.loads(out_json.read_text())
    assert payload["mode"] == "production_status"
    assert payload["gpt55_used"] is False
    assert telegram.exists()
