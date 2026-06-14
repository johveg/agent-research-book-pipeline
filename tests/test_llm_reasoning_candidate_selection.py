import json
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_selector(*args):
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "llm_select_reasoning_candidates.py"), *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )


def db_bytes():
    return (ROOT / ".var" / "book.sqlite").read_bytes()


def status_snapshots():
    con = sqlite3.connect(f"file:{ROOT / '.var' / 'book.sqlite'}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        return {
            "sources": [dict(r) for r in con.execute("SELECT id, quality_score, privacy_publication_status, duplicate_status FROM sources ORDER BY id LIMIT 50")],
            "claims": [dict(r) for r in con.execute("SELECT id, status, publication_decision, contradiction_status FROM claims ORDER BY id LIMIT 50")],
            "editorial_reviews": [dict(r) for r in con.execute("SELECT id, run_id, review_type, status, summary, report_path, created_at FROM editorial_reviews ORDER BY id LIMIT 50")],
        }
    finally:
        con.close()


def test_candidate_selector_prefers_public_web_non_human_review_sources_and_is_report_only(tmp_path):
    before_db = db_bytes()
    before_statuses = status_snapshots()
    result = run_selector(
        "--run-id", "run7-candidate-test",
        "--limit", "5",
        "--output-dir", str(tmp_path),
        "--prefer-public-sources",
        "--exclude-human-review",
        "--min-quality", "C",
    )

    assert result.returncode == 0, result.stderr + result.stdout
    assert db_bytes() == before_db
    assert status_snapshots() == before_statuses

    payload = json.loads((tmp_path / "run7-candidate-test-reasoning-candidate-selection.json").read_text())
    assert payload["mode"] == "reasoning_candidate_selection_report_only"
    assert payload["db_modified"] is False
    assert payload["chapters_modified"] is False
    assert payload["statuses_modified"] is False
    assert payload["schema_modified"] is False
    assert payload["daily_worker_modified"] is False
    assert payload["commit_allowlist_modified"] is False
    assert payload["selected_sources"]
    assert len(payload["selected_sources"]) <= 5
    assert payload["materially_better_than_run5_sample"] is True

    for item in payload["selected_sources"]:
        assert item["selection_decision"] == "selected"
        assert item["selection_score"] > 0
        assert item["source_type"] != "linkedin_search_result"
        assert item["privacy_publication_status"] != "human_review"
        assert item["quality_score"] in {"A", "B", "C"}
        assert item["canonical_url_available"] is True
        assert item["expected_chapter_targets"]
        assert item["why_better_than_run5_sample"]

    skipped = payload["skipped_sources"]
    assert any("human_review" in s["selection_reason"] or "quality_score D" in s["selection_reason"] or "linkedin_search_result" in s["selection_reason"] for s in skipped)


def test_source_cards_accepts_candidate_selection_flags_and_writes_run7_suffix(tmp_path):
    result = subprocess.run(
        [
            sys.executable, str(ROOT / "scripts" / "llm_source_cards.py"),
            "--run-id", "run7-source-card-test",
            "--limit", "3",
            "--output-dir", str(tmp_path),
            "--prefer-public-sources",
            "--exclude-human-review",
            "--min-quality", "C",
            "--report-suffix", "run7",
            "--no-llm",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    payload = json.loads((tmp_path / "run7-source-card-test-source-card-drafts-run7.json").read_text())
    assert payload["candidate_selection"]["selected_count"] <= 3
    assert payload["candidate_selection"]["materially_better_than_run5_sample"] is True
    assert all(card["source_type"] != "linkedin_search_result" for card in payload["source_cards"])
    assert all(card["privacy_publication_status"] != "human_review" for card in payload["source_cards"])


def test_semantic_extractor_accepts_explicit_source_card_report_and_run7_suffix(tmp_path):
    source_cards = {
        "run_id": "run7-semantic-test",
        "llm_used": True,
        "reasoning_status": "high_reasoning_used",
        "provider": "copilot",
        "model": "gpt-5.5",
        "db_modified": False,
        "source_cards": [
            {
                "card_id": "source_card_draft_src_public_1",
                "source_id": "src_public_1",
                "run_id": "run7-semantic-test",
                "source_type": "web",
                "title": "Hermes agent memory architecture",
                "publisher": "example.org",
                "author": "",
                "canonical_url_available": True,
                "captured_at": "2026-06-13T00:00:00Z",
                "quality_score": "B",
                "privacy_publication_status": "publishable_metadata_only",
                "duplicate_status": "unique",
                "safe_summary": "Public web source about Hermes agent memory architecture.",
                "main_thesis": "Agent memory architecture affects reliable operator workflows.",
                "useful_observations": ["Public agent systems use memory and context to support workflows."],
                "candidate_claims": ["Agent memory architecture can improve loop engineering reliability."],
                "candidate_examples": [],
                "candidate_counterpoints": [],
                "named_entities": ["Hermes"],
                "technical_terms": ["memory", "agent", "workflow"],
                "likely_chapter_targets": ["05-context-memory-architecture"],
                "evidence_strength": "moderate",
                "recommended_use": "semantic_extraction_candidate",
                "risk_flags": [],
                "do_not_publish_reason": "Needs editor review before use.",
                "source_text_hash": "hash-source",
                "card_input_hash": "hash-input",
                "card_output_hash": "hash-output",
                "model": "gpt-5.5",
                "provider": "copilot",
                "llm_used": True,
                "confidence": "high",
                "advisory_only": True,
            }
        ],
    }
    src_path = tmp_path / "run7-semantic-test-source-card-drafts-high-reasoning-run7.json"
    src_path.write_text(json.dumps(source_cards))

    result = subprocess.run(
        [
            sys.executable, str(ROOT / "scripts" / "llm_extract_semantic_objects.py"),
            "--run-id", "run7-semantic-test",
            "--limit", "5",
            "--output-dir", str(tmp_path),
            "--source-card-report", str(src_path),
            "--report-suffix", "run7",
            "--no-llm",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    payload = json.loads((tmp_path / "run7-semantic-test-semantic-object-drafts-run7.json").read_text())
    assert payload["source_card_report_input"] == str(src_path)
    assert payload["source_card_notes_read"] == 1
    assert payload["semantic_objects_generated"] >= 1
    for obj in payload["semantic_objects"]:
        assert obj["source_card_id"] == "source_card_draft_src_public_1"
        assert obj["source_id"] == "src_public_1"
        assert obj["author_allowed"] is False
        assert obj["publication_approved"] is False
        assert obj["advisory_only"] is True
        assert obj["paraphrase_only"] is True
