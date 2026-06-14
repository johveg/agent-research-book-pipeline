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
        [sys.executable, str(ROOT / "scripts" / "llm_corroboration_research.py"), *args],
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
        INSERT INTO sources VALUES ('src_a', 'B', 'publishable_metadata_only', 'unique');
        INSERT INTO claims VALUES ('claim_a', 'draft', 'not_reviewed', 'none');
        INSERT INTO editorial_reviews VALUES ('review_a', 'old', 'manual', 'open', 'summary', 'report', '2026-01-01T00:00:00Z');
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


def file_bytes(rel):
    return (ROOT / rel).read_bytes()


def review_item(idx, *, support="partially_supported", corr="corroboration_required", evidence="needs_corroboration_before_filing", next_stage="run_corroboration_research"):
    return {
        "source_review_id": f"source_review_{idx}",
        "run_id": "run12-fixture",
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
        "semantic_object_text": f"Advisory statement {idx} needing review.",
        "filing_decision": "needs_corroboration",
        "novelty_decision": "partially_novel",
        "source_support_decision": support,
        "corroboration_decision": corr,
        "evidence_use_decision": evidence,
        "next_stage_recommendation": next_stage,
        "support_rationale": "Short support rationale.",
        "corroboration_rationale": "Short corroboration rationale.",
        "corroboration_questions": ["What independent source supports this?"],
        "suggested_corroboration_sources": ["official docs"],
        "blockers": [],
        "risk_flags": [],
        "required_editor_decisions": ["Editor must review."],
        "confidence": "medium",
        "author_allowed": False,
        "publication_approved": False,
        "advisory_only": True,
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
        "run_id": "run12-fixture",
        "mode": "source_support_review",
        "llm_used": True,
        "provider": "copilot",
        "model": "gpt-5.5",
        "bridge": "hermes_cli",
        "reasoning_status": "high_reasoning_used",
        "items_reviewed": 6,
        "db_modified": False,
        "author_allowed": False,
        "publication_approved": False,
        "advisory_only": True,
        "source_reviews": [
            review_item("run_corr"),
            review_item("needs_corr", next_stage="needs_editor_review"),
            review_item("unsupported_only", support="unsupported", corr="corroboration_not_required", evidence="do_not_use", next_stage="exclude_from_pipeline"),
            review_item("unsupported_corr", support="unsupported", corr="corroboration_required", evidence="needs_corroboration_before_filing", next_stage="run_corroboration_research"),
            review_item("unclear_only", support="unclear", corr="corroboration_not_required", evidence="needs_source_review", next_stage="needs_source_review"),
            review_item("eligible", support="supported", corr="corroboration_not_required", evidence="eligible_as_caveat_only", next_stage="eligible_for_filing_persistence"),
        ],
    }
    path.write_text(json.dumps(report), encoding="utf-8")
    return path


def write_mock_bridge(path: Path, *, invalid=False):
    if invalid:
        path.write_text("#!/usr/bin/env python3\nprint('not json')\n", encoding="utf-8")
    else:
        path.write_text(
            "#!/usr/bin/env python3\n"
            "import json,sys\n"
            "payload=json.load(sys.stdin)\n"
            "print(json.dumps({'corroboration_reviews':["
            "{'source_review_id':'source_review_run_corr','corroboration_status':'partially_corroborated','evidence_use_decision':'needs_more_sources','recommended_next_stage':'run_additional_source_collection','what_needs_corroboration':'Independent source support.','corroboration_strategy':'Search official docs and independent analyses.','suggested_search_queries':['query one'],'required_source_types':['official docs'],'corroboration_findings':['No live source collection in this run.'],'current_source_support_enough':False,'risk_flags':['single_source'],'advisory_only':True,'author_allowed':False,'publication_approved':False},"
            "{'source_review_id':'source_review_needs_corr','corroboration_status':'insufficient_evidence','evidence_use_decision':'needs_more_sources','recommended_next_stage':'run_additional_source_collection','what_needs_corroboration':'Second source.','corroboration_strategy':'Collect primary and independent sources.','suggested_search_queries':['query two'],'required_source_types':['primary source'],'corroboration_findings':['Needs source collection.'],'current_source_support_enough':False,'risk_flags':['needs_sources'],'advisory_only':True,'author_allowed':False,'publication_approved':False},"
            "{'source_review_id':'source_review_unsupported_corr','corroboration_status':'source_context_unclear','evidence_use_decision':'needs_source_review','recommended_next_stage':'needs_editor_review','what_needs_corroboration':'Unsupported statement context.','corroboration_strategy':'Resolve source chain first.','suggested_search_queries':['query three'],'required_source_types':['source review'],'corroboration_findings':['Source context unclear.'],'current_source_support_enough':False,'risk_flags':['unsupported_source_chain'],'advisory_only':True,'author_allowed':False,'publication_approved':False}"
            "]}))\n",
            encoding="utf-8",
        )
    path.chmod(0o755)


