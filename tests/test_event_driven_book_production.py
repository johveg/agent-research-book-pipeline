import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_script(name: str):
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def write_contract(tmp_path: Path) -> Path:
    contract = tmp_path / "contract.json"
    contract.write_text(json.dumps({
        "chapters": {
            "agent_runtime_security": {
                "title": "Agent Runtime Security",
                "target_path": "docs/book/agent-runtime-security.md",
                "topics": ["agent runtime security", "sandbox", "tool permission", "runtime"]
            },
            "browser_agents": {
                "title": "Browser Agents",
                "target_path": "docs/book/browser-agents.md",
                "topics": ["browser agents", "browser automation", "web automation"]
            },
        }
    }), encoding="utf-8")
    return contract


def packet(**overrides):
    data = {
        "packet_id": "packet-runtime-security-1",
        "title": "Agent runtime sandboxing",
        "summary": "New material describes sandboxed agent runtimes, tool permission boundaries, and browser automation caveats.",
        "topics": ["agent runtime security", "sandbox", "tool permission"],
        "evidence_strength": "corroborated",
        "publication_safety": "public_summary_only",
        "privacy_status": "public",
        "contradiction_status": "none",
        "source_ids": ["src1", "src2"],
        "claim_ids": ["claim1"],
        "safe_summary": "Corroborated public sources support a cautious runtime security update.",
    }
    data.update(overrides)
    return data


def test_chapter_router_fans_out_existing_update_and_research_gap(tmp_path):
    router = load_script("chapter_router")
    result = router.route_packet(packet(), router.load_chapters(write_contract(tmp_path)))
    event_types = [event["event_type"] for event in result["events"]]
    assert "chapter.update.requested" in event_types
    update = next(event for event in result["events"] if event["event_type"] == "chapter.update.requested")
    assert update["chapter_id"] == "agent_runtime_security"
    assert update["target_path"] == "docs/book/agent-runtime-security.md"
    assert update["confidence"] >= 0.5
    assert update["payload"]["packet_id"] == "packet-runtime-security-1"
    assert all(event["human_in_loop_dependency_added"] is False for event in result["events"])


def test_chapter_router_requests_new_chapter_when_no_existing_fit(tmp_path):
    router = load_script("chapter_router")
    result = router.route_packet(packet(
        packet_id="packet-eval-harness-1",
        title="Evaluation Harnesses",
        summary="Independent evaluation harnesses are emerging as a distinct lifecycle concern for autonomous agents.",
        topics=["evaluation harness", "benchmark", "test harness"],
    ), router.load_chapters(write_contract(tmp_path)))
    creation = next(event for event in result["events"] if event["event_type"] == "chapter.creation.requested")
    assert creation["chapter_id"] == "evaluation_harnesses"
    assert creation["target_path"] == "docs/book/evaluation-harnesses.md"
    assert creation["payload"]["reason_new_chapter_needed"]


def test_router_defers_weak_or_social_only_material_without_chapter_mutation(tmp_path):
    router = load_script("chapter_router")
    result = router.route_packet(packet(evidence_strength="weak", source_ids=["linkedin:1"], topics=["browser agents"]), router.load_chapters(write_contract(tmp_path)))
    assert [event["event_type"] for event in result["events"]] == ["evidence.packet.deferred", "research_gap.detected"]
    assert result["events"][0]["payload"]["no_book_mutation"] is True


