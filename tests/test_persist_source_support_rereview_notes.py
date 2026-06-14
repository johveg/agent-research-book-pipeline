import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "persist_source_support_rereview_notes.py"
RUN15 = ROOT / "reports" / "editorial" / "citation-pipeline-test-20260612-source-support-rereview-run15.json"
NOTE_TYPE = "source_support_rereview_draft"
ELIGIBLE_REVIEW_ID = "source_review_5baf68d86960f91b97ac"
SKIPPED_REVIEW_ID = "source_review_12c73455aa1816e5df8c"


def run_script(*args, db_path: Path, output_dir: Path):
    env = os.environ.copy()
    env["TEREFO_BOOK_DB_PATH"] = str(db_path)
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args, "--output-dir", str(output_dir)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        env=env,
    )


def db_copy(tmp_path: Path) -> Path:
    dst = tmp_path / "book.sqlite"
    shutil.copy2(ROOT / ".var" / "book.sqlite", dst)
    # Tests need a clean fixture even after the explicit production Run 16 write
    # has inserted the deterministic note in the real runtime DB.
    con = sqlite3.connect(dst)
    try:
        con.execute("DELETE FROM source_notes WHERE note_type=?", (NOTE_TYPE,))
        con.commit()
    finally:
        con.close()
    return dst


def counts(db_path: Path):
    con = sqlite3.connect(db_path)
    try:
        return {
            "source_notes": con.execute("SELECT COUNT(*) FROM source_notes").fetchone()[0],
            "drafts": con.execute("SELECT COUNT(*) FROM source_notes WHERE note_type=?", (NOTE_TYPE,)).fetchone()[0],
            "claims": con.execute("SELECT COUNT(*) FROM claims").fetchone()[0],
            "editorial_reviews": con.execute("SELECT COUNT(*) FROM editorial_reviews").fetchone()[0],
        }
    finally:
        con.close()


def status_hashes(db_path: Path):
    con = sqlite3.connect(db_path)
    try:
        out = {}
        for name, sql in {
            "sources": "SELECT id, quality_score, privacy_publication_status, duplicate_status FROM sources ORDER BY id",
            "claims": "SELECT id, status, publication_decision, contradiction_status FROM claims ORDER BY id",
            "editorial_reviews": "SELECT id, run_id, review_type, status, summary, report_path, created_at FROM editorial_reviews ORDER BY id",
        }.items():
            rows = con.execute(sql).fetchall()
            out[name] = hashlib.sha256(json.dumps(rows, sort_keys=True, default=str).encode()).hexdigest()
        return out
    finally:
        con.close()


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_snapshot(path: Path):
    return {str(p.relative_to(ROOT)): sha(p) for p in sorted(path.rglob("*")) if p.is_file()}


def read_report(output_dir: Path, suffix="run16"):
    p = output_dir / f"citation-pipeline-test-20260612-persisted-source-support-rereview-notes-{suffix}.json"
    return json.loads(p.read_text())


def test_report_only_does_not_modify_database_and_selects_expected_item(tmp_path):
    db = db_copy(tmp_path)
    before = counts(db)
    before_status = status_hashes(db)
    res = run_script(
        "--run-id", "citation-pipeline-test-20260612",
        "--source-support-rereview-report", str(RUN15),
        "--report-suffix", "run16",
        db_path=db,
        output_dir=tmp_path,
    )
    assert res.returncode == 0, res.stderr + res.stdout
    assert counts(db) == before
    assert status_hashes(db) == before_status
    payload = read_report(tmp_path)
    assert payload["report_only"] is True
    assert payload["write_source_notes"] is False
    assert payload["eligible_items_count"] == 1
    assert payload["skipped_items_count"] == 1
    assert payload["inserted_notes_count"] == 0
    assert payload["eligible_items"][0]["source_review_id"] == ELIGIBLE_REVIEW_ID
    assert payload["eligible_items"][0]["persistence_result"] == "would_insert"


