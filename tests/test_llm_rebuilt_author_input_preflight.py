import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "llm_rebuilt_author_input_preflight.py"
RUN26 = ROOT / "reports" / "editorial" / "citation-pipeline-test-20260612-author-draft-input-rebuild-run26.json"
REBUILT_ID = "rebuilt_input_run26_enriched_caveat_only_cluster_4e8554045cfaf827bc68bcc5"
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


def report_path(output_dir: Path) -> Path:
    return output_dir / "citation-pipeline-test-20260612-rebuilt-author-input-preflight-run27.json"


def read_report(output_dir: Path) -> dict:
    path = report_path(output_dir)
    assert path.exists(), f"missing report {path}"
    return json.loads(path.read_text())


def copy_json(src: Path, dst: Path, mutator=None) -> Path:
    data = json.loads(src.read_text())
    if mutator:
        mutator(data)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    return dst


def write_mock_bridge(tmp_path: Path, *, invalid_json=False, invalid_enum=False, missing_flags=False, author_allowed=False, publication_approved=False, eligible_claim=False, eligible_authoring=False, eligible_publication=False, chapter_update=False, decision="rebuilt_input_canary_ready", readiness="ready_for_second_controlled_caveat_only_author_draft_canary", disposition="caveat_only", next_stage="run_second_controlled_caveat_only_author_draft_canary"):
    tmp_path.mkdir(parents=True, exist_ok=True)
    mock = tmp_path / "mock_bridge.py"
    if invalid_json:
        mock.write_text("#!/usr/bin/env python3\nprint('not-json')\n", encoding="utf-8")
    else:
        decision_value = "bad_enum" if invalid_enum else decision
        safety = "" if missing_flags else (
            f", 'advisory_only': True, 'author_allowed': {author_allowed}, 'publication_approved': {publication_approved}, "
            f"'eligible_for_claim_insertion': {eligible_claim}, 'eligible_for_authoring': {eligible_authoring}, "
            f"'eligible_for_publication': {eligible_publication}, 'chapter_update_allowed': {chapter_update}"
        )
        mock.write_text(
            "#!/usr/bin/env python3\n"
            "import json,sys\njson.load(sys.stdin)\n"
            f"review={{'rebuilt_input_id':'{REBUILT_ID}','rebuilt_input_type':'enriched_caveat_only_author_draft_input','rebuilt_input_use':'caveat_only','preflight_decision':'{decision_value}','canary_readiness':'{readiness}','closed_loop_disposition':'{disposition}','usefulness_improvement_assessment':'Run 26 adds atoms, boundaries, function suggestions, and instructions beyond a restated caveat.','caveat_integrity_assessment':'Required caveat remains intact and narrow.','do_not_say_compliance_assessment':'All do-not-say guidance is preserved.','prose_containment_assessment':'No finished paragraph, chapter prose, or publishable wording; instruction seed is instructions only.','provenance_assessment':'Prior draft input, canary, source packet, source cluster, notes, reviews, sources, candidates, and report paths are present.','residual_risk_assessment':'Evidence remains singleton and narrow but risk is controlled for a report-only canary preflight.','required_caveats':['{REQUIRED_CAVEAT}'],'do_not_say':['Do not say Hermes is a runtime dependency of OpenClaw.','Do not say Hermes is the general operating environment for OpenClaw.','Do not say OpenClaw requires Hermes for web or phone access.','Do not generalize beyond migration/setup/import tooling contexts unless additional sources support it.','Do not use this material as a factual claim without the caveat.','Do not use this material for chapter prose before later author/red-team gates pass.'],'limitations':['Singleton evidence remains narrow.','No authoring or publication approval.'],'residual_risk':'Overclaiming if later stages ignore caveat.','recommended_next_stage':'{next_stage}'{safety}}}\n"
            "print(json.dumps({'rebuilt_input_preflight_reviews':[review]}))\n",
            encoding="utf-8",
        )
    mock.chmod(0o755)
    return mock


def test_selects_current_rebuilt_input_and_writes_report_only_preflight(tmp_path):
    db = db_copy(tmp_path)
    mock = write_mock_bridge(tmp_path)
    before = counts(db)
    before_status = status_hashes(db)
    before_registry = sha(ROOT / "data" / "source_registry.json")
    before_raw = tree_snapshot(ROOT / "raw")
    before_book = tree_snapshot(ROOT / "docs" / "book")
    before_schema = sha(ROOT / "data" / "schema.sql")
    before_worker = sha(ROOT / "scripts" / "daily_book_worker.py")
    res = run_script("--run-id", "citation-pipeline-test-20260612", "--rebuild-report", str(RUN26), "--report-suffix", "run27", db_path=db, output_dir=tmp_path, env={"TEREFO_HIGH_REASONING_BRIDGE_COMMAND": str(mock)})
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
    assert report["selected_rebuilt_input_count"] == 1
    assert report["reviewed_rebuilt_input_count"] == 1
    assert report["excluded_rebuilt_input_count"] == 0
    assert report["preflight_decision_counts"] == {"rebuilt_input_canary_ready": 1}
    assert report["canary_readiness_counts"] == {"ready_for_second_controlled_caveat_only_author_draft_canary": 1}
    assert report["closed_loop_disposition_counts"] == {"caveat_only": 1}
    assert report["recommended_next_stage_counts"] == {"run_second_controlled_caveat_only_author_draft_canary": 1}
    review = report["rebuilt_input_preflight_reviews"][0]
    assert review["rebuilt_input_id"] == REBUILT_ID
    assert REQUIRED_CAVEAT in review["required_caveats"]
    assert review["author_allowed"] is False
    assert review["eligible_for_authoring"] is False
    assert review["chapter_update_allowed"] is False


