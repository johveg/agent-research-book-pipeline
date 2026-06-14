import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_eval(*args, env=None):
    full_env = os.environ.copy()
    if env:
        full_env.update(env)
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "llm_evaluate_filing_novelty.py"), *args],
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


def write_packet(tmp_path):
    packet = {
        "run_id": "run9-fixture",
        "mode": "editor_review_packet",
        "packet_items_total": 2,
        "downstream_eligible_count": 1,
        "author_allowed": False,
        "publication_approved": False,
        "advisory_only": True,
        "db_modified": False,
        "packet_items": [
            {
                "packet_item_id": "packet_pass",
                "run_id": "run9-fixture",
                "source_id": "src_good",
                "source_card_id": "card_good",
                "semantic_object_id": "obj_good",
                "quality_review_id": "review_good",
                "semantic_object_type": "claim_candidate",
                "semantic_object_text": "Agent memory architecture can improve reliable operator workflows.",
                "candidate_chapter_targets": ["05-context-memory-architecture"],
                "quality_decision": "pass",
                "downstream_eligible": True,
                "source_text_hash": "sourcehash",
                "source_card_hash": "cardhash",
                "semantic_object_hash": "objecthash",
                "quality_review_hash": "reviewhash",
                "risk_flags": [],
                "required_fixes": [],
                "author_allowed": False,
                "publication_approved": False,
                "advisory_only": True,
            },
            {
                "packet_item_id": "packet_warn",
                "run_id": "run9-fixture",
                "source_id": "src_warn",
                "source_card_id": "card_warn",
                "semantic_object_id": "obj_warn",
                "quality_review_id": "review_warn",
                "semantic_object_type": "example_candidate",
                "semantic_object_text": "A weak workflow example needs review.",
                "candidate_chapter_targets": ["01-the-agent-loop"],
                "quality_decision": "warn",
                "downstream_eligible": False,
                "source_text_hash": "sourcehash2",
                "source_card_hash": "cardhash2",
                "semantic_object_hash": "objecthash2",
                "quality_review_hash": "reviewhash2",
                "risk_flags": ["needs_corroboration"],
                "required_fixes": ["corroborate"],
                "author_allowed": False,
                "publication_approved": False,
                "advisory_only": True,
            },
        ],
    }
    path = tmp_path / "packet.json"
    path.write_text(json.dumps(packet), encoding="utf-8")
    return path


def test_no_llm_run_writes_reports_only_for_downstream_eligible_items(tmp_path):
    packet = write_packet(tmp_path)
    before_counts = db_counts()
    before_docs = docs_book_snapshot()
    before_status = status_snapshots()
    result = run_eval(
        "--run-id", "run9-fixture",
        "--output-dir", str(tmp_path),
        "--editor-packet-report", str(packet),
        "--only-downstream-eligible",
        "--no-llm",
        "--report-suffix", "run9",
    )
    assert result.returncode == 0, result.stderr + result.stdout
    js = tmp_path / "run9-fixture-filing-novelty-evaluation-run9.json"
    md = tmp_path / "run9-fixture-filing-novelty-evaluation-run9.md"
    assert js.exists()
    assert md.exists()
    payload = json.loads(js.read_text())
    assert payload["mode"] == "filing_novelty_evaluation"
    assert payload["llm_used"] is False
    assert payload["reasoning_status"] == "no_llm_structural_only"
    assert payload["editor_packet_items_available"] == 2
    assert payload["downstream_eligible_items_available"] == 1
    assert payload["items_evaluated"] == 1
    item = payload["filing_evaluations"][0]
    for key in ["source_id", "source_card_id", "semantic_object_id", "quality_review_id", "packet_item_id"]:
        assert item[key]
    assert item["author_allowed"] is False
    assert item["publication_approved"] is False
    assert item["advisory_only"] is True
    assert payload["claims_inserted"] == 0
    assert payload["db_modified"] is False
    assert db_counts() == before_counts
    assert docs_book_snapshot() == before_docs
    assert status_snapshots() == before_status


