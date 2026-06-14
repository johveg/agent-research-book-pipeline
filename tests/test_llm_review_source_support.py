import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_review(*args, env=None):
    full_env = os.environ.copy()
    if env:
        full_env.update(env)
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "llm_review_source_support.py"), *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        env=full_env,
    )


def db_counts():
    p = ROOT / ".var" / "book.sqlite"
    con = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    try:
        return {
            "claims": con.execute("SELECT COUNT(*) FROM claims").fetchone()[0],
            "source_notes": con.execute("SELECT COUNT(*) FROM source_notes").fetchone()[0],
            "editorial_reviews": con.execute("SELECT COUNT(*) FROM editorial_reviews").fetchone()[0],
        }
    finally:
        con.close()


def docs_book_snapshot():
    docs = ROOT / "docs" / "book"
    return {str(p.relative_to(ROOT)): p.read_bytes() for p in sorted(docs.glob("**/*")) if p.is_file()}


def status_snapshots():
    p = ROOT / ".var" / "book.sqlite"
    con = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        return {
            "sources": [dict(r) for r in con.execute("SELECT id, quality_score, privacy_publication_status, duplicate_status FROM sources ORDER BY id LIMIT 25")],
            "claims": [dict(r) for r in con.execute("SELECT id, status, publication_decision, contradiction_status FROM claims ORDER BY id LIMIT 25")],
            "editorial_reviews": [dict(r) for r in con.execute("SELECT id, run_id, review_type, status, summary, report_path, created_at FROM editorial_reviews ORDER BY id LIMIT 25")],
        }
    finally:
        con.close()


def write_filing_report(tmp_path):
    report = {
        "run_id": "run10-fixture",
        "mode": "filing_novelty_evaluation",
        "llm_used": True,
        "provider": "copilot",
        "model": "gpt-5.5",
        "bridge": "hermes_cli",
        "reasoning_status": "high_reasoning_used",
        "items_evaluated": 2,
        "author_allowed": False,
        "publication_approved": False,
        "advisory_only": True,
        "db_modified": False,
        "filing_evaluations": [
            {
                "filing_evaluation_id": "filing_eval_good",
                "run_id": "run10-fixture",
                "packet_item_id": "packet_good",
                "source_id": "src_good",
                "source_card_id": "card_good",
                "semantic_object_id": "obj_good",
                "quality_review_id": "review_good",
                "semantic_object_type": "claim_candidate",
                "semantic_object_text": "Agent workflow caveats need source support before filing.",
                "candidate_chapter_targets": ["05-context-memory-architecture"],
                "filing_decision": "needs_corroboration",
                "novelty_decision": "partially_novel",
                "next_stage_recommendation": "needs_source_review",
                "corroboration_needed": True,
                "corroboration_questions": ["Find independent support."],
                "blockers": [],
                "risk_flags": ["requires_corroboration"],
                "author_allowed": False,
                "publication_approved": False,
                "advisory_only": True,
                "input_hash": "ihash",
                "output_hash": "ohash",
            },
            {
                "filing_evaluation_id": "filing_eval_skip",
                "run_id": "run10-fixture",
                "packet_item_id": "packet_skip",
                "source_id": "src_skip",
                "source_card_id": "card_skip",
                "semantic_object_id": "obj_skip",
                "quality_review_id": "review_skip",
                "semantic_object_type": "example_candidate",
                "semantic_object_text": "Already reviewed item.",
                "candidate_chapter_targets": [],
                "filing_decision": "new_example_candidate",
                "novelty_decision": "partially_novel",
                "next_stage_recommendation": "eligible_for_filing_later",
                "corroboration_needed": False,
                "corroboration_questions": [],
                "blockers": [],
                "risk_flags": [],
                "author_allowed": False,
                "publication_approved": False,
                "advisory_only": True,
                "input_hash": "ihash2",
                "output_hash": "ohash2",
            },
        ],
    }
    path = tmp_path / "filing.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    return path


def write_packet_report(tmp_path):
    packet = {
        "run_id": "run10-fixture",
        "mode": "editor_review_packet",
        "author_allowed": False,
        "publication_approved": False,
        "advisory_only": True,
        "db_modified": False,
        "packet_items": [
            {
                "packet_item_id": "packet_good",
                "source_id": "src_good",
                "source_card_id": "card_good",
                "semantic_object_id": "obj_good",
                "quality_review_id": "review_good",
                "source_title": "Good source title",
                "source_type": "web",
                "publisher": "Example Publisher",
                "quality_score": "B",
                "privacy_publication_status": "publishable_metadata_only",
                "canonical_url_available": True,
                "source_card_summary": "Compact safe source card summary supporting a caveat.",
                "semantic_object_type": "claim_candidate",
                "semantic_object_text": "Agent workflow caveats need source support before filing.",
                "quality_decision": "pass",
                "downstream_eligible": True,
                "risk_flags": [],
                "required_fixes": [],
                "source_text_hash": "shash",
                "source_card_hash": "chash",
                "semantic_object_hash": "ohash",
                "quality_review_hash": "rhash",
                "author_allowed": False,
                "publication_approved": False,
                "advisory_only": True,
            }
        ],
    }
    path = tmp_path / "packet.json"
    path.write_text(json.dumps(packet), encoding="utf-8")
    return path


