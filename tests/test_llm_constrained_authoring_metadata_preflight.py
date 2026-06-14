import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "llm_constrained_authoring_metadata_preflight.py"
RUN30 = ROOT / "reports" / "editorial" / "citation-pipeline-test-20260612-constrained-authoring-metadata-run30.json"
METADATA_ID = "metadata_run30_constrained_authoring_4e8554045cfaf827bc68bcc5"
DRAFT_CANARY_ID = "draft_canary_run28_caveat_only_v2_cluster_4e8554045cfaf827bc68bcc5"
REBUILT_INPUT_ID = "rebuilt_input_run26_enriched_caveat_only_cluster_4e8554045cfaf827bc68bcc5"
PRIOR_DRAFT_INPUT_ID = "draft_input_run22b_caveat_only_cluster_4e8554045cfaf827bc68bcc5"
REQUIRED_CAVEAT = "Frame narrowly: OpenClaw documentation names Hermes in migration/setup tooling contexts; do not state that Hermes is a runtime dependency or general operating environment without additional sources."


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


def run_script(*args, db_path: Path, output_dir: Path, env=None):
    full_env = os.environ.copy()
    full_env["TEREFO_BOOK_DB_PATH"] = str(db_path)
    if env:
        full_env.update(env)
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--output-dir", str(output_dir), *args],
        cwd=ROOT,
        env=full_env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=180,
    )


def read_report(output_dir: Path) -> dict:
    path = output_dir / "citation-pipeline-test-20260612-constrained-authoring-metadata-preflight-run31.json"
    assert path.exists(), f"missing report {path}"
    return json.loads(path.read_text())


def run30_copy(tmp_path: Path, mutator=None) -> Path:
    data = json.loads(RUN30.read_text())
    if mutator:
        mutator(data)
    path = tmp_path / "run30.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    return path


def candidate(data: dict) -> dict:
    return data["constrained_authoring_metadata_candidates"][0]


def write_mock_bridge(
    tmp_path: Path,
    *,
    invalid_json=False,
    invalid_enum=False,
    missing_flags=False,
    author_allowed=False,
    publication_approved=False,
    eligible_claim=False,
    eligible_authoring=False,
    eligible_publication=False,
    chapter_update=False,
    decision="metadata_preflight_passed",
    readiness="ready_for_promotion_contract_update",
    disposition="caveat_only",
    next_stage="update_closed_loop_promotion_contract_for_authoring_metadata",
    missing_field=None,
):
    tmp_path.mkdir(parents=True, exist_ok=True)
    mock = tmp_path / "mock_bridge.py"
    if invalid_json:
        mock.write_text("#!/usr/bin/env python3\nprint('not-json')\n", encoding="utf-8")
    else:
        preflight_decision = "bad_enum" if invalid_enum else decision
        safety = "" if missing_flags else (
            f", 'advisory_only': True, 'author_allowed': {author_allowed}, 'publication_approved': {publication_approved}, "
            f"'eligible_for_claim_insertion': {eligible_claim}, 'eligible_for_authoring': {eligible_authoring}, "
            f"'eligible_for_publication': {eligible_publication}, 'chapter_update_allowed': {chapter_update}"
        )
        delete_line = f"review.pop('{missing_field}', None)\n" if missing_field else ""
        mock.write_text(
            "#!/usr/bin/env python3\n"
            "import json,sys\n"
            "payload=json.load(sys.stdin)\n"
            f"review={{'metadata_id':'{METADATA_ID}','draft_canary_id':'{DRAFT_CANARY_ID}','rebuilt_input_id':'{REBUILT_INPUT_ID}','prior_draft_input_id':'{PRIOR_DRAFT_INPUT_ID}',"
            "'metadata_type':'constrained_authoring_metadata_candidate','metadata_use':'caveat_only',"
            f"'preflight_decision':'{preflight_decision}','metadata_readiness':'{readiness}','closed_loop_disposition':'{disposition}',"
            "'metadata_containment_assessment':'Strict metadata only; no new author prose, no chapter-ready wording, no claim insertion language, and all hard safety flags remain false.',"
            "'caveat_integrity_assessment':'The required caveat is preserved exactly and scope remains narrow.',"
            "'do_not_say_compliance_assessment':'It does not assert runtime dependency, general operating environment, web or phone access requirements, or broader scope.',"
            "'evidence_use_assessment':'It preserves bounded evidence atoms only and does not turn tooling adjacency into architectural dependency.',"
            "'provenance_assessment':'Source review, source note, packet, cluster, draft input, rebuilt input, canary, candidate source IDs, and report paths are present.',"
            "'usefulness_as_metadata_assessment':'Useful as an intermediate control metadata object while not approving authoring or publication; thinness remains explicit.',"
            "'residual_risk_assessment':'Main residual risk is downstream promotion from tooling adjacency into dependency language; singleton evidence remains narrow.',"
            f"'required_caveats':['{REQUIRED_CAVEAT}'],"
            "'do_not_say':['Do not say Hermes is a runtime dependency of OpenClaw.','Do not say Hermes is the general operating environment for OpenClaw.','Do not say OpenClaw requires Hermes for web or phone access.','Do not generalize beyond migration/setup/import tooling contexts unless additional sources support it.','Do not use this material as a factual claim without the caveat.','Do not use this material for chapter prose before later author/red-team gates pass.'],"
            "'unsupported_inferences':['Hermes is a runtime dependency of OpenClaw.','Hermes is the general operating environment for OpenClaw.'],"
            "'promotion_blockers':['No authoring approval has been granted.','No publication approval has been granted.','No chapter update is allowed.'],"
            "'limitations':['singleton narrow evidence','suggested-only target chapter','metadata only, not prose'],"
            "'residual_risk':'Low if kept metadata-only; higher if promoted to prose without later gates.',"
            f"'recommended_next_stage':'{next_stage}'{safety}}}\n"
            f"{delete_line}"
            "print(json.dumps({'constrained_authoring_metadata_preflight_reviews':[review]}))\n",
            encoding="utf-8",
        )
    mock.chmod(0o755)
    return mock