def test_chapter_update_worker_produces_patch_proposal_without_mutating_docs(tmp_path):
    worker = load_script("chapter_update_worker")
    docs = tmp_path / "docs" / "book"
    docs.mkdir(parents=True)
    target = docs / "agent-runtime-security.md"
    before = "# Agent Runtime Security\n\nThe central argument of this chapter is that runtime security turns agent autonomy into a bounded operating model. Evidence limits remain visible because the field is still young. References guide the claims. [1]\n\nA second sustained paragraph describes why permission boundaries matter when tools execute external actions. [2]\n\nA third sustained paragraph keeps the discussion cautious and analytical for production operators. [3]\n\nA fourth sustained paragraph connects runtime boundaries to operational verification and references. [1] [2] [3]\n\n## References\n[1] Existing ref.\n[2] Existing ref.\n[3] Existing ref.\n"
    target.write_text(before, encoding="utf-8")
    event = {
        "event_id": "evt-update-1",
        "event_type": "chapter.update.requested",
        "chapter_id": "agent_runtime_security",
        "target_path": "docs/book/agent-runtime-security.md",
        "payload": {"packet": packet()},
    }
    report = worker.build_patch_proposal(event, repo_root=tmp_path, output_dir=tmp_path / "patches")
    assert report["ok"] is True
    assert report["event_type"] == "chapter.patch.proposed"
    assert report["target_path"] == "docs/book/agent-runtime-security.md"
    assert report["patch_json_path"]
    assert target.read_text(encoding="utf-8") == before


def test_chapter_creation_worker_creates_seed_patch_and_nav_instruction_without_mutating_docs(tmp_path):
    worker = load_script("chapter_creation_worker")
    (tmp_path / "docs" / "book").mkdir(parents=True)
    (tmp_path / "mkdocs.yml").write_text("site_name: Test\nnav:\n  - Book:\n      - Existing: book/existing.md\n", encoding="utf-8")
    event = {
        "event_id": "evt-create-1",
        "event_type": "chapter.creation.requested",
        "chapter_id": "evaluation_harnesses",
        "target_path": "docs/book/evaluation-harnesses.md",
        "payload": {"packet": packet(title="Evaluation Harnesses", topics=["evaluation harness", "benchmark"]), "title": "Evaluation Harnesses"},
    }
    report = worker.build_creation_patch(event, repo_root=tmp_path, output_dir=tmp_path / "patches")
    assert report["ok"] is True
    assert report["event_type"] == "chapter.patch.proposed"
    patch = json.loads(Path(report["patch_json_path"]).read_text(encoding="utf-8"))
    assert patch["operation"] == "create_chapter"
    assert patch["nav_entry"]["title"] == "Evaluation Harnesses"
    assert not (tmp_path / "docs" / "book" / "evaluation-harnesses.md").exists()


def test_publication_joiner_blocks_only_changed_chapter_not_unrelated_legacy_chapter(tmp_path):
    joiner = load_script("book_publication_joiner")
    docs = tmp_path / "docs" / "book"
    docs.mkdir(parents=True)
    (docs / "agent-runtime-security.md").write_text("# Agent Runtime Security\n\nOld seed.\n", encoding="utf-8")
    (docs / "legacy.md").write_text("# Legacy\n\n## Current evidence status\n\n- status supported.\n\n## Source/claim mapping\nBullet 1 maps to supported claim.\n", encoding="utf-8")
    (tmp_path / "mkdocs.yml").write_text("site_name: Test\nnav:\n  - Book:\n      - Agent Runtime Security: book/agent-runtime-security.md\n      - Legacy: book/legacy.md\n", encoding="utf-8")
    proposal = tmp_path / "proposal.json"
    proposal.write_text(json.dumps({
        "event_type": "chapter.patch.proposed",
        "event_id": "evt-update-1",
        "chapter_id": "agent_runtime_security",
        "target_path": "docs/book/agent-runtime-security.md",
        "operation": "update_chapter",
        "proposed_markdown": "# Agent Runtime Security\n\nThe central argument of this chapter is that secure agent runtimes transform autonomous execution into bounded, inspectable operation. The evidence limits are important: current public sources describe sandboxing and permission boundaries unevenly, so this chapter treats them as operational design patterns rather than settled standards. References anchor the discussion without exposing raw collection material. [1]\n\nA second sustained paragraph explains how tool permissions shape the agent loop. Runtime policies define which tools may act, which data may cross boundaries, and which actions require verification before execution. This matters for browser agents and computer-use agents because they can touch public interfaces directly. [2]\n\nA third sustained paragraph connects sandboxing to observability. A production runtime needs logs, approvals, and recovery paths that let operators understand why a tool call was allowed or denied. The chapter therefore presents security as a continuous operating constraint, not a one-time checklist. [3]\n\nA fourth sustained paragraph keeps the claims cautious. These mechanisms reduce risk but do not eliminate failure modes such as prompt injection, overbroad credentials, or unsafe fallback behavior. The practical conclusion is that agent security must combine runtime limits, evidence-aware monitoring, and explicit escalation paths. [1] [2] [3]\n\n## References\n[1] Public source.\n[2] Public source.\n[3] Public source.\n",
        "citation_map": {"1": ["src1"], "2": ["src2"], "3": ["src3"]},
        "evidence_refs": ["src1", "src2", "src3"],
    }), encoding="utf-8")
    report = joiner.apply_patch_proposals([proposal], repo_root=tmp_path, apply=True, run_id="test-run", output_dir=tmp_path / "reports")
    assert report["ok"] is True
    assert report["changed_files"] == ["docs/book/agent-runtime-security.md"]
    assert report["all_chapters_public_proof_blocking"] is False
    assert report["full_manuscript_proof"]["ok"] is False
    assert "legacy" in report["full_manuscript_proof"]["failed_chapters"]
    assert (docs / "agent-runtime-security.md").read_text(encoding="utf-8").startswith("# Agent Runtime Security")


