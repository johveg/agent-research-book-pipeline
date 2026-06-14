import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "llm_rebuild_author_draft_input.py"
RUN25 = ROOT / "reports" / "editorial" / "citation-pipeline-test-20260612-author-draft-canary-redteam-run25.json"
RUN24 = ROOT / "reports" / "editorial" / "citation-pipeline-test-20260612-author-draft-canary-run24.json"
RUN23 = ROOT / "reports" / "editorial" / "citation-pipeline-test-20260612-author-draft-input-preflight-run23.json"
RUN22B = ROOT / "reports" / "editorial" / "citation-pipeline-test-20260612-author-draft-input-run22b.json"
DRAFT_INPUT_ID = "draft_input_run22b_caveat_only_cluster_4e8554045cfaf827bc68bcc5"
DRAFT_CANARY_ID = "draft_canary_run24_caveat_only_cluster_4e8554045cfaf827bc68bcc5"
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
    path = output_dir / "citation-pipeline-test-20260612-author-draft-input-rebuild-run26.json"
    assert path.exists(), f"missing report {path}"
    return json.loads(path.read_text())


def copy_json(src: Path, dst: Path, mutator=None) -> Path:
    data = json.loads(src.read_text())
    if mutator:
        mutator(data)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    return dst


def write_mock_bridge(tmp_path: Path, *, invalid_json=False, invalid_enum=False, missing_flags=False, author_allowed=False, publication_approved=False, eligible_claim=False, eligible_authoring=False, eligible_publication=False, chapter_update=False, type_="enriched_caveat_only_author_draft_input", decision="rebuilt_draft_input_candidate", use="caveat_only"):
    tmp_path.mkdir(parents=True, exist_ok=True)
    mock = tmp_path / "mock_bridge.py"
    if invalid_json:
        mock.write_text("#!/usr/bin/env python3\nprint('not-json')\n", encoding="utf-8")
    else:
        rtype = "bad_enum" if invalid_enum else type_
        safety = "" if missing_flags else (
            f", 'advisory_only': True, 'author_allowed': {author_allowed}, 'publication_approved': {publication_approved}, "
            f"'eligible_for_claim_insertion': {eligible_claim}, 'eligible_for_authoring': {eligible_authoring}, "
            f"'eligible_for_publication': {eligible_publication}, 'chapter_update_allowed': {chapter_update}"
        )
        mock.write_text(
            "#!/usr/bin/env python3\n"
            "import json,sys\njson.load(sys.stdin)\n"
            f"pkg={{'rebuilt_input_id':'rebuilt_input_run26_caveat_only_cluster_4e8554045cfaf827bc68bcc5','prior_draft_input_id':'{DRAFT_INPUT_ID}','prior_draft_canary_id':'{DRAFT_CANARY_ID}','source_packet_id':'packet_run20_caveat_only_cluster_4e8554045cfaf827bc68bcc5','source_cluster_id':'cluster_4e8554045cfaf827bc68bcc5','source_note_ids':['note_a30056d3f19faa7deb0c9dbc'],'source_review_ids':['source_review_5baf68d86960f91b97ac'],'source_ids':['src_6d7b6d80cda4e784877d'],'manifest_item_ids':['manifest_2901cc01a0bc7a2252b35183'],'candidate_source_ids':['cand_20e9401eaf1118d440d3e64b','cand_6fcbc84f35207ab87be6a1d7'],'rebuilt_input_type':'{rtype}','rebuilt_input_decision':'{decision}','rebuilt_input_use':'{use}','title':'Caveat-only OpenClaw/Hermes tooling adjacency input','authoring_purpose':'Planning-only input for a later controlled canary about narrow documentation references, not prose.','evidence_bound_factual_atoms':['OpenClaw documentation names Hermes in migration/setup/import tooling contexts.','The current evidence does not establish runtime dependency.','The safe narrative function is ecosystem/tooling adjacency only.'],'allowed_author_scope':['Explain narrow documentation-reference context in planning language.','Use as caveated context note only.'],'forbidden_author_scope':['No runtime dependency claim.','No general operating environment claim.','No publication or chapter update language.'],'narrative_function_suggestions':['Use as a caveated context note.','Show how weak-but-not-useless evidence is constrained.'],'placement_suggestions':['Suggested only: background/tooling adjacency context; no chapter assignment.'],'target_chapter_candidates':['suggested_only_openclaw_context','suggested_only_agent_loop_context'],'target_chapter_status':'suggested_only','required_caveats':['{REQUIRED_CAVEAT}'],'do_not_say':['Do not say Hermes is a runtime dependency of OpenClaw.','Do not say Hermes is the general operating environment for OpenClaw.','Do not say OpenClaw requires Hermes for web or phone access.','Do not generalize beyond migration/setup/import tooling contexts unless additional sources support it.','Do not use this material as a factual claim without the caveat.','Do not use this material for chapter prose before later author/red-team gates pass.'],'evidence_summary':'Planning summary only: evidence supports narrow references in migration/setup/import tooling documentation.','evidence_limitations':['Singleton narrow evidence.','No support for dependency, runtime, web, or phone access claims.'],'residual_risk':'Overclaiming risk if converted into prose without caveat.','confidence':'limited_caveat_only','citation_requirements':['Preserve source, note, source review, packet, and report provenance.','Do not cite as dependency evidence.'],'later_canary_instruction_seed':'Instruction only: draft a short caveat-only canary that treats this as tooling adjacency and preserves the required caveat; do not write final prose.','usefulness_improvement_notes':'Adds factual atoms, narrative function, boundaries, and author constraints beyond merely restating the caveat.','why_prior_canary_was_not_useful':'Run 24 canary restated the mandatory caveat without additional structured authoring context.','provenance_paths':['reports/editorial/citation-pipeline-test-20260612-author-draft-canary-redteam-run25.json','reports/editorial/citation-pipeline-test-20260612-author-draft-input-run22b.json'],'singleton_input':True,'evidence_narrowness_warning':'Evidence remains singleton and narrow.'{safety}}}\n"
            "print(json.dumps({'rebuilt_author_draft_inputs':[pkg]}))\n",
            encoding="utf-8",
        )
    mock.chmod(0o755)
    return mock


