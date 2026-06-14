import hashlib
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "llm_source_support_rereview.py"


def run_rereview(*args, env=None):
    full_env = os.environ.copy()
    if env:
        full_env.update(env)
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        env=full_env,
    )


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def db_counts_and_status_hashes():
    con = sqlite3.connect(f"file:{(ROOT/'.var/book.sqlite').resolve()}?mode=ro", uri=True)
    try:
        counts = {
            "claims": con.execute("SELECT COUNT(*) FROM claims").fetchone()[0],
            "editorial_reviews": con.execute("SELECT COUNT(*) FROM editorial_reviews").fetchone()[0],
            "source_notes": con.execute("SELECT COUNT(*) FROM source_notes").fetchone()[0],
        }
        status = {}
        for name, query in {
            "sources": "SELECT id, quality_score, privacy_publication_status, duplicate_status FROM sources ORDER BY id",
            "claims": "SELECT id, status, publication_decision, contradiction_status FROM claims ORDER BY id",
            "editorial_reviews": "SELECT id, run_id, review_type, status, summary, report_path, created_at FROM editorial_reviews ORDER BY id",
        }.items():
            rows = con.execute(query).fetchall()
            status[name] = hashlib.sha256(json.dumps(rows, sort_keys=True, default=str).encode()).hexdigest()
        return counts, status
    finally:
        con.close()


def tree_snapshot(path: Path):
    return {str(p.relative_to(ROOT)): sha(p) for p in sorted(path.rglob("*")) if p.is_file()}