def test_write_source_notes_writes_only_eligible_item_and_preserves_protected_artifacts(tmp_path):
    db = db_copy(tmp_path)
    before = counts(db)
    before_status = status_hashes(db)
    before_registry = sha(ROOT / "data" / "source_registry.json")
    before_raw = tree_snapshot(ROOT / "raw")
    before_book = tree_snapshot(ROOT / "docs" / "book")
    before_schema = sha(ROOT / "data" / "schema.sql")
    before_worker = sha(ROOT / "scripts" / "daily_book_worker.py")

    res = run_script(
        "--run-id", "citation-pipeline-test-20260612",
        "--source-support-rereview-report", str(RUN15),
        "--report-suffix", "run16",
        "--write-source-notes",
        db_path=db,
        output_dir=tmp_path,
    )
    assert res.returncode == 0, res.stderr + res.stdout
    after = counts(db)
    assert after["source_notes"] == before["source_notes"] + 1
    assert after["drafts"] == before["drafts"] + 1
    assert after["claims"] == before["claims"]
    assert after["editorial_reviews"] == before["editorial_reviews"]
    assert status_hashes(db) == before_status
    assert sha(ROOT / "data" / "source_registry.json") == before_registry
    assert tree_snapshot(ROOT / "raw") == before_raw
    assert tree_snapshot(ROOT / "docs" / "book") == before_book
    assert sha(ROOT / "data" / "schema.sql") == before_schema
    assert sha(ROOT / "scripts" / "daily_book_worker.py") == before_worker

    payload = read_report(tmp_path)
    assert payload["inserted_notes_count"] == 1
    assert payload["existing_notes_count"] == 0
    item = payload["persisted_items"][0]
    assert item["source_review_id"] == ELIGIBLE_REVIEW_ID
    assert item["note_id"].startswith("note_")
    con = sqlite3.connect(db)
    try:
        row = con.execute("SELECT note_type, note FROM source_notes WHERE id=?", (item["note_id"],)).fetchone()
    finally:
        con.close()
    assert row[0] == NOTE_TYPE
    note = json.loads(row[1])
    assert note["note_kind"] == NOTE_TYPE
    assert note["closed_loop_disposition"] == "eligible_for_review_note_persistence"
    assert note["advisory_only"] is True
    assert note["author_allowed"] is False
    assert note["publication_approved"] is False
    assert note["claim_inserted"] is False
    assert note["editorial_review_inserted"] is False
    assert note["source_registry_promoted"] is False


def test_idempotent_second_write_skips_existing_identical_note(tmp_path):
    db = db_copy(tmp_path)
    args = [
        "--run-id", "citation-pipeline-test-20260612",
        "--source-support-rereview-report", str(RUN15),
        "--report-suffix", "run16",
        "--write-source-notes",
    ]
    first = run_script(*args, db_path=db, output_dir=tmp_path)
    assert first.returncode == 0, first.stderr + first.stdout
    after_first = counts(db)
    second = run_script(*args, db_path=db, output_dir=tmp_path)
    assert second.returncode == 0, second.stderr + second.stdout
    assert counts(db) == after_first
    payload = read_report(tmp_path)
    assert payload["inserted_notes_count"] == 0
    assert payload["existing_notes_count"] == 1
    assert payload["persisted_items"][0]["persistence_result"] == "existing_identical"


def test_needs_editor_review_item_is_skipped_with_automated_disposition_not_human_only(tmp_path):
    db = db_copy(tmp_path)
    res = run_script(
        "--run-id", "citation-pipeline-test-20260612",
        "--source-support-rereview-report", str(RUN15),
        "--report-suffix", "run16",
        db_path=db,
        output_dir=tmp_path,
    )
    assert res.returncode == 0, res.stderr + res.stdout
    payload = read_report(tmp_path)
    skipped = {i["source_review_id"]: i for i in payload["skipped_items"]}
    assert SKIPPED_REVIEW_ID in skipped
    assert skipped[SKIPPED_REVIEW_ID]["closed_loop_disposition"] in {"source_context_unclear", "needs_more_sources", "safe_reports_only"}
    assert "human review required" not in json.dumps(skipped[SKIPPED_REVIEW_ID]).lower()
    assert payload["closed_loop_disposition_counts"]["source_context_unclear"] == 1