def test_selects_current_redteam_and_writes_report_only_rebuilt_input(tmp_path):
    db = db_copy(tmp_path)
    mock = write_mock_bridge(tmp_path)
    before = counts(db)
    before_status = status_hashes(db)
    before_registry = sha(ROOT / "data" / "source_registry.json")
    before_raw = tree_snapshot(ROOT / "raw")
    before_book = tree_snapshot(ROOT / "docs" / "book")
    before_schema = sha(ROOT / "data" / "schema.sql")
    before_worker = sha(ROOT / "scripts" / "daily_book_worker.py")
    res = run_script("--run-id", "citation-pipeline-test-20260612", "--redteam-report", str(RUN25), "--canary-report", str(RUN24), "--preflight-report", str(RUN23), "--draft-input-report", str(RUN22B), "--report-suffix", "run26", db_path=db, output_dir=tmp_path, env={"TEREFO_HIGH_REASONING_BRIDGE_COMMAND": str(mock)})
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
    assert report["selected_canary_redteam_count"] == 1
    assert report["rebuilt_input_count"] == 1
    assert report["excluded_canary_redteam_count"] == 0
    assert report["rebuilt_input_type_counts"] == {"enriched_caveat_only_author_draft_input": 1}
    assert report["rebuilt_input_decision_counts"] == {"rebuilt_draft_input_candidate": 1}
    assert report["rebuilt_input_use_counts"] == {"caveat_only": 1}
    pkg = report["rebuilt_author_draft_inputs"][0]
    assert pkg["prior_draft_input_id"] == DRAFT_INPUT_ID
    assert pkg["prior_draft_canary_id"] == DRAFT_CANARY_ID
    assert REQUIRED_CAVEAT in pkg["required_caveats"]
    assert pkg["evidence_bound_factual_atoms"]
    assert pkg["narrative_function_suggestions"]
    assert pkg["why_prior_canary_was_not_useful"]
    assert "chapter_prose" not in json.dumps(pkg)
    assert pkg["author_allowed"] is False
    assert pkg["eligible_for_authoring"] is False
    assert pkg["chapter_update_allowed"] is False


