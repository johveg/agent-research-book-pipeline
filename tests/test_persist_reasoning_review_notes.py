import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NOTE_TYPE = "reasoning_review_filing_draft"


def run_persist(*args, env=None):
    full_env = os.environ.copy()
    if env:
        full_env.update(env)
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "persist_reasoning_review_notes.py"), *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        env=full_env,
    )


def make_db(path: Path):
    con = sqlite3.connect(path)
    con.executescript(
        """
        CREATE TABLE sources (
          id TEXT PRIMARY KEY,
          quality_score TEXT,
          privacy_publication_status TEXT,
          duplicate_status TEXT
        );
        CREATE TABLE source_notes (
          id TEXT PRIMARY KEY,
          source_id TEXT NOT NULL,
          note TEXT NOT NULL,
          note_type TEXT DEFAULT 'summary',
          created_at TEXT NOT NULL
        );
        CREATE TABLE claims (
          id TEXT PRIMARY KEY,
          status TEXT,
          publication_decision TEXT,
          contradiction_status TEXT
        );
        CREATE TABLE editorial_reviews (
          id TEXT PRIMARY KEY,
          run_id TEXT,
          review_type TEXT,
          status TEXT,
          summary TEXT,
          report_path TEXT,
          created_at TEXT
        );
        INSERT INTO sources (id, quality_score, privacy_publication_status, duplicate_status)
        VALUES ('src_a', 'B', 'publishable_metadata_only', 'unique');
        INSERT INTO claims (id, status, publication_decision, contradiction_status)
        VALUES ('claim_a', 'draft', 'not_reviewed', 'none');
        INSERT INTO editorial_reviews (id, run_id, review_type, status, summary, report_path, created_at)
        VALUES ('review_a', 'old', 'manual', 'open', 'summary', 'report', '2026-01-01T00:00:00Z');
        """
    )
    con.commit()
    con.close()


def db_snapshot(path: Path):
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    try:
        return {
            "source_notes": [dict(r) for r in con.execute("SELECT * FROM source_notes ORDER BY id")],
            "claims": [dict(r) for r in con.execute("SELECT * FROM claims ORDER BY id")],
            "editorial_reviews": [dict(r) for r in con.execute("SELECT * FROM editorial_reviews ORDER BY id")],
            "sources_status": [dict(r) for r in con.execute("SELECT id, quality_score, privacy_publication_status, duplicate_status FROM sources ORDER BY id")],
        }
    finally:
        con.close()


def docs_book_snapshot():
    docs = ROOT / "docs" / "book"
    return {str(p.relative_to(ROOT)): p.read_bytes() for p in sorted(docs.glob("**/*")) if p.is_file()}


def review_item(idx, *, support="supported", evidence="eligible_as_caveat_only", next_stage="eligible_for_filing_persistence", advisory=True):
    return {
        "source_review_id": f"source_review_{idx}",
        "run_id": "run11-fixture",
        "filing_evaluation_id": f"filing_eval_{idx}",
        "packet_item_id": f"packet_{idx}",
        "source_id": "src_a",
        "source_card_id": f"card_{idx}",
        "semantic_object_id": f"obj_{idx}",
        "quality_review_id": f"qreview_{idx}",
        "source_title": "Compact source title",
        "source_type": "web",
        "publisher": "Publisher",
        "quality_score": "B",
        "privacy_publication_status": "publishable_metadata_only",
        "canonical_url_available": True,
        "semantic_object_type": "caveat_candidate",
        "semantic_object_text": "Short caveat text for advisory filing note.",
        "filing_decision": "new_caveat_candidate",
        "novelty_decision": "partially_novel",
        "source_support_decision": support,
        "corroboration_decision": "corroboration_not_required" if evidence == "eligible_as_caveat_only" else "corroboration_required",
        "evidence_use_decision": evidence,
        "next_stage_recommendation": next_stage,
        "support_rationale": "Short support rationale.",
        "corroboration_rationale": "Short corroboration rationale.",
        "corroboration_questions": [],
        "blockers": [],
        "risk_flags": [],
        "required_editor_decisions": ["Editor must review before publication."],
        "confidence": "high",
        "author_allowed": False if advisory else True,
        "publication_approved": False,
        "advisory_only": advisory,
        "input_hash": f"input_hash_{idx}",
        "output_hash": f"output_hash_{idx}",
        "llm_used": True,
        "provider": "copilot",
        "model": "gpt-5.5",
        "bridge": "hermes_cli",
        "reasoning_status": "high_reasoning_used",
    }


def make_report(path: Path):
    report = {
        "run_id": "run11-fixture",
        "mode": "source_support_review",
        "llm_used": True,
        "provider": "copilot",
        "model": "gpt-5.5",
        "bridge": "hermes_cli",
        "reasoning_status": "high_reasoning_used",
        "items_reviewed": 5,
        "db_modified": False,
        "author_allowed": False,
        "publication_approved": False,
        "advisory_only": True,
        "source_reviews": [
            review_item("eligible_a"),
            review_item("eligible_b", support="partially_supported"),
            review_item("unsupported", support="unsupported", evidence="needs_corroboration_before_filing", next_stage="run_corroboration_research"),
            review_item("unclear", support="unclear", evidence="needs_source_review", next_stage="needs_source_review"),
            review_item("corroboration", evidence="needs_corroboration_before_filing", next_stage="run_corroboration_research"),
        ],
    }
    path.write_text(json.dumps(report), encoding="utf-8")
    return path


