import json
import sqlite3
import subprocess
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_OBJECT_FIELDS = {
    "semantic_object_id",
    "object_type",
    "source_id",
    "source_note_id",
    "source_card_id",
    "run_id",
    "text",
    "paraphrase_only",
    "evidence_basis",
    "source_quality_score",
    "privacy_publication_status",
    "evidence_strength",
    "recommended_use",
    "candidate_chapter_targets",
    "risk_flags",
    "do_not_publish_reason",
    "author_allowed",
    "publication_approved",
    "advisory_only",
    "source_text_hash",
    "source_card_hash",
    "object_input_hash",
    "object_output_hash",
    "llm_used",
    "model",
    "confidence",
}


def run_semantic(*args):
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "llm_extract_semantic_objects.py"), *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )


def db_bytes():
    p = ROOT / ".var" / "book.sqlite"
    return p.read_bytes() if p.exists() else None


def status_snapshots():
    p = ROOT / ".var" / "book.sqlite"
    con = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        return {
            "sources": [
                dict(r)
                for r in con.execute(
                    "SELECT id, quality_score, privacy_publication_status, duplicate_status FROM sources ORDER BY id LIMIT 25"
                )
            ],
            "claims": [
                dict(r)
                for r in con.execute(
                    "SELECT id, status, publication_decision, contradiction_status FROM claims ORDER BY id LIMIT 25"
                )
            ],
            "editorial_reviews": [
                dict(r)
                for r in con.execute(
                    "SELECT id, run_id, review_type, status, summary, report_path, created_at FROM editorial_reviews ORDER BY id LIMIT 25"
                )
            ],
        }
    finally:
        con.close()


def semantic_note_count(run_id=None):
    p = ROOT / ".var" / "book.sqlite"
    con = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    try:
        if run_id:
            return con.execute(
                "SELECT COUNT(*) FROM source_notes WHERE note_type='semantic_object_draft' AND note LIKE ?",
                [f'%"run_id":"{run_id}"%'],
            ).fetchone()[0]
        return con.execute("SELECT COUNT(*) FROM source_notes WHERE note_type='semantic_object_draft'").fetchone()[0]
    finally:
        con.close()


def delete_semantic_notes_for_run(run_id):
    p = ROOT / ".var" / "book.sqlite"
    con = sqlite3.connect(p)
    try:
        con.execute(
            "DELETE FROM source_notes WHERE note_type='semantic_object_draft' AND note LIKE ?",
            [f'%"run_id":"{run_id}"%'],
        )
        con.commit()
    finally:
        con.close()


def read_semantic_notes(run_id):
    p = ROOT / ".var" / "book.sqlite"
    con = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        return [
            dict(r)
            for r in con.execute(
                "SELECT id, source_id, note, note_type, created_at FROM source_notes WHERE note_type='semantic_object_draft' AND note LIKE ? ORDER BY created_at DESC, id DESC",
                [f'%"run_id":"{run_id}"%'],
            )
        ]
    finally:
        con.close()


def test_semantic_objects_no_llm_report_only_writes_reports_and_schema(tmp_path):
    before_db = db_bytes()
    before_statuses = status_snapshots()
    before_book = {p.relative_to(ROOT): p.read_bytes() for p in sorted((ROOT / "docs" / "book").glob("*.md"))}

    result = run_semantic(
        "--run-id",
        "latest",
        "--limit",
        "3",
        "--output-dir",
        str(tmp_path),
        "--no-llm",
        "--max-object-chars",
        "160",
    )

    assert result.returncode == 0, result.stderr + result.stdout
    json_path = tmp_path / "citation-pipeline-test-20260612-semantic-object-drafts.json"
    md_path = tmp_path / "citation-pipeline-test-20260612-semantic-object-drafts.md"
    assert json_path.exists()
    assert md_path.exists()
    payload = json.loads(json_path.read_text())
    assert payload["mode"] == "semantic_object_drafts"
    assert payload["reasoning_status"] == "no_llm_structural_only"
    assert payload["llm_used"] is False
    assert payload["confidence_level"] == "low_draft_structural"
    assert payload["db_modified"] is False
    assert payload["db_write_scope"] == "none"
    assert payload["chapters_modified"] is False
    assert payload["statuses_modified"] is False
    assert payload["schema_modified"] is False
    assert payload["daily_worker_modified"] is False
    assert payload["commit_allowlist_modified"] is False
    assert payload["raw_private_material_written"] is False
    assert payload["long_source_excerpt_written"] is False
    assert payload["source_card_notes_read"] <= 3
    assert payload["semantic_objects_generated"] == len(payload["semantic_objects"])
    assert payload["semantic_objects"]
    for obj in payload["semantic_objects"]:
        assert REQUIRED_OBJECT_FIELDS <= set(obj)
        assert obj["source_id"]
        assert obj["source_note_id"]
        assert obj["source_card_id"]
        assert obj["run_id"] == payload["run_id"]
        assert obj["author_allowed"] is False
        assert obj["publication_approved"] is False
        assert obj["advisory_only"] is True
        assert obj["paraphrase_only"] is True
        assert obj["evidence_basis"] == "source_card_draft"
        assert obj["llm_used"] is False
        assert obj["confidence"] == "low"
        assert len(obj["text"]) <= 160
    md = md_path.read_text()
    assert "High-reasoning canary" in md
    assert "Safety assessment" in md
    assert "Recommendation for Run 5" in md
    assert db_bytes() == before_db
    assert status_snapshots() == before_statuses
    after_book = {p.relative_to(ROOT): p.read_bytes() for p in sorted((ROOT / "docs" / "book").glob("*.md"))}
    assert after_book == before_book


