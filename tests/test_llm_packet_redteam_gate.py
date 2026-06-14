import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "llm_packet_redteam_gate.py"
RUN20 = ROOT / "reports" / "editorial" / "citation-pipeline-test-20260612-narrative-packet-candidates-run20.json"
PACKET_ID = "packet_run20_caveat_only_cluster_4e8554045cfaf827bc68bcc5"
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
    path = output_dir / "citation-pipeline-test-20260612-packet-redteam-gate-run21.json"
    assert path.exists(), f"missing report {path}"
    return json.loads(path.read_text())


def packet_report_copy(tmp_path: Path, mutator=None) -> Path:
    data = json.loads(RUN20.read_text())
    if mutator:
        mutator(data)
    path = tmp_path / "packets.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    return path


def write_mock_bridge(tmp_path: Path, *, invalid_json=False, invalid_enum=False, missing_flags=False, approve_author=False, eligible_authoring=False):
    tmp_path.mkdir(parents=True, exist_ok=True)
    mock = tmp_path / "mock_bridge.py"
    if invalid_json:
        mock.write_text("#!/usr/bin/env python3\nprint('not-json')\n", encoding="utf-8")
    else:
        decision = "bad_enum" if invalid_enum else "caveat_only_author_input_ready"
        author_allowed = "True" if approve_author else "False"
        eligible_for_authoring = "True" if eligible_authoring else "False"
        safety = "" if missing_flags else f", 'advisory_only': True, 'author_allowed': {author_allowed}, 'publication_approved': False, 'eligible_for_claim_insertion': False, 'eligible_for_authoring': {eligible_for_authoring}, 'eligible_for_publication': False, 'chapter_update_allowed': False"
        mock.write_text(
            "#!/usr/bin/env python3\n"
            "import json,sys\n"
            "payload=json.load(sys.stdin)\n"
            f"review={{'packet_id':'{PACKET_ID}','packet_type':'caveat_only_packet_candidate','packet_use':'caveat_only','redteam_decision':'{decision}','author_input_readiness':'ready_for_caveat_only_draft_input','closed_loop_disposition':'caveat_only','caveat_integrity_assessment':'Caveat is present and not weakened; packet remains caveat-only and not a factual claim.','do_not_say_compliance_assessment':'All do-not-say guidance is preserved.','provenance_assessment':'Cluster, note, source review, manifest item, source, candidate source IDs, and report paths are present.','residual_risk_assessment':'Singleton evidence remains narrow; overclaiming risk persists if caveat is dropped.','author_input_readiness_assessment':'Safe only as later caveat-only draft-input construction material, not authoring approval.','required_caveats':['{REQUIRED_CAVEAT}'],'do_not_say':['Do not say Hermes is a runtime dependency of OpenClaw.','Do not say Hermes is the general operating environment for OpenClaw.','Do not say OpenClaw requires Hermes for web or phone access.','Do not generalize beyond migration/setup/import tooling contexts unless additional sources support it.','Do not use this packet as a factual claim without the caveat.','Do not use this packet for chapter prose before later author/red-team gates pass.'],'limitations':['singleton packet','not chapter-ready'],'residual_risk':'low to moderate if caveat-only; high if generalized','recommended_next_stage':'build_caveat_only_author_draft_input'{safety}}}\n"
            "print(json.dumps({'packet_redteam_reviews':[review]}))\n",
            encoding="utf-8",
        )
    mock.chmod(0o755)
    return mock


def test_selects_current_packet_and_writes_report_only_redteam(tmp_path):
    db = db_copy(tmp_path)
    mock = write_mock_bridge(tmp_path)
    before = counts(db)
    before_status = status_hashes(db)
    before_registry = sha(ROOT / "data" / "source_registry.json")
    before_raw = tree_snapshot(ROOT / "raw")
    before_book = tree_snapshot(ROOT / "docs" / "book")
    before_schema = sha(ROOT / "data" / "schema.sql")
    before_worker = sha(ROOT / "scripts" / "daily_book_worker.py")
    res = run_script("--run-id", "citation-pipeline-test-20260612", "--packet-report", str(RUN20), "--report-suffix", "run21", db_path=db, output_dir=tmp_path, env={"TEREFO_HIGH_REASONING_BRIDGE_COMMAND": str(mock)})
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
    assert report["selected_packet_count"] == 1
    assert report["reviewed_packet_count"] == 1
    assert report["excluded_packet_count"] == 0
    assert report["redteam_decision_counts"] == {"caveat_only_author_input_ready": 1}
    assert report["author_input_readiness_counts"] == {"ready_for_caveat_only_draft_input": 1}
    review = report["packet_redteam_reviews"][0]
    assert review["author_allowed"] is False
    assert review["eligible_for_authoring"] is False
    assert review["publication_approved"] is False
    assert review["chapter_update_allowed"] is False
    assert REQUIRED_CAVEAT in review["required_caveats"]


