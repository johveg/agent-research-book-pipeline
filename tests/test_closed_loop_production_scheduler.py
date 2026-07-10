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
    assert "CRON_TZ=Europe/Oslo" in out.read_text()
    assert "run_production_daily_cron.sh" in report["schedule_command"]
    assert "closed_loop_production_scheduler.py" not in out.read_text()
    assert "crontab" in report["install_command"]


def test_execute_once_starts_ledger_probes_worker_invokes_daily_runner_and_orchestrator(monkeypatch, tmp_path):
    mod = load_module()
    calls = []
    def fake_run(cmd, **kw):
        calls.append(cmd)
        if any("daily_book_worker.py" in str(part) for part in cmd) and "--print-capabilities-json" not in cmd:
            return {"returncode": 0, "stdout": '{"ok": true, "all_chapter_public_proof_ok": true, "chapter_revision_policy_executed": true}', "stderr": ""}
        return {"returncode": 0, "stdout": '{"ok": true, "llm_used": true, "publication_status": "substantive_canary_applied", "docs_book_applied": true, "daily_status_fallback_applied": false}', "stderr": ""}
    monkeypatch.setattr(mod, "run_cmd", fake_run)
    monkeypatch.setattr(mod, "append_event", lambda *a, **kw: {"event_type": kw.get("event_type", "event")})
    monkeypatch.setattr(mod, "db_counts", lambda: {"source_notes": 1, "claims": 2, "editorial_reviews": 3})
    def fake_summary(path):
        text = str(path)
        if "guarded-book-publication" in text:
            return {"ok": True, "docs_book_update_applied": True, "chapter_rewrite_applied": True, "append_only_publication_refused": True}
        return {"ok": True, "llm_used": True, "publication_status": "substantive_canary_applied", "docs_book_applied": True, "daily_status_fallback_applied": False, "publish_packet_count": 1, "disposition_counts": {}}
    monkeypatch.setattr(mod, "summarize_json", fake_summary)
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
        wrapper_invocation_id="wrapper-test",
        run_started_at_unix_s=1781674200,
    )
    flat = "\n".join(" ".join(map(str, c)) for c in calls)
    assert "daily_book_worker.py" in flat or "closed_loop_daily_runner.py" in flat
    assert "closed_loop_publication_orchestrator.py" in flat
    assert report["event_ledger_attempt_started"] is True
    assert report["daily_worker_capability_probe_ok"] is True
    worker_call = next(c for c in calls if "daily_book_worker.py" in " ".join(map(str, c)) and "--print-capabilities-json" not in c)
    assert "--run-chapter-revision-policy" in worker_call
    assert "--run-all-chapter-public-proof" in worker_call
    assert report["chapter_revision_policy_gate_invoked"] is True
    assert report["all_chapter_public_proof_gate_invoked"] is True
    assert report["all_chapter_public_proof_gate_ok"] is True
    assert report["publication_orchestrator_invoked"] is True
    assert report["telegram_status_written"] is True
    assert report["production_execution_attempted"] is True
    assert report["production_execution_completed"] is True
    assert report["run_started_at_unix_s"] == 1781674200
    assert report["run_finished_at_unix_s"] is not None
    assert report["duration_seconds"] >= 0
    assert report["wrapper_invocation_id"] == "wrapper-test"


