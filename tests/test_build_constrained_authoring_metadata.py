import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build_constrained_authoring_metadata.py"
RUN29 = ROOT / "reports" / "editorial" / "citation-pipeline-test-20260612-author-draft-canary-v2-redteam-run29.json"
RUN28 = ROOT / "reports" / "editorial" / "citation-pipeline-test-20260612-author-draft-canary-v2-run28.json"
RUN26 = ROOT / "reports" / "editorial" / "citation-pipeline-test-20260612-author-draft-input-rebuild-run26.json"
CANARY_ID = "draft_canary_run28_caveat_only_v2_cluster_4e8554045cfaf827bc68bcc5"
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


def run_script(*args, db_path: Path, output_dir: Path):
    env = os.environ.copy()
    env["TEREFO_BOOK_DB_PATH"] = str(db_path)
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--output-dir", str(output_dir), *args],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=180,
    )


def report_copy(tmp_path: Path, src: Path, name: str, mutator=None) -> Path:
    data = json.loads(src.read_text())
    if mutator:
        mutator(data)
    path = tmp_path / name
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    return path


def read_report(output_dir: Path) -> dict:
    path = output_dir / "citation-pipeline-test-20260612-constrained-authoring-metadata-run30.json"
    assert path.exists(), f"missing report {path}"
    return json.loads(path.read_text())


def base_args(run29=RUN29, run28=RUN28, run26=RUN26):
    return ["--redteam-report", str(run29), "--canary-v2-report", str(run28), "--rebuild-report", str(run26), "--report-suffix", "run30"]


def test_selects_run29_passed_canary_and_writes_report_only_metadata(tmp_path):
    db = db_copy(tmp_path)
    before = counts(db)
    before_status = status_hashes(db)
    before_registry = sha(ROOT / "data" / "source_registry.json")
    before_raw = tree_snapshot(ROOT / "raw")
    before_book = tree_snapshot(ROOT / "docs" / "book")
    before_schema = sha(ROOT / "data" / "schema.sql")
    before_worker = sha(ROOT / "scripts" / "daily_book_worker.py")

    res = run_script(*base_args(), db_path=db, output_dir=tmp_path)
    assert res.returncode == 0, res.stderr + res.stdout
    assert counts(db) == before
    assert status_hashes(db) == before_status
    assert sha(ROOT / "data" / "source_registry.json") == before_registry
    assert tree_snapshot(ROOT / "raw") == before_raw
    assert tree_snapshot(ROOT / "docs" / "book") == before_book
    assert sha(ROOT / "data" / "schema.sql") == before_schema
    assert sha(ROOT / "scripts" / "daily_book_worker.py") == before_worker

    report = read_report(tmp_path)
    assert report["llm_used"] is False
    assert report["provider"] is None and report["model"] is None and report["bridge"] is None and report["model_profile"] is None
    assert report["selected_redteam_count"] == 1
    assert report["metadata_candidate_count"] == 1
    assert report["excluded_redteam_count"] == 0
    assert report["metadata_type_counts"] == {"constrained_authoring_metadata_candidate": 1}
    assert report["metadata_decision_counts"] == {"metadata_candidate_created": 1}
    assert report["metadata_use_counts"] == {"caveat_only": 1}
    assert report["canary_usefulness_counts"] == {"improved_but_still_thin": 1}
    assert report["target_chapter_status_counts"] == {"suggested_only": 1}
    meta = report["constrained_authoring_metadata_candidates"][0]
    assert meta["draft_canary_id"] == CANARY_ID
    assert meta["rebuilt_input_id"] == REBUILT_ID
    assert "improved_but_still_thin" in meta["thinness_warning"]
    assert meta["unsupported_inferences"]
    assert meta["promotion_blockers"]
    assert meta["canary_text_quoted"].startswith("REPORT-ONLY CANARY TEXT")
    assert meta["author_allowed"] is False
    assert meta["eligible_for_authoring"] is False
    assert meta["chapter_update_allowed"] is False
    forbidden_keys = {"draft_prose", "new_draft_prose", "chapter_ready_prose", "chapter_prose", "publishable_wording", "citation_resolved_chapter_text"}
    assert not (forbidden_keys & set(meta.keys()))


