import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "llm_author_draft_canary_v2.py"
RUN27 = ROOT / "reports" / "editorial" / "citation-pipeline-test-20260612-rebuilt-author-input-preflight-run27.json"
RUN26 = ROOT / "reports" / "editorial" / "citation-pipeline-test-20260612-author-draft-input-rebuild-run26.json"
REBUILT_ID = "rebuilt_input_run26_enriched_caveat_only_cluster_4e8554045cfaf827bc68bcc5"
REQUIRED_CAVEAT = "Frame narrowly: OpenClaw documentation names Hermes in migration/setup tooling contexts; do not state that Hermes is a runtime dependency or general operating environment without additional sources."
GOOD_TEXT = REQUIRED_CAVEAT + " As a report-only canary, the useful extra atom is that documentation summaries name Hermes in migration tooling context while the singleton cluster keeps corroboration narrow."


def word_count(text):
    import re
    return len(re.findall(r"\b\S+\b", text))


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


def copy_json(src: Path, dst: Path, mutator=None) -> Path:
    data = json.loads(src.read_text())
    if mutator:
        mutator(data)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    return dst


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
    return output_dir / "citation-pipeline-test-20260612-author-draft-canary-v2-run28.json"


def read_report(output_dir: Path) -> dict:
    path = report_path(output_dir)
    assert path.exists(), f"missing report {path}"
    return json.loads(path.read_text())


def write_mock_bridge(tmp_path: Path, *, invalid_json=False, invalid_enum=False, missing_flags=False, author_allowed=False, publication_approved=False, eligible_claim=False, eligible_authoring=False, eligible_publication=False, chapter_update=False, text=GOOD_TEXT, canary_type="caveat_only_author_draft_canary_v2", decision="draft_canary_v2_created", use="caveat_only"):
    tmp_path.mkdir(parents=True, exist_ok=True)
    mock = tmp_path / "mock_bridge.py"
    if invalid_json:
        mock.write_text("#!/usr/bin/env python3\nprint('not-json')\n", encoding="utf-8")
    else:
        canary_type = "bad_enum" if invalid_enum else canary_type
        safety = "" if missing_flags else (
            f", 'advisory_only': True, 'draft_canary_only': True, 'author_allowed': {author_allowed}, 'publication_approved': {publication_approved}, "
            f"'eligible_for_claim_insertion': {eligible_claim}, 'eligible_for_authoring': {eligible_authoring}, "
            f"'eligible_for_publication': {eligible_publication}, 'chapter_update_allowed': {chapter_update}"
        )
        mock.write_text(
            "#!/usr/bin/env python3\n"
            "import json,sys\njson.load(sys.stdin)\n"
            f"text={text!r}\n"
            f"canary={{'draft_canary_id':'draft_canary_v2_run28_cluster_4e8554045cfaf827bc68bcc5','rebuilt_input_id':'{REBUILT_ID}','prior_draft_input_id':'draft_input_run22b_caveat_only_cluster_4e8554045cfaf827bc68bcc5','prior_draft_canary_id':'draft_canary_run24_caveat_only_cluster_4e8554045cfaf827bc68bcc5','source_packet_id':'packet_run20_caveat_only_cluster_4e8554045cfaf827bc68bcc5','source_cluster_id':'cluster_4e8554045cfaf827bc68bcc5','source_note_ids':['note_a30056d3f19faa7deb0c9dbc'],'source_review_ids':['source_review_5baf68d86960f91b97ac'],'source_ids':['src_6d7b6d80cda4e784877d'],'manifest_item_ids':['manifest_2901cc01a0bc7a2252b35183'],'candidate_source_ids':['cand_20e9401eaf1118d440d3e64b'],'draft_canary_type':'{canary_type}','draft_canary_decision':'{decision}','draft_canary_use':'{use}','draft_canary_text':text,'word_count':len(text.split()),'usefulness_improvement_over_run24':'Adds a concrete evidence atom and singleton limitation rather than only restating the caveat.','required_caveats':['{REQUIRED_CAVEAT}'],'do_not_say':['Do not say Hermes is a runtime dependency of OpenClaw.','Do not say Hermes is the general operating environment for OpenClaw.','Do not say OpenClaw requires Hermes for web or phone access.','Do not generalize beyond migration/setup/import tooling contexts unless additional sources support it.','Do not use this material as a factual claim without the caveat.','Do not use this material for chapter prose before later author/red-team gates pass.'],'caveat_compliance_notes':'Required caveat is preserved and do-not-say guidance is respected.','evidence_usage_notes':'Uses the atom that documentation summaries name Hermes in migration tooling context.','evidence_limitations':['Singleton evidence remains narrow.'],'residual_risk':'Overclaiming risk if later stages treat tooling adjacency as dependency.','provenance_paths':['reports/editorial/citation-pipeline-test-20260612-author-draft-input-rebuild-run26.json','reports/editorial/citation-pipeline-test-20260612-rebuilt-author-input-preflight-run27.json'],'target_chapter_status':'suggested_only','singleton_canary':True,'evidence_narrowness_warning':'Singleton caveat-only evidence remains narrow.'{safety}}}\n"
            "print(json.dumps({'draft_canaries':[canary]}))\n",
            encoding="utf-8",
        )
    mock.chmod(0o755)
    return mock


