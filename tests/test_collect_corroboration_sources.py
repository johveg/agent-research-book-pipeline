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
        [sys.executable, str(ROOT / "scripts" / "collect_corroboration_sources.py"), *args],
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


def review(idx, *, status="insufficient_evidence", evidence="needs_more_sources", next_stage="run_additional_source_collection"):
    return {
        "item_id": f"item_{idx}",
        "source_review_id": f"source_review_{idx}",
        "filing_evaluation_id": f"filing_{idx}",
        "source_id": "src_a",
        "semantic_object_id": f"obj_{idx}",
        "original_statement": f"Statement {idx}",
        "what_needs_corroboration": f"Needs public corroboration {idx}",
        "suggested_search_queries": [f"query {idx} a", f"query {idx} b"],
        "required_source_types": ["official reports", "academic papers"],
        "corroboration_status": status,
        "evidence_use_decision": evidence,
        "recommended_next_stage": next_stage,
        "advisory_only": True,
        "author_allowed": False,
        "publication_approved": False,
    }


def make_run12(path: Path):
    payload = {
        "run_id": "run13-fixture",
        "mode": "corroboration_research",
        "report_only": True,
        "changed_db": False,
        "changed_docs_book": False,
        "changed_schema": False,
        "changed_daily_worker": False,
        "claims_inserted": 0,
        "editorial_reviews_inserted": 0,
        "source_status_changed": False,
        "claim_status_changed": False,
        "editorial_status_changed": False,
        "corroboration_reviews": [
            review("one"),
            review("two"),
            review("editor", status="source_context_unclear", evidence="needs_source_review", next_stage="needs_editor_review"),
            review("eligible", status="corroborated", evidence="eligible_as_caveat_only_after_corroboration", next_stage="eligible_for_review_note_persistence"),
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def make_candidates(path: Path):
    payload = {
        "candidate_sources": [
            {
                "item_id": "item_one",
                "source_review_id": "source_review_one",
                "title": "Official report",
                "url": "https://example.org/report",
                "publisher": "Example Org",
                "author": "",
                "publication_date": "2025-01-01",
                "access_type": "public",
                "source_type": "official reports",
                "candidate_relevance": "Relevant primary context",
                "support_direction": "partially_supports",
                "evidence_strength": "moderate",
                "reason_for_inclusion": "Matches requested official report source type",
                "limitations": "Not yet entered in source registry",
                "safe_summary": "Short public summary only.",
                "raw_content_stored": False,
            },
            {
                "item_id": "item_one",
                "source_review_id": "source_review_one",
                "title": "SEO repost",
                "url": "https://spam.example/repost",
                "publisher": "Content Farm",
                "access_type": "public",
                "source_type": "SEO content farms",
                "candidate_relevance": "Low quality repost",
                "support_direction": "unclear",
                "evidence_strength": "strong",
                "reason_for_inclusion": "Test rejection",
                "limitations": "Disallowed source type",
                "safe_summary": "No raw content.",
                "raw_content_stored": False,
            },
            {
                "item_id": "item_two",
                "source_review_id": "source_review_two",
                "title": "Academic paper",
                "url": "https://doi.org/10.0000/example",
                "publisher": "Journal",
                "access_type": "public",
                "source_type": "academic papers",
                "candidate_relevance": "Relevant background",
                "support_direction": "context_only",
                "evidence_strength": "weak",
                "reason_for_inclusion": "Matches requested academic source type",
                "limitations": "Background only",
                "safe_summary": "Short public abstract-like summary.",
                "raw_content_stored": False,
            },
        ]
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_selection_candidate_validation_and_report_only_safety(tmp_path):
    db = tmp_path / "book.sqlite"; make_db(db)
    run12 = make_run12(tmp_path / "run12.json")
    candidates = make_candidates(tmp_path / "candidates.json")
    before_db = db_snapshot(db)
    before_registry = file_bytes("data/source_registry.json")
    before_schema = file_bytes("data/schema.sql")
    before_worker = file_bytes("scripts/daily_book_worker.py")
    before_docs = docs_book_snapshot()
    result = run_script(
        "--run-id", "run13-fixture",
        "--output-dir", str(tmp_path),
        "--corroboration-research-report", str(run12),
        "--candidate-sources-json", str(candidates),
        "--max-candidates-per-item", "1",
        "--report-suffix", "run13",
        env={"TEREFO_BOOK_DB_PATH": str(db)},
    )
    assert result.returncode == 0, result.stderr + result.stdout
    payload = json.loads((tmp_path / "run13-fixture-corroboration-source-collection-run13.json").read_text())
    assert (tmp_path / "run13-fixture-corroboration-source-collection-run13.md").exists()
    assert payload["selected_items_count"] == 2
    assert payload["skipped_items_count"] == 2
    assert payload["collected_candidate_sources_count"] == 2
    assert payload["source_collection_executed"] is True
    skipped = {i["source_review_id"]: i["skip_reason"] for i in payload["skipped_items"]}
    assert skipped["source_review_editor"] == "needs_editor_review_not_source_collection"
    assert skipped["source_review_eligible"] == "not_additional_source_collection_candidate"
    assert payload["candidate_source_type_counts"] == {"academic_paper": 1, "official_report": 1}
    assert payload["support_direction_counts"] == {"context_only": 1, "partially_supports": 1}
    assert payload["evidence_strength_counts"] == {"moderate": 1, "weak": 1}
    for item in payload["collection_results"]:
        assert item["candidate_source_count"] <= 1
        assert item["advisory_only"] is True
        assert item["author_allowed"] is False
        assert item["publication_approved"] is False
        for cand in item["candidate_sources"]:
            assert cand["candidate_source_id"].startswith("cand_")
            assert cand["raw_content_stored"] is False
            assert cand["access_type"] == "public"
            assert cand["source_type"] != "seo_content_farm"
    assert payload["changed_db"] is False
    assert payload["changed_source_registry"] is False
    assert payload["changed_raw_captures"] is False
    assert payload["changed_docs_book"] is False
    assert payload["changed_schema"] is False
    assert payload["changed_daily_worker"] is False
    assert payload["claims_inserted"] == 0
    assert payload["editorial_reviews_inserted"] == 0
    assert db_snapshot(db) == before_db
    assert file_bytes("data/source_registry.json") == before_registry
    assert file_bytes("data/schema.sql") == before_schema
    assert file_bytes("scripts/daily_book_worker.py") == before_worker
    assert docs_book_snapshot() == before_docs


def test_no_live_collection_tooling_mode_and_invalid_input_fail_closed(tmp_path):
    db = tmp_path / "book.sqlite"; make_db(db)
    run12 = make_run12(tmp_path / "run12.json")
    result = run_script(
        "--run-id", "run13-fixture",
        "--output-dir", str(tmp_path),
        "--corroboration-research-report", str(run12),
        "--report-suffix", "run13",
        env={"TEREFO_BOOK_DB_PATH": str(db)},
    )
    assert result.returncode == 0, result.stderr + result.stdout
    payload = json.loads((tmp_path / "run13-fixture-corroboration-source-collection-run13.json").read_text())
    assert payload["source_collection_executed"] is False
    assert payload["collection_method"] == "collection_plan_only_tooling_unavailable"
    assert payload["collected_candidate_sources_count"] == 0
    assert {r["source_collection_status"] for r in payload["collection_results"]} == {"collection_not_executed_tooling_unavailable"}

    missing = run_script(
        "--run-id", "run13-fixture",
        "--output-dir", str(tmp_path),
        "--corroboration-research-report", str(tmp_path / "missing.json"),
        env={"TEREFO_BOOK_DB_PATH": str(db)},
    )
    assert missing.returncode != 0


def test_candidate_ids_are_deterministic_and_limit_is_enforced(tmp_path):
    db = tmp_path / "book.sqlite"; make_db(db)
    run12 = make_run12(tmp_path / "run12.json")
    candidates = make_candidates(tmp_path / "candidates.json")
    args = ["--run-id", "run13-fixture", "--output-dir", str(tmp_path), "--corroboration-research-report", str(run12), "--candidate-sources-json", str(candidates), "--max-candidates-per-item", "1", "--report-suffix"]
    r1 = run_script(*args, "a", env={"TEREFO_BOOK_DB_PATH": str(db)})
    r2 = run_script(*args, "b", env={"TEREFO_BOOK_DB_PATH": str(db)})
    assert r1.returncode == 0 and r2.returncode == 0
    p1 = json.loads((tmp_path / "run13-fixture-corroboration-source-collection-a.json").read_text())
    p2 = json.loads((tmp_path / "run13-fixture-corroboration-source-collection-b.json").read_text())
    ids1 = [c["candidate_source_id"] for item in p1["collection_results"] for c in item["candidate_sources"]]
    ids2 = [c["candidate_source_id"] for item in p2["collection_results"] for c in item["candidate_sources"]]
    assert ids1 == ids2
    assert all(item["candidate_source_count"] <= 1 for item in p1["collection_results"])



def make_run13(path: Path):
    payload = {
        "run_id": "run14-fixture",
        "mode": "corroboration_source_collection",
        "report_only": True,
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
        "collection_results": [
            {**review("one"), "source_collection_status": "collection_not_executed_tooling_unavailable", "candidate_sources": [], "candidate_source_count": 0},
            {**review("two"), "source_collection_status": "collection_not_executed_tooling_unavailable", "candidate_sources": [], "candidate_source_count": 0},
            {**review("editor", status="source_context_unclear", evidence="needs_source_review", next_stage="needs_editor_review"), "source_collection_status": "collection_not_executed_tooling_unavailable", "candidate_sources": [], "candidate_source_count": 0},
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def make_run14_candidates(path: Path):
    sources = []
    for n in range(6):
        sources.append({
            "item_id": "item_one",
            "source_review_id": "source_review_one",
            "url": f"https://example.org/one/{n}",
            "title": f"Official report {n}",
            "publisher": "Example Org",
            "publication_date": None,
            "author": None,
            "source_type": "official_report",
            "access_type": "public",
            "candidate_relevance": "Relevant",
            "support_direction": "supports" if n == 0 else "partially_supports",
            "evidence_strength": "strong" if n == 0 else "moderate",
            "reason_for_inclusion": "Curated public source",
            "limitations": "Candidate only",
            "safe_summary": "Short summary only",
            "raw_content_stored": False,
        })
    sources += [
        {**sources[0], "url": "https://example.org/one/0"},
        {**sources[0], "item_id": "item_two", "source_review_id": "source_review_two", "url": "https://example.org/one/0", "title": "Same URL reused"},
        {**sources[0], "item_id": "item_two", "source_review_id": "source_review_two", "url": "https://example.org/two/0", "title": "Academic paper", "source_type": "academic_paper", "support_direction": "context_only", "evidence_strength": "moderate"},
        {**sources[0], "item_id": "item_editor", "source_review_id": "source_review_editor", "url": "https://example.org/editor", "title": "Editor item should reject"},
        {**sources[0], "item_id": "unknown", "source_review_id": "source_review_unknown", "url": "https://example.org/unknown", "title": "Unknown item"},
        {**sources[0], "url": "https://example.org/disallowed", "title": "Social", "source_type": "social_media_post"},
        {**sources[0], "url": "https://example.org/raw", "title": "Raw true", "raw_content_stored": True},
        {**sources[0], "url": "https://example.org/private", "title": "Private", "access_type": "private"},
        {**sources[0], "url": "ftp://example.org/bad", "title": "Bad URL"},
    ]
    path.write_text(json.dumps({"candidate_sources": sources}), encoding="utf-8")
    return path


def test_run14a_requires_candidate_json_and_validates_curated_import(tmp_path):
    db = tmp_path / "book.sqlite"; make_db(db)
    run13 = make_run13(tmp_path / "run13.json")
    missing = run_script(
        "--run-id", "run14-fixture", "--output-dir", str(tmp_path),
        "--corroboration-research-report", str(run13),
        "--candidate-sources-json", str(tmp_path / "definitely-missing-candidates.json"),
        "--require-candidate-sources", "--report-suffix", "run14",
        env={"TEREFO_BOOK_DB_PATH": str(db)},
    )
    assert missing.returncode != 0
    assert "curated candidate-source JSON" in (missing.stderr + missing.stdout)

    candidates = make_run14_candidates(tmp_path / "candidates.json")
    before_db = db_snapshot(db)
    before_registry = file_bytes("data/source_registry.json")
    result = run_script(
        "--run-id", "run14-fixture", "--output-dir", str(tmp_path),
        "--corroboration-research-report", str(run13),
        "--candidate-sources-json", str(candidates),
        "--require-candidate-sources", "--max-candidates-per-item", "5",
        "--report-suffix", "run14",
        env={"TEREFO_BOOK_DB_PATH": str(db)},
    )
    assert result.returncode == 0, result.stderr + result.stdout
    payload = json.loads((tmp_path / "run14-fixture-corroboration-source-import-run14.json").read_text())
    assert payload["mode"] == "corroboration_source_import"
    assert payload["selected_items_count"] == 2
    assert payload["skipped_items_count"] == 1
    assert payload["candidate_sources_submitted_count"] == 15
    assert payload["candidate_sources_accepted_count"] == 6
    assert payload["candidate_sources_rejected_count"] == 9
    assert payload["duplicate_url_count"] == 2
    assert payload["preliminary_collection_assessment_counts"]["enough_candidates_for_re_review"] == 2
    assert payload["recommended_next_stage_counts"]["run_source_support_re_review"] == 2
    rejected = {r["reason"] for r in payload["rejected_candidate_sources"]}
    assert "candidate_for_unselected_item" in rejected
    assert "bounded_collection_limit_enforced" in rejected
    assert "duplicate_url_for_item" in rejected
    assert "duplicate_url_across_items" in rejected
    assert "disallowed_source_type" in rejected
    assert "raw_content_stored_not_false" in rejected
    assert "access_type_not_public" in rejected
    assert "invalid_public_url" in rejected
    assert db_snapshot(db) == before_db
    assert file_bytes("data/source_registry.json") == before_registry
    assert payload["changed_db"] is False
    assert payload["changed_source_registry"] is False
    assert payload["claims_inserted"] == 0
    assert payload["editorial_reviews_inserted"] == 0
