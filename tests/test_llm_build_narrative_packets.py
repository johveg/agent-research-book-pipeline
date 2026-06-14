import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "llm_build_narrative_packets.py"
RUN19 = ROOT / "reports" / "editorial" / "citation-pipeline-test-20260612-cluster-quality-gate-run19.json"
CLUSTER_ID = "cluster_4e8554045cfaf827bc68bcc5"
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
        timeout=120,
    )


def read_report(output_dir: Path) -> dict:
    path = output_dir / "citation-pipeline-test-20260612-narrative-packet-candidates-run20.json"
    assert path.exists(), f"missing report {path}"
    return json.loads(path.read_text())


def quality_report_copy(tmp_path: Path, mutator=None) -> Path:
    data = json.loads(RUN19.read_text())
    if mutator:
        mutator(data)
    path = tmp_path / "quality.json"
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    return path


def write_mock_bridge(tmp_path: Path, *, invalid_json=False, invalid_enum=False, missing_flags=False, missing_caveat=False, chapter_update=False, paragraph_prose=False):
    tmp_path.mkdir(parents=True, exist_ok=True)
    mock = tmp_path / "mock_bridge.py"
    if invalid_json:
        mock.write_text("#!/usr/bin/env python3\nprint('not-json')\n", encoding="utf-8")
    else:
        ptype = "bad_enum" if invalid_enum else "caveat_only_packet_candidate"
        flags = "" if missing_flags else ", 'advisory_only': True, 'author_allowed': False, 'publication_approved': False, 'eligible_for_claim_insertion': False, 'eligible_for_authoring': False, 'eligible_for_publication': False, 'chapter_update_allowed': False"
        caveats = [] if missing_caveat else [REQUIRED_CAVEAT, "Use only as planning guidance, not prose."]
        extra = ", 'chapter_update_allowed': True" if chapter_update and missing_flags else ""
        prose = ", 'publishable_paragraph': 'This is forbidden chapter-ready prose.'" if paragraph_prose else ""
        mock.write_text(
            "#!/usr/bin/env python3\n"
            "import json,sys\n"
            "payload=json.load(sys.stdin)\n"
            f"packet={{'packet_id':'packet_fixture','packet_type':'{ptype}','packet_decision':'caveat_only_packet_candidate','packet_use':'caveat_only','title':'Caveat-only Hermes/OpenClaw planning packet','packet_summary':'Non-publishable planning summary for a caveat-only packet candidate.','packet_angle':'Plan a narrow caveat-only discussion of Hermes mentions in OpenClaw migration/setup tooling context.','target_chapter_candidates':['02-hermes','03-openclaw'],'target_chapter_status':'suggested_only','target_section_candidates':['tooling context note'],'cluster_ids':['{CLUSTER_ID}'],'source_ids':['src_6d7b6d80cda4e784877d'],'note_ids':['note_a30056d3f19faa7deb0c9dbc'],'manifest_item_ids':['manifest_2901cc01a0bc7a2252b35183'],'source_review_ids':['source_review_5baf68d86960f91b97ac'],'candidate_source_ids':['cand_20e9401eaf1118d440d3e64b','cand_6fcbc84f35207ab87be6a1d7'],'support_decisions':['partially_supported'],'corroboration_decisions':['partially_corroborated'],'evidence_use_decisions':['eligible_for_filing_later_after_corroboration'],'quality_gate_decision':'caveat_only_packet_candidate_ready','packet_readiness':'ready_for_caveat_only_packet','required_caveats':{json.dumps(caveats)},'caveat_text':'{REQUIRED_CAVEAT}','limitations':['singleton evidence','not chapter-ready'],'residual_risk':'moderate if generalized','do_not_say':['Do not say Hermes is a runtime dependency of OpenClaw.','Do not say Hermes is the general operating environment for OpenClaw.','Do not say OpenClaw requires Hermes for web or phone access.','Do not generalize beyond migration/setup/import tooling contexts unless additional sources support it.','Do not use this packet as a factual claim without the caveat.','Do not use this packet for chapter prose before later author/red-team gates pass.'],'author_guidance':['Use as planning checklist only.','Do not draft paragraphs.'],'citation_requirements':['Cite candidate sources only after later gates.'],'provenance_paths':[{{'run19_report':'reports/editorial/citation-pipeline-test-20260612-cluster-quality-gate-run19.json'}}],'singleton_packet':True,'evidence_narrowness_warning':'Singleton caveat-only packet; evidence is narrow.'{flags}{extra}{prose}}}\n"
            "print(json.dumps({'packet_candidates':[packet]}))\n",
            encoding="utf-8",
        )
    mock.chmod(0o755)
    return mock