def test_build_event_driven_evidence_packets_consumes_linkedin_catalogue_safely(monkeypatch, tmp_path):
    mod = load_module()
    monkeypatch.setattr(mod, "ROOT", tmp_path)
    (tmp_path / "data").mkdir()
    (tmp_path / "reports" / "editorial").mkdir(parents=True)
    catalogue = tmp_path / "data" / "linkedin_content_catalogue.jsonl"
    catalogue.write_text(
        "\n".join([
            json.dumps({
                "schema_version": 1,
                "source_platform": "linkedin",
                "status": "catalogued",
                "activity_id": "new-social",
                "ingested_at": "2026-07-10T12:00:00Z",
                "title": "Uncorroborated LinkedIn claim",
                "author": "Example Author",
                "post_text_summary": "Raw social post text should not be copied into the packet body.",
                "book_relevance": {"score": 8, "candidate_chapters": ["Browser Agents"], "claim_or_example": "Social-only discovery item.", "evidence_strength": "discovery-only"},
                "limitations": ["LinkedIn post is social/discovery evidence until corroborated."],
            }),
            json.dumps({
                "schema_version": 1,
                "source_platform": "linkedin",
                "status": "catalogued",
                "activity_id": "older-corroborated",
                "ingested_at": "2026-07-09T12:00:00Z",
                "title": "Primary source checked item",
                "author": "Example Author",
                "post_text_summary": "This raw LinkedIn wording should not be used directly.",
                "book_relevance": {"score": 9, "candidate_chapters": ["Agent Runtime Security"], "claim_or_example": "Corroborated public-source lesson."},
                "wider_web_research": {"assessment": "Primary sources support the narrow lesson.", "primary_sources": ["https://example.com/repo", "https://example.com/docs"]},
            }),
        ]) + "\n",
        encoding="utf-8",
    )

    out = mod.build_event_driven_evidence_packets("run-linkedin", {"max_substantive_book_updates_per_run": 4})
    payload = json.loads(out.read_text(encoding="utf-8"))
    packets = payload["evidence_packets"]

    assert payload["linkedin_catalogue_entries_seen"] == 2
    assert payload["linkedin_catalogue_packet_count"] == 2
    assert packets[0]["packet_id"].endswith("new-social")
    assert packets[0]["evidence_strength"] == "social_only"
    assert packets[0]["no_raw_social_text_publication"] is True
    assert "Raw social post text" not in packets[0]["safe_summary"]
    assert packets[1]["evidence_strength"] == "moderate"
    assert packets[1]["corroboration_status"] == "public_sources_checked"
    assert "https://example.com/repo" in packets[1]["source_ids"]


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
    assert report["production_execution_attempted"] is True
    assert report["production_execution_completed"] is False
    assert report["run_started_at_unix_s"] is not None
    assert report["run_finished_at_unix_s"] is not None
    assert report["failed_closed_reason"] == "runtime_config_failed_closed"


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
    assert payload["production_execution_attempted"] is True
    assert payload["production_execution_completed"] is True
    assert payload["run_started_at_unix_s"] is not None
    assert payload["run_finished_at_unix_s"] is not None
    for key in ["run_id", "status", "severity", "disposition", "duration_seconds", "emitted_at_unix_s", "emitted_at_unix_ms", "emitted_at_utc_iso", "emitted_at_oslo_iso", "target_channel", "fallback_channel_used", "failed_closed_reason", "git_branch", "git_commit"]:
        assert key in payload
    assert telegram.exists()


def test_scheduler_status_reports_include_timestamp_contract(tmp_path):
    mod = load_module()
    out = tmp_path / "status.md"
    report = {"run_id": "production-daily-20260616", "final_disposition": "production_daily_completed", "production_daily_completed": True}
    mod.write_telegram_status(out, report)
    text = out.read_text()
    assert "status_metadata:" in text
    assert "target_channel: AL-Hermoine-OPS" in text


def test_write_telegram_status_syncs_latest_json_with_markdown(tmp_path):
    mod = load_module()
    out = tmp_path / "production-daily-latest.md"
    report = {
        "run_id": "production-daily-20260616",
        "status": "production_daily_completed",
        "final_disposition": "production_daily_completed",
        "production_daily_completed": True,
        "fallback_channel_used": False,
    }
    mod.write_telegram_status(out, report)
    latest_json = out.with_suffix(".json")
    assert latest_json.exists()
    payload = json.loads(latest_json.read_text())
    assert payload["run_id"] == "production-daily-20260616"
    assert payload["status"] == "production_daily_completed"
    assert payload["final_disposition"] == "production_daily_completed"


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
    assert report["target_channel"] == "AL-Hermoine-OPS"
    assert (tmp_path / "telegram.md").read_text().count("status_metadata:") >= 1
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
