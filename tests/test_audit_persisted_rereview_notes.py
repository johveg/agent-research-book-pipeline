import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "audit_persisted_rereview_notes.py"
RUN16 = ROOT / "reports" / "editorial" / "citation-pipeline-test-20260612-persisted-source-support-rereview-notes-run16.json"
RUN15 = ROOT / "reports" / "editorial" / "citation-pipeline-test-20260612-source-support-rereview-run15.json"
NOTE_ID = "note_a30056d3f19faa7deb0c9dbc"
NOTE_TYPE = "source_support_rereview_draft"
ELIGIBLE_REVIEW_ID = "source_review_5baf68d86960f91b97ac"
SKIPPED_REVIEW_ID = "source_review_12c73455aa1816e5df8c"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_snapshot(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    return {str(p.relative_to(path)): sha(p) for p in sorted(path.rglob("*")) if p.is_file()}


def db_copy(tmp_path: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    dst = tmp_path / "book.sqlite"
    shutil.copy2(ROOT / ".var" / "book.sqlite", dst)
    return dst


def counts(db: Path) -> dict[str, int]:
    con = sqlite3.connect(db)
    try:
        return {
            "source_notes": con.execute("SELECT COUNT(*) FROM source_notes").fetchone()[0],
            "drafts": con.execute("SELECT COUNT(*) FROM source_notes WHERE note_type=?", (NOTE_TYPE,)).fetchone()[0],
            "claims": con.execute("SELECT COUNT(*) FROM claims").fetchone()[0],
            "editorial_reviews": con.execute("SELECT COUNT(*) FROM editorial_reviews").fetchone()[0],
        }
    finally:
        con.close()


def status_hashes(db: Path) -> dict[str, str]:
    con = sqlite3.connect(db)
    try:
        specs = {
            "sources": "SELECT id, quality_score, privacy_publication_status, duplicate_status FROM sources ORDER BY id",
            "claims": "SELECT id, status, publication_decision, contradiction_status FROM claims ORDER BY id",
            "editorial_reviews": "SELECT id, run_id, review_type, status, summary, report_path, created_at FROM editorial_reviews ORDER BY id",
        }
        return {name: hashlib.sha256(json.dumps(con.execute(sql).fetchall(), sort_keys=True, default=str).encode()).hexdigest() for name, sql in specs.items()}
    finally:
        con.close()


def run_script(*args, db_path: Path, output_dir: Path):
    env = os.environ.copy()
    env["TEREFO_BOOK_DB_PATH"] = str(db_path)
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--output-dir", str(output_dir), *args],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=60,
    )


def read_manifest(output_dir: Path) -> dict:
    path = output_dir / "citation-pipeline-test-20260612-downstream-eligibility-manifest-run17.json"
    assert path.exists(), f"missing manifest {path}"
    return json.loads(path.read_text())


def mutate_note(db: Path, mutator):
    con = sqlite3.connect(db)
    try:
        row = con.execute("SELECT note FROM source_notes WHERE id=?", (NOTE_ID,)).fetchone()
        assert row, "fixture missing persisted note"
        note = json.loads(row[0])
        mutator(note)
        con.execute("UPDATE source_notes SET note=? WHERE id=?", (json.dumps(note, sort_keys=True, separators=(",", ":")), NOTE_ID))
        con.commit()
    finally:
        con.close()


def test_audits_exactly_one_persisted_note_and_emits_manifest_without_db_changes(tmp_path):
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
        "--run16-report", str(RUN16),
        "--run15-report", str(RUN15),
        "--report-suffix", "run17",
        db_path=db,
        output_dir=tmp_path,
    )

    assert res.returncode == 0, res.stderr + res.stdout
    assert counts(db) == before
    assert status_hashes(db) == before_status
    assert sha(ROOT / "data" / "source_registry.json") == before_registry
    assert tree_snapshot(ROOT / "raw") == before_raw
    assert tree_snapshot(ROOT / "docs" / "book") == before_book
    assert sha(ROOT / "data" / "schema.sql") == before_schema
    assert sha(ROOT / "scripts" / "daily_book_worker.py") == before_worker

    payload = read_manifest(tmp_path)
    assert payload["report_only"] is True
    assert payload["reviewed_persisted_notes_count"] == 1
    assert payload["eligible_for_clustering_count"] + payload["caveat_only_cluster_candidate_count"] == 1
    assert payload["excluded_items_count"] == 1
    assert payload["skipped_items_count"] == 0
    assert payload["changed_db"] is False
    assert payload["changed_source_notes"] is False
    assert payload["claims_inserted"] == 0
    assert payload["editorial_reviews_inserted"] == 0
    item = payload["manifest_items"][0]
    assert item["note_id"] == NOTE_ID
    assert item["source_review_id"] == ELIGIBLE_REVIEW_ID
    assert item["downstream_manifest_decision"] in {"eligible_for_clustering", "caveat_only_cluster_candidate"}
    assert item["eligible_for_claim_insertion"] is False
    assert item["eligible_for_authoring"] is False
    assert item["eligible_for_publication"] is False
    assert item["advisory_only"] is True
    assert item["author_allowed"] is False
    assert item["publication_approved"] is False
    assert item["provenance_paths"]["run15_report"] == "reports/editorial/citation-pipeline-test-20260612-source-support-rereview-run15.json"
    assert item["provenance_paths"]["run16_report"] == "reports/editorial/citation-pipeline-test-20260612-persisted-source-support-rereview-notes-run16.json"


