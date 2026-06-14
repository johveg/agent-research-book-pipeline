import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "llm_cluster_quality_gate.py"
RUN18 = ROOT / "reports" / "editorial" / "citation-pipeline-test-20260612-research-object-clusters-run18.json"
CLUSTER_ID = "cluster_4e8554045cfaf827bc68bcc5"
EXCLUDED_REVIEW_ID = "source_review_12c73455aa1816e5df8c"


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
    path = output_dir / "citation-pipeline-test-20260612-cluster-quality-gate-run19.json"
    assert path.exists(), f"missing report {path}"
    return json.loads(path.read_text())


def cluster_report_copy(tmp_path: Path, mutator=None) -> Path:
    data = json.loads(RUN18.read_text())
    if mutator:
        mutator(data)
    path = tmp_path / "clusters.json"
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    return path


def write_mock_bridge(tmp_path: Path, *, invalid_json=False, invalid_enum=False, missing_flags=False, normal_packet=False):
    mock = tmp_path / "mock_bridge.py"
    if invalid_json:
        mock.write_text("#!/usr/bin/env python3\nprint('not-json')\n", encoding="utf-8")
    else:
        quality = "bad_enum" if invalid_enum else ("packet_candidate_ready" if normal_packet else "caveat_only_packet_candidate_ready")
        readiness = "ready_for_context_packet" if normal_packet else "ready_for_caveat_only_packet"
        disposition = "eligible_for_packet_candidate"
        safety = "" if missing_flags else ", 'advisory_only': True, 'author_allowed': False, 'publication_approved': False, 'eligible_for_claim_insertion': False, 'eligible_for_authoring': False, 'eligible_for_publication': False"
        mock.write_text(
            "#!/usr/bin/env python3\n"
            "import json,sys\n"
            "payload=json.load(sys.stdin)\n"
            f"review={{'cluster_id':'{CLUSTER_ID}','cluster_type':'caveat_only_support_cluster','cluster_use':'caveat_only','singleton_cluster':True,'quality_gate_decision':'{quality}','packet_readiness':'{readiness}','closed_loop_disposition':'{disposition}','traceability_assessment':'source, note, manifest, source-review, candidate-source, and provenance paths are present','evidence_strength_assessment':'partially supported and partially corroborated; singleton evidence is narrow','caveat_integrity_assessment':'caveat is preserved and not converted into a confident claim','packet_readiness_assessment':'ready only for later caveat-only packet candidate work','safety_assessment':'no authoring, publication, claim insertion, raw capture, or unresolved contradiction approval','required_caveats':['Keep Hermes mention limited to OpenClaw migration/setup tooling context.'],'limitations':['singleton caveat-only cluster','does not prove runtime dependency'],'residual_risk':'moderate if generalized beyond caveat','do_not_say':['Hermes is a runtime dependency','publication approved'],'recommended_next_stage':'build_caveat_only_packet_candidate'{safety}}}\n"
            "print(json.dumps({'cluster_reviews':[review]}))\n",
            encoding="utf-8",
        )
    mock.chmod(0o755)
    return mock


def test_selects_current_cluster_and_writes_report_only_quality_gate(tmp_path):
    db = db_copy(tmp_path)
    mock = write_mock_bridge(tmp_path)
    before = counts(db)
    before_status = status_hashes(db)
    before_registry = sha(ROOT / "data" / "source_registry.json")
    before_raw = tree_snapshot(ROOT / "raw")
    before_book = tree_snapshot(ROOT / "docs" / "book")
    before_schema = sha(ROOT / "data" / "schema.sql")
    before_worker = sha(ROOT / "scripts" / "daily_book_worker.py")

    res = run_script(
        "--run-id", "citation-pipeline-test-20260612",
        "--cluster-report", str(RUN18),
        "--report-suffix", "run19",
        db_path=db,
        output_dir=tmp_path,
        env={"TEREFO_HIGH_REASONING_BRIDGE_COMMAND": str(mock)},
    )

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
    assert report["selected_cluster_count"] == 1
    assert report["reviewed_cluster_count"] == 1
    assert report["excluded_cluster_count"] == 1
    assert report["quality_gate_decision_counts"] == {"caveat_only_packet_candidate_ready": 1}
    assert report["packet_readiness_counts"] == {"ready_for_caveat_only_packet": 1}
    assert report["closed_loop_disposition_counts"] == {"eligible_for_packet_candidate": 1}
    assert report["recommended_next_stage_counts"] == {"build_caveat_only_packet_candidate": 1}
    review = report["cluster_reviews"][0]
    assert review["cluster_id"] == CLUSTER_ID
    assert review["advisory_only"] is True
    assert review["author_allowed"] is False
    assert review["publication_approved"] is False
    assert review["eligible_for_claim_insertion"] is False
    assert review["eligible_for_authoring"] is False
    assert review["eligible_for_publication"] is False
    assert report["changed_db"] is False
    assert report["changed_source_notes"] is False
    assert report["claims_inserted"] == 0
    assert report["editorial_reviews_inserted"] == 0