def test_no_llm_source_review_writes_reports_without_side_effects(tmp_path):
    filing = write_filing_report(tmp_path)
    packet = write_packet_report(tmp_path)
    before_counts = db_counts()
    before_docs = docs_book_snapshot()
    before_status = status_snapshots()
    result = run_review(
        "--run-id", "run10-fixture",
        "--output-dir", str(tmp_path),
        "--filing-novelty-report", str(filing),
        "--editor-packet-report", str(packet),
        "--only-needs-source-review",
        "--no-llm",
        "--report-suffix", "run10",
    )
    assert result.returncode == 0, result.stderr + result.stdout
    js = tmp_path / "run10-fixture-source-support-review-run10.json"
    md = tmp_path / "run10-fixture-source-support-review-run10.md"
    assert js.exists()
    assert md.exists()
    payload = json.loads(js.read_text())
    assert payload["mode"] == "source_support_review"
    assert payload["llm_used"] is False
    assert payload["reasoning_status"] == "no_llm_structural_only"
    assert payload["filing_evaluations_available"] == 2
    assert payload["items_reviewed"] == 1
    item = payload["source_reviews"][0]
    for key in ["filing_evaluation_id", "packet_item_id", "source_id", "source_card_id", "semantic_object_id", "quality_review_id"]:
        assert item[key]
    assert item["author_allowed"] is False
    assert item["publication_approved"] is False
    assert item["advisory_only"] is True
    assert payload["claims_inserted"] == 0
    assert payload["editorial_reviews_inserted"] == 0
    assert payload["db_modified"] is False
    assert db_counts() == before_counts
    assert docs_book_snapshot() == before_docs
    assert status_snapshots() == before_status


def test_mocked_high_reasoning_path_sets_metadata_and_keeps_no_write(tmp_path):
    filing = write_filing_report(tmp_path)
    packet = write_packet_report(tmp_path)
    mock = tmp_path / "mock_bridge.py"
    mock.write_text(
        "#!/usr/bin/env python3\n"
        "import json,sys\n"
        "json.load(sys.stdin)\n"
        "print(json.dumps({'source_reviews':[{'filing_evaluation_id':'filing_eval_good','source_support_decision':'partially_supported','corroboration_decision':'corroboration_required','evidence_use_decision':'needs_corroboration_before_filing','next_stage_recommendation':'run_corroboration_research','support_rationale':'Fixture support is partial.','corroboration_rationale':'Needs independent corroboration.','corroboration_questions':['Find source.'],'suggested_corroboration_sources':['official docs'],'blockers':[],'risk_flags':['overclaiming_risk'],'required_editor_decisions':['Confirm support.'],'confidence':'medium'}]}))\n",
        encoding="utf-8",
    )
    mock.chmod(0o755)
    result = run_review(
        "--run-id", "run10-fixture",
        "--output-dir", str(tmp_path),
        "--filing-novelty-report", str(filing),
        "--editor-packet-report", str(packet),
        "--only-needs-source-review",
        "--require-high-reasoning",
        "--report-suffix", "run10",
        env={"TEREFO_HIGH_REASONING_BRIDGE_COMMAND": str(mock)},
    )
    assert result.returncode == 0, result.stderr + result.stdout
    payload = json.loads((tmp_path / "run10-fixture-source-support-review-run10.json").read_text())
    assert payload["llm_used"] is True
    assert payload["provider"] == "copilot"
    assert payload["model"] == "gpt-5.5"
    assert payload["bridge"] == "hermes_cli"
    assert payload["reasoning_status"] == "high_reasoning_used"
    assert payload["eligible_for_filing_persistence_count"] == 0
    assert payload["db_modified"] is False
    assert payload["source_reviews"][0]["evidence_use_decision"] == "needs_corroboration_before_filing"
    assert payload["source_reviews"][0]["publication_approved"] is False


def test_invalid_json_and_weak_provider_fail_closed(tmp_path):
    filing = write_filing_report(tmp_path)
    packet = write_packet_report(tmp_path)
    bad = tmp_path / "bad_bridge.py"
    bad.write_text("#!/usr/bin/env python3\nprint('not json')\n", encoding="utf-8")
    bad.chmod(0o755)
    invalid = run_review(
        "--run-id", "run10-fixture",
        "--output-dir", str(tmp_path),
        "--filing-novelty-report", str(filing),
        "--editor-packet-report", str(packet),
        "--only-needs-source-review",
        "--require-high-reasoning",
        "--report-suffix", "run10",
        env={"TEREFO_HIGH_REASONING_BRIDGE_COMMAND": str(bad)},
    )
    assert invalid.returncode != 0
    assert "json" in (invalid.stderr + invalid.stdout).lower() or "high-reasoning" in (invalid.stderr + invalid.stdout).lower()

    weak = run_review(
        "--run-id", "run10-fixture",
        "--output-dir", str(tmp_path),
        "--filing-novelty-report", str(filing),
        "--editor-packet-report", str(packet),
        "--only-needs-source-review",
        "--require-high-reasoning",
        "--provider", "local",
        "--report-suffix", "run10",
    )
    assert weak.returncode != 0
    assert "provider" in (weak.stderr + weak.stdout).lower() or "fallback" in (weak.stderr + weak.stdout).lower()
