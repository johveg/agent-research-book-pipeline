import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_script(*args, env=None):
    full_env = os.environ.copy()
    if env:
        full_env.update(env)
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "build_candidate_source_template.py"), *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        env=full_env,
    )


def make_db(path: Path):
    con = sqlite3.connect(path)
    con.executescript(
        """
        CREATE TABLE sources (id TEXT PRIMARY KEY, quality_score TEXT, privacy_publication_status TEXT, duplicate_status TEXT);
        CREATE TABLE source_notes (id TEXT PRIMARY KEY, source_id TEXT NOT NULL, note TEXT NOT NULL, note_type TEXT DEFAULT 'summary', created_at TEXT NOT NULL);
        CREATE TABLE claims (id TEXT PRIMARY KEY, status TEXT, publication_decision TEXT, contradiction_status TEXT);
        CREATE TABLE editorial_reviews (id TEXT PRIMARY KEY, run_id TEXT, review_type TEXT, status TEXT, summary TEXT, report_path TEXT, created_at TEXT);
        INSERT INTO sources VALUES ('src_a', 'B', 'publishable_metadata_only', 'unique');
        INSERT INTO claims VALUES ('claim_a', 'draft', 'not_reviewed', 'none');
        INSERT INTO editorial_reviews VALUES ('review_a', 'old', 'manual', 'open', 'summary', 'report', '2026-01-01T00:00:00Z');
        """
    )
    con.commit(); con.close()


def db_snapshot(path: Path):
    con = sqlite3.connect(path); con.row_factory = sqlite3.Row
    try:
        return {
            "source_notes": [dict(r) for r in con.execute("SELECT * FROM source_notes ORDER BY id")],
            "claims": [dict(r) for r in con.execute("SELECT * FROM claims ORDER BY id")],
            "editorial_reviews": [dict(r) for r in con.execute("SELECT * FROM editorial_reviews ORDER BY id")],
            "sources_status": [dict(r) for r in con.execute("SELECT id, quality_score, privacy_publication_status, duplicate_status FROM sources ORDER BY id")],
        }
    finally:
        con.close()


def file_bytes(rel):
    return (ROOT / rel).read_bytes()


def docs_book_snapshot():
    docs = ROOT / "docs" / "book"
    return {str(p.relative_to(ROOT)): p.read_bytes() for p in sorted(docs.glob("**/*")) if p.is_file()}


def item(idx, *, next_stage="run_additional_source_collection"):
    return {
        "item_id": f"item_{idx}",
        "source_review_id": f"source_review_{idx}",
        "source_id": "src_a",
        "original_statement": f"Statement {idx}",
        "what_needs_corroboration": f"Needs corroboration {idx}",
        "why_current_evidence_is_insufficient": f"Insufficient evidence {idx}",
        "suggested_search_queries": [f"query {idx} a", f"query {idx} b"],
        "required_source_types": ["official_report", "academic_paper"],
        "recommended_next_stage": next_stage,
        "preliminary_collection_assessment": "needs_more_collection" if next_stage == "run_additional_source_collection" else "needs_editor_review",
        "candidate_sources": [],
        "candidate_source_count": 0,
        "advisory_only": True,
        "author_allowed": False,
        "publication_approved": False,
    }


