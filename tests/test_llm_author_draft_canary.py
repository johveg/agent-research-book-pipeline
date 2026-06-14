import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "llm_author_draft_canary.py"
RUN23 = ROOT / "reports" / "editorial" / "citation-pipeline-test-20260612-author-draft-input-preflight-run23.json"
RUN22B = ROOT / "reports" / "editorial" / "citation-pipeline-test-20260612-author-draft-input-run22b.json"
DRAFT_INPUT_ID = "draft_input_run22b_caveat_only_cluster_4e8554045cfaf827bc68bcc5"
REQUIRED_CAVEAT = "Frame narrowly: OpenClaw documentation names Hermes in migration/setup tooling contexts; do not state that Hermes is a runtime dependency or general operating environment without additional sources."
SAFE_TEXT = "In a caveat-only planning context, OpenClaw documentation names Hermes in migration and setup tooling contexts. Frame narrowly: OpenClaw documentation names Hermes in migration/setup tooling contexts; do not state that Hermes is a runtime dependency or general operating environment without additional sources."


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
    path = output_dir / "citation-pipeline-test-20260612-author-draft-canary-run24.json"
    assert path.exists(), f"missing report {path}"
    return json.loads(path.read_text())


def preflight_copy(tmp_path: Path, mutator=None) -> Path:
    data = json.loads(RUN23.read_text())
    if mutator:
        mutator(data)
    path = tmp_path / "preflight.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    return path


def draft_input_copy(tmp_path: Path, mutator=None) -> Path:
    data = json.loads(RUN22B.read_text())
    if mutator:
        mutator(data)
    path = tmp_path / "draft-input.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    return path


def write_mock_bridge(tmp_path: Path, *, invalid_json=False, invalid_enum=False, missing_flags=False, text=None, author_allowed=False, publication_approved=False, eligible_claim=False, eligible_authoring=False, eligible_publication=False, chapter_update=False):
    tmp_path.mkdir(parents=True, exist_ok=True)
    mock = tmp_path / "mock_bridge.py"
    if invalid_json:
        mock.write_text("#!/usr/bin/env python3\nprint('not-json')\n", encoding="utf-8")
    else:
        decision = "bad_enum" if invalid_enum else "draft_canary_created"
        canary_text = text or SAFE_TEXT
        safety = "" if missing_flags else (
            f", 'advisory_only': True, 'draft_canary_only': True, 'author_allowed': {author_allowed}, 'publication_approved': {publication_approved}, "
            f"'eligible_for_claim_insertion': {eligible_claim}, 'eligible_for_authoring': {eligible_authoring}, "
            f"'eligible_for_publication': {eligible_publication}, 'chapter_update_allowed': {chapter_update}"
        )
        mock.write_text(
            "#!/usr/bin/env python3\n"
            "import json,sys\n"
            "payload=json.load(sys.stdin)\n"
            f"canary={{'draft_canary_id':'draft_canary_run24_caveat_only_cluster_4e8554045cfaf827bc68bcc5','draft_input_id':'{DRAFT_INPUT_ID}','source_packet_id':'packet_run20_caveat_only_cluster_4e8554045cfaf827bc68bcc5','source_cluster_id':'cluster_4e8554045cfaf827bc68bcc5','source_note_ids':['note_a30056d3f19faa7deb0c9dbc'],'source_review_ids':['source_review_5baf68d86960f91b97ac'],'source_ids':['src_6d7b6d80cda4e784877d'],'manifest_item_ids':['manifest_2901cc01a0bc7a2252b35183'],'candidate_source_ids':['cand_20e9401eaf1118d440d3e64b','cand_6fcbc84f35207ab87be6a1d7'],'draft_canary_type':'caveat_only_author_draft_canary','draft_canary_decision':'{decision}','draft_canary_use':'caveat_only','draft_canary_text':{canary_text!r},'word_count':len({canary_text!r}.split()),'required_caveats':['{REQUIRED_CAVEAT}'],'do_not_say':['Do not say Hermes is a runtime dependency of OpenClaw.','Do not say Hermes is the general operating environment for OpenClaw.','Do not say OpenClaw requires Hermes for web or phone access.','Do not generalize beyond migration/setup/import tooling contexts unless additional sources support it.','Do not use this material as a factual claim without the caveat.','Do not use this material for chapter prose before later author/red-team gates pass.'],'caveat_compliance_notes':'Caveat preserved exactly and scope remains migration/setup tooling only.','evidence_limitations':['singleton narrow evidence'],'residual_risk':'Low to moderate if kept as report-only canary; high if promoted.','provenance_paths':['reports/editorial/citation-pipeline-test-20260612-author-draft-input-preflight-run23.json'],'target_chapter_status':'not_assigned','singleton_canary':True,'evidence_narrowness_warning':'Evidence is singleton and narrow.'{safety}}}\n"
            "print(json.dumps({'draft_canaries':[canary]}))\n",
            encoding="utf-8",
        )
    mock.chmod(0o755)
    return mock