def write_reports(tmp_path: Path):
    source_review_selected = "source_review_selected"
    source_review_selected_2 = "source_review_selected_2"
    import_report = {
        "run_id": "fixture-run15",
        "mode": "corroboration_source_import",
        "report_only": True,
        "candidate_sources_accepted_count": 3,
        "candidate_sources_rejected_count": 2,
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
        "selected_items": [
            {"source_review_id": source_review_selected, "item_id": "item_selected", "source_id": "src_original", "recommended_next_stage": "run_additional_source_collection"},
            {"source_review_id": source_review_selected_2, "item_id": "item_selected_2", "source_id": "src_original", "recommended_next_stage": "run_additional_source_collection"},
        ],
        "skipped_items": [
            {"source_review_id": "source_review_editor", "item_id": "item_editor", "source_id": "src_editor", "recommended_next_stage": "needs_editor_review", "skip_reason": "needs_editor_review_not_source_collection"},
            {"source_review_id": "source_review_persisted", "item_id": "item_persisted", "source_id": "src_persisted", "recommended_next_stage": "eligible_for_review_note_persistence", "skip_reason": "already_persisted_run11_caveat_only"},
        ],
        "collection_results": [
            {
                "source_review_id": source_review_selected,
                "item_id": "item_selected",
                "source_id": "src_original",
                "original_statement": "The project metadata suggests a web or phone interface for using Hermes Agent.",
                "accepted_candidate_source_count": 2,
                "candidate_source_count": 2,
                "recommended_next_stage": "run_source_support_re_review",
                "preliminary_collection_assessment": "enough_candidates_for_re_review",
                "what_needs_corroboration": "Whether public documentation supports web or phone access.",
                "candidate_sources": [],
            },
            {
                "source_review_id": source_review_selected_2,
                "item_id": "item_selected_2",
                "source_id": "src_original",
                "original_statement": "OpenClaw names Hermes as an adjacent environment.",
                "accepted_candidate_source_count": 1,
                "candidate_source_count": 1,
                "recommended_next_stage": "run_source_support_re_review",
                "preliminary_collection_assessment": "enough_candidates_for_re_review",
                "what_needs_corroboration": "Whether official docs explicitly name Hermes.",
                "candidate_sources": [],
            },
            {
                "source_review_id": "source_review_no_candidates",
                "item_id": "item_no_candidates",
                "source_id": "src_original",
                "original_statement": "No candidate item.",
                "accepted_candidate_source_count": 0,
                "candidate_source_count": 0,
                "recommended_next_stage": "run_source_support_re_review",
                "preliminary_collection_assessment": "enough_candidates_for_re_review",
                "what_needs_corroboration": "Should not call GPT.",
                "candidate_sources": [],
            },
            {
                "source_review_id": "unknown_source_review",
                "item_id": "item_unknown",
                "source_id": "src_original",
                "original_statement": "Unknown ID should be skipped/fail closed.",
                "accepted_candidate_source_count": 1,
                "candidate_source_count": 1,
                "recommended_next_stage": "run_source_support_re_review",
                "preliminary_collection_assessment": "enough_candidates_for_re_review",
                "what_needs_corroboration": "Unknown source review id.",
                "candidate_sources": [],
            },
        ],
        "candidate_sources_by_item": {
            "item_selected": [],
            "item_selected_2": [],
        },
        "rejected_candidate_sources": [{"source_review_id": source_review_selected, "url": "https://rejected.invalid", "reason": "duplicate_url"}],
    }
    curated = {
        "run_id": "fixture-run15",
        "ready_for_import": True,
        "template_only": False,
        "items": [
            {"source_review_id": source_review_selected, "item_id": "item_selected", "original_source_id": "src_original", "original_statement": "The project metadata suggests a web or phone interface for using Hermes Agent.", "what_needs_corroboration": "Whether public documentation supports web or phone access.", "why_current_evidence_is_insufficient": "Original source was metadata-only."},
            {"source_review_id": source_review_selected_2, "item_id": "item_selected_2", "original_source_id": "src_original", "original_statement": "OpenClaw names Hermes as an adjacent environment.", "what_needs_corroboration": "Whether official docs explicitly name Hermes.", "why_current_evidence_is_insufficient": "Original source was weak."},
            {"source_review_id": "source_review_editor", "item_id": "item_editor", "original_source_id": "src_editor", "original_statement": "Editor review only.", "what_needs_corroboration": "Should be skipped."},
        ],
        "candidate_sources": [
            {"candidate_source_id": "cand_keep_1", "source_review_id": source_review_selected, "item_id": "item_selected", "title": "Control UI", "url": "https://docs.example/control-ui", "publisher": "Docs", "source_type": "public_documentation", "access_type": "public", "raw_content_stored": False, "support_direction": "supports", "evidence_strength": "strong", "safe_summary": "Documents browser control UI.", "limitations": "Does not prove phone access."},
            {"candidate_source_id": "cand_keep_2", "source_review_id": source_review_selected, "item_id": "item_selected", "title": "WebChat", "url": "https://docs.example/webchat", "publisher": "Docs", "source_type": "public_documentation", "access_type": "public", "raw_content_stored": False, "support_direction": "partially_supports", "evidence_strength": "moderate", "safe_summary": "Documents web chat.", "limitations": "Not Hermes-specific."},
            {"candidate_source_id": "cand_keep_3", "source_review_id": source_review_selected_2, "item_id": "item_selected_2", "title": "Hermes migrate", "url": "https://docs.example/migrate", "publisher": "Docs", "source_type": "public_documentation", "access_type": "public", "raw_content_stored": False, "support_direction": "partially_supports", "evidence_strength": "moderate", "safe_summary": "Names Hermes migration.", "limitations": "Migration only."},
            {"candidate_source_id": "cand_reject_raw", "source_review_id": source_review_selected, "item_id": "item_selected", "title": "Raw", "url": "https://docs.example/raw", "publisher": "Docs", "source_type": "public_documentation", "access_type": "public", "raw_content_stored": True, "support_direction": "supports", "evidence_strength": "strong", "safe_summary": "Should be rejected.", "limitations": "Raw content stored."},
            {"candidate_source_id": "cand_reject_private", "source_review_id": source_review_selected_2, "item_id": "item_selected_2", "title": "Private", "url": "https://private.invalid", "publisher": "Private", "source_type": "public_documentation", "access_type": "private", "raw_content_stored": False, "support_direction": "supports", "evidence_strength": "strong", "safe_summary": "Should be rejected.", "limitations": "Not public."},
        ],
        "skipped_items": [{"source_review_id": "source_review_editor", "item_id": "item_editor", "skip_reason": "needs_editor_review"}],
        "safety_flags": {"advisory_only": True, "author_allowed": False, "publication_approved": False, "raw_content_stored": False},
    }
    run10 = {
        "mode": "source_support_review",
        "source_reviews": [
            {"source_review_id": source_review_selected, "source_support_decision": "unsupported", "corroboration_decision": "corroboration_required", "evidence_use_decision": "needs_corroboration_before_filing", "next_stage_recommendation": "run_corroboration_research"},
            {"source_review_id": source_review_selected_2, "source_support_decision": "partially_supported", "corroboration_decision": "corroboration_required", "evidence_use_decision": "needs_corroboration_before_filing", "next_stage_recommendation": "run_corroboration_research"},
            {"source_review_id": "source_review_persisted", "source_support_decision": "supported", "corroboration_decision": "corroboration_not_required", "evidence_use_decision": "eligible_as_caveat_only", "next_stage_recommendation": "eligible_for_filing_persistence"},
        ],
    }
    run12 = {"mode": "corroboration_research", "corroboration_reviews": [], "skipped_items": [{"source_review_id": "source_review_editor", "skip_reason": "needs_editor_review"}]}
    run13 = {"mode": "corroboration_source_collection", "collection_results": import_report["collection_results"], "skipped_items": import_report["skipped_items"]}
    paths = {}
    for name, obj in {"import": import_report, "curated": curated, "run10": run10, "run12": run12, "run13": run13}.items():
        p = tmp_path / f"{name}.json"
        p.write_text(json.dumps(obj), encoding="utf-8")
        paths[name] = p
    return paths


