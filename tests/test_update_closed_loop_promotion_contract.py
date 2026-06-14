import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "update_closed_loop_promotion_contract.py"
RUN31 = ROOT / "reports" / "editorial" / "citation-pipeline-test-20260612-constrained-authoring-metadata-preflight-run31.json"
RUN30 = ROOT / "reports" / "editorial" / "citation-pipeline-test-20260612-constrained-authoring-metadata-run30.json"
CONFIG = ROOT / "config" / "closed_loop_state_machine.json"
DB = ROOT / ".var" / "book.sqlite"
METADATA_ID = "metadata_run30_constrained_authoring_4e8554045cfaf827bc68bcc5"
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
    shutil.copy2(DB, dst)
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


def report_copy(tmp_path: Path, src: Path, name: str, mutator=None) -> Path:
    data = json.loads(src.read_text())
    if mutator:
        mutator(data)
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / name
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    return path


def config_copy(tmp_path: Path, mutator=None) -> Path:
    return report_copy(tmp_path, CONFIG, "closed_loop_state_machine.json", mutator)


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


def base_args(run31=RUN31, run30=RUN30, config=CONFIG):
    return [
        "--preflight-report", str(run31),
        "--metadata-report", str(run30),
        "--state-machine-config", str(config),
        "--report-suffix", "run32",
    ]


def read_report(output_dir: Path) -> dict:
    path = output_dir / "citation-pipeline-test-20260612-promotion-contract-authoring-metadata-run32.json"
    assert path.exists(), f"missing report {path}"
    return json.loads(path.read_text())


def test_selects_run31_preflight_and_creates_report_only_contract_candidate(tmp_path):
    db = db_copy(tmp_path)
    before_counts = counts(db)
    before_status = status_hashes(db)
    before_config = sha(CONFIG)
    before_registry = sha(ROOT / "data" / "source_registry.json")
    before_raw = tree_snapshot(ROOT / "raw")
    before_book = tree_snapshot(ROOT / "docs" / "book")
    before_schema = sha(ROOT / "data" / "schema.sql")
    before_worker = sha(ROOT / "scripts" / "daily_book_worker.py")

    res = run_script(*base_args(), db_path=db, output_dir=tmp_path)
    assert res.returncode == 0, res.stderr + res.stdout
    assert counts(db) == before_counts
    assert status_hashes(db) == before_status
    assert sha(CONFIG) == before_config
    assert sha(ROOT / "data" / "source_registry.json") == before_registry
    assert tree_snapshot(ROOT / "raw") == before_raw
    assert tree_snapshot(ROOT / "docs" / "book") == before_book
    assert sha(ROOT / "data" / "schema.sql") == before_schema
    assert sha(ROOT / "scripts" / "daily_book_worker.py") == before_worker

    report = read_report(tmp_path)
    assert report["report_only"] is True
    assert report["llm_used"] is False
    assert report["provider"] is None and report["model"] is None and report["bridge"] is None and report["model_profile"] is None
    assert report["selected_metadata_preflight_count"] == 1
    assert report["promotion_contract_candidate_count"] == 1
    assert report["excluded_metadata_preflight_count"] == 0
    assert report["config_updated"] is False
    assert report["human_in_loop_dependency_added"] is False
    assert report["promotion_contract_decision_counts"] in [
        {"config_update_needed": 1},
        {"promotion_contract_already_satisfied": 1},
    ]
    assert set(report["transition_decision_counts"]).issubset({"allowed_for_future_promotion_contract_update", "already_represented_in_contract"})
    assert report["recommended_next_stage_counts"]
    candidate = report["promotion_contract_candidates"][0]
    assert candidate["metadata_id"] == METADATA_ID
    assert candidate["current_state"] == "constrained_authoring_metadata_preflight_passed"
    assert candidate["proposed_next_state"] == "authoring_metadata_promotion_contract_ready"
    assert candidate["human_in_loop_dependency_added"] is False
    assert candidate["automated_disposition"] == "caveat_only"
    assert candidate["author_allowed"] is False
    assert candidate["eligible_for_authoring"] is False
    assert candidate["chapter_update_allowed"] is False
    assert report["changed_db"] is False
    assert report["changed_docs_book"] is False
    assert report["changed_daily_worker"] is False


