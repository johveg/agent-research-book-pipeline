import json
import sqlite3
import subprocess
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_CARD_FIELDS = {
    "card_id",
    "source_id",
    "run_id",
    "source_type",
    "title",
    "publisher",
    "author",
    "canonical_url_available",
    "captured_at",
    "quality_score",
    "privacy_publication_status",
    "duplicate_status",
    "safe_summary",
    "main_thesis",
    "useful_observations",
    "candidate_claims",
    "candidate_examples",
    "candidate_counterpoints",
    "named_entities",
    "technical_terms",
    "likely_chapter_targets",
    "evidence_strength",
    "recommended_use",
    "risk_flags",
    "do_not_publish_reason",
    "source_text_hash",
    "card_input_hash",
    "card_output_hash",
    "model",
    "llm_used",
    "confidence",
    "advisory_only",
}


def run_source_cards(*args):
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "llm_source_cards.py"), *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )


def db_bytes():
    db_path = ROOT / ".var" / "book.sqlite"
    return db_path.read_bytes() if db_path.exists() else None


def status_snapshots():
    db_path = ROOT / ".var" / "book.sqlite"
    if not db_path.exists():
        return {"sources": [], "claims": [], "editorial_reviews": []}
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        sources = [
            dict(r)
            for r in con.execute(
                "SELECT id, quality_score, privacy_publication_status, duplicate_status FROM sources ORDER BY id LIMIT 25"
            )
        ]
        claims = [
            dict(r)
            for r in con.execute(
                "SELECT id, status, publication_decision, contradiction_status FROM claims ORDER BY id LIMIT 25"
            )
        ]
        reviews = [
            dict(r)
            for r in con.execute(
                "SELECT id, run_id, review_type, status, summary, report_path, created_at FROM editorial_reviews ORDER BY id LIMIT 25"
            )
        ]
        return {"sources": sources, "claims": claims, "editorial_reviews": reviews}
    finally:
        con.close()


def source_card_note_count():
    db_path = ROOT / ".var" / "book.sqlite"
    if not db_path.exists():
        return 0
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        return con.execute("SELECT COUNT(*) FROM source_notes WHERE note_type='source_card_draft'").fetchone()[0]
    finally:
        con.close()


def read_source_card_notes():
    db_path = ROOT / ".var" / "book.sqlite"
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        return [
            dict(r)
            for r in con.execute(
                "SELECT id, source_id, note, note_type, created_at FROM source_notes WHERE note_type='source_card_draft' ORDER BY created_at DESC, id DESC"
            )
        ]
    finally:
        con.close()



def delete_source_card_notes_for_run(run_id):
    db_path = ROOT / ".var" / "book.sqlite"
    if not db_path.exists():
        return
    con = sqlite3.connect(db_path)
    try:
        con.execute(
            "DELETE FROM source_notes WHERE note_type='source_card_draft' AND note LIKE ?",
            [f'%"run_id":"{run_id}"%'],
        )
        con.commit()
    finally:
        con.close()

def test_source_cards_no_llm_writes_markdown_and_json_with_required_schema(tmp_path):
    before_notes = source_card_note_count()
    result = run_source_cards(
        "--run-id",
        "test-source-cards",
        "--limit",
        "3",
        "--output-dir",
        str(tmp_path),
        "--no-llm",
        "--max-summary-chars",
        "180",
    )

    assert result.returncode == 0, result.stderr + result.stdout
    assert source_card_note_count() == before_notes
    md_path = tmp_path / "test-source-cards-source-card-drafts.md"
    json_path = tmp_path / "test-source-cards-source-card-drafts.json"
    assert md_path.exists()
    assert json_path.exists()

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["mode"] == "source_card_drafts_with_optional_persistence"
    assert payload["write_source_notes_requested"] is False
    assert payload["db_write_scope"] == "none"
    assert payload["llm_used"] is False
    assert payload["confidence_level"] == "low_draft_structural"
    assert payload["db_modified"] is False
    assert payload["chapters_modified"] is False
    assert payload["statuses_modified"] is False
    assert payload["daily_worker_modified"] is False
    assert payload["commit_allowlist_modified"] is False
    assert payload["schema_modified"] is False
    assert payload["raw_private_material_written"] is False
    assert payload["long_source_excerpt_written"] is False
    assert payload["source_notes_inserted"] == 0
    assert payload["source_notes_updated"] == 0
    assert payload["source_notes_skipped_existing"] == 0
    assert payload["source_notes_failed"] == 0
    assert payload["sample_counts"]["sources"] <= 3
    assert payload["source_cards"]

    for card in payload["source_cards"]:
        assert REQUIRED_CARD_FIELDS <= set(card)
        assert card["card_id"] == f"source_card_draft_{card['source_id']}"
        assert card["advisory_only"] is True
        assert card["llm_used"] is False
        assert card["confidence"] == "low"
        assert card["recommended_use"] in {
            "ignore",
            "monitor",
            "needs_review",
            "source_card_candidate",
            "semantic_extraction_candidate",
            "chapter_packet_candidate_later",
            "do_not_use",
        }
        assert card["evidence_strength"] in {"strong", "moderate", "weak", "discovery_only", "reject"}
        assert len(card["safe_summary"]) <= 180
        assert len(card["main_thesis"]) <= 180
        for key in ["useful_observations", "candidate_claims", "candidate_examples", "candidate_counterpoints"]:
            assert all(len(item) <= 180 for item in card[key])

    md = md_path.read_text(encoding="utf-8")
    assert "Executive summary" in md
    assert "Source-card draft table" in md
    assert "Persistence summary" in md
    assert "Safety assessment" in md
    assert "Recommended Run 4" in md