def note_id_for(item):
    import hashlib

    seed = f"{NOTE_TYPE}:{item['source_review_id']}:{item['output_hash']}"
    return "note_" + hashlib.sha256(seed.encode()).hexdigest()[:24]


def test_default_report_only_writes_reports_and_does_not_modify_db_or_docs(tmp_path):
    db = tmp_path / "book.sqlite"
    make_db(db)
    report = make_report(tmp_path / "run10.json")
    before_db = db_snapshot(db)
    before_docs = docs_book_snapshot()
    result = run_persist(
        "--run-id", "run11-fixture",
        "--output-dir", str(tmp_path),
        "--source-support-review-report", str(report),
        "--report-suffix", "run11",
        env={"TEREFO_BOOK_DB_PATH": str(db)},
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert (tmp_path / "run11-fixture-persisted-review-notes-run11.json").exists()
    assert (tmp_path / "run11-fixture-persisted-review-notes-run11.md").exists()
    payload = json.loads((tmp_path / "run11-fixture-persisted-review-notes-run11.json").read_text())
    assert payload["source_reviews_available"] == 5
    assert payload["eligible_items_available"] == 2
    assert payload["items_selected_for_persistence"] == 2
    assert payload["write_source_notes_requested"] is False
    assert payload["db_modified"] is False
    assert payload["notes_inserted"] == 0
    assert db_snapshot(db) == before_db
    assert docs_book_snapshot() == before_docs


def test_write_source_notes_persists_only_eligible_and_is_idempotent(tmp_path):
    db = tmp_path / "book.sqlite"
    make_db(db)
    report = make_report(tmp_path / "run10.json")
    before = db_snapshot(db)
    result = run_persist(
        "--run-id", "run11-fixture",
        "--output-dir", str(tmp_path),
        "--source-support-review-report", str(report),
        "--write-source-notes",
        "--report-suffix", "run11",
        env={"TEREFO_BOOK_DB_PATH": str(db)},
    )
    assert result.returncode == 0, result.stderr + result.stdout
    payload = json.loads((tmp_path / "run11-fixture-persisted-review-notes-run11.json").read_text())
    assert payload["db_modified"] is True
    assert payload["db_write_scope"] == "source_notes"
    assert payload["notes_inserted"] == 2
    assert payload["notes_skipped_existing"] == 0
    assert payload["notes_failed"] == 0
    assert payload["notes_conflicted"] == 0
    snap = db_snapshot(db)
    assert len(snap["source_notes"]) == 2
    assert snap["claims"] == before["claims"]
    assert snap["editorial_reviews"] == before["editorial_reviews"]
    assert snap["sources_status"] == before["sources_status"]
    for row in snap["source_notes"]:
        assert row["note_type"] == NOTE_TYPE
        note = json.loads(row["note"])
        for key in ["source_review_id", "filing_evaluation_id", "packet_item_id", "source_id", "source_card_id", "semantic_object_id", "quality_review_id"]:
            assert note[key]
        assert note["author_allowed"] is False
        assert note["publication_approved"] is False
        assert note["advisory_only"] is True
        assert note["eligible_for_filing_persistence"] is True
        assert note["eligible_as_caveat_only"] is True
    skipped = {i["source_review_id"]: i["skip_reason"] for i in payload["skipped_items"]}
    assert skipped["source_review_unsupported"] == "unsupported"
    assert skipped["source_review_unclear"] == "unclear"
    assert skipped["source_review_corroboration"] == "needs_corroboration"

    again = run_persist(
        "--run-id", "run11-fixture",
        "--output-dir", str(tmp_path),
        "--source-support-review-report", str(report),
        "--write-source-notes",
        "--report-suffix", "run11",
        env={"TEREFO_BOOK_DB_PATH": str(db)},
    )
    assert again.returncode == 0, again.stderr + again.stdout
    payload2 = json.loads((tmp_path / "run11-fixture-persisted-review-notes-run11.json").read_text())
    assert payload2["notes_inserted"] == 0
    assert payload2["notes_skipped_existing"] == 2
    assert payload2["idempotent"] is True
    assert len(db_snapshot(db)["source_notes"]) == 2


def test_conflicting_note_id_fails_closed_and_rolls_back(tmp_path):
    db = tmp_path / "book.sqlite"
    make_db(db)
    report = make_report(tmp_path / "run10.json")
    data = json.loads(report.read_text())
    first = data["source_reviews"][0]
    conflicting_id = note_id_for(first)
    con = sqlite3.connect(db)
    con.execute(
        "INSERT INTO source_notes (id, source_id, note, note_type, created_at) VALUES (?, ?, ?, ?, ?)",
        (conflicting_id, first["source_id"], json.dumps({"different": True}), NOTE_TYPE, "2026-01-01T00:00:00Z"),
    )
    con.commit()
    con.close()
    before = db_snapshot(db)
    result = run_persist(
        "--run-id", "run11-fixture",
        "--output-dir", str(tmp_path),
        "--source-support-review-report", str(report),
        "--write-source-notes",
        "--report-suffix", "run11",
        env={"TEREFO_BOOK_DB_PATH": str(db)},
    )
    assert result.returncode != 0
    assert "conflict" in (result.stderr + result.stdout).lower()
    assert db_snapshot(db) == before