def test_selects_run30_metadata_and_writes_report_only_preflight(tmp_path):
    db = db_copy(tmp_path)
    mock = write_mock_bridge(tmp_path)
    before = counts(db)
    before_status = status_hashes(db)
    before_registry = sha(ROOT / "data" / "source_registry.json")
    before_raw = tree_snapshot(ROOT / "raw")
    before_book = tree_snapshot(ROOT / "docs" / "book")
    before_schema = sha(ROOT / "data" / "schema.sql")
    before_worker = sha(ROOT / "scripts" / "daily_book_worker.py")
    res = run_script("--run-id", "citation-pipeline-test-20260612", "--metadata-report", str(RUN30), "--report-suffix", "run31", db_path=db, output_dir=tmp_path, env={"TEREFO_HIGH_REASONING_BRIDGE_COMMAND": str(mock)})
    assert res.returncode == 0, res.stderr + res.stdout
    assert counts(db) == before
    assert status_hashes(db) == before_status
    assert sha(ROOT / "data" / "source_registry.json") == before_registry
    assert tree_snapshot(ROOT / "raw") == before_raw
    assert tree_snapshot(ROOT / "docs" / "book") == before_book
    assert sha(ROOT / "data" / "schema.sql") == before_schema
    assert sha(ROOT / "scripts" / "daily_book_worker.py") == before_worker
    report = read_report(tmp_path)
    assert report["llm_used"] is True
    assert report["provider"] == "copilot"
    assert report["model"] == "gpt-5.5"
    assert report["bridge"] == "hermes_cli"
    assert report["model_profile"] == "closed_loop_editorial"
    assert report["selected_metadata_count"] == 1
    assert report["reviewed_metadata_count"] == 1
    assert report["excluded_metadata_count"] == 0
    assert report["preflight_decision_counts"] == {"metadata_preflight_passed": 1}
    assert report["metadata_readiness_counts"] == {"ready_for_promotion_contract_update": 1}
    assert report["closed_loop_disposition_counts"] == {"caveat_only": 1}
    assert report["recommended_next_stage_counts"] == {"update_closed_loop_promotion_contract_for_authoring_metadata": 1}
    review = report["constrained_authoring_metadata_preflight_reviews"][0]
    assert review["metadata_id"] == METADATA_ID
    assert review["author_allowed"] is False
    assert review["publication_approved"] is False
    assert review["eligible_for_claim_insertion"] is False
    assert review["eligible_for_authoring"] is False
    assert review["eligible_for_publication"] is False
    assert review["chapter_update_allowed"] is False
    assert REQUIRED_CAVEAT in review["required_caveats"]