def test_semantic_objects_write_semantic_notes_only_and_idempotent(tmp_path):
    run_id = f"test-semantic-{uuid.uuid4().hex}"
    delete_semantic_notes_for_run(run_id)
    before_statuses = status_snapshots()
    before_book = {p.relative_to(ROOT): p.read_bytes() for p in sorted((ROOT / "docs" / "book").glob("*.md"))}
    protected = [
        ROOT / "scripts" / "daily_book_worker.py",
        ROOT / "scripts" / "extract_claims.py",
        ROOT / "data" / "schema.sql",
    ]
    before_protected = {p.relative_to(ROOT): p.read_bytes() for p in protected}
    before_count = semantic_note_count()

    first = run_semantic(
        "--run-id",
        run_id,
        "--limit",
        "2",
        "--output-dir",
        str(tmp_path),
        "--no-llm",
        "--write-semantic-notes",
        "--max-object-chars",
        "150",
    )
    assert first.returncode == 0, first.stderr + first.stdout
    payload = json.loads((tmp_path / f"{run_id}-semantic-object-drafts.json").read_text())
    assert payload["write_semantic_notes_requested"] is True
    assert payload["db_write_scope"] == "source_notes_only"
    assert payload["db_modified"] is True
    assert payload["semantic_notes_inserted"] == payload["semantic_objects_generated"]
    assert payload["semantic_notes_failed"] == 0
    assert semantic_note_count() == before_count + payload["semantic_notes_inserted"]

    notes = read_semantic_notes(run_id)
    assert len(notes) == payload["semantic_objects_generated"]
    for row in notes:
        assert row["note_type"] == "semantic_object_draft"
        obj = json.loads(row["note"])
        assert REQUIRED_OBJECT_FIELDS <= set(obj)
        assert obj["advisory_only"] is True
        assert obj["author_allowed"] is False
        assert obj["publication_approved"] is False
        assert obj["llm_used"] is False
        assert obj["confidence"] == "low"
        assert obj["object_input_hash"]
        assert obj["object_output_hash"]
        assert len(obj["text"]) <= 150

    second = run_semantic(
        "--run-id",
        run_id,
        "--limit",
        "2",
        "--output-dir",
        str(tmp_path),
        "--no-llm",
        "--write-semantic-notes",
        "--max-object-chars",
        "150",
    )
    assert second.returncode == 0, second.stderr + second.stdout
    payload2 = json.loads((tmp_path / f"{run_id}-semantic-object-drafts.json").read_text())
    assert payload2["semantic_notes_inserted"] == 0
    assert payload2["semantic_notes_skipped_existing"] == payload2["semantic_objects_generated"]
    assert semantic_note_count() == before_count + payload["semantic_notes_inserted"]
    assert status_snapshots() == before_statuses
    after_book = {p.relative_to(ROOT): p.read_bytes() for p in sorted((ROOT / "docs" / "book").glob("*.md"))}
    assert after_book == before_book
    after_protected = {p.relative_to(ROOT): p.read_bytes() for p in protected}
    assert after_protected == before_protected
    delete_semantic_notes_for_run(run_id)