def test_excludes_source_context_unclear_item(tmp_path):
    db = db_copy(tmp_path)
    mock = write_mock_bridge(tmp_path)
    res = run_script("--cluster-report", str(RUN18), db_path=db, output_dir=tmp_path, env={"TEREFO_HIGH_REASONING_BRIDGE_COMMAND": str(mock)})
    assert res.returncode == 0, res.stderr + res.stdout
    report = read_report(tmp_path)
    excluded = [i for i in report["excluded_clusters"] if i.get("source_review_id") == EXCLUDED_REVIEW_ID]
    assert excluded
    assert excluded[0]["exclusion_decision"] == "source_context_unclear"
    assert "human review required" not in json.dumps(excluded).lower()


def test_invalid_llm_json_and_invalid_enum_fail_closed(tmp_path):
    for case, kwargs, expected in [
        ("badjson", {"invalid_json": True}, "invalid_json"),
        ("badenum", {"invalid_enum": True}, "schema_mismatch"),
    ]:
        case_dir = tmp_path / case
        db = db_copy(case_dir)
        mock = write_mock_bridge(case_dir, **kwargs)
        before = counts(db)
        res = run_script("--cluster-report", str(RUN18), db_path=db, output_dir=case_dir, env={"TEREFO_HIGH_REASONING_BRIDGE_COMMAND": str(mock)})
        assert res.returncode == 2, res.stdout + res.stderr
        assert expected in res.stderr
        assert counts(db) == before


def test_missing_safety_flags_and_forbidden_cluster_flags_fail_closed(tmp_path):
    db = db_copy(tmp_path / "missing")
    mock = write_mock_bridge(tmp_path / "missing", missing_flags=True)
    res = run_script("--cluster-report", str(RUN18), db_path=db, output_dir=tmp_path / "missing", env={"TEREFO_HIGH_REASONING_BRIDGE_COMMAND": str(mock)})
    assert res.returncode == 2
    assert "schema_mismatch" in res.stderr

    for key in ["author_allowed", "publication_approved", "eligible_for_claim_insertion", "eligible_for_authoring", "eligible_for_publication"]:
        case_dir = tmp_path / key
        db = db_copy(case_dir)
        def mutate(data, key=key):
            data["cluster_candidates"][0][key] = True
        cluster_path = cluster_report_copy(case_dir, mutate)
        mock = write_mock_bridge(case_dir)
        before = counts(db)
        res = run_script("--cluster-report", str(cluster_path), db_path=db, output_dir=case_dir, env={"TEREFO_HIGH_REASONING_BRIDGE_COMMAND": str(mock)})
        assert res.returncode == 2, key
        assert "safety flag" in res.stderr
        assert counts(db) == before


def test_caveat_only_cluster_cannot_become_normal_packet_or_approved(tmp_path):
    db = db_copy(tmp_path)
    mock = write_mock_bridge(tmp_path, normal_packet=True)
    res = run_script("--cluster-report", str(RUN18), db_path=db, output_dir=tmp_path, env={"TEREFO_HIGH_REASONING_BRIDGE_COMMAND": str(mock)})
    assert res.returncode == 2
    assert "schema_mismatch" in res.stderr


def test_weak_local_fallback_and_missing_profile_fail_closed(tmp_path):
    db = db_copy(tmp_path / "weak")
    mock = write_mock_bridge(tmp_path / "weak")
    res = run_script("--cluster-report", str(RUN18), "--provider", "local", db_path=db, output_dir=tmp_path / "weak", env={"TEREFO_HIGH_REASONING_BRIDGE_COMMAND": str(mock)})
    assert res.returncode == 2
    assert "weak_or_unapproved_provider_refused" in res.stderr

    db = db_copy(tmp_path / "profile")
    res = run_script("--cluster-report", str(RUN18), "--reasoning-profile", "missing_profile", db_path=db, output_dir=tmp_path / "profile", env={"TEREFO_HIGH_REASONING_BRIDGE_COMMAND": str(mock)})
    assert res.returncode == 2
    assert "model_profile_error" in res.stderr


def test_missing_or_malformed_cluster_report_fails_closed(tmp_path):
    db = db_copy(tmp_path / "missing")
    mock = write_mock_bridge(tmp_path / "missing")
    res = run_script("--cluster-report", str(tmp_path / "nope.json"), db_path=db, output_dir=tmp_path / "missing", env={"TEREFO_HIGH_REASONING_BRIDGE_COMMAND": str(mock)})
    assert res.returncode == 2
    assert "missing input" in res.stderr

    db = db_copy(tmp_path / "bad")
    bad = tmp_path / "bad" / "bad.json"
    bad.write_text("{bad")
    res = run_script("--cluster-report", str(bad), db_path=db, output_dir=tmp_path / "bad", env={"TEREFO_HIGH_REASONING_BRIDGE_COMMAND": str(mock)})
    assert res.returncode == 2
    assert "invalid JSON" in res.stderr
