import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import daily_book_worker as worker  # noqa: E402
import editorial_pipeline_report as editorial  # noqa: E402


class FakeConnection:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, *args, **kwargs):
        return self

    def commit(self):
        return None


def _configure_worker(monkeypatch, tmp_path, editorial_payload, *, docs_book_dirty=False):
    logs = tmp_path / "logs"
    reports = tmp_path / "reports"
    config = tmp_path / "search_config.json"
    config.write_text(json.dumps({"web_queries": [], "linkedin_queries": []}))
    monkeypatch.setattr(worker, "LOGS", logs)
    monkeypatch.setattr(worker, "REPORTS", reports)
    monkeypatch.setattr(worker, "CONFIG_PATH", config)
    monkeypatch.setattr(worker, "ROOT", tmp_path)
    monkeypatch.setattr(worker, "init_db", lambda: None)
    monkeypatch.setattr(worker, "connect_db", lambda: FakeConnection())
    monkeypatch.setattr(worker, "utc_now", lambda: "2026-06-14T00:00:00Z")
    monkeypatch.setattr(worker, "docs_book_dirty_files", lambda: ["docs/book/preface.md"] if docs_book_dirty else [])

    calls = []

    def fake_run(cmd, log):
        calls.append(cmd)
        name = Path(cmd[1] if len(cmd) > 1 else cmd[0]).name
        if name == "editorial_pipeline_report.py":
            out = Path(cmd[cmd.index("--json-out") + 1])
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(editorial_payload))
            return {"cmd": cmd, "returncode": 2 if editorial_payload["final_status"] == "blocked" else 0, "stdout_tail": json.dumps(editorial_payload), "stderr_tail": ""}
        return {"cmd": cmd, "returncode": 0, "stdout_tail": "ok", "stderr_tail": ""}

    monkeypatch.setattr(worker, "run", fake_run)
    return calls, logs, reports


def _blocked_editorial_payload():
    return {
        "final_status": "blocked",
        "counts": {"source_counts": {"web": 1}, "entity_count": 1, "claim_counts": {"needs_review": 1}, "source_quality_distribution": {"D": 1}},
        "new_candidate_trends": [{"term": "weak", "decision": "discovery_only"}],
        "claims_promoted": [],
        "claims_rejected": [],
        "chapter_sections_updated": ["book/preface.md"],
        "editor_warnings": [],
        "publication_recommendation": "do_not_publish_chapter_updates",
        "blocked_reasons": ["chapter publication blocked: privacy_uncertainty_or_weak_evidence"],
        "blocked_state_output": {
            "block_reasons": ["privacy_uncertainty_or_weak_evidence"],
            "data_collected": True,
            "data_usable_for_reports": True,
            "data_usable_for_chapter_update": False,
            "chapter_update_allowed": False,
            "chapter_update_skipped_reason": "blocked_for_publication_by_policy",
            "automated_disposition": "safe_reports_only",
            "publication_recommendation": "do_not_publish_chapter_updates",
            "safe_updates_allowed": ["editor reports", "source index updates", "no chapter update notes"],
        },
    }


def test_blocked_editorial_gate_skips_synthesize_and_update_even_when_allowed(monkeypatch, tmp_path):
    calls, logs, reports = _configure_worker(monkeypatch, tmp_path, _blocked_editorial_payload())
    monkeypatch.setattr(sys, "argv", ["daily_book_worker.py", "run14d-blocked", "--skip-capture", "--skip-vector", "--no-commit", "--allow-chapter-updates"])

    assert worker.main() == 0

    command_names = [Path(c[1] if len(c) > 1 else c[0]).name for c in calls]
    assert "synthesize_chapters.py" not in command_names
    assert "update_book_pages.py" not in command_names
    steps = json.loads((logs / "runs" / "run14d-blocked-steps.json").read_text())["steps"]
    synth_step = [s for s in steps if Path(s["cmd"][1]).name == "synthesize_chapters.py"][-1]
    update_step = [s for s in steps if Path(s["cmd"][1]).name == "update_book_pages.py"][-1]
    assert "blocked_for_publication_by_policy" in synth_step["stdout_tail"]
    assert "blocked_for_publication_by_policy" in update_step["stdout_tail"]
    summary = (reports / "daily" / "run14d-blocked.md").read_text()
    assert "chapter_update_status: `skipped`" in summary
    assert "chapter_sections_updated: `[]`" in summary
    assert "automated_disposition: `safe_reports_only`" in summary
    assert "Human review required" not in summary


def test_daily_worker_runs_visual_capture_when_config_enabled(monkeypatch, tmp_path):
    passed = _blocked_editorial_payload()
    passed.update({"final_status": "success", "blocked_reasons": [], "chapter_sections_updated": [], "publication_recommendation": "publish"})
    passed["blocked_state_output"] = {
        "data_collected": True,
        "data_usable_for_reports": True,
        "data_usable_for_chapter_update": True,
        "chapter_update_allowed": False,
        "chapter_update_skipped_reason": "allow_chapter_updates_flag_absent",
        "automated_disposition": "safe_reports_only",
        "publication_recommendation": "do_not_publish_chapter_updates",
    }
    calls, logs, reports = _configure_worker(monkeypatch, tmp_path, passed)
    config = tmp_path / "search_config.json"
    config.write_text(json.dumps({
        "web_queries": ["visual agents"],
        "linkedin_queries": [],
        "visual_capture": {"enabled": True, "mode": "pixelshot", "max_urls_per_run": 3},
    }))
    monkeypatch.setattr(sys, "argv", ["daily_book_worker.py", "run-visual", "--skip-vector", "--no-commit"])

    assert worker.main() == 0

    visual_cmds = [c for c in calls if Path(c[1] if len(c) > 1 else c[0]).name == "capture_visual_daily.py"]
    assert len(visual_cmds) == 1
    visual_cmd = visual_cmds[0]
    assert "--enabled" in visual_cmd
    assert "--from-web-capture-json" in visual_cmd
    assert "--max-urls" in visual_cmd
    assert visual_cmd[visual_cmd.index("--max-urls") + 1] == "3"
    steps = json.loads((logs / "runs" / "run-visual-steps.json").read_text())["steps"]
    assert any(Path(s["cmd"][1]).name == "capture_visual_daily.py" for s in steps)
    summary = (reports / "daily" / "run-visual.md").read_text()
    assert "capture_visual_daily.py" in summary


