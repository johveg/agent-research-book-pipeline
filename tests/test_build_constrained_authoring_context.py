import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build_constrained_authoring_context.py"
RUN33 = ROOT / "reports" / "editorial" / "citation-pipeline-test-20260612-promotion-contract-authoring-metadata-run33.json"
RUN34 = ROOT / "reports" / "editorial" / "citation-pipeline-test-20260612-transition-engine-evaluation-run34.json"


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
            "source_notes": "SELECT id, source_id, note_type, created_at FROM source_notes ORDER BY id",
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
    path = output_dir / "citation-pipeline-test-20260612-constrained-authoring-context-run42.json"
    assert path.exists(), f"missing report {path}"
    return json.loads(path.read_text())


def base_args(contract=RUN33, transition=RUN34):
    return ["--promotion-contract-report", str(contract), "--transition-report", str(transition), "--report-suffix", "run42"]


def test_selects_ready_promotion_contract_and_writes_context_metadata_only(tmp_path):
    db = db_copy(tmp_path)
    before_counts = counts(db)
    before_status = status_hashes(db)
    before_registry = sha(ROOT / "data" / "source_registry.json")
    before_raw = tree_snapshot(ROOT / "raw")
    before_book = tree_snapshot(ROOT / "docs" / "book")
    before_entities = tree_snapshot(ROOT / "docs" / "entities")
    before_claims_md = sha(ROOT / "docs" / "research" / "claims.md")
    before_schema = sha(ROOT / "data" / "schema.sql")
    before_worker = sha(ROOT / "scripts" / "daily_book_worker.py")

    res = run_script(*base_args(), db_path=db, output_dir=tmp_path)
    assert res.returncode == 0, res.stderr + res.stdout
    assert counts(db) == before_counts
    assert status_hashes(db) == before_status
    assert sha(ROOT / "data" / "source_registry.json") == before_registry
    assert tree_snapshot(ROOT / "raw") == before_raw
    assert tree_snapshot(ROOT / "docs" / "book") == before_book
    assert tree_snapshot(ROOT / "docs" / "entities") == before_entities
    assert sha(ROOT / "docs" / "research" / "claims.md") == before_claims_md
    assert sha(ROOT / "data" / "schema.sql") == before_schema
    assert sha(ROOT / "scripts" / "daily_book_worker.py") == before_worker

    report = read_report(tmp_path)
    assert report["llm_used"] is False
    assert report["reasoning_status"] == "deterministic_context_packaging_only"
    assert report["context_candidate_count"] == 1
    candidate = report["constrained_authoring_context_candidates"][0]
    assert candidate["context_type"] == "constrained_authoring_context_candidate"
    assert candidate["context_decision"] == "context_candidate_created"
    assert candidate["context_use"] == "caveat_only_authoring_context"
    assert candidate["source_state"] == "authoring_metadata_promotion_contract_ready"
    assert candidate["target_state"] == "constrained_authoring_context_candidate"
    assert candidate["required_caveats"]
    assert candidate["do_not_say"]
    assert candidate["evidence_context_atoms"]
    assert candidate["author_allowed"] is False
    assert candidate["publication_approved"] is False
    assert candidate["eligible_for_authoring"] is False
    assert candidate["chapter_update_allowed"] is False
    forbidden_keys = {"draft_prose", "chapter_prose", "chapter_ready_prose", "publishable_wording", "final_prose", "book_text"}
    assert not (forbidden_keys & set(candidate.keys()))


def test_unsafe_flags_missing_guardrails_and_bad_transition_fail_closed_or_exclude(tmp_path):
    cases = [
        ("unsafe_author", RUN33, lambda d: d["promotion_contract_candidates"][0].__setitem__("author_allowed", True), "safety flag"),
        ("missing_caveat", RUN33, lambda d: d["selected_metadata_preflights"][0].__setitem__("required_caveats", []), "required_caveats"),
        ("missing_dns", RUN33, lambda d: d["selected_metadata_preflights"][0].__setitem__("do_not_say", []), "do_not_say"),
        ("missing_provenance", RUN33, lambda d: d["selected_metadata_preflights"][0].__setitem__("provenance_paths", []), "provenance"),
        ("bad_transition", RUN34, lambda d: d.__setitem__("transition_decision", "transition_blocked"), "transition"),
    ]
    for name, src, mutator, expected in cases:
        case = tmp_path / name
        db = db_copy(case)
        contract, transition = RUN33, RUN34
        if src == RUN33:
            contract = report_copy(case, RUN33, "run33.json", mutator)
        else:
            transition = report_copy(case, RUN34, "run34.json", mutator)
        before = counts(db)
        res = run_script(*base_args(contract, transition), db_path=db, output_dir=case)
        assert res.returncode == 2, name
        assert expected.lower() in res.stderr.lower()
        assert counts(db) == before


def test_non_context_recommendation_is_excluded_without_authoring_approval(tmp_path):
    def mutate(data):
        cand = data["promotion_contract_candidates"][0]
        cand["recommended_next_stage"] = "keep_safe_reports_only"
        cand["automated_disposition"] = "safe_reports_only"

    case = tmp_path / "exclude"
    db = db_copy(case)
    contract = report_copy(case, RUN33, "run33.json", mutate)
    res = run_script(*base_args(contract, RUN34), db_path=db, output_dir=case)
    assert res.returncode == 0, res.stderr + res.stdout
    report = read_report(case)
    assert report["selected_contract_count"] == 0
    assert report["context_candidate_count"] == 0
    assert report["excluded_contract_count"] == 1
    assert report["safety_flags"]["author_allowed"] is False
    assert report["safety_flags"]["publication_approved"] is False