def test_unsafe_run30_metadata_input_fails_closed(tmp_path):
    cases = []
    for key in ["author_allowed", "publication_approved", "eligible_for_claim_insertion", "eligible_for_authoring", "eligible_for_publication", "chapter_update_allowed"]:
        cases.append((key, lambda d, key=key: candidate(d).__setitem__(key, True), "safety flag"))
    cases += [
        ("bad_decision", lambda d: candidate(d).__setitem__("metadata_decision", "safe_reports_only"), "no selected"),
        ("bad_use", lambda d: candidate(d).__setitem__("metadata_use", "safe_reports_only"), "no selected"),
        ("caveat", lambda d: candidate(d).__setitem__("required_caveats", []), "required caveat"),
        ("dns", lambda d: candidate(d).__setitem__("do_not_say", []), "do_not_say"),
        ("unsupported", lambda d: candidate(d).__setitem__("unsupported_inferences", []), "unsupported_inferences"),
        ("blockers", lambda d: candidate(d).__setitem__("promotion_blockers", []), "promotion_blockers"),
        ("provenance", lambda d: candidate(d).__setitem__("provenance_paths", []), "provenance"),
        ("thinness", lambda d: candidate(d).__setitem__("thinness_warning", ""), "thinness_warning"),
        ("raw", lambda d: candidate(d).__setitem__("raw_capture_dependency", True), "raw capture"),
        ("draft_prose", lambda d: candidate(d).__setitem__("new_draft_prose", "Hermes appears in OpenClaw setup tooling."), "prose"),
        ("chapter_prose", lambda d: candidate(d).__setitem__("chapter_ready_prose", "This is ready for the book."), "prose"),
        ("approval_text", lambda d: candidate(d).__setitem__("metadata_note", "approved for publication"), "publication"),
    ]
    for name, mut, expected in cases:
        case = tmp_path / name
        db = db_copy(case)
        report = run30_copy(case, mut)
        mock = write_mock_bridge(case)
        before = counts(db)
        res = run_script("--metadata-report", str(report), db_path=db, output_dir=case, env={"TEREFO_HIGH_REASONING_BRIDGE_COMMAND": str(mock)})
        assert res.returncode == 2, name
        assert expected.lower() in res.stderr.lower()
        assert counts(db) == before