def test_include_warn_evaluates_warn_items(tmp_path):
    packet = write_packet(tmp_path)
    result = run_eval(
        "--run-id", "run9-fixture",
        "--output-dir", str(tmp_path),
        "--editor-packet-report", str(packet),
        "--include-warn",
        "--no-llm",
        "--report-suffix", "run9",
    )
    assert result.returncode == 0, result.stderr + result.stdout
    payload = json.loads((tmp_path / "run9-fixture-filing-novelty-evaluation-run9.json").read_text())
    assert payload["items_evaluated"] == 2
    assert {i["packet_item_id"] for i in payload["filing_evaluations"]} == {"packet_pass", "packet_warn"}


def test_mocked_high_reasoning_path_sets_metadata(tmp_path):
    packet = write_packet(tmp_path)
    mock = tmp_path / "mock_bridge.py"
    mock.write_text(
        "#!/usr/bin/env python3\n"
        "import json,sys\n"
        "json.load(sys.stdin)\n"
        "print(json.dumps({'filing_evaluations':[{'packet_item_id':'packet_pass','filing_decision':'new_claim_candidate','novelty_decision':'partially_novel','next_stage_recommendation':'needs_corroboration','matched_existing_claim_ids':[],'matched_existing_source_ids':[],'similarity_rationale':'No close fixture match.','filing_summary':'Candidate filing item.','why_it_matters':'Useful for operator workflow theme.','corroboration_needed':True,'corroboration_questions':['Find independent source.'],'blockers':[],'risk_flags':[],'required_editor_decisions':['Confirm filing category.'],'confidence':'medium'}]}))\n",
        encoding="utf-8",
    )
    mock.chmod(0o755)
    result = run_eval(
        "--run-id", "run9-fixture",
        "--output-dir", str(tmp_path),
        "--editor-packet-report", str(packet),
        "--only-downstream-eligible",
        "--require-high-reasoning",
        "--report-suffix", "run9",
        env={"TEREFO_HIGH_REASONING_BRIDGE_COMMAND": str(mock)},
    )
    assert result.returncode == 0, result.stderr + result.stdout
    payload = json.loads((tmp_path / "run9-fixture-filing-novelty-evaluation-run9.json").read_text())
    assert payload["llm_used"] is True
    assert payload["provider"] == "copilot"
    assert payload["model"] == "gpt-5.5"
    assert payload["bridge"] == "hermes_cli"
    assert payload["reasoning_status"] == "high_reasoning_used"
    assert payload["filing_evaluations"][0]["filing_decision"] == "new_claim_candidate"
    assert payload["filing_evaluations"][0]["publication_approved"] is False


def test_invalid_high_reasoning_json_and_weak_provider_fail_closed(tmp_path):
    packet = write_packet(tmp_path)
    bad = tmp_path / "bad_bridge.py"
    bad.write_text("print('not json')\n", encoding="utf-8")
    invalid = run_eval(
        "--run-id", "run9-fixture",
        "--output-dir", str(tmp_path),
        "--editor-packet-report", str(packet),
        "--only-downstream-eligible",
        "--require-high-reasoning",
        "--report-suffix", "run9",
        env={"TEREFO_HIGH_REASONING_BRIDGE_COMMAND": str(bad)},
    )
    assert invalid.returncode != 0
    assert "high-reasoning" in (invalid.stderr + invalid.stdout).lower() or "json" in (invalid.stderr + invalid.stdout).lower()

    weak = run_eval(
        "--run-id", "run9-fixture",
        "--output-dir", str(tmp_path),
        "--editor-packet-report", str(packet),
        "--only-downstream-eligible",
        "--require-high-reasoning",
        "--provider", "local",
        "--report-suffix", "run9",
    )
    assert weak.returncode != 0
    assert "fallback" in (weak.stderr + weak.stdout).lower() or "provider" in (weak.stderr + weak.stdout).lower()