def write_mock_bridge(tmp_path: Path, *, invalid_json=False, invalid_enum=False, missing_flags=False):
    mock = tmp_path / "mock_bridge.py"
    if invalid_json:
        mock.write_text("#!/usr/bin/env python3\nprint('not json')\n", encoding="utf-8")
    else:
        support = "bad_enum" if invalid_enum else "partially_supported"
        item_flags = "" if missing_flags else ", 'advisory_only': True, 'author_allowed': False, 'publication_approved': False"
        mock.write_text(
            "#!/usr/bin/env python3\n"
            "import json,sys\n"
            "payload=json.load(sys.stdin); prompt=payload['prompt']\n"
            "ids=[]\n"
            "for wanted in ['source_review_selected','source_review_selected_2']:\n"
            "    if wanted in prompt: ids.append(wanted)\n"
            "reviews=[]\n"
            "for rid in ids:\n"
            f"    reviews.append({{'source_review_id': rid, 'item_id': 'item_selected' if rid.endswith('selected') else 'item_selected_2', 'original_statement': 'fixture statement', 'accepted_candidate_source_ids': ['cand_keep_1'] if rid.endswith('selected') else ['cand_keep_3'], 'candidate_source_assessment': 'candidate docs give partial support', 'original_source_assessment': 'original was weak', 'combined_evidence_assessment': 'combined support remains narrow', 'support_decision': '{support}', 'corroboration_decision': 'partially_corroborated', 'evidence_use_decision': 'eligible_as_caveat_only_after_corroboration', 'recommended_next_stage': 'eligible_for_review_note_persistence', 'caveat_required': True, 'caveat_text': 'Use narrowly with caveat.', 'contradiction_notes': '', 'limitations': ['narrow support'], 'residual_risk': 'medium', 'why_not_author_approved': 'advisory only review, not editor approval'{item_flags}}})\n"
            "print(json.dumps({'rereviews': reviews}))\n",
            encoding="utf-8",
        )
    mock.chmod(0o755)
    return mock


