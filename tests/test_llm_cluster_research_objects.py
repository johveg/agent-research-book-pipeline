import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "llm_cluster_research_objects.py"
RUN17 = ROOT / "reports" / "editorial" / "citation-pipeline-test-20260612-downstream-eligibility-manifest-run17.json"
MANIFEST_ID = "manifest_2901cc01a0bc7a2252b35183"
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
        timeout=60,
    )


def read_report(output_dir: Path) -> dict:
    path = output_dir / "citation-pipeline-test-20260612-research-object-clusters-run18.json"
    assert path.exists(), f"missing report {path}"
    return json.loads(path.read_text())


def manifest_copy(tmp_path: Path, mutator=None) -> Path:
    data = json.loads(RUN17.read_text())
    if mutator:
        mutator(data)
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(data, indent=2, sort_keys=True))
    return path


def test_selects_caveat_manifest_item_and_creates_singleton_cluster_without_side_effects(tmp_path):
    db = db_copy(tmp_path)
    before = counts(db)
    before_status = status_hashes(db)
    before_registry = sha(ROOT / "data" / "source_registry.json")
    before_raw = tree_snapshot(ROOT / "raw")
    before_book = tree_snapshot(ROOT / "docs" / "book")
    before_schema = sha(ROOT / "data" / "schema.sql")
    before_worker = sha(ROOT / "scripts" / "daily_book_worker.py")

    res = run_script(
        "--run-id", "citation-pipeline-test-20260612",
        "--downstream-manifest", str(RUN17),
        "--report-suffix", "run18",
        db_path=db,
        output_dir=tmp_path,
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
    assert report["report_only"] is True
    assert report["selected_manifest_items_count"] == 1
    assert report["excluded_manifest_items_count"] == 1
    assert report["cluster_candidates_count"] == 1
    assert report["singleton_cluster_count"] == 1
    assert report["caveat_only_cluster_count"] == 1
    assert report["support_cluster_count"] == 0
    assert report["changed_db"] is False
    assert report["changed_source_notes"] is False
    assert report["claims_inserted"] == 0
    assert report["editorial_reviews_inserted"] == 0
    cluster = report["cluster_candidates"][0]
    assert cluster["cluster_type"] == "caveat_only_support_cluster"
    assert cluster["cluster_use"] == "caveat_only"
    assert cluster["cluster_decision"] == "caveat_only_cluster_candidate"
    assert cluster["singleton_cluster"] is True
    assert cluster["manifest_item_ids"] == [MANIFEST_ID]
    assert cluster["eligible_for_claim_insertion"] is False
    assert cluster["eligible_for_authoring"] is False
    assert cluster["eligible_for_publication"] is False
    assert cluster["author_allowed"] is False
    assert cluster["publication_approved"] is False
    assert cluster["advisory_only"] is True
    assert cluster["caveat_required"] is True
    assert "not a claim" in cluster["excluded_from_claiming_reason"].lower()


def test_excludes_source_context_unclear_item(tmp_path):
    db = db_copy(tmp_path)
    res = run_script("--downstream-manifest", str(RUN17), db_path=db, output_dir=tmp_path)
    assert res.returncode == 0, res.stderr + res.stdout
    report = read_report(tmp_path)
    excluded = [i for i in report["excluded_manifest_items"] if i.get("source_review_id") == EXCLUDED_REVIEW_ID]
    assert excluded
    assert excluded[0]["downstream_manifest_decision"] == "source_context_unclear"
    assert "human review required" not in json.dumps(excluded).lower()


def test_malformed_manifest_fails_closed(tmp_path):
    db = db_copy(tmp_path)
    path = tmp_path / "bad.json"
    path.write_text("{bad-json")
    before = counts(db)
    res = run_script("--downstream-manifest", str(path), db_path=db, output_dir=tmp_path)
    assert res.returncode == 2
    assert "invalid JSON" in res.stderr
    assert counts(db) == before


def test_missing_manifest_fails_closed(tmp_path):
    db = db_copy(tmp_path)
    before = counts(db)
    res = run_script("--downstream-manifest", str(tmp_path / "missing.json"), db_path=db, output_dir=tmp_path)
    assert res.returncode == 2
    assert "missing input" in res.stderr
    assert counts(db) == before


def test_contradiction_do_not_use_and_source_context_unclear_items_are_excluded(tmp_path):
    db = db_copy(tmp_path)
    def mutate(data):
        item = dict(data["manifest_items"][0])
        item.update({
            "manifest_item_id": "manifest_do_not_use",
            "downstream_manifest_decision": "eligible_for_clustering",
            "closed_loop_disposition": "eligible_for_review_note_persistence",
            "evidence_use_decision": "do_not_use",
            "contradiction_flag": True,
        })
        unclear = dict(data["manifest_items"][0])
        unclear.update({
            "manifest_item_id": "manifest_unclear",
            "downstream_manifest_decision": "source_context_unclear",
            "closed_loop_disposition": "source_context_unclear",
        })
        data["manifest_items"] = [item, unclear]
        data["excluded_items"] = []
    path = manifest_copy(tmp_path, mutate)
    res = run_script("--downstream-manifest", str(path), db_path=db, output_dir=tmp_path)
    assert res.returncode == 0, res.stderr + res.stdout
    report = read_report(tmp_path)
    assert report["cluster_candidates_count"] == 0
    decisions = {i["manifest_item_id"]: i["downstream_manifest_decision"] for i in report["excluded_manifest_items"]}
    assert decisions["manifest_do_not_use"] == "contradiction_review_required"
    assert decisions["manifest_unclear"] == "source_context_unclear"


def test_eligible_for_clustering_item_becomes_non_caveat_support_context_cluster(tmp_path):
    db = db_copy(tmp_path)
    def mutate(data):
        item = data["manifest_items"][0]
        item["downstream_manifest_decision"] = "eligible_for_clustering"
        item["caveat_required"] = False
        item["caveat_text"] = ""
        item["evidence_use_decision"] = "eligible_for_filing_later_after_corroboration"
    path = manifest_copy(tmp_path, mutate)
    res = run_script("--downstream-manifest", str(path), db_path=db, output_dir=tmp_path)
    assert res.returncode == 0, res.stderr + res.stdout
    report = read_report(tmp_path)
    cluster = report["cluster_candidates"][0]
    assert cluster["cluster_type"] == "support_cluster"
    assert cluster["cluster_use"] == "support_context_only"
    assert cluster["cluster_decision"] == "cluster_candidate"
    assert cluster["eligible_for_claim_insertion"] is False
    assert cluster["eligible_for_authoring"] is False
    assert cluster["eligible_for_publication"] is False


def test_forbidden_approval_flags_fail_closed(tmp_path):
    for key in ["advisory_only", "author_allowed", "publication_approved", "eligible_for_claim_insertion", "eligible_for_authoring", "eligible_for_publication"]:
        case_dir = tmp_path / key
        db = db_copy(case_dir)
        def mutate(data, key=key):
            item = data["manifest_items"][0]
            if key == "advisory_only":
                item[key] = False
            else:
                item[key] = True
        path = manifest_copy(case_dir, mutate)
        before = counts(db)
        res = run_script("--downstream-manifest", str(path), db_path=db, output_dir=case_dir)
        assert res.returncode == 2, key
        assert "safety flag" in res.stderr or "not eligible" in res.stderr
        assert counts(db) == before