def test_selects_current_ready_cluster_and_writes_report_only_packet(tmp_path):
    db = db_copy(tmp_path)
    mock = write_mock_bridge(tmp_path)
    before = counts(db)
    before_status = status_hashes(db)
    before_registry = sha(ROOT / "data" / "source_registry.json")
    before_raw = tree_snapshot(ROOT / "raw")
    before_book = tree_snapshot(ROOT / "docs" / "book")
    before_schema = sha(ROOT / "data" / "schema.sql")
    before_worker = sha(ROOT / "scripts" / "daily_book_worker.py")

    res = run_script("--run-id", "citation-pipeline-test-20260612", "--quality-gate-report", str(RUN19), "--report-suffix", "run20", db_path=db, output_dir=tmp_path, env={"TEREFO_HIGH_REASONING_BRIDGE_COMMAND": str(mock)})
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
    assert report["selected_cluster_review_count"] == 1
    assert report["packet_candidate_count"] == 1
    assert report["excluded_cluster_review_count"] == 1
    assert report["packet_type_counts"] == {"caveat_only_packet_candidate": 1}
    assert report["packet_decision_counts"] == {"caveat_only_packet_candidate": 1}
    assert report["packet_use_counts"] == {"caveat_only": 1}
    assert report["target_chapter_status_counts"] == {"suggested_only": 1}
    packet = report["packet_candidates"][0]
    assert packet["singleton_packet"] is True
    assert packet["chapter_update_allowed"] is False
    assert packet["advisory_only"] is True
    assert packet["author_allowed"] is False
    assert packet["publication_approved"] is False
    assert packet["eligible_for_claim_insertion"] is False
    assert packet["eligible_for_authoring"] is False
    assert packet["eligible_for_publication"] is False
    assert REQUIRED_CAVEAT in packet["required_caveats"]
    assert "publishable_paragraph" not in packet
    assert any("runtime dependency" in x for x in packet["do_not_say"])


def test_excludes_non_ready_quality_gate_decisions(tmp_path):
    def mutate(data):
        clone = dict(data["cluster_reviews"][0])
        clone["cluster_id"] = "cluster_not_ready"
        clone["quality_gate_decision"] = "safe_reports_only"
        clone["packet_readiness"] = "not_ready_safe_reports_only"
        clone["recommended_next_stage"] = "keep_safe_reports_only"
        data["cluster_reviews"].append(clone)
    q = quality_report_copy(tmp_path, mutate)
    db = db_copy(tmp_path)
    mock = write_mock_bridge(tmp_path)
    res = run_script("--quality-gate-report", str(q), db_path=db, output_dir=tmp_path, env={"TEREFO_HIGH_REASONING_BRIDGE_COMMAND": str(mock)})
    assert res.returncode == 0, res.stderr + res.stdout
    report = read_report(tmp_path)
    assert report["selected_cluster_review_count"] == 1
    assert any(i.get("cluster_id") == "cluster_not_ready" for i in report["excluded_cluster_reviews"])


def test_invalid_llm_json_and_invalid_enum_fail_closed(tmp_path):
    for case, kwargs, expected in [("badjson", {"invalid_json": True}, "invalid_json"), ("badenum", {"invalid_enum": True}, "schema_mismatch")]:
        case_dir = tmp_path / case
        db = db_copy(case_dir)
        mock = write_mock_bridge(case_dir, **kwargs)
        before = counts(db)
        res = run_script("--quality-gate-report", str(RUN19), db_path=db, output_dir=case_dir, env={"TEREFO_HIGH_REASONING_BRIDGE_COMMAND": str(mock)})
        assert res.returncode == 2, res.stdout + res.stderr
        assert expected in res.stderr
        assert counts(db) == before