def test_invalid_upstream_shapes_flags_caveat_dns_and_provenance_fail_closed(tmp_path):
    cases = []
    cases.append(("bad_mode", RUN29, lambda d: d.__setitem__("mode", "bad"), "mode"))
    cases.append(("bad_enum", RUN29, lambda d: d["draft_canary_v2_redteam_reviews"][0].__setitem__("redteam_decision", "bad_enum"), "redteam_decision"))
    for key in ["author_allowed", "publication_approved", "eligible_for_claim_insertion", "eligible_for_authoring", "eligible_for_publication", "chapter_update_allowed"]:
        cases.append((key, RUN29, lambda d, key=key: d["draft_canary_v2_redteam_reviews"][0].__setitem__(key, True), "safety flag"))
    cases += [
        ("missing_caveat", RUN29, lambda d: d["draft_canary_v2_redteam_reviews"][0].__setitem__("required_caveats", []), "required caveat"),
        ("missing_dns", RUN29, lambda d: d["draft_canary_v2_redteam_reviews"][0].__setitem__("do_not_say", []), "do_not_say"),
        ("bad_next", RUN29, lambda d: d["draft_canary_v2_redteam_reviews"][0].__setitem__("recommended_next_stage", "publish_to_docs_book"), "recommended_next_stage"),
        ("missing_provenance", RUN28, lambda d: d["draft_canaries"][0].__setitem__("provenance_paths", []), "provenance"),
        ("run28_author", RUN28, lambda d: d["draft_canaries"][0].__setitem__("author_allowed", True), "safety flag"),
        ("run26_missing_atoms", RUN26, lambda d: d["rebuilt_author_draft_inputs"][0].__setitem__("evidence_bound_factual_atoms", []), "evidence_bound_factual_atoms"),
        ("run26_missing_forbidden", RUN26, lambda d: d["rebuilt_author_draft_inputs"][0].__setitem__("forbidden_author_scope", []), "forbidden_author_scope"),
    ]
    for name, src, mut, expected in cases:
        case = tmp_path / name
        db = db_copy(case)
        run29, run28, run26 = RUN29, RUN28, RUN26
        if src == RUN29:
            run29 = report_copy(case, RUN29, "run29.json", mut)
        elif src == RUN28:
            run28 = report_copy(case, RUN28, "run28.json", mut)
        else:
            run26 = report_copy(case, RUN26, "run26.json", mut)
        before = counts(db)
        res = run_script(*base_args(run29, run28, run26), db_path=db, output_dir=case)
        assert res.returncode == 2, name
        assert expected.lower() in res.stderr.lower()
        assert counts(db) == before


def test_non_metadata_recommendations_are_excluded_or_fail_closed(tmp_path):
    def mutate_safe_reports(data):
        r = data["draft_canary_v2_redteam_reviews"][0]
        r["redteam_decision"] = "safe_reports_only"
        r["closed_loop_disposition"] = "safe_reports_only"
        r["recommended_next_stage"] = "keep_safe_reports_only"

    case = tmp_path / "exclude"
    db = db_copy(case)
    run29 = report_copy(case, RUN29, "run29.json", mutate_safe_reports)
    res = run_script(*base_args(run29, RUN28, RUN26), db_path=db, output_dir=case)
    assert res.returncode == 0, res.stderr + res.stdout
    report = read_report(case)
    assert report["selected_redteam_count"] == 0
    assert report["metadata_candidate_count"] == 0
    assert report["excluded_redteam_count"] == 1
    assert report["metadata_decision_counts"] == {}


def test_invalid_json_missing_inputs_and_no_llm_fallback(tmp_path):
    db = db_copy(tmp_path / "badjson")
    bad = tmp_path / "bad.json"
    bad.write_text("{bad", encoding="utf-8")
    res = run_script(*base_args(bad, RUN28, RUN26), db_path=db, output_dir=tmp_path / "badjson")
    assert res.returncode == 2
    assert "invalid JSON" in res.stderr

    db = db_copy(tmp_path / "missing")
    res = run_script(*base_args(tmp_path / "missing.json", RUN28, RUN26), db_path=db, output_dir=tmp_path / "missing")
    assert res.returncode == 2
    assert "missing" in res.stderr

    db = db_copy(tmp_path / "normal")
    res = run_script(*base_args(), db_path=db, output_dir=tmp_path / "normal")
    assert res.returncode == 0, res.stderr + res.stdout
    report = read_report(tmp_path / "normal")
    assert report["llm_used"] is False
    assert report["weak_local_fallback_refused"] is True
    assert counts(db) == {"source_notes": 365, "claims": 181, "editorial_reviews": 10}
