import json
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_packet(*args):
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "llm_build_editor_review_packet.py"), *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )


def db_bytes():
    p = ROOT / ".var" / "book.sqlite"
    return p.read_bytes() if p.exists() else None


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


def write_fixture_reports(tmp_path):
    candidate = {
        "run_id": "run8-fixture",
        "selected_count": 1,
        "selected_sources": [{"source_id": "src_good", "selection_score": 90, "selection_decision": "selected"}],
        "db_modified": False,
    }
    source_cards = {
        "run_id": "run8-fixture",
        "llm_used": True,
        "reasoning_status": "high_reasoning_used",
        "provider": "copilot",
        "model": "gpt-5.5",
        "bridge": "hermes_cli",
        "db_modified": False,
        "source_cards": [
            {
                "card_id": "card_good",
                "source_id": "src_good",
                "title": "Hermes public source",
                "source_type": "web",
                "publisher": "Example Publisher",
                "canonical_url_available": True,
                "quality_score": "B",
                "privacy_publication_status": "publishable_metadata_only",
                "likely_chapter_targets": ["05-context-memory-architecture"],
                "safe_summary": "Public metadata source about agent memory and workflows.",
                "evidence_strength": "moderate",
                "recommended_use": "semantic_extraction_candidate",
                "risk_flags": [],
                "source_text_hash": "sourcehash-good",
                "card_output_hash": "cardhash-good",
                "author_allowed": False,
                "publication_approved": False,
                "advisory_only": True,
            },
            {
                "card_id": "card_orphan",
                "source_id": "src_orphan",
                "title": "Orphan source",
                "source_type": "web",
                "publisher": "Example Publisher",
                "canonical_url_available": True,
                "quality_score": "C",
                "privacy_publication_status": "publishable_metadata_only",
                "likely_chapter_targets": ["01-the-agent-loop"],
                "safe_summary": "A card without a semantic object review.",
                "source_text_hash": "sourcehash-orphan",
                "card_output_hash": "cardhash-orphan",
                "author_allowed": False,
                "publication_approved": False,
                "advisory_only": True,
            },
        ],
    }
    semantic = {
        "run_id": "run8-fixture",
        "llm_used": True,
        "reasoning_status": "high_reasoning_used",
        "provider": "copilot",
        "model": "gpt-5.5",
        "bridge": "hermes_cli",
        "db_modified": False,
        "semantic_objects": [
            {
                "semantic_object_id": "obj_good",
                "object_type": "claim_candidate",
                "source_id": "src_good",
                "source_card_id": "card_good",
                "text": "Agent memory can support reliable operator workflows.",
                "candidate_chapter_targets": ["05-context-memory-architecture"],
                "risk_flags": [],
                "source_text_hash": "sourcehash-good",
                "source_card_hash": "cardhash-good",
                "object_output_hash": "objecthash-good",
                "author_allowed": False,
                "publication_approved": False,
                "advisory_only": True,
                "paraphrase_only": True,
            },
            {
                "semantic_object_id": "obj_blocked",
                "object_type": "claim_candidate",
                "source_id": "src_good",
                "source_card_id": "card_good",
                "text": "Blocked object.",
                "candidate_chapter_targets": ["05-context-memory-architecture"],
                "risk_flags": ["blocked"],
                "source_text_hash": "sourcehash-good",
                "source_card_hash": "cardhash-good",
                "object_output_hash": "objecthash-blocked",
                "author_allowed": False,
                "publication_approved": False,
                "advisory_only": True,
                "paraphrase_only": True,
            },
        ],
    }
    quality = {
        "run_id": "run8-fixture",
        "llm_used": True,
        "reasoning_status": "high_reasoning_used",
        "provider": "copilot",
        "model": "gpt-5.5",
        "bridge": "hermes_cli",
        "db_modified": False,
        "source_cards_reviewed": 2,
        "semantic_objects_reviewed": 2,
        "decision_counts": {"pass": 1, "warn": 0, "fail": 1},
        "source_card_reviews": [
            {"review_id": "review_card_good", "target_type": "source_card", "target_id": "card_good", "source_card_id": "card_good", "source_id": "src_good", "decision": "pass", "downstream_eligible": True, "downstream_eligibility": "ready_for_editor_review", "recommended_next_stage": "editor_review_packet", "strengths": ["clear public metadata"], "weaknesses": [], "required_fixes": [], "risk_flags": [], "review_summary": "Good enough for editor packet.", "review_output_hash": "reviewhash-card", "author_allowed": False, "publication_approved": False, "advisory_only": True}
        ],
        "semantic_object_reviews": [
            {"review_id": "review_obj_good", "target_type": "semantic_object", "target_id": "obj_good", "source_card_id": "card_good", "source_id": "src_good", "decision": "pass", "downstream_eligibility": "ready_for_editor_review", "recommended_next_stage": "filing_novelty_evaluation_candidate", "strengths": ["good linkage"], "weaknesses": [], "required_fixes": [], "risk_flags": [], "review_summary": "Ready for editor packet only.", "review_output_hash": "reviewhash-good", "author_allowed": False, "publication_approved": False, "advisory_only": True},
            {"review_id": "review_obj_blocked", "target_type": "semantic_object", "target_id": "obj_blocked", "source_card_id": "card_good", "source_id": "src_good", "decision": "fail", "downstream_eligible": False, "downstream_eligibility": "blocked", "recommended_next_stage": "do_not_advance", "strengths": [], "weaknesses": ["blocked"], "required_fixes": ["remove blocker"], "risk_flags": ["blocked"], "review_summary": "Blocked.", "review_output_hash": "reviewhash-blocked", "author_allowed": False, "publication_approved": False, "advisory_only": True},
        ],
    }
    paths = {}
    for name, data in [("candidate", candidate), ("source", source_cards), ("semantic", semantic), ("quality", quality)]:
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        paths[name] = path
    return paths


