import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import daily_book_worker as worker  # noqa: E402
import book_manuscript_contract as contract_mod  # noqa: E402


def _write_queue(path: Path) -> None:
    flags = list(contract_mod.REQUIRED_GATES)
    path.write_text(json.dumps({
        "queue_name": "book_manuscript_production_queue",
        "queue": [
            {
                "chapter_id": "agent_runtime_security",
                "title": "Agent Runtime Security",
                "target_path": "docs/book/agent-runtime-security.md",
                "mode": "human_approved_research_pair",
                "status": "approved_research_lane",
                "human_approved_at_utc": "2026-06-21T19:43:40Z",
                "required_gates": flags,
                "research_pair": {"web_query": "agent runtime security AI agents", "linkedin_query": "agent runtime security"},
            }
        ],
    }), encoding="utf-8")


def test_approved_research_lanes_are_promoted_to_visible_seed_chapters_and_nav(tmp_path):
    queue_path = tmp_path / "config" / "book_manuscript_queue.json"
    queue_path.parent.mkdir(parents=True)
    _write_queue(queue_path)
    docs_book = tmp_path / "docs" / "book"
    docs_book.mkdir(parents=True)
    mkdocs = tmp_path / "mkdocs.yml"
    mkdocs.write_text("site_name: Test\nnav:\n  - Home: index.md\n  - Book:\n      - Introduction: book/introduction.md\n", encoding="utf-8")

    report = worker.ensure_visible_approved_seed_chapters(
        queue_path=queue_path,
        docs_root=docs_book,
        mkdocs_path=mkdocs,
        max_new_chapters=1,
    )

    chapter = docs_book / "agent-runtime-security.md"
    assert report["ok"] is True
    assert report["seed_chapter_count"] == 1
    assert report["nav_added_count"] == 1
    assert report["seed_chapters"][0]["chapter_state"] == "chapter_seed_created"
    text = chapter.read_text(encoding="utf-8")
    assert "# Agent Runtime Security" in text
    assert "central argument" in text.lower()
    assert "evidence limits" in text.lower()
    assert "## References" in text
    assert "Current evidence status" not in text
    assert "Source/claim mapping" not in text
    assert "claim record" not in text
    assert "- Agent Runtime Security: book/agent-runtime-security.md" in mkdocs.read_text(encoding="utf-8")


def test_visible_seed_chapter_promotion_is_idempotent(tmp_path):
    queue_path = tmp_path / "config" / "book_manuscript_queue.json"
    queue_path.parent.mkdir(parents=True)
    _write_queue(queue_path)
    docs_book = tmp_path / "docs" / "book"
    docs_book.mkdir(parents=True)
    mkdocs = tmp_path / "mkdocs.yml"
    mkdocs.write_text("site_name: Test\nnav:\n  - Book:\n      - Agent Runtime Security: book/agent-runtime-security.md\n", encoding="utf-8")
    existing = docs_book / "agent-runtime-security.md"
    existing.write_text("# Agent Runtime Security\n\nExisting book prose with a central argument, evidence limits, and references. [1]\n\n## References\n\n[1] Existing.\n", encoding="utf-8")

    report = worker.ensure_visible_approved_seed_chapters(
        queue_path=queue_path,
        docs_root=docs_book,
        mkdocs_path=mkdocs,
        max_new_chapters=1,
    )

    assert report["ok"] is True
    assert report["seed_chapter_count"] == 0
    assert report["nav_added_count"] == 0
    assert report["visible_approved_chapter_count"] == 1
    assert existing.read_text(encoding="utf-8").startswith("# Agent Runtime Security")


def test_contract_includes_human_approved_subjects_as_configured_chapters(tmp_path):
    queue_path = tmp_path / "config" / "book_manuscript_queue.json"
    queue_path.parent.mkdir(parents=True)
    _write_queue(queue_path)
    base = contract_mod.build_contract()

    enriched = worker.contract_with_approved_queue_chapters(base, queue_path)

    assert "agent_runtime_security" in enriched["chapters"]
    assert enriched["chapters"]["agent_runtime_security"]["target_path"] == "docs/book/agent-runtime-security.md"
    assert enriched["chapters"]["agent_runtime_security"]["publication_mode"] == "human_approved_guarded_seed"