def test_source_context_unclear_item_remains_excluded_and_not_human_only(tmp_path):
    db = db_copy(tmp_path)
    res = run_script("--run16-report", str(RUN16), "--run15-report", str(RUN15), db_path=db, output_dir=tmp_path)
    assert res.returncode == 0, res.stderr + res.stdout
    payload = read_manifest(tmp_path)
    excluded = [i for i in payload["excluded_items"] if i["source_review_id"] == SKIPPED_REVIEW_ID]
    assert excluded
    assert excluded[0]["downstream_manifest_decision"] in {"source_context_unclear", "needs_more_sources", "safe_reports_only"}
    assert "human review required" not in json.dumps(excluded).lower()
    assert "source_context_unclear" in payload["downstream_manifest_decision_counts"]


def test_missing_persisted_note_fails_closed(tmp_path):
    db = db_copy(tmp_path)
    con = sqlite3.connect(db)
    try:
        con.execute("DELETE FROM source_notes WHERE id=?", (NOTE_ID,))
        con.commit()
    finally:
        con.close()
    before = counts(db)
    res = run_script("--run16-report", str(RUN16), "--run15-report", str(RUN15), db_path=db, output_dir=tmp_path)
    assert res.returncode == 2
    assert "missing persisted source_notes row" in res.stderr
    assert counts(db) == before


def test_malformed_persisted_note_json_fails_closed(tmp_path):
    db = db_copy(tmp_path)
    con = sqlite3.connect(db)
    try:
        con.execute("UPDATE source_notes SET note=? WHERE id=?", ("{not-json", NOTE_ID))
        con.commit()
    finally:
        con.close()
    before = counts(db)
    res = run_script("--run16-report", str(RUN16), "--run15-report", str(RUN15), db_path=db, output_dir=tmp_path)
    assert res.returncode == 2
    assert "malformed persisted note JSON" in res.stderr
    assert counts(db) == before


def test_missing_or_forbidden_safety_flags_fail_closed(tmp_path):
    for key, value in [
        ("advisory_only", None),
        ("author_allowed", True),
        ("publication_approved", True),
        ("claim_inserted", True),
        ("editorial_review_inserted", True),
        ("source_registry_promoted", True),
    ]:
        db = db_copy(tmp_path / key)
        (tmp_path / key).mkdir(exist_ok=True)
        def mut(note, key=key, value=value):
            if value is None:
                note.pop(key, None)
            else:
                note[key] = value
        mutate_note(db, mut)
        before = counts(db)
        out = tmp_path / f"out-{key}"
        out.mkdir()
        res = run_script("--run16-report", str(RUN16), "--run15-report", str(RUN15), db_path=db, output_dir=out)
        assert res.returncode == 2, key
        assert "safety flag" in res.stderr
        assert counts(db) == before


def test_contradiction_or_do_not_use_note_is_excluded_not_eligible(tmp_path):
    db = db_copy(tmp_path)
    mutate_note(db, lambda note: note.update({
        "support_decision": "contradicted",
        "corroboration_decision": "not_corroborated",
        "evidence_use_decision": "do_not_use",
        "contradiction_flag": True,
    }))
    res = run_script("--run16-report", str(RUN16), "--run15-report", str(RUN15), db_path=db, output_dir=tmp_path)
    assert res.returncode == 0, res.stderr + res.stdout
    payload = read_manifest(tmp_path)
    assert payload["eligible_for_clustering_count"] == 0
    assert payload["caveat_only_cluster_candidate_count"] == 0
    assert any(i["note_id"] == NOTE_ID and i["downstream_manifest_decision"] == "contradiction_review_required" for i in payload["excluded_items"])


def test_missing_input_fails_closed(tmp_path):
    db = db_copy(tmp_path)
    before = counts(db)
    res = run_script("--run16-report", str(tmp_path / "missing.json"), "--run15-report", str(RUN15), db_path=db, output_dir=tmp_path)
    assert res.returncode == 2
    assert "missing input" in res.stderr
    assert counts(db) == before