def test_selects_current_canary_ready_input_and_writes_report_only_canary(tmp_path):
    db = db_copy(tmp_path)
    mock = write_mock_bridge(tmp_path)
    before = counts(db)
    before_status = status_hashes(db)
    before_registry = sha(ROOT / "data" / "source_registry.json")
    before_raw = tree_snapshot(ROOT / "raw")
    before_book = tree_snapshot(ROOT / "docs" / "book")
    before_schema = sha(ROOT / "data" / "schema.sql")
    before_worker = sha(ROOT / "scripts" / "daily_book_worker.py")
    res = run_script("--run-id", "citation-pipeline-test-20260612", "--preflight-report", str(RUN23), "--draft-input-report", str(RUN22B), "--report-suffix", "run24", db_path=db, output_dir=tmp_path, env={"TEREFO_HIGH_REASONING_BRIDGE_COMMAND": str(mock)})
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
    assert report["selected_draft_input_count"] == 1
    assert report["draft_canary_count"] == 1
    assert report["excluded_draft_input_count"] == 0
    assert report["draft_canary_type_counts"] == {"caveat_only_author_draft_canary": 1}
    assert report["draft_canary_decision_counts"] == {"draft_canary_created": 1}
    assert report["draft_canary_use_counts"] == {"caveat_only": 1}
    canary = report["draft_canaries"][0]
    assert canary["draft_input_id"] == DRAFT_INPUT_ID
    assert canary["word_count"] <= 90
    assert canary["draft_canary_only"] is True
    assert canary["author_allowed"] is False
    assert canary["eligible_for_authoring"] is False
    assert canary["publication_approved"] is False
    assert canary["eligible_for_publication"] is False
    assert canary["chapter_update_allowed"] is False
    assert REQUIRED_CAVEAT in canary["required_caveats"]


def test_unsafe_preflight_or_draft_input_flags_fail_closed(tmp_path):
    for key in ["author_allowed", "publication_approved", "eligible_for_claim_insertion", "eligible_for_authoring", "eligible_for_publication", "chapter_update_allowed"]:
        case = tmp_path / key
        db = db_copy(case)
        def mutate_pre(data, key=key):
            data["draft_input_preflight_reviews"][0][key] = True
        pre = preflight_copy(case, mutate_pre)
        mock = write_mock_bridge(case)
        res = run_script("--preflight-report", str(pre), "--draft-input-report", str(RUN22B), db_path=db, output_dir=case, env={"TEREFO_HIGH_REASONING_BRIDGE_COMMAND": str(mock)})
        assert res.returncode == 2
        assert "safety flag" in res.stderr

        case2 = tmp_path / (key + "_input")
        db2 = db_copy(case2)
        def mutate_input(data, key=key):
            data["draft_input_packages"][0][key] = True
        inp = draft_input_copy(case2, mutate_input)
        res2 = run_script("--preflight-report", str(RUN23), "--draft-input-report", str(inp), db_path=db2, output_dir=case2, env={"TEREFO_HIGH_REASONING_BRIDGE_COMMAND": str(mock)})
        assert res2.returncode == 2
        assert "safety flag" in res2.stderr