def test_selects_only_accepted_candidates_and_writes_report_only_outputs(tmp_path):
    paths = write_reports(tmp_path)
    mock = write_mock_bridge(tmp_path)
    before_counts, before_status = db_counts_and_status_hashes()
    before_registry = sha(ROOT / "data" / "source_registry.json")
    before_raw = tree_snapshot(ROOT / "raw")
    before_book = tree_snapshot(ROOT / "docs" / "book")
    before_schema = sha(ROOT / "data" / "schema.sql")
    before_worker = sha(ROOT / "scripts" / "daily_book_worker.py")

    result = run_rereview(
        "--run-id", "fixture-run15",
        "--output-dir", str(tmp_path),
        "--source-import-report", str(paths["import"]),
        "--candidate-sources-report", str(paths["curated"]),
        "--source-support-review-report", str(paths["run10"]),
        "--corroboration-research-report", str(paths["run12"]),
        "--source-collection-report", str(paths["run13"]),
        "--require-high-reasoning",
        "--report-suffix", "run15",
        env={"TEREFO_HIGH_REASONING_BRIDGE_COMMAND": str(mock)},
    )
    assert result.returncode == 0, result.stderr + result.stdout
    payload = json.loads((tmp_path / "fixture-run15-source-support-rereview-run15.json").read_text())
    assert payload["mode"] == "source_support_rereview"
    assert payload["selected_items_count"] == 2
    assert payload["reviewed_items_count"] == 2
    assert payload["skipped_items_count"] >= 3
    assert payload["accepted_candidate_sources_count"] == 3
    assert payload["rejected_candidate_sources_ignored_count"] >= 2
    assert payload["llm_used"] is True
    assert payload["provider"] == "copilot"
    assert payload["model"] == "gpt-5.5"
    assert payload["bridge"] == "hermes_cli"
    assert {r["source_review_id"] for r in payload["rereviews"]} == {"source_review_selected", "source_review_selected_2"}
    for review in payload["rereviews"]:
        assert review["advisory_only"] is True
        assert review["author_allowed"] is False
        assert review["publication_approved"] is False
        assert "cand_reject" not in json.dumps(review)
    skipped_reasons = {s["skip_reason"] for s in payload["skipped_items"]}
    assert "no_accepted_candidate_sources" in skipped_reasons
    assert "needs_editor_review_not_source_support_rereview" in skipped_reasons
    assert "already_persisted_run11_or_already_eligible" in skipped_reasons
    assert any("unknown_source_review_id" in r for r in skipped_reasons)
    assert payload["changed_db"] is False
    assert payload["changed_source_registry"] is False
    assert payload["changed_raw_captures"] is False
    assert payload["changed_docs_book"] is False
    assert payload["changed_schema"] is False
    assert payload["changed_daily_worker"] is False
    assert payload["claims_inserted"] == 0
    assert payload["editorial_reviews_inserted"] == 0
    assert db_counts_and_status_hashes() == (before_counts, before_status)
    assert sha(ROOT / "data" / "source_registry.json") == before_registry
    assert tree_snapshot(ROOT / "raw") == before_raw
    assert tree_snapshot(ROOT / "docs" / "book") == before_book
    assert sha(ROOT / "data" / "schema.sql") == before_schema
    assert sha(ROOT / "scripts" / "daily_book_worker.py") == before_worker


def test_invalid_or_missing_import_report_fails_closed(tmp_path):
    missing = run_rereview("--source-import-report", str(tmp_path / "missing.json"), "--candidate-sources-report", str(tmp_path / "missing2.json"), "--output-dir", str(tmp_path))
    assert missing.returncode != 0
    bad_import = tmp_path / "bad.json"
    bad_import.write_text(json.dumps({"mode": "wrong"}), encoding="utf-8")
    paths = write_reports(tmp_path)
    result = run_rereview("--source-import-report", str(bad_import), "--candidate-sources-report", str(paths["curated"]), "--output-dir", str(tmp_path))
    assert result.returncode != 0


def test_invalid_llm_json_enum_and_missing_safety_flags_fail_closed(tmp_path):
    paths = write_reports(tmp_path)
    for kwargs in [{"invalid_json": True}, {"invalid_enum": True}, {"missing_flags": True}]:
        mock = write_mock_bridge(tmp_path, **kwargs)
        result = run_rereview(
            "--run-id", "fixture-run15",
            "--output-dir", str(tmp_path),
            "--source-import-report", str(paths["import"]),
            "--candidate-sources-report", str(paths["curated"]),
            "--source-support-review-report", str(paths["run10"]),
            "--require-high-reasoning",
            env={"TEREFO_HIGH_REASONING_BRIDGE_COMMAND": str(mock)},
        )
        assert result.returncode != 0, kwargs


def test_no_weak_local_fallback_when_high_reasoning_required(tmp_path):
    paths = write_reports(tmp_path)
    mock = write_mock_bridge(tmp_path)
    result = run_rereview(
        "--run-id", "fixture-run15",
        "--output-dir", str(tmp_path),
        "--source-import-report", str(paths["import"]),
        "--candidate-sources-report", str(paths["curated"]),
        "--source-support-review-report", str(paths["run10"]),
        "--require-high-reasoning",
        env={"TEREFO_HIGH_REASONING_BRIDGE_COMMAND": str(mock), "TEREFO_LLM_PROVIDER": "local"},
    )
    assert result.returncode != 0
    assert "weak_or_unapproved_provider_refused" in result.stderr or "weak_or_unapproved_provider_refused" in result.stdout