def test_missing_flags_chapter_update_and_forbidden_upstream_flags_fail_closed(tmp_path):
    for case, kwargs in [("missing", {"missing_flags": True}), ("chapter", {"missing_flags": True, "chapter_update": True})]:
        case_dir = tmp_path / case
        db = db_copy(case_dir)
        mock = write_mock_bridge(case_dir, **kwargs)
        res = run_script("--quality-gate-report", str(RUN19), db_path=db, output_dir=case_dir, env={"TEREFO_HIGH_REASONING_BRIDGE_COMMAND": str(mock)})
        assert res.returncode == 2
        assert "schema_mismatch" in res.stderr

    for key in ["author_allowed", "publication_approved", "eligible_for_claim_insertion", "eligible_for_authoring", "eligible_for_publication"]:
        case_dir = tmp_path / key
        db = db_copy(case_dir)
        def mutate(data, key=key):
            data["cluster_reviews"][0][key] = True
        q = quality_report_copy(case_dir, mutate)
        mock = write_mock_bridge(case_dir)
        res = run_script("--quality-gate-report", str(q), db_path=db, output_dir=case_dir, env={"TEREFO_HIGH_REASONING_BRIDGE_COMMAND": str(mock)})
        assert res.returncode == 2, key
        assert "safety flag" in res.stderr


def test_caveat_and_do_not_say_and_no_prose_schema_checks(tmp_path):
    for case, kwargs, text in [
        ("nocaveat", {"missing_caveat": True}, "required caveat"),
        ("prose", {"paragraph_prose": True}, "chapter-ready prose"),
    ]:
        case_dir = tmp_path / case
        db = db_copy(case_dir)
        mock = write_mock_bridge(case_dir, **kwargs)
        res = run_script("--quality-gate-report", str(RUN19), db_path=db, output_dir=case_dir, env={"TEREFO_HIGH_REASONING_BRIDGE_COMMAND": str(mock)})
        assert res.returncode == 2
        assert text in res.stderr


def test_weak_local_fallback_and_missing_profile_fail_closed(tmp_path):
    db = db_copy(tmp_path / "weak")
    mock = write_mock_bridge(tmp_path / "weak")
    res = run_script("--quality-gate-report", str(RUN19), "--provider", "local", db_path=db, output_dir=tmp_path / "weak", env={"TEREFO_HIGH_REASONING_BRIDGE_COMMAND": str(mock)})
    assert res.returncode == 2
    assert "weak_or_unapproved_provider_refused" in res.stderr

    db = db_copy(tmp_path / "profile")
    res = run_script("--quality-gate-report", str(RUN19), "--reasoning-profile", "missing_profile", db_path=db, output_dir=tmp_path / "profile", env={"TEREFO_HIGH_REASONING_BRIDGE_COMMAND": str(mock)})
    assert res.returncode == 2
    assert "model_profile_error" in res.stderr


def test_missing_or_malformed_quality_report_fails_closed(tmp_path):
    db = db_copy(tmp_path / "missing")
    mock = write_mock_bridge(tmp_path / "missing")
    res = run_script("--quality-gate-report", str(tmp_path / "nope.json"), db_path=db, output_dir=tmp_path / "missing", env={"TEREFO_HIGH_REASONING_BRIDGE_COMMAND": str(mock)})
    assert res.returncode == 2
    assert "missing input" in res.stderr

    db = db_copy(tmp_path / "bad")
    bad = tmp_path / "bad" / "bad.json"
    bad.write_text("{bad")
    res = run_script("--quality-gate-report", str(bad), db_path=db, output_dir=tmp_path / "bad", env={"TEREFO_HIGH_REASONING_BRIDGE_COMMAND": str(mock)})
    assert res.returncode == 2
    assert "invalid JSON" in res.stderr