def test_missing_caveat_or_do_not_say_fails_closed(tmp_path):
    cases = [
        ("pre_caveat", lambda d: d["draft_input_preflight_reviews"][0].__setitem__("required_caveats", []), None, "required caveat"),
        ("pre_dns", lambda d: d["draft_input_preflight_reviews"][0].__setitem__("do_not_say", []), None, "do_not_say"),
        ("input_caveat", None, lambda d: d["draft_input_packages"][0].__setitem__("required_caveats", []), "required caveat"),
        ("input_dns", None, lambda d: d["draft_input_packages"][0].__setitem__("do_not_say", []), "do_not_say"),
    ]
    for name, pre_mut, input_mut, expected in cases:
        case = tmp_path / name
        db = db_copy(case)
        pre = preflight_copy(case, pre_mut) if pre_mut else RUN23
        inp = draft_input_copy(case, input_mut) if input_mut else RUN22B
        mock = write_mock_bridge(case)
        res = run_script("--preflight-report", str(pre), "--draft-input-report", str(inp), db_path=db, output_dir=case, env={"TEREFO_HIGH_REASONING_BRIDGE_COMMAND": str(mock)})
        assert res.returncode == 2
        assert expected in res.stderr


def test_invalid_llm_json_enums_flags_and_bad_canary_text_fail_closed(tmp_path):
    long_text = " ".join(["word"] * 91)
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
        ("long", {"text": long_text}, "schema_mismatch"),
        ("runtime", {"text": "Hermes is a runtime dependency of OpenClaw. " + REQUIRED_CAVEAT}, "schema_mismatch"),
        ("environment", {"text": "Hermes is the general operating environment for OpenClaw. " + REQUIRED_CAVEAT}, "schema_mismatch"),
        ("webphone", {"text": "OpenClaw requires Hermes for web or phone access. " + REQUIRED_CAVEAT}, "schema_mismatch"),
        ("generalize", {"text": "Hermes is broadly used across OpenClaw beyond migration setup import tooling. " + REQUIRED_CAVEAT}, "schema_mismatch"),
        ("approved", {"text": "This draft is approved for publication. " + REQUIRED_CAVEAT}, "schema_mismatch"),
        ("chapterready", {"text": "This chapter-ready paragraph says: " + REQUIRED_CAVEAT}, "schema_mismatch"),
    ]
    for case_name, kwargs, expected in cases:
        case = tmp_path / case_name
        db = db_copy(case)
        mock = write_mock_bridge(case, **kwargs)
        before = counts(db)
        res = run_script("--preflight-report", str(RUN23), "--draft-input-report", str(RUN22B), db_path=db, output_dir=case, env={"TEREFO_HIGH_REASONING_BRIDGE_COMMAND": str(mock)})
        assert res.returncode == 2, res.stdout + res.stderr
        assert expected in res.stderr
        assert counts(db) == before


def test_weak_local_fallback_missing_profile_and_missing_inputs_fail_closed(tmp_path):
    db = db_copy(tmp_path / "weak")
    mock = write_mock_bridge(tmp_path / "weak")
    res = run_script("--preflight-report", str(RUN23), "--draft-input-report", str(RUN22B), "--provider", "local", db_path=db, output_dir=tmp_path / "weak", env={"TEREFO_HIGH_REASONING_BRIDGE_COMMAND": str(mock)})
    assert res.returncode == 2
    assert "weak_or_unapproved_provider_refused" in res.stderr

    db = db_copy(tmp_path / "profile")
    res = run_script("--preflight-report", str(RUN23), "--draft-input-report", str(RUN22B), "--reasoning-profile", "missing_profile", db_path=db, output_dir=tmp_path / "profile", env={"TEREFO_HIGH_REASONING_BRIDGE_COMMAND": str(mock)})
    assert res.returncode == 2
    assert "model_profile_error" in res.stderr

    db = db_copy(tmp_path / "missing")
    res = run_script("--preflight-report", str(tmp_path / "nope.json"), "--draft-input-report", str(RUN22B), db_path=db, output_dir=tmp_path / "missing", env={"TEREFO_HIGH_REASONING_BRIDGE_COMMAND": str(mock)})
    assert res.returncode == 2
    assert "missing input" in res.stderr

    bad = tmp_path / "bad.json"
    bad.write_text("{bad")
    res = run_script("--preflight-report", str(bad), "--draft-input-report", str(RUN22B), db_path=db, output_dir=tmp_path / "bad", env={"TEREFO_HIGH_REASONING_BRIDGE_COMMAND": str(mock)})
    assert res.returncode == 2
    assert "invalid JSON" in res.stderr