def test_excludes_or_fails_closed_for_unsafe_or_incomplete_rebuilt_inputs(tmp_path):
    cases = []
    for key in ["author_allowed", "publication_approved", "eligible_for_claim_insertion", "eligible_for_authoring", "eligible_for_publication", "chapter_update_allowed"]:
        cases.append((key, lambda d, key=key: d["rebuilt_author_draft_inputs"][0].__setitem__(key, True), "safety flag"))
    cases += [
        ("type", lambda d: d["rebuilt_author_draft_inputs"][0].__setitem__("rebuilt_input_type", "safe_reports_only_author_input"), "no selected"),
        ("caveat", lambda d: d["rebuilt_author_draft_inputs"][0].__setitem__("required_caveats", []), "required caveat"),
        ("dns", lambda d: d["rebuilt_author_draft_inputs"][0].__setitem__("do_not_say", []), "do_not_say"),
        ("atoms", lambda d: d["rebuilt_author_draft_inputs"][0].__setitem__("evidence_bound_factual_atoms", []), "evidence_bound_factual_atoms"),
        ("narrative", lambda d: d["rebuilt_author_draft_inputs"][0].__setitem__("narrative_function_suggestions", []), "narrative_function_suggestions"),
        ("seed", lambda d: d["rebuilt_author_draft_inputs"][0].__setitem__("later_canary_instruction_seed", ""), "later_canary_instruction_seed"),
        ("final", lambda d: d["rebuilt_author_draft_inputs"][0].__setitem__("final_prose", "This is a final paragraph."), "chapter-ready"),
        ("chapter", lambda d: d["rebuilt_author_draft_inputs"][0].__setitem__("chapter_prose", "Chapter-ready prose."), "chapter-ready"),
    ]
    for name, mut, expected in cases:
        case = tmp_path / name
        db = db_copy(case)
        inp = copy_json(RUN26, case / "run26.json", mut)
        mock = write_mock_bridge(case)
        res = run_script("--rebuild-report", str(inp), db_path=db, output_dir=case, env={"TEREFO_HIGH_REASONING_BRIDGE_COMMAND": str(mock)})
        assert res.returncode == 2, name
        assert expected.lower() in res.stderr.lower()


def test_invalid_llm_json_enums_flags_and_too_thin_route_fail_or_validate(tmp_path):
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
        ("toothin_good", {"decision": "still_safe_but_too_thin", "readiness": "not_ready_still_too_thin", "disposition": "needs_better_authoring_input", "next_stage": "rebuild_author_draft_input_again"}, None),
        ("toothin_bad", {"decision": "still_safe_but_too_thin", "readiness": "not_ready_still_too_thin", "disposition": "needs_better_authoring_input", "next_stage": "run_second_controlled_caveat_only_author_draft_canary"}, "schema_mismatch"),
    ]
    for case_name, kwargs, expected in cases:
        case = tmp_path / case_name
        db = db_copy(case)
        mock = write_mock_bridge(case, **kwargs)
        before = counts(db)
        res = run_script("--rebuild-report", str(RUN26), db_path=db, output_dir=case, env={"TEREFO_HIGH_REASONING_BRIDGE_COMMAND": str(mock)})
        if expected is None:
            assert res.returncode == 0, res.stderr + res.stdout
            review = read_report(case)["rebuilt_input_preflight_reviews"][0]
            assert review["author_allowed"] is False
            assert review["eligible_for_authoring"] is False
            assert review["chapter_update_allowed"] is False
        else:
            assert res.returncode == 2, res.stdout + res.stderr
            assert expected in res.stderr
        assert counts(db) == before


def test_weak_local_fallback_missing_profile_and_missing_inputs_fail_closed(tmp_path):
    db = db_copy(tmp_path / "weak")
    mock = write_mock_bridge(tmp_path / "weak")
    res = run_script("--rebuild-report", str(RUN26), "--provider", "local", db_path=db, output_dir=tmp_path / "weak", env={"TEREFO_HIGH_REASONING_BRIDGE_COMMAND": str(mock)})
    assert res.returncode == 2
    assert "weak_or_unapproved_provider_refused" in res.stderr

    db = db_copy(tmp_path / "profile")
    res = run_script("--rebuild-report", str(RUN26), "--reasoning-profile", "missing_profile", db_path=db, output_dir=tmp_path / "profile", env={"TEREFO_HIGH_REASONING_BRIDGE_COMMAND": str(mock)})
    assert res.returncode == 2
    assert "model_profile_error" in res.stderr

    db = db_copy(tmp_path / "missing")
    res = run_script("--rebuild-report", str(tmp_path / "nope.json"), db_path=db, output_dir=tmp_path / "missing", env={"TEREFO_HIGH_REASONING_BRIDGE_COMMAND": str(mock)})
    assert res.returncode == 2
    assert "missing input" in res.stderr