def test_invalid_llm_json_enums_flags_fields_and_decision_routing_fail_closed(tmp_path):
    cases = [
        ("badjson", {"invalid_json": True}, "invalid_json"),
        ("badenum", {"invalid_enum": True}, "schema_mismatch"),
        ("missingflags", {"missing_flags": True}, "schema_mismatch"),
        ("missingcaveat", {"missing_field": "required_caveats"}, "schema_mismatch"),
        ("missingdns", {"missing_field": "do_not_say"}, "schema_mismatch"),
        ("missingunsupported", {"missing_field": "unsupported_inferences"}, "schema_mismatch"),
        ("missingblockers", {"missing_field": "promotion_blockers"}, "schema_mismatch"),
        ("author", {"author_allowed": True}, "schema_mismatch"),
        ("publication", {"publication_approved": True}, "schema_mismatch"),
        ("claim", {"eligible_claim": True}, "schema_mismatch"),
        ("authoring", {"eligible_authoring": True}, "schema_mismatch"),
        ("publish", {"eligible_publication": True}, "schema_mismatch"),
        ("chapter", {"chapter_update": True}, "schema_mismatch"),
        ("passed_safe", {"decision": "metadata_preflight_passed", "readiness": "ready_for_promotion_contract_update", "disposition": "caveat_only", "next_stage": "update_closed_loop_promotion_contract_for_authoring_metadata"}, None),
        ("thin_rebuild", {"decision": "safe_but_too_thin", "readiness": "not_ready_still_too_thin", "disposition": "needs_better_authoring_metadata", "next_stage": "rebuild_authoring_metadata"}, None),
        ("thin_reports", {"decision": "safe_but_too_thin", "readiness": "not_ready_safe_reports_only", "disposition": "safe_reports_only", "next_stage": "keep_safe_reports_only"}, None),
        ("needs_sources", {"decision": "needs_more_sources", "readiness": "not_ready_needs_more_sources", "disposition": "needs_more_sources", "next_stage": "run_additional_source_collection"}, None),
        ("source_context", {"decision": "source_context_unclear", "readiness": "not_ready_source_context_unclear", "disposition": "source_context_unclear", "next_stage": "run_source_context_review"}, None),
        ("bad_thin_route", {"decision": "safe_but_too_thin", "readiness": "not_ready_still_too_thin", "disposition": "needs_better_authoring_metadata", "next_stage": "run_additional_source_collection"}, "schema_mismatch"),
        ("bad_sources_route", {"decision": "needs_more_sources", "readiness": "not_ready_needs_more_sources", "disposition": "needs_more_sources", "next_stage": "keep_safe_reports_only"}, "schema_mismatch"),
        ("bad_context_route", {"decision": "source_context_unclear", "readiness": "not_ready_source_context_unclear", "disposition": "source_context_unclear", "next_stage": "keep_safe_reports_only"}, "schema_mismatch"),
    ]
    for case_name, kwargs, expected in cases:
        case = tmp_path / case_name
        db = db_copy(case)
        mock = write_mock_bridge(case, **kwargs)
        before = counts(db)
        res = run_script("--metadata-report", str(RUN30), db_path=db, output_dir=case, env={"TEREFO_HIGH_REASONING_BRIDGE_COMMAND": str(mock)})
        if expected is None:
            assert res.returncode == 0, res.stderr + res.stdout
            report = read_report(case)
            review = report["constrained_authoring_metadata_preflight_reviews"][0]
            assert review["author_allowed"] is False
            assert review["publication_approved"] is False
            assert review["eligible_for_claim_insertion"] is False
            assert review["eligible_for_authoring"] is False
            assert review["eligible_for_publication"] is False
            assert review["chapter_update_allowed"] is False
            if review["preflight_decision"] == "safe_but_too_thin":
                assert review["recommended_next_stage"] in {"rebuild_authoring_metadata", "keep_safe_reports_only"}
            if review["preflight_decision"] == "needs_more_sources":
                assert review["recommended_next_stage"] == "run_additional_source_collection"
            if review["preflight_decision"] == "source_context_unclear":
                assert review["recommended_next_stage"] == "run_source_context_review"
        else:
            assert res.returncode == 2, res.stdout + res.stderr
            assert expected in res.stderr
        assert counts(db) == before


def test_weak_local_fallback_missing_profile_and_missing_inputs_fail_closed(tmp_path):
    db = db_copy(tmp_path / "weak")
    mock = write_mock_bridge(tmp_path / "weak")
    res = run_script("--metadata-report", str(RUN30), "--provider", "local", db_path=db, output_dir=tmp_path / "weak", env={"TEREFO_HIGH_REASONING_BRIDGE_COMMAND": str(mock)})
    assert res.returncode == 2
    assert "weak_or_unapproved_provider_refused" in res.stderr

    db = db_copy(tmp_path / "profile")
    res = run_script("--metadata-report", str(RUN30), "--reasoning-profile", "missing_profile", db_path=db, output_dir=tmp_path / "profile", env={"TEREFO_HIGH_REASONING_BRIDGE_COMMAND": str(mock)})
    assert res.returncode == 2
    assert "model_profile_error" in res.stderr

    db = db_copy(tmp_path / "missing")
    res = run_script("--metadata-report", str(tmp_path / "nope.json"), db_path=db, output_dir=tmp_path / "missing", env={"TEREFO_HIGH_REASONING_BRIDGE_COMMAND": str(mock)})
    assert res.returncode == 2
    assert "missing input" in res.stderr

    bad = tmp_path / "bad.json"
    bad.write_text("{bad")
    res = run_script("--metadata-report", str(bad), db_path=db, output_dir=tmp_path / "bad", env={"TEREFO_HIGH_REASONING_BRIDGE_COMMAND": str(mock)})
    assert res.returncode == 2
    assert "invalid JSON" in res.stderr