def test_invalid_upstream_shape_enums_flags_and_required_metadata_fail_closed(tmp_path):
    cases = []
    cases.append(("bad_mode", RUN31, lambda d: d.__setitem__("mode", "bad"), "mode"))
    cases.append(("bad_preflight_enum", RUN31, lambda d: d["constrained_authoring_metadata_preflight_reviews"][0].__setitem__("preflight_decision", "bad_enum"), "preflight_decision"))
    cases.append(("bad_next_stage", RUN31, lambda d: d["constrained_authoring_metadata_preflight_reviews"][0].__setitem__("recommended_next_stage", "publish_chapter"), "recommended_next_stage"))
    for key in ["author_allowed", "publication_approved", "eligible_for_claim_insertion", "eligible_for_authoring", "eligible_for_publication", "chapter_update_allowed"]:
        cases.append((key, RUN31, lambda d, key=key: d["constrained_authoring_metadata_preflight_reviews"][0].__setitem__(key, True), "safety flag"))
    cases += [
        ("missing_caveat", RUN31, lambda d: d["constrained_authoring_metadata_preflight_reviews"][0].__setitem__("required_caveats", []), "required caveat"),
        ("missing_dns", RUN31, lambda d: d["constrained_authoring_metadata_preflight_reviews"][0].__setitem__("do_not_say", []), "do_not_say"),
        ("missing_unsupported", RUN31, lambda d: d["constrained_authoring_metadata_preflight_reviews"][0].__setitem__("unsupported_inferences", []), "unsupported_inferences"),
        ("missing_blockers", RUN31, lambda d: d["constrained_authoring_metadata_preflight_reviews"][0].__setitem__("promotion_blockers", []), "promotion_blockers"),
        ("missing_provenance", RUN30, lambda d: d["constrained_authoring_metadata_candidates"][0].__setitem__("provenance_paths", []), "provenance"),
    ]
    for name, src, mut, expected in cases:
        case = tmp_path / name
        db = db_copy(case)
        run31, run30 = RUN31, RUN30
        if src == RUN31:
            run31 = report_copy(case, RUN31, "run31.json", mut)
        else:
            run30 = report_copy(case, RUN30, "run30.json", mut)
        before = counts(db)
        res = run_script(*base_args(run31, run30, CONFIG), db_path=db, output_dir=case)
        assert res.returncode == 2, name
        assert expected.lower() in res.stderr.lower()
        assert counts(db) == before


def test_non_promotion_routes_are_excluded_not_human_review(tmp_path):
    def mutate_safe_reports(data):
        r = data["constrained_authoring_metadata_preflight_reviews"][0]
        r["preflight_decision"] = "safe_reports_only"
        r["metadata_readiness"] = "not_ready_safe_reports_only"
        r["closed_loop_disposition"] = "safe_reports_only"
        r["recommended_next_stage"] = "keep_safe_reports_only"

    case = tmp_path / "safe_reports_only"
    db = db_copy(case)
    run31 = report_copy(case, RUN31, "run31.json", mutate_safe_reports)
    res = run_script(*base_args(run31, RUN30, CONFIG), db_path=db, output_dir=case)
    assert res.returncode == 0, res.stderr + res.stdout
    report = read_report(case)
    assert report["selected_metadata_preflight_count"] == 0
    assert report["promotion_contract_candidate_count"] == 0
    assert report["excluded_metadata_preflight_count"] == 1
    assert report["excluded_metadata_preflights"][0]["automated_disposition"] == "safe_reports_only"
    blob = json.dumps(report).lower()
    assert "human_review_required" not in blob
    assert report["human_in_loop_dependency_added"] is False


