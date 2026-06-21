import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DISCOVERY_SCRIPT = ROOT / "scripts" / "chapter_subject_discovery.py"
PAIR_SCRIPT = ROOT / "scripts" / "chapter_research_pair_manager.py"
CONFIG = ROOT / "config" / "chapter_discovery_topics.json"
SCHEDULER = ROOT / "scripts" / "closed_loop_production_scheduler.py"
WORKER = ROOT / "scripts" / "daily_book_worker.py"


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_subject_discovery_proposes_human_approval_for_new_chapter_without_docs_mutation(tmp_path):
    mod = load(DISCOVERY_SCRIPT, "chapter_subject_discovery")
    contract = {
        "chapters": {
            "hermes": {"title": "Hermes", "target_path": "docs/book/02-hermes.md", "topics": ["hermes", "skills"]},
            "loop_engineering": {"title": "Loop Engineering", "target_path": "docs/book/04-loop-engineering.md", "topics": ["loop", "verification"]},
        }
    }
    trends = {
        "candidates": [
            {"term": "agent runtime security", "count": 7, "doc_count": 4, "term_type": "phrase"},
            {"term": "hermes skills", "count": 3, "doc_count": 2, "term_type": "phrase"},
        ]
    }
    proposals = mod.build_subject_proposals(contract, trends, run_id="run-test")
    assert proposals["ok"] is True
    assert proposals["human_approval_required"] is True
    assert proposals["docs_book_changed"] is False
    assert proposals["proposal_count"] == 1
    proposal = proposals["proposals"][0]
    assert proposal["status"] == "pending_human_approval"
    assert proposal["candidate_chapter_id"] == "agent_runtime_security"
    assert proposal["candidate_target_path"] == "docs/book/agent-runtime-security.md"
    assert proposal["recommended_action"] == "ask_human_approval_before_research_lane"
    assert proposal["research_pair"]["linkedin_query"] == '"agent runtime security"'
    assert proposal["research_pair"]["web_query"] == '"agent runtime security" AI agents'
    assert "merge_into_existing_chapter" in proposal["approval_options"]


def test_subject_discovery_config_has_human_approval_and_research_pair_policy():
    data = json.loads(CONFIG.read_text(encoding="utf-8"))
    assert data["human_approval_required_for_new_chapters"] is True
    assert data["auto_publish_new_chapters_without_approval"] is False
    assert data["create_research_pairs_after_approval"] is True
    assert set(data["approval_options"]) >= {"approve_new_chapter", "merge_into_existing_chapter", "monitor_only", "reject"}


def test_research_pair_manager_creates_pairs_only_for_approved_subjects(tmp_path):
    mod = load(PAIR_SCRIPT, "chapter_research_pair_manager")
    config = {
        "schema_version": 1,
        "approved_subjects": [
            {"chapter_id": "agent_runtime_security", "title": "Agent Runtime Security", "status": "approved", "linkedin_query": '"agent runtime security"', "web_query": '"agent runtime security" AI agents'},
            {"chapter_id": "agent_economics", "title": "Agent Economics", "status": "pending_human_approval", "linkedin_query": '"agent economics"', "web_query": '"agent economics" AI agents'},
        ],
    }
    search_config = {"web_queries": ["existing"], "linkedin_queries": ["existing"]}
    queue = {"queue": []}
    updated = mod.apply_approved_subjects(config, search_config, queue)
    assert updated["research_pairs_created"] == 1
    assert '"agent runtime security" AI agents' in updated["search_config"]["web_queries"]
    assert '"agent runtime security"' in updated["search_config"]["linkedin_queries"]
    assert '"agent economics" AI agents' not in updated["search_config"]["web_queries"]
    assert updated["queue"]["queue"][0]["chapter_id"] == "agent_runtime_security"
    assert updated["queue"]["queue"][0]["status"] == "approved_research_lane"
    assert updated["docs_book_changed"] is False


def test_research_pair_manager_cli_updates_search_config_and_queue_after_human_approval(tmp_path):
    discovery_cfg = tmp_path / "chapter_discovery_topics.json"
    search_cfg = tmp_path / "search_config.json"
    queue = tmp_path / "queue.json"
    out = tmp_path / "report.json"
    discovery_cfg.write_text(json.dumps({
        "schema_version": 1,
        "approved_subjects": [{
            "chapter_id": "agent_runtime_security",
            "title": "Agent Runtime Security",
            "status": "approved",
            "linkedin_query": '"agent runtime security"',
            "web_query": '"agent runtime security" AI agents',
        }],
    }))
    search_cfg.write_text(json.dumps({"web_queries": [], "linkedin_queries": []}))
    queue.write_text(json.dumps({"queue": []}))
    proc = subprocess.run([sys.executable, str(PAIR_SCRIPT), "--discovery-config", str(discovery_cfg), "--search-config", str(search_cfg), "--queue-json", str(queue), "--write", "--output-json", str(out)], text=True, capture_output=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert json.loads(search_cfg.read_text())["web_queries"] == ['"agent runtime security" AI agents']
    assert json.loads(queue.read_text())["queue"][0]["chapter_id"] == "agent_runtime_security"
    report = json.loads(out.read_text())
    assert report["human_approval_required"] is True
    assert report["research_pairs_created"] == 1


def test_daily_worker_and_production_scheduler_wire_chapter_subject_discovery():
    worker_text = WORKER.read_text(encoding="utf-8")
    scheduler_text = SCHEDULER.read_text(encoding="utf-8")
    assert "supports_human_approved_chapter_subject_discovery" in worker_text
    assert "chapter_subject_discovery.py" in worker_text
    assert "--run-chapter-subject-discovery" in worker_text
    assert "--run-chapter-subject-discovery" in scheduler_text
    assert "chapter_subject_discovery_invoked" in scheduler_text