def test_source_cards_default_does_not_modify_db_docs_book_statuses_or_pipeline_files(tmp_path):
    before_db = db_bytes()
    before_notes = source_card_note_count()
    before_statuses = status_snapshots()
    book_files = sorted((ROOT / "docs" / "book").glob("*.md"))
    before_book = {p.relative_to(ROOT): p.read_bytes() for p in book_files}
    protected_paths = [
        ROOT / "scripts" / "daily_book_worker.py",
        ROOT / "scripts" / "research_common.py",
        ROOT / "data" / "schema.sql",
    ]
    before_protected = {p.relative_to(ROOT): p.read_bytes() for p in protected_paths}

    result = run_source_cards(
        "--run-id",
        "test-source-cards-safety",
        "--limit",
        "2",
        "--output-dir",
        str(tmp_path),
        "--no-llm",
    )

    assert result.returncode == 0, result.stderr + result.stdout
    assert db_bytes() == before_db
    assert source_card_note_count() == before_notes
    assert status_snapshots() == before_statuses
    after_book = {p.relative_to(ROOT): p.read_bytes() for p in book_files}
    assert after_book == before_book
    after_protected = {p.relative_to(ROOT): p.read_bytes() for p in protected_paths}
    assert after_protected == before_protected


def test_source_cards_write_source_notes_only_and_is_idempotent(tmp_path):
    unique_run_id = f"test-source-cards-persist-{uuid.uuid4().hex}"
    delete_source_card_notes_for_run(unique_run_id)
    before_statuses = status_snapshots()
    before_reviews = before_statuses["editorial_reviews"]
    before_note_count = source_card_note_count()
    book_files = sorted((ROOT / "docs" / "book").glob("*.md"))
    before_book = {p.relative_to(ROOT): p.read_bytes() for p in book_files}
    protected_paths = [
        ROOT / "scripts" / "daily_book_worker.py",
        ROOT / "scripts" / "research_common.py",
        ROOT / "data" / "schema.sql",
    ]
    before_protected = {p.relative_to(ROOT): p.read_bytes() for p in protected_paths}

    first = run_source_cards(
        "--run-id",
        unique_run_id,
        "--limit",
        "2",
        "--output-dir",
        str(tmp_path),
        "--no-llm",
        "--write-source-notes",
        "--max-summary-chars",
        "160",
    )
    assert first.returncode == 0, first.stderr + first.stdout
    first_payload = json.loads((tmp_path / f"{unique_run_id}-source-card-drafts.json").read_text())
    assert first_payload["write_source_notes_requested"] is True
    assert first_payload["db_modified"] is True
    assert first_payload["db_write_scope"] == "source_notes_only"
    assert first_payload["source_notes_table_schema_checked"] is True
    assert first_payload["source_notes_schema_supported"] is True
    assert first_payload["source_notes_note_type"] == "source_card_draft"
    assert first_payload["idempotent"] is True
    assert first_payload["source_notes_failed"] == 0
    assert first_payload["source_notes_inserted"] + first_payload["source_notes_skipped_existing"] == first_payload["sample_counts"]["sources"]

    notes_after_first = source_card_note_count()
    assert notes_after_first >= before_note_count + first_payload["source_notes_inserted"]
    stored = read_source_card_notes()
    assert stored
    stored_cards = [json.loads(row["note"]) for row in stored[: first_payload["sample_counts"]["sources"]]]
    for card in stored_cards:
        assert REQUIRED_CARD_FIELDS <= set(card)
        assert card["advisory_only"] is True
        assert card["llm_used"] is False
        assert card["confidence"] == "low"
        assert card["source_text_hash"]
        assert card["card_input_hash"]
        assert card["card_output_hash"]
        assert isinstance(card["risk_flags"], list)
        assert len(card["safe_summary"]) <= 160
        assert len(card["main_thesis"]) <= 160

    second = run_source_cards(
        "--run-id",
        unique_run_id,
        "--limit",
        "2",
        "--output-dir",
        str(tmp_path),
        "--no-llm",
        "--write-source-notes",
        "--max-summary-chars",
        "160",
    )
    assert second.returncode == 0, second.stderr + second.stdout
    second_payload = json.loads((tmp_path / f"{unique_run_id}-source-card-drafts.json").read_text())
    assert second_payload["source_notes_inserted"] == 0
    assert second_payload["source_notes_skipped_existing"] == second_payload["sample_counts"]["sources"]
    assert source_card_note_count() == notes_after_first

    after_statuses = status_snapshots()
    assert after_statuses["sources"] == before_statuses["sources"]
    assert after_statuses["claims"] == before_statuses["claims"]
    assert after_statuses["editorial_reviews"] == before_reviews
    after_book = {p.relative_to(ROOT): p.read_bytes() for p in book_files}
    assert after_book == before_book
    after_protected = {p.relative_to(ROOT): p.read_bytes() for p in protected_paths}
    assert after_protected == before_protected
    delete_source_card_notes_for_run(unique_run_id)