def test_config_validation_and_optional_write_config_are_idempotent_and_safe(tmp_path):
    def strip_authoring_metadata_contract(config):
        remove_states = {
            "constrained_authoring_metadata_candidate",
            "constrained_authoring_metadata_preflight_passed",
            "authoring_metadata_promotion_contract_ready",
            "constrained_authoring_context_candidate",
        }
        config["states"] = [s for s in config["states"] if s not in remove_states]
        remove_dispositions = {
            "metadata_preflight_passed",
            "ready_for_promotion_contract_update",
            "update_closed_loop_promotion_contract_for_authoring_metadata",
            "needs_better_authoring_metadata",
        }
        config["automated_dispositions"] = [d for d in config["automated_dispositions"] if d not in remove_dispositions]
        remove_pairs = {
            ("constrained_authoring_metadata_candidate", "constrained_authoring_metadata_preflight_passed"),
            ("constrained_authoring_metadata_preflight_passed", "authoring_metadata_promotion_contract_ready"),
            ("authoring_metadata_promotion_contract_ready", "constrained_authoring_context_candidate"),
        }
        config["transitions"] = [t for t in config["transitions"] if (t.get("from_state"), t.get("to_state")) not in remove_pairs]

    cfg = config_copy(tmp_path, strip_authoring_metadata_contract)
    db = db_copy(tmp_path)
    before_cfg = sha(cfg)
    res = run_script(*base_args(RUN31, RUN30, cfg), db_path=db, output_dir=tmp_path)
    assert res.returncode == 0, res.stderr + res.stdout
    report = read_report(tmp_path)
    assert report["config_update_needed"] is True
    assert report["config_updated"] is False
    assert sha(cfg) == before_cfg
    assert report["state_count_before"] == report["state_count_after"]
    assert report["transition_count_before"] == report["transition_count_after"]
    assert report["disposition_count_before"] == report["disposition_count_after"]
    assert "human_review_required" not in json.dumps(report).lower()

    out2 = tmp_path / "write1"
    res = run_script(*base_args(RUN31, RUN30, cfg), "--write-config", db_path=db, output_dir=out2)
    assert res.returncode == 0, res.stderr + res.stdout
    written_once = json.loads(cfg.read_text())
    assert len(written_once["states"]) == len(set(written_once["states"]))
    assert len(written_once["automated_dispositions"]) == len(set(written_once["automated_dispositions"]))
    pairs = [(t["from_state"], t["to_state"]) for t in written_once["transitions"]]
    assert len(pairs) == len(set(pairs))
    assert "human_review_required" not in json.dumps(written_once).lower()
    assert written_once["hard_invariants"]["author_allowed_until_explicit_authoring_gate"] is False
    assert written_once["hard_invariants"]["chapter_update_allowed_until_chapter_update_integration_gate"] is False

    hash_after_first = sha(cfg)
    out3 = tmp_path / "write2"
    res = run_script(*base_args(RUN31, RUN30, cfg), "--write-config", db_path=db, output_dir=out3)
    assert res.returncode == 0, res.stderr + res.stdout
    assert sha(cfg) == hash_after_first
    second_report = read_report(out3)
    assert second_report["config_update_needed"] is False
    assert second_report["config_updated"] is False


def test_missing_config_or_human_loop_dependency_fails_closed(tmp_path):
    db = db_copy(tmp_path / "missing")
    res = run_script(*base_args(RUN31, RUN30, tmp_path / "missing.json"), db_path=db, output_dir=tmp_path / "missing")
    assert res.returncode == 2
    assert "missing" in res.stderr.lower()

    def add_human_dependency(config):
        config["states"].append("human_review_required")
        config["transitions"].append({
            "from_state": "constrained_authoring_metadata_preflight_passed",
            "to_state": "human_review_required",
            "transition_type": "production_dependency",
            "guards": [{"name": "requires_human_review", "field": "requires_human_review", "equals": True}],
        })

    case = tmp_path / "human"
    cfg = config_copy(case, add_human_dependency)
    db = db_copy(case)
    res = run_script(*base_args(RUN31, RUN30, cfg), db_path=db, output_dir=case)
    assert res.returncode == 2
    assert "human" in res.stderr.lower()