def test_excludes_or_fails_closed_for_unsafe_or_non_rebuild_inputs(tmp_path):
    cases = []
    for key in ["author_allowed", "publication_approved", "eligible_for_claim_insertion", "eligible_for_authoring", "eligible_for_publication", "chapter_update_allowed"]:
        cases.append((key, lambda d, key=key: d["draft_canary_redteam_reviews"][0].__setitem__(key, True), "safety flag"))
    cases += [
        ("decision", lambda d: d["draft_canary_redteam_reviews"][0].__setitem__("redteam_decision", "draft_canary_passed"), "no selected"),
        ("next", lambda d: d["draft_canary_redteam_reviews"][0].__setitem__("recommended_next_stage", "keep_safe_reports_only"), "no selected"),
        ("caveat", lambda d: d["draft_canary_redteam_reviews"][0].__setitem__("required_caveats", []), "required caveat"),
        ("dns", lambda d: d["draft_canary_redteam_reviews"][0].__setitem__("do_not_say", []), "do_not_say"),
    ]
    for name, mut, expected in cases:
        case = tmp_path / name
        db = db_copy(case)
        red = copy_json(RUN25, case / "run25.json", mut)
        mock = write_mock_bridge(case)
        res = run_script("--redteam-report", str(red), "--canary-report", str(RUN24), "--preflight-report", str(RUN23), "--draft-input-report", str(RUN22B), db_path=db, output_dir=case, env={"TEREFO_HIGH_REASONING_BRIDGE_COMMAND": str(mock)})
        assert res.returncode == 2, name
        assert expected.lower() in res.stderr.lower()


def test_invalid_llm_json_enums_flags_and_no_prose_constraints_fail_closed(tmp_path):
    cases = [
        ("badjson", {"invalid_json": True}, "invalid_json"),
        ("badenum", {"invalid_enum": True}, "schema_mismatch"),
        ("missingflags", {"missing_flags": True}, "schema_mismatch"),
        ("author", {"author_allowed": True}, "schema_mismatch"),
        ("publication", {"publication_approved": True}, "schema_mismatch"),
        ("claim", {"eligible_claim": True}, "schema_mismatch"),
        ("authoring", {"eligible_authoring": True}, "schema_mismatch"),
        ("publish", {"eligible_publication": True}, "schema_mismatch"),
        ("chapter", {"chapter_update": True}, "schema_mismatch"),
        ("safe_reports", {"type_": "safe_reports_only_author_input", "decision": "safe_reports_only", "use": "safe_reports_only"}, None),
    ]
    for case_name, kwargs, expected in cases:
        case = tmp_path / case_name
        db = db_copy(case)
        mock = write_mock_bridge(case, **kwargs)
        before = counts(db)
        res = run_script("--redteam-report", str(RUN25), "--canary-report", str(RUN24), "--preflight-report", str(RUN23), "--draft-input-report", str(RUN22B), db_path=db, output_dir=case, env={"TEREFO_HIGH_REASONING_BRIDGE_COMMAND": str(mock)})
        if expected is None:
            assert res.returncode == 0, res.stderr + res.stdout
            pkg = read_report(case)["rebuilt_author_draft_inputs"][0]
            assert pkg["author_allowed"] is False
            assert pkg["eligible_for_authoring"] is False
            assert pkg["chapter_update_allowed"] is False
            assert "approved for publication" not in json.dumps(pkg).lower()
            assert "chapter-ready" not in json.dumps(pkg).lower()
        else:
            assert res.returncode == 2, res.stdout + res.stderr
            assert expected in res.stderr
        assert counts(db) == before


def test_weak_local_fallback_missing_profile_and_missing_inputs_fail_closed(tmp_path):
    db = db_copy(tmp_path / "weak")
    mock = write_mock_bridge(tmp_path / "weak")
    res = run_script("--redteam-report", str(RUN25), "--canary-report", str(RUN24), "--preflight-report", str(RUN23), "--draft-input-report", str(RUN22B), "--provider", "local", db_path=db, output_dir=tmp_path / "weak", env={"TEREFO_HIGH_REASONING_BRIDGE_COMMAND": str(mock)})
    assert res.returncode == 2
    assert "weak_or_unapproved_provider_refused" in res.stderr

    db = db_copy(tmp_path / "profile")
    res = run_script("--redteam-report", str(RUN25), "--canary-report", str(RUN24), "--preflight-report", str(RUN23), "--draft-input-report", str(RUN22B), "--reasoning-profile", "missing_profile", db_path=db, output_dir=tmp_path / "profile", env={"TEREFO_HIGH_REASONING_BRIDGE_COMMAND": str(mock)})
    assert res.returncode == 2
    assert "model_profile_error" in res.stderr

    db = db_copy(tmp_path / "missing")
    res = run_script("--redteam-report", str(tmp_path / "nope.json"), "--canary-report", str(RUN24), "--preflight-report", str(RUN23), "--draft-input-report", str(RUN22B), db_path=db, output_dir=tmp_path / "missing", env={"TEREFO_HIGH_REASONING_BRIDGE_COMMAND": str(mock)})
    assert res.returncode == 2
    assert "missing input" in res.stderr