def test_selects_current_run27_ready_input_and_writes_report_only_canary(tmp_path):
    db = db_copy(tmp_path)
    mock = write_mock_bridge(tmp_path)
    before = counts(db)
    before_status = status_hashes(db)
    before_registry = sha(ROOT / "data" / "source_registry.json")
    before_raw = tree_snapshot(ROOT / "raw")
    before_book = tree_snapshot(ROOT / "docs" / "book")
    before_schema = sha(ROOT / "data" / "schema.sql")
    before_worker = sha(ROOT / "scripts" / "daily_book_worker.py")
    res = run_script("--run-id", "citation-pipeline-test-20260612", "--preflight-report", str(RUN27), "--rebuild-report", str(RUN26), "--report-suffix", "run28", db_path=db, output_dir=tmp_path, env={"TEREFO_HIGH_REASONING_BRIDGE_COMMAND": str(mock)})
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
    assert report["draft_canary_count"] == 1
    assert report["excluded_rebuilt_input_count"] == 0
    assert report["draft_canary_type_counts"] == {"caveat_only_author_draft_canary_v2": 1}
    canary = report["draft_canaries"][0]
    assert canary["rebuilt_input_id"] == REBUILT_ID
    assert canary["author_allowed"] is False
    assert canary["eligible_for_authoring"] is False
    assert canary["chapter_update_allowed"] is False


def test_excludes_or_fails_closed_for_unsafe_or_incomplete_upstream_inputs(tmp_path):
    cases = []
    for key in ["author_allowed", "publication_approved", "eligible_for_claim_insertion", "eligible_for_authoring", "eligible_for_publication", "chapter_update_allowed"]:
        cases.append((key, lambda d, key=key: d["rebuilt_input_preflight_reviews"][0].__setitem__(key, True), "safety flag"))
    cases += [
        ("decision", lambda d: d["rebuilt_input_preflight_reviews"][0].__setitem__("preflight_decision", "safe_reports_only"), "no selected"),
        ("caveat", lambda d: d["rebuilt_input_preflight_reviews"][0].__setitem__("required_caveats", []), "required caveat"),
        ("dns", lambda d: d["rebuilt_input_preflight_reviews"][0].__setitem__("do_not_say", []), "do_not_say"),
    ]
    for name, mut, expected in cases:
        case = tmp_path / name
        db = db_copy(case)
        preflight = copy_json(RUN27, case / "run27.json", mut)
        mock = write_mock_bridge(case)
        res = run_script("--preflight-report", str(preflight), "--rebuild-report", str(RUN26), db_path=db, output_dir=case, env={"TEREFO_HIGH_REASONING_BRIDGE_COMMAND": str(mock)})
        assert res.returncode == 2, name
        assert expected.lower() in res.stderr.lower()

    for name, mut, expected in [
        ("atoms", lambda d: d["rebuilt_author_draft_inputs"][0].__setitem__("evidence_bound_factual_atoms", []), "evidence_bound_factual_atoms"),
        ("caveat2", lambda d: d["rebuilt_author_draft_inputs"][0].__setitem__("required_caveats", []), "required caveat"),
        ("dns2", lambda d: d["rebuilt_author_draft_inputs"][0].__setitem__("do_not_say", []), "do_not_say"),
    ]:
        case = tmp_path / name
        db = db_copy(case)
        rebuild = copy_json(RUN26, case / "run26.json", mut)
        mock = write_mock_bridge(case)
        res = run_script("--preflight-report", str(RUN27), "--rebuild-report", str(rebuild), db_path=db, output_dir=case, env={"TEREFO_HIGH_REASONING_BRIDGE_COMMAND": str(mock)})
        assert res.returncode == 2, name
        assert expected.lower() in res.stderr.lower()