def test_source_cards_fail_if_high_reasoning_bridge_invalid_writes_no_notes(tmp_path):
    before_notes = source_card_note_count()
    before_db = db_bytes()
    bridge = make_mock_bridge(tmp_path, {"ok": False, "error": "invalid_json"}, exit_code=2)

    result = run_source_cards_with_env(
        {"TEREFO_HIGH_REASONING_BRIDGE_COMMAND": bridge},
        "--run-id",
        "test-source-cards-fail-safe",
        "--limit",
        "1",
        "--output-dir",
        str(tmp_path),
        "--fail-if-no-high-reasoning-model",
    )

    assert result.returncode != 0
    assert "high-reasoning bridge failed" in result.stderr
    assert "weak/local fallback refused" in result.stderr
    assert source_card_note_count() == before_notes
    assert db_bytes() == before_db
    assert not (tmp_path / "test-source-cards-fail-safe-source-card-drafts-high-reasoning.json").exists()



def make_mock_bridge(tmp_path, payload, exit_code=0):
    p = tmp_path / "mock_bridge_source_cards.py"
    body = "#!/usr/bin/env python3\nimport json, sys\n"
    if exit_code == 0:
        body += "json.load(sys.stdin)\n"
        body += "print(json.dumps(" + repr(payload) + "))\n"
    else:
        body += "print(json.dumps({'ok': False, 'error': 'mock failure'}))\nsys.exit(" + str(exit_code) + ")\n"
    p.write_text(body, encoding="utf-8")
    p.chmod(0o755)
    return str(p)


def run_source_cards_with_env(env, *args):
    import os
    full_env = os.environ.copy()
    full_env.update(env)
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "llm_source_cards.py"), *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        env=full_env,
    )


def test_source_cards_high_reasoning_path_mocked_sets_llm_used_true_and_report_only(tmp_path):
    payload = {
        "ok": True,
        "provider": "copilot",
        "model": "gpt-5.5",
        "bridge": "hermes_cli",
        "llm_used": True,
        "reasoning_status": "high_reasoning_used",
        "source_cards": [],
    }
    before_db = db_bytes()
    before_statuses = status_snapshots()
    bridge = make_mock_bridge(tmp_path, payload)
    res = run_source_cards_with_env(
        {"TEREFO_HIGH_REASONING_BRIDGE_COMMAND": bridge, "TEREFO_LLM_PROVIDER": "copilot", "TEREFO_LLM_REASONING_MODEL": "gpt-5.5"},
        "--run-id", "test-source-cards-hr", "--limit", "2", "--output-dir", str(tmp_path), "--max-summary-chars", "160",
    )
    assert res.returncode == 0, res.stderr + res.stdout
    report = json.loads((tmp_path / "test-source-cards-hr-source-card-drafts-high-reasoning.json").read_text())
    assert report["llm_used"] is True
    assert report["reasoning_status"] == "high_reasoning_used"
    assert report["provider"] == "copilot"
    assert report["model"] == "gpt-5.5"
    assert report["db_modified"] is False
    assert db_bytes() == before_db
    assert status_snapshots() == before_statuses
    for card in report["source_cards"]:
        assert REQUIRED_CARD_FIELDS <= set(card)
        assert card["llm_used"] is True
        assert card["model"] == "gpt-5.5"
        assert card["confidence"] == "high"
        assert card["advisory_only"] is True


def test_source_cards_high_reasoning_invalid_bridge_fails_closed_no_db_write(tmp_path):
    before_db = db_bytes()
    bridge = make_mock_bridge(tmp_path, {"ok": False, "error": "invalid_json"}, exit_code=2)
    res = run_source_cards_with_env(
        {"TEREFO_HIGH_REASONING_BRIDGE_COMMAND": bridge},
        "--run-id", "test-source-cards-hr-fail", "--limit", "1", "--output-dir", str(tmp_path),
    )
    assert res.returncode != 0
    assert db_bytes() == before_db
    assert not (tmp_path / "test-source-cards-hr-fail-source-card-drafts-high-reasoning.json").exists()