def test_conflict_on_deterministic_note_id_fails_closed_and_rolls_back(tmp_path):
    db = db_copy(tmp_path)
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    first = run_script(
        "--run-id", "citation-pipeline-test-20260612",
        "--source-support-rereview-report", str(RUN15),
        "--report-suffix", "run16",
        db_path=db,
        output_dir=output_dir,
    )
    assert first.returncode == 0, first.stderr + first.stdout
    note_id = read_report(output_dir)["eligible_items"][0]["note_id"]
    before = counts(db)
    con = sqlite3.connect(db)
    try:
        con.execute(
            "INSERT INTO source_notes (id, source_id, note, note_type, created_at) VALUES (?, ?, ?, ?, ?)",
            (note_id, "src_0ad8d7a30c5f24cb6506", '{"different":true}', NOTE_TYPE, "2026-06-14T00:00:00Z"),
        )
        con.commit()
    finally:
        con.close()
    after_conflict_seed = counts(db)
    res = run_script(
        "--run-id", "citation-pipeline-test-20260612",
        "--source-support-rereview-report", str(RUN15),
        "--report-suffix", "run16",
        "--write-source-notes",
        db_path=db,
        output_dir=output_dir,
    )
    assert res.returncode != 0
    assert counts(db) == after_conflict_seed
    assert after_conflict_seed["source_notes"] == before["source_notes"] + 1


def test_invalid_missing_input_and_missing_safety_flags_fail_closed(tmp_path):
    db = db_copy(tmp_path)
    missing = run_script(
        "--run-id", "citation-pipeline-test-20260612",
        "--source-support-rereview-report", str(tmp_path / "missing.json"),
        "--report-suffix", "run16",
        db_path=db,
        output_dir=tmp_path,
    )
    assert missing.returncode != 0

    bad_report = tmp_path / "bad.json"
    data = json.loads(RUN15.read_text())
    del data["rereviews"][1]["advisory_only"]
    bad_report.write_text(json.dumps(data), encoding="utf-8")
    before = counts(db)
    bad = run_script(
        "--run-id", "citation-pipeline-test-20260612",
        "--source-support-rereview-report", str(bad_report),
        "--report-suffix", "run16",
        "--write-source-notes",
        db_path=db,
        output_dir=tmp_path,
    )
    assert bad.returncode != 0
    assert counts(db) == before


def test_unsupported_contradicted_or_do_not_use_items_are_not_persisted(tmp_path):
    db = db_copy(tmp_path)
    report = tmp_path / "unsupported.json"
    data = json.loads(RUN15.read_text())
    eligible = data["rereviews"][1]
    eligible["support_decision"] = "unsupported"
    eligible["corroboration_decision"] = "not_corroborated"
    eligible["evidence_use_decision"] = "do_not_use"
    eligible["recommended_next_stage"] = "exclude_from_pipeline"
    report.write_text(json.dumps(data), encoding="utf-8")
    before = counts(db)
    res = run_script(
        "--run-id", "citation-pipeline-test-20260612",
        "--source-support-rereview-report", str(report),
        "--report-suffix", "run16",
        "--write-source-notes",
        db_path=db,
        output_dir=tmp_path,
    )
    assert res.returncode == 0, res.stderr + res.stdout
    assert counts(db) == before
    payload = read_report(tmp_path)
    assert payload["eligible_items_count"] == 0
    assert payload["inserted_notes_count"] == 0
    assert any(i["source_review_id"] == ELIGIBLE_REVIEW_ID and i["closed_loop_disposition"] == "exclude_from_pipeline" for i in payload["skipped_items"])