def test_llm_schema_text_safety_and_flags_fail_closed(tmp_path):
    bad_texts = [
        ("long", GOOD_TEXT + " " + "word " * 120, "exceeds 110 words"),
        ("restates", REQUIRED_CAVEAT, "merely restates"),
        ("noatom", REQUIRED_CAVEAT + " This is a safe report-only canary with no concrete atom.", "evidence-bound factual atom"),
        ("runtime", REQUIRED_CAVEAT + " Hermes is a runtime dependency of OpenClaw in this context.", "runtime dependency"),
        ("environment", REQUIRED_CAVEAT + " Hermes is the general operating environment for OpenClaw.", "general operating"),
        ("web", REQUIRED_CAVEAT + " OpenClaw requires Hermes for web or phone access.", "web/phone"),
        ("generalize", REQUIRED_CAVEAT + " This shows broad OpenClaw platform integration beyond migration/setup/import tooling.", "beyond migration"),
        ("publication", REQUIRED_CAVEAT + " This draft is approved for publication.", "publication approval"),
        ("chapter", REQUIRED_CAVEAT + " This is chapter-ready prose.", "chapter readiness"),
    ]
    cases = [
        ("badjson", {"invalid_json": True}, "invalid_json"),
        ("badenum", {"invalid_enum": True}, "schema_mismatch"),
        ("missingflags", {"missing_flags": True}, "schema_mismatch"),
        ("author", {"author_allowed": True}, "schema_mismatch"),
        ("publicationflag", {"publication_approved": True}, "schema_mismatch"),
        ("claim", {"eligible_claim": True}, "schema_mismatch"),
        ("authoring", {"eligible_authoring": True}, "schema_mismatch"),
        ("publish", {"eligible_publication": True}, "schema_mismatch"),
        ("chapterflag", {"chapter_update": True}, "schema_mismatch"),
    ] + [(name, {"text": text}, expected) for name, text, expected in bad_texts]
    for case_name, kwargs, expected in cases:
        case = tmp_path / case_name
        db = db_copy(case)
        mock = write_mock_bridge(case, **kwargs)
        before = counts(db)
        res = run_script("--preflight-report", str(RUN27), "--rebuild-report", str(RUN26), db_path=db, output_dir=case, env={"TEREFO_HIGH_REASONING_BRIDGE_COMMAND": str(mock)})
        assert res.returncode == 2, case_name + res.stdout + res.stderr
        assert expected.lower() in res.stderr.lower()
        assert counts(db) == before


def test_weak_local_fallback_and_missing_profile_fail_closed(tmp_path):
    db = db_copy(tmp_path / "weak")
    mock = write_mock_bridge(tmp_path / "weak")
    res = run_script("--preflight-report", str(RUN27), "--rebuild-report", str(RUN26), "--provider", "local", db_path=db, output_dir=tmp_path / "weak", env={"TEREFO_HIGH_REASONING_BRIDGE_COMMAND": str(mock)})
    assert res.returncode == 2
    assert "weak_or_unapproved_provider_refused" in res.stderr

    db = db_copy(tmp_path / "profile")
    res = run_script("--preflight-report", str(RUN27), "--rebuild-report", str(RUN26), "--reasoning-profile", "missing_profile", db_path=db, output_dir=tmp_path / "profile", env={"TEREFO_HIGH_REASONING_BRIDGE_COMMAND": str(mock)})
    assert res.returncode == 2
    assert "model_profile_error" in res.stderr