def test_mocked_high_reasoning_selects_only_corroboration_required_and_is_report_only(tmp_path):
    db = tmp_path / "book.sqlite"
    make_db(db)
    report = make_report(tmp_path / "run10.json")
    mock = tmp_path / "mock_bridge.py"
    write_mock_bridge(mock)
    before_db = db_snapshot(db)
    before_docs = docs_book_snapshot()
    schema_before = file_bytes("data/schema.sql")
    worker_before = file_bytes("scripts/daily_book_worker.py")
    result = run_script(
        "--run-id", "run12-fixture",
        "--output-dir", str(tmp_path),
        "--source-support-review-report", str(report),
        "--require-high-reasoning",
        "--report-suffix", "run12",
        env={"TEREFO_BOOK_DB_PATH": str(db), "TEREFO_HIGH_REASONING_BRIDGE_COMMAND": str(mock)},
    )
    assert result.returncode == 0, result.stderr + result.stdout
    js = tmp_path / "run12-fixture-corroboration-research-run12.json"
    md = tmp_path / "run12-fixture-corroboration-research-run12.md"
    assert js.exists()
    assert md.exists()
    payload = json.loads(js.read_text())
    assert payload["selected_items_count"] == 3
    assert payload["reviewed_items_count"] == 3
    assert payload["skipped_items_count"] == 3
    selected_ids = {i["source_review_id"] for i in payload["selected_items"]}
    assert selected_ids == {"source_review_run_corr", "source_review_needs_corr", "source_review_unsupported_corr"}
    skipped = {i["source_review_id"]: i["skip_reason"] for i in payload["skipped_items"]}
    assert skipped["source_review_unsupported_only"] == "unsupported_without_corroboration_requirement"
    assert skipped["source_review_unclear_only"] == "unclear_without_corroboration_requirement"
    assert skipped["source_review_eligible"] == "already_eligible_or_persisted"
    assert payload["llm_used"] is True
    assert payload["provider"] == "copilot"
    assert payload["model"] == "gpt-5.5"
    assert payload["bridge"] == "hermes_cli"
    assert payload["changed_db"] is False
    assert payload["claims_inserted"] == 0
    assert payload["editorial_reviews_inserted"] == 0
    assert payload["changed_docs_book"] is False
    assert payload["changed_schema"] is False
    assert payload["changed_daily_worker"] is False
    for item in payload["corroboration_reviews"]:
        assert item["advisory_only"] is True
        assert item["author_allowed"] is False
        assert item["publication_approved"] is False
    assert db_snapshot(db) == before_db
    assert docs_book_snapshot() == before_docs
    assert file_bytes("data/schema.sql") == schema_before
    assert file_bytes("scripts/daily_book_worker.py") == worker_before


def test_no_llm_structural_mode_writes_low_confidence_report(tmp_path):
    db = tmp_path / "book.sqlite"
    make_db(db)
    report = make_report(tmp_path / "run10.json")
    result = run_script(
        "--run-id", "run12-fixture",
        "--output-dir", str(tmp_path),
        "--source-support-review-report", str(report),
        "--no-llm",
        "--report-suffix", "run12",
        env={"TEREFO_BOOK_DB_PATH": str(db)},
    )
    assert result.returncode == 0, result.stderr + result.stdout
    payload = json.loads((tmp_path / "run12-fixture-corroboration-research-run12.json").read_text())
    assert payload["llm_used"] is False
    assert payload["reasoning_status"] == "no_llm_structural_only"
    assert payload["selected_items_count"] == 3
    assert payload["reviewed_items_count"] == 3
    assert payload["changed_db"] is False


def test_invalid_input_invalid_json_and_weak_provider_fail_closed(tmp_path):
    db = tmp_path / "book.sqlite"
    make_db(db)
    missing = run_script(
        "--run-id", "run12-fixture",
        "--output-dir", str(tmp_path),
        "--source-support-review-report", str(tmp_path / "missing.json"),
        "--no-llm",
        env={"TEREFO_BOOK_DB_PATH": str(db)},
    )
    assert missing.returncode != 0

    report = make_report(tmp_path / "run10.json")
    bad = tmp_path / "bad_bridge.py"
    write_mock_bridge(bad, invalid=True)
    invalid = run_script(
        "--run-id", "run12-fixture",
        "--output-dir", str(tmp_path),
        "--source-support-review-report", str(report),
        "--require-high-reasoning",
        "--report-suffix", "run12",
        env={"TEREFO_BOOK_DB_PATH": str(db), "TEREFO_HIGH_REASONING_BRIDGE_COMMAND": str(bad)},
    )
    assert invalid.returncode != 0
    assert "high-reasoning" in (invalid.stderr + invalid.stdout).lower() or "json" in (invalid.stderr + invalid.stdout).lower()

    weak = run_script(
        "--run-id", "run12-fixture",
        "--output-dir", str(tmp_path),
        "--source-support-review-report", str(report),
        "--require-high-reasoning",
        "--provider", "local",
        "--report-suffix", "run12",
        env={"TEREFO_BOOK_DB_PATH": str(db)},
    )
    assert weak.returncode != 0
    assert db_snapshot(db)["claims"] == [{"id": "claim_a", "status": "draft", "publication_decision": "not_reviewed", "contradiction_status": "none"}]