def test_daily_worker_skips_visual_capture_when_config_disabled(monkeypatch, tmp_path):
    calls, logs, _reports = _configure_worker(monkeypatch, tmp_path, _blocked_editorial_payload())
    config = tmp_path / "search_config.json"
    config.write_text(json.dumps({"web_queries": [], "linkedin_queries": [], "visual_capture": {"enabled": False}}))
    monkeypatch.setattr(sys, "argv", ["daily_book_worker.py", "run-no-visual", "--skip-capture", "--skip-vector", "--no-commit"])

    assert worker.main() == 0

    command_names = [Path(c[1] if len(c) > 1 else c[0]).name for c in calls]
    assert "capture_visual_daily.py" not in command_names
    steps = json.loads((logs / "runs" / "run-no-visual-steps.json").read_text())["steps"]
    assert not any(Path(s["cmd"][1]).name == "capture_visual_daily.py" for s in steps if len(s["cmd"]) > 1)


def test_allow_chapter_updates_absent_skips_chapter_update_even_when_gate_passes(monkeypatch, tmp_path):
    passed = _blocked_editorial_payload()
    passed.update({"final_status": "success", "blocked_reasons": [], "chapter_sections_updated": [], "publication_recommendation": "publish"})
    passed["blocked_state_output"] = {
        "data_collected": True,
        "data_usable_for_reports": True,
        "data_usable_for_chapter_update": True,
        "chapter_update_allowed": False,
        "chapter_update_skipped_reason": "allow_chapter_updates_flag_absent",
        "automated_disposition": "safe_reports_only",
        "publication_recommendation": "do_not_publish_chapter_updates",
    }
    calls, logs, _reports = _configure_worker(monkeypatch, tmp_path, passed)
    monkeypatch.setattr(sys, "argv", ["daily_book_worker.py", "run14d-no-allow", "--skip-capture", "--skip-vector", "--no-commit"])

    assert worker.main() == 0

    command_names = [Path(c[1] if len(c) > 1 else c[0]).name for c in calls]
    assert "synthesize_chapters.py" not in command_names
    assert "update_book_pages.py" not in command_names
    steps = json.loads((logs / "runs" / "run14d-no-allow-steps.json").read_text())["steps"]
    assert any("allow_chapter_updates_flag_absent" in s["stdout_tail"] for s in steps)


def test_blocked_run_with_docs_book_dirty_does_not_commit(monkeypatch, tmp_path):
    _calls, _logs, reports = _configure_worker(monkeypatch, tmp_path, _blocked_editorial_payload(), docs_book_dirty=True)
    commit_calls = []
    monkeypatch.setattr(worker, "git_commit_push", lambda *args, **kwargs: commit_calls.append((args, kwargs)) or {"committed": True, "commit_sha": "bad"})
    monkeypatch.setattr(sys, "argv", ["daily_book_worker.py", "run14d-dirty", "--skip-capture", "--skip-vector", "--allow-chapter-updates"])

    assert worker.main() == 0

    assert commit_calls == []
    summary = (reports / "daily" / "run14d-dirty.md").read_text()
    assert "docs/book has uncommitted changes after blocked run" in summary
    assert "Git commit hash: `not committed`" in summary


def test_editorial_blocked_payload_uses_closed_loop_automated_dispositions():
    payload = _blocked_editorial_payload()
    bso = payload["blocked_state_output"]
    assert bso["data_collected"] is True
    assert bso["data_usable_for_reports"] is True
    assert bso["data_usable_for_chapter_update"] is False
    assert bso["chapter_update_allowed"] is False
    assert bso["chapter_update_skipped_reason"] == "blocked_for_publication_by_policy"
    assert bso["automated_disposition"] in {"auto_quarantine", "discovery_only", "needs_more_sources", "caveat_only", "exclude_from_publication", "safe_reports_only", "blocked_for_publication_by_policy"}
    assert "human_review_required" not in bso


def test_policy_disposition_helpers_map_privacy_weak_social_and_raw_capture():
    assert editorial.automated_disposition_for_reason("privacy review requires human review for some sources") == "auto_quarantine"
    assert editorial.automated_disposition_for_reason("trend promotion with weak evidence") == "needs_more_sources"
    assert editorial.automated_disposition_for_reason("social-only evidence") == "discovery_only"
    assert editorial.automated_disposition_for_reason("raw capture to chapter prose path") == "exclude_from_publication"
    decision = editorial.publication_decision_model(
        data_collected=True,
        block_reasons=["privacy review requires human review for some sources", "social-only evidence"],
        chapter_requested=True,
    )
    assert decision["data_usable_for_reports"] is True
    assert decision["data_usable_for_chapter_update"] is False
    assert decision["chapter_update_allowed"] is False
    assert decision["chapter_update_skipped_reason"] == "blocked_for_publication_by_policy"
    assert decision["automated_disposition"] in {"auto_quarantine", "safe_reports_only"}
    assert decision["publication_recommendation"] == "do_not_publish_chapter_updates"