def test_editor_review_packet_builds_linked_advisory_reports_without_side_effects(tmp_path):
    before_db = db_bytes()
    before_docs = docs_book_snapshot()
    before_statuses = status_snapshots()
    paths = write_fixture_reports(tmp_path)

    result = run_packet(
        "--run-id", "run8-fixture",
        "--output-dir", str(tmp_path),
        "--candidate-selection-report", str(paths["candidate"]),
        "--source-card-report", str(paths["source"]),
        "--semantic-object-report", str(paths["semantic"]),
        "--quality-gate-report", str(paths["quality"]),
        "--report-suffix", "run8",
    )

    assert result.returncode == 0, result.stderr + result.stdout
    json_path = tmp_path / "run8-fixture-editor-review-packet-run8.json"
    md_path = tmp_path / "run8-fixture-editor-review-packet-run8.md"
    assert json_path.exists()
    assert md_path.exists()

    payload = json.loads(json_path.read_text())
    assert payload["mode"] == "editor_review_packet"
    assert payload["packet_items_total"] == 1
    assert payload["packet_items_pass"] == 1
    assert payload["packet_items_fail"] == 0
    assert payload["complete_chains_total"] == 1
    assert payload["downstream_eligible_count"] == 1
    assert payload["author_allowed"] is False
    assert payload["publication_approved"] is False
    assert payload["advisory_only"] is True
    assert payload["db_modified"] is False
    assert payload["chapters_modified"] is False
    assert payload["statuses_modified"] is False

    item = payload["packet_items"][0]
    assert item["source_id"] == "src_good"
    assert item["source_card_id"] == "card_good"
    assert item["semantic_object_id"] == "obj_good"
    assert item["quality_review_id"] == "review_obj_good"
    assert item["quality_decision"] == "pass"
    assert item["downstream_eligible"] is True
    assert item["author_allowed"] is False
    assert item["publication_approved"] is False
    assert item["advisory_only"] is True
    assert item["source_text_hash"] == "sourcehash-good"
    assert item["source_card_hash"] == "cardhash-good"
    assert item["semantic_object_hash"] == "objecthash-good"
    assert item["quality_review_hash"] == "reviewhash-good"
    assert "not author-approved" in md_path.read_text(encoding="utf-8")

    assert db_bytes() == before_db
    assert docs_book_snapshot() == before_docs
    assert status_snapshots() == before_statuses


def test_packet_rejects_approval_flags_and_never_marks_failed_items_eligible(tmp_path):
    paths = write_fixture_reports(tmp_path)
    semantic = json.loads(paths["semantic"].read_text())
    semantic["semantic_objects"][0]["publication_approved"] = True
    paths["semantic"].write_text(json.dumps(semantic), encoding="utf-8")

    result = run_packet(
        "--run-id", "run8-fixture",
        "--output-dir", str(tmp_path),
        "--candidate-selection-report", str(paths["candidate"]),
        "--source-card-report", str(paths["source"]),
        "--semantic-object-report", str(paths["semantic"]),
        "--quality-gate-report", str(paths["quality"]),
        "--report-suffix", "run8",
    )

    assert result.returncode != 0
    assert "approval" in (result.stderr + result.stdout).lower()
