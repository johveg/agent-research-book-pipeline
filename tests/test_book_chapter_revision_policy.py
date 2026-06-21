import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY_SCRIPT = ROOT / "scripts" / "book_chapter_revision_policy.py"
CONTRACT_SCRIPT = ROOT / "scripts" / "book_manuscript_contract.py"
WORKER_SCRIPT = ROOT / "scripts" / "daily_book_worker.py"


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_contract_requires_post_processing_revision_and_new_chapter_decisions():
    mod = load(CONTRACT_SCRIPT, "book_manuscript_contract")
    contract = mod.build_contract()
    policy = contract["autonomous_chapter_revision_policy"]
    assert policy["trigger"] == "after_automatic_collection_and_processing"
    assert policy["existing_chapter_revision"]["required"] is True
    assert policy["existing_chapter_revision"]["integration_style"] == "fluent_refactor_rewrite"
    assert policy["new_chapter_creation"]["required"] is True
    assert policy["new_chapter_creation"]["chapter_creation_mode"] == "automatic_guarded_queue_item"
    queue = mod.build_queue(contract)
    assert all("chapter_revision_decision" in item["required_gates"] for item in queue["queue"])


def test_revision_policy_routes_new_information_to_existing_chapter_with_fluent_rewrite_instruction():
    mod = load(POLICY_SCRIPT, "book_chapter_revision_policy")
    contract = {
        "chapters": {
            "hermes": {"title": "Hermes", "target_path": "docs/book/02-hermes.md", "topics": ["hermes", "skills", "cron"]},
        },
        "autonomous_chapter_revision_policy": mod.DEFAULT_POLICY,
    }
    processed = {
        "processed_information": [
            {"title": "Hermes skill memory update", "summary": "Hermes skills now preserve reusable workflow knowledge.", "topics": ["Hermes", "skills"], "evidence_status": "supported"}
        ]
    }
    plan = mod.build_revision_plan(contract, processed, run_id="test-run")
    assert plan["ok"] is True
    assert plan["revision_required"] is True
    assert plan["new_chapter_required"] is False
    assert plan["existing_chapter_revisions"][0]["chapter_id"] == "hermes"
    assert plan["existing_chapter_revisions"][0]["target_path"] == "docs/book/02-hermes.md"
    assert plan["existing_chapter_revisions"][0]["revision_instruction"] == "refactor_rewrite_for_fluent_integration"
    assert plan["existing_chapter_revisions"][0]["append_only_allowed"] is False
    assert plan["publication_safety_flags"] == mod.FALSE_FLAGS


def test_revision_policy_creates_guarded_new_chapter_when_information_has_no_fit():
    mod = load(POLICY_SCRIPT, "book_chapter_revision_policy")
    contract = {
        "chapters": {
            "hermes": {"title": "Hermes", "target_path": "docs/book/02-hermes.md", "topics": ["hermes"]},
        },
        "autonomous_chapter_revision_policy": mod.DEFAULT_POLICY,
    }
    processed = {
        "processed_information": [
            {"title": "Evaluation Harnesses", "summary": "Independent evaluation harnesses are emerging as a separate lifecycle concern.", "topics": ["evaluation", "harness", "benchmark"], "evidence_status": "supported"}
        ]
    }
    plan = mod.build_revision_plan(contract, processed, run_id="test-run")
    assert plan["ok"] is True
    assert plan["revision_required"] is False
    assert plan["new_chapter_required"] is True
    new_chapter = plan["new_chapter_candidates"][0]
    assert new_chapter["chapter_id"] == "evaluation_harnesses"
    assert new_chapter["target_path"] == "docs/book/evaluation-harnesses.md"
    assert new_chapter["queue_mode"] == "automatic_guarded_new_chapter"
    assert new_chapter["required_gates"] == mod.REQUIRED_GATES
    assert new_chapter["write_docs_book_now"] is False


def test_revision_policy_appends_new_chapter_candidates_to_guarded_queue_without_docs_mutation():
    mod = load(POLICY_SCRIPT, "book_chapter_revision_policy")
    contract = {
        "chapters": {
            "hermes": {"title": "Hermes", "target_path": "docs/book/02-hermes.md", "topics": ["hermes"]},
        },
        "autonomous_chapter_revision_policy": mod.DEFAULT_POLICY,
    }
    queue = {"queue_name": "book_manuscript_production_queue", "queue": []}
    processed = {"processed_information": [{"title": "Evaluation Harnesses", "summary": "Separate evaluation lifecycle concern.", "topics": ["evaluation", "harness"], "evidence_status": "supported"}]}
    plan = mod.build_revision_plan(contract, processed, run_id="test-run")
    updated = mod.apply_new_chapter_candidates_to_queue(queue, plan)
    assert updated["queue"][0]["chapter_id"] == "evaluation_harnesses"
    assert updated["queue"][0]["mode"] == "automatic_guarded_new_chapter"
    assert updated["queue"][0]["target_path"] == "docs/book/evaluation-harnesses.md"
    assert updated["queue"][0]["required_gates"] == mod.REQUIRED_GATES
    assert updated["queue"][0]["status"] == "queued_after_revision_policy"
    assert updated["docs_book_changed"] is False


def test_revision_policy_cli_writes_machine_readable_reports(tmp_path):
    contract = tmp_path / "contract.json"
    processed = tmp_path / "processed.json"
    outj = tmp_path / "plan.json"
    outm = tmp_path / "plan.md"
    contract.write_text(json.dumps({
        "chapters": {"openclaw": {"title": "OpenClaw", "target_path": "docs/book/03-openclaw.md", "topics": ["openclaw"]}},
        "autonomous_chapter_revision_policy": {"trigger": "after_automatic_collection_and_processing"},
    }))
    processed.write_text(json.dumps({"processed_information": [{"title": "OpenClaw update", "summary": "OpenClaw adds guarded operator workflows.", "topics": ["openclaw"], "evidence_status": "supported"}]}))
    proc = subprocess.run([sys.executable, str(POLICY_SCRIPT), "--contract", str(contract), "--processed-json", str(processed), "--run-id", "cli-run", "--output-json", str(outj), "--output-md", str(outm)], text=True, capture_output=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    data = json.loads(outj.read_text())
    assert data["existing_chapter_revisions"][0]["chapter_id"] == "openclaw"
    assert "refactor/rewrite" in outm.read_text(encoding="utf-8")


def test_daily_worker_exposes_and_wires_chapter_revision_policy():
    text = WORKER_SCRIPT.read_text(encoding="utf-8")
    assert "supports_post_processing_chapter_revision_policy" in text
    assert "book_chapter_revision_policy.py" in text
    assert "--run-chapter-revision-policy" in text