def test_excludes_unsafe_packet_inputs(tmp_path):
    for key in ["author_allowed", "publication_approved", "eligible_for_claim_insertion", "eligible_for_authoring", "eligible_for_publication", "chapter_update_allowed"]:
        case = tmp_path / key
        db = db_copy(case)
        def mutate(data, key=key):
            data["packet_candidates"][0][key] = True
        packet = packet_report_copy(case, mutate)
        mock = write_mock_bridge(case)
        res = run_script("--packet-report", str(packet), db_path=db, output_dir=case, env={"TEREFO_HIGH_REASONING_BRIDGE_COMMAND": str(mock)})
        assert res.returncode == 2, key
        assert "safety flag" in res.stderr


def test_missing_caveat_do_not_say_or_chapter_prose_fails_closed(tmp_path):
    cases = [
        ("caveat", lambda d: d["packet_candidates"][0].__setitem__("required_caveats", []), "required caveat"),
        ("donotsay", lambda d: d["packet_candidates"][0].__setitem__("do_not_say", []), "do_not_say"),
        ("prose", lambda d: d["packet_candidates"][0].__setitem__("chapter_prose", "Forbidden prose"), "chapter-ready prose"),
    ]
    for name, mut, expected in cases:
        case = tmp_path / name
        db = db_copy(case)
        packet = packet_report_copy(case, mut)
        mock = write_mock_bridge(case)
        res = run_script("--packet-report", str(packet), db_path=db, output_dir=case, env={"TEREFO_HIGH_REASONING_BRIDGE_COMMAND": str(mock)})
        assert res.returncode == 2
        assert expected in res.stderr


def test_invalid_llm_json_invalid_enum_and_missing_flags_fail_closed(tmp_path):
    for case_name, kwargs, expected in [
        ("badjson", {"invalid_json": True}, "invalid_json"),
        ("badenum", {"invalid_enum": True}, "schema_mismatch"),
        ("missingflags", {"missing_flags": True}, "schema_mismatch"),
        ("authorapproved", {"approve_author": True}, "schema_mismatch"),
        ("eligibleauthoring", {"eligible_authoring": True}, "schema_mismatch"),
    ]:
        case = tmp_path / case_name
        db = db_copy(case)
        mock = write_mock_bridge(case, **kwargs)
        before = counts(db)
        res = run_script("--packet-report", str(RUN20), db_path=db, output_dir=case, env={"TEREFO_HIGH_REASONING_BRIDGE_COMMAND": str(mock)})
        assert res.returncode == 2, res.stdout + res.stderr
        assert expected in res.stderr
        assert counts(db) == before


def test_weak_local_fallback_and_missing_profile_fail_closed(tmp_path):
    db = db_copy(tmp_path / "weak")
    mock = write_mock_bridge(tmp_path / "weak")
    res = run_script("--packet-report", str(RUN20), "--provider", "local", db_path=db, output_dir=tmp_path / "weak", env={"TEREFO_HIGH_REASONING_BRIDGE_COMMAND": str(mock)})
    assert res.returncode == 2
    assert "weak_or_unapproved_provider_refused" in res.stderr

    db = db_copy(tmp_path / "profile")
    res = run_script("--packet-report", str(RUN20), "--reasoning-profile", "missing_profile", db_path=db, output_dir=tmp_path / "profile", env={"TEREFO_HIGH_REASONING_BRIDGE_COMMAND": str(mock)})
    assert res.returncode == 2
    assert "model_profile_error" in res.stderr


def test_missing_or_malformed_packet_report_fails_closed(tmp_path):
    db = db_copy(tmp_path / "missing")
    mock = write_mock_bridge(tmp_path / "missing")
    res = run_script("--packet-report", str(tmp_path / "nope.json"), db_path=db, output_dir=tmp_path / "missing", env={"TEREFO_HIGH_REASONING_BRIDGE_COMMAND": str(mock)})
    assert res.returncode == 2
    assert "missing input" in res.stderr

    db = db_copy(tmp_path / "bad")
    bad = tmp_path / "bad" / "bad.json"
    bad.write_text("{bad")
    res = run_script("--packet-report", str(bad), db_path=db, output_dir=tmp_path / "bad", env={"TEREFO_HIGH_REASONING_BRIDGE_COMMAND": str(mock)})
    assert res.returncode == 2
    assert "invalid JSON" in res.stderr