def make_run14a(path: Path):
    payload = {
        "run_id": "fixture-run",
        "mode": "corroboration_source_import",
        "template_only": False,
        "report_only": True,
        "candidate_json_present": False,
        "changed_db": False,
        "changed_source_registry": False,
        "changed_raw_captures": False,
        "changed_docs_book": False,
        "changed_schema": False,
        "changed_daily_worker": False,
        "claims_inserted": 0,
        "editorial_reviews_inserted": 0,
        "source_status_changed": False,
        "claim_status_changed": False,
        "editorial_status_changed": False,
        "selected_items": [item("one"), item("two")],
        "skipped_items": [
            {**item("editor", next_stage="needs_editor_review"), "skip_reason": "needs_editor_review_not_source_collection"},
            {**item("persisted", next_stage="eligible_for_review_note_persistence"), "skip_reason": "not_additional_source_collection_candidate"},
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_build_template_includes_only_unresolved_items_and_safety(tmp_path):
    db = tmp_path / "book.sqlite"; make_db(db)
    run14a = make_run14a(tmp_path / "run14a.json")
    before_db = db_snapshot(db)
    before_registry = file_bytes("data/source_registry.json")
    before_schema = file_bytes("data/schema.sql")
    before_worker = file_bytes("scripts/daily_book_worker.py")
    before_docs = docs_book_snapshot()

    result = run_script(
        "--run-id", "fixture-run",
        "--output-dir", str(tmp_path),
        "--source-import-report", str(run14a),
        "--create-expected-candidate-json",
        "--report-suffix", "run14b",
        env={"TEREFO_BOOK_DB_PATH": str(db)},
    )
    assert result.returncode == 0, result.stderr + result.stdout
    report = json.loads((tmp_path / "fixture-run-curated-candidate-sources-run14-template-run14b.json").read_text())
    template = json.loads((tmp_path / "fixture-run-curated-candidate-sources-run14-template.json").read_text())
    expected = json.loads((tmp_path / "fixture-run-curated-candidate-sources-run14.json").read_text())
    assert (tmp_path / "fixture-run-curated-candidate-sources-run14-template-run14b.md").exists()

    assert report["unresolved_items_count"] == 2
    assert report["skipped_items_count"] == 2
    assert report["template_only"] is True
    assert report["ready_for_import"] is False
    assert report["claims_inserted"] == 0
    assert report["editorial_reviews_inserted"] == 0
    assert report["changed_db"] is False
    assert report["changed_source_registry"] is False
    assert report["changed_raw_captures"] is False
    assert report["changed_docs_book"] is False
    assert report["changed_schema"] is False
    assert report["changed_daily_worker"] is False

    assert template["template_only"] is True
    assert template["ready_for_import"] is False
    assert template["max_candidates_per_item"] == 5
    assert len(template["items"]) == 2
    assert {i["source_review_id"] for i in template["items"]} == {"source_review_one", "source_review_two"}
    assert all(i["candidate_sources"] == [] for i in template["items"])
    assert all("example_candidate_source_object" in i for i in template["items"])
    assert all("https://example.invalid/replace-with-real-public-source" == i["example_candidate_source_object"]["url"] for i in template["items"])
    assert "source_review_editor" not in json.dumps(template["items"])
    assert "source_review_persisted" not in json.dumps(template["items"])
    assert "candidate_source_schema" in template
    assert set(["primary_source", "official_report", "academic_paper", "reputable_industry_analysis", "reputable_news_or_magazine", "public_documentation", "public_original_interview"]).issubset(set(template["allowed_source_type_values"]))
    assert set(["social_media_post", "seo_content_farm", "unsourced_blog_post", "scraped_repost", "ai_generated_summary", "vendor_marketing_page", "private_or_raw_capture", "unverifiable_screenshot", "unattributed_source"]).issubset(set(template["disallowed_source_type_values"]))
    assert template["allowed_support_direction_values"] == ["supports", "partially_supports", "contradicts", "context_only", "unclear"]
    assert template["allowed_evidence_strength_values"] == ["strong", "moderate", "weak", "unsuitable"]

    assert expected["template_only"] is True
    assert expected["ready_for_import"] is False
    assert expected["candidate_sources"] == []
    assert "https://" not in json.dumps(expected)
    assert db_snapshot(db) == before_db
    assert file_bytes("data/source_registry.json") == before_registry
    assert file_bytes("data/schema.sql") == before_schema
    assert file_bytes("scripts/daily_book_worker.py") == before_worker
    assert docs_book_snapshot() == before_docs


def test_missing_or_unsafe_input_fails_closed(tmp_path):
    missing = run_script("--source-import-report", str(tmp_path / "missing.json"), "--output-dir", str(tmp_path))
    assert missing.returncode != 0

    unsafe_path = tmp_path / "unsafe.json"
    payload = {"mode": "corroboration_source_import", "changed_db": True, "selected_items": []}
    unsafe_path.write_text(json.dumps(payload), encoding="utf-8")
    unsafe = run_script("--source-import-report", str(unsafe_path), "--output-dir", str(tmp_path))
    assert unsafe.returncode != 0