def test_scheduler_event_driven_mode_invokes_router_and_joiner_without_old_one_canary(monkeypatch, tmp_path):
    scheduler = load_script("closed_loop_production_scheduler")
    calls = []
    def fake_run(cmd, **kw):
        calls.append(cmd)
        return {"returncode": 0, "stdout": '{"ok": true}', "stderr": ""}
    monkeypatch.setattr(scheduler, "run_cmd", fake_run)
    monkeypatch.setattr(scheduler, "append_event", lambda *a, **kw: {"event_type": kw.get("event_type", "event")})
    monkeypatch.setattr(scheduler, "db_counts", lambda: {"source_notes": 1, "claims": 2})
    monkeypatch.setattr(scheduler, "summarize_json", lambda path: {"ok": True, "llm_used": True, "changed_files": ["docs/book/agent-runtime-security.md"], "full_manuscript_proof": {"ok": False, "failed_chapters": ["legacy"]}} if "event-driven-publication" in str(path) else {})
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
        "event_driven_book_production_enabled": True,
        "max_substantive_book_updates_per_run": 5,
        "allow_daily_status_only_update": True,
        "allowed_book_targets": ["docs/book/"],
        "blocked_paths": ["raw/", "data/schema.sql"],
        "blocked_unless_explicit_profile": ["data/source_registry.json", "docs/entities/", "docs/research/claims.md", ".var/book.sqlite"],
        "default_disposition_on_failure": "production_daily_failed_closed",
        "default_disposition_on_no_safe_promotions": "publish_daily_no_safe_promotions",
        "model_gate": {"provider": "copilot", "model": "gpt-5.5", "bridge": "hermes_cli", "reasoning_profile": "closed_loop_editorial", "strict_json": True, "weak_local_fallback": False},
    }
    report = scheduler.execute_once(
        run_id="event-run",
        config=cfg,
        output_json=tmp_path / "out.json",
        output_md=tmp_path / "out.md",
        telegram_status=tmp_path / "telegram.md",
        allow_raw_collection=True,
        allow_extraction=True,
        allow_evidence_promotion=True,
        allow_author_editor_redteam=True,
        allow_guarded_book_publication=True,
        allow_daily_status_fallback=True,
    )
    flat = "\n".join(" ".join(map(str, c)) for c in calls)
    assert "book_event_dispatcher.py" in flat
    assert "book_publication_joiner.py" in flat
    assert "closed_loop_publication_orchestrator.py" not in flat
    assert report["event_driven_book_production_used"] is True
    assert report["all_chapters_public_proof_blocking"] is False