def test_semantic_objects_require_high_reasoning_invalid_bridge_fails_safely_without_notes(tmp_path):
    before = semantic_note_count()
    before_db = db_bytes()
    bridge = make_mock_bridge(tmp_path, {"ok": False, "error": "mock failure"}, exit_code=2)
    result = run_semantic_with_env(
        {"TEREFO_HIGH_REASONING_BRIDGE_COMMAND": bridge},
        "--run-id",
        "latest",
        "--limit",
        "1",
        "--output-dir",
        str(tmp_path),
        "--llm-canary-only",
        "--require-high-reasoning",
    )
    assert result.returncode != 0
    assert "high-reasoning bridge failed" in result.stderr
    assert "weak/local fallback refused" in result.stderr
    assert semantic_note_count() == before
    assert db_bytes() == before_db


def test_semantic_objects_fail_safe_with_write_flag_writes_no_notes(tmp_path):
    before = semantic_note_count()
    before_db = db_bytes()
    bridge = make_mock_bridge(tmp_path, {"ok": False, "error": "mock failure"}, exit_code=2)
    result = run_semantic_with_env(
        {"TEREFO_HIGH_REASONING_BRIDGE_COMMAND": bridge},
        "--run-id",
        "latest",
        "--limit",
        "1",
        "--output-dir",
        str(tmp_path),
        "--require-high-reasoning",
        "--write-semantic-notes",
    )
    assert result.returncode != 0
    assert semantic_note_count() == before
    assert db_bytes() == before_db



def make_mock_bridge(tmp_path, payload, exit_code=0):
    p = tmp_path / "mock_bridge_semantic.py"
    body = "#!/usr/bin/env python3\nimport json, sys\n"
    if exit_code == 0:
        body += "req=json.load(sys.stdin)\n"
        body += "schema=req.get('schema_name')\n"
        body += "payload=" + repr(payload) + "\n"
        body += "print(json.dumps({'ok': True, 'model': 'gpt-5.5', 'reasoning': 'available'} if schema == 'canary' else payload))\n"
    else:
        body += "print(json.dumps({'ok': False, 'error': 'mock failure'}))\nsys.exit(" + str(exit_code) + ")\n"
    p.write_text(body, encoding="utf-8")
    p.chmod(0o755)
    return str(p)


def run_semantic_with_env(env, *args):
    import os
    full_env = os.environ.copy()
    full_env.update(env)
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "llm_extract_semantic_objects.py"), *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        env=full_env,
    )


def test_semantic_high_reasoning_path_mocked_sets_llm_used_true_and_report_only(tmp_path):
    payload = {
        "ok": True,
        "provider": "copilot",
        "model": "gpt-5.5",
        "bridge": "hermes_cli",
        "llm_used": True,
        "reasoning_status": "high_reasoning_used",
        "semantic_objects": [],
    }
    before_db = db_bytes()
    before_statuses = status_snapshots()
    bridge = make_mock_bridge(tmp_path, payload)
    res = run_semantic_with_env(
        {"TEREFO_HIGH_REASONING_BRIDGE_COMMAND": bridge, "TEREFO_LLM_PROVIDER": "copilot", "TEREFO_LLM_REASONING_MODEL": "gpt-5.5"},
        "--run-id", "test-semantic-hr", "--limit", "2", "--output-dir", str(tmp_path), "--max-object-chars", "160",
    )
    assert res.returncode == 0, res.stderr + res.stdout
    report = json.loads((tmp_path / "test-semantic-hr-semantic-object-drafts-high-reasoning.json").read_text())
    assert report["llm_used"] is True
    assert report["reasoning_status"] == "high_reasoning_used"
    assert report["provider"] == "copilot"
    assert report["model"] == "gpt-5.5"
    assert report["db_modified"] is False
    assert db_bytes() == before_db
    assert status_snapshots() == before_statuses
    assert report["semantic_objects"]
    for obj in report["semantic_objects"]:
        assert REQUIRED_OBJECT_FIELDS <= set(obj)
        assert obj["llm_used"] is True
        assert obj["model"] == "gpt-5.5"
        assert obj["author_allowed"] is False
        assert obj["publication_approved"] is False
        assert obj["advisory_only"] is True


def test_semantic_high_reasoning_invalid_bridge_fails_closed_no_db_write(tmp_path):
    before_db = db_bytes()
    bridge = make_mock_bridge(tmp_path, {"ok": False, "error": "invalid_json"}, exit_code=2)
    res = run_semantic_with_env(
        {"TEREFO_HIGH_REASONING_BRIDGE_COMMAND": bridge},
        "--run-id", "test-semantic-hr-fail", "--limit", "1", "--output-dir", str(tmp_path),
    )
    assert res.returncode != 0
    assert db_bytes() == before_db
    assert not (tmp_path / "test-semantic-hr-fail-semantic-object-drafts-high-reasoning.json").exists()
