import hashlib
import importlib.util
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build_author_draft_input.py"
RUN22A = ROOT / "reports" / "editorial" / "citation-pipeline-test-20260612-closed-loop-state-machine-run22a.json"
RUN21 = ROOT / "reports" / "editorial" / "citation-pipeline-test-20260612-packet-redteam-gate-run21.json"
RUN20 = ROOT / "reports" / "editorial" / "citation-pipeline-test-20260612-narrative-packet-candidates-run20.json"
DB = ROOT / ".var" / "book.sqlite"
REQUIRED_CAVEAT = "Frame narrowly: OpenClaw documentation names Hermes in migration/setup tooling contexts; do not state that Hermes is a runtime dependency or general operating environment without additional sources."
REQUIRED_DO_NOT_SAY = [
    "Do not say Hermes is a runtime dependency of OpenClaw.",
    "Do not say Hermes is the general operating environment for OpenClaw.",
    "Do not say OpenClaw requires Hermes for web or phone access.",
    "Do not generalize beyond migration/setup/import tooling contexts unless additional sources support it.",
    "Do not use this packet as a factual claim without the caveat.",
    "Do not use this material for chapter prose before later author/red-team gates pass.",
]


def run_cli(tmp_path, run22a=RUN22A, run21=RUN21, run20=RUN20, db=DB):
    out = tmp_path / "reports"
    env = os.environ.copy()
    env["TEREFO_BOOK_DB_PATH"] = str(db)
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--run-id",
            "citation-pipeline-test-20260612",
            "--state-machine-report",
            str(run22a),
            "--packet-redteam-report",
            str(run21),
            "--packet-report",
            str(run20),
            "--output-dir",
            str(out),
            "--report-suffix",
            "run22b-test",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        env=env,
    )


def load_output(tmp_path):
    p = tmp_path / "reports" / "citation-pipeline-test-20260612-author-draft-input-run22b-test.json"
    assert p.exists()
    return json.loads(p.read_text())


def copy_json(src, tmp_path, name):
    dst = tmp_path / name
    shutil.copyfile(src, dst)
    return dst


def mutate_json(src, tmp_path, name, mutator):
    dst = copy_json(src, tmp_path, name)
    data = json.loads(dst.read_text())
    mutator(data)
    dst.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    return dst


def file_hash(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def db_counts(path):
    con = sqlite3.connect(path)
    try:
        return {
            "source_notes": con.execute("SELECT COUNT(*) FROM source_notes").fetchone()[0],
            "claims": con.execute("SELECT COUNT(*) FROM claims").fetchone()[0],
            "editorial_reviews": con.execute("SELECT COUNT(*) FROM editorial_reviews").fetchone()[0],
        }
    finally:
        con.close()


def test_selects_current_allowed_transition_and_builds_one_safe_package(tmp_path):
    result = run_cli(tmp_path)
    assert result.returncode == 0, result.stderr
    data = load_output(tmp_path)
    assert data["selected_transition_count"] == 1
    assert data["draft_input_package_count"] == 1
    assert data["excluded_transition_count"] == 0
    assert data["draft_input_type_counts"] == {"caveat_only_author_draft_input": 1}
    assert data["draft_input_decision_counts"] == {"caveat_only_draft_input_candidate": 1}
    assert data["draft_input_use_counts"] == {"caveat_only": 1}
    assert data["target_chapter_status_counts"] == {"not_assigned": 1}
    package = data["draft_input_packages"][0]
    assert package["source_packet_id"] == "packet_run20_caveat_only_cluster_4e8554045cfaf827bc68bcc5"
    assert package["draft_input_type"] == "caveat_only_author_draft_input"
    assert package["draft_input_decision"] == "caveat_only_draft_input_candidate"
    assert package["draft_input_use"] == "caveat_only"
    assert REQUIRED_CAVEAT in package["required_caveats"]
    assert package["do_not_say"] == REQUIRED_DO_NOT_SAY
    assert "chapter_prose" not in package
    assert "publishable_paragraph" not in package
    assert package["planning_summary"].startswith("Planning-only")
    assert package["later_author_prompt_seed"].startswith("Instruction seed only")
    assert package["author_allowed"] is False
    assert package["publication_approved"] is False
    assert package["eligible_for_authoring"] is False
    assert package["eligible_for_publication"] is False
    assert package["chapter_update_allowed"] is False
    assert package["eligible_for_claim_insertion"] is False


def test_cross_checks_run21_and_run20_constraints(tmp_path):
    spec = importlib.util.spec_from_file_location("build_author_draft_input", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    run22a = mod.load_json(RUN22A, "run22a")
    run21 = mod.load_json(RUN21, "run21")
    run20 = mod.load_json(RUN20, "run20")
    selected, excluded = mod.select_eligible_transitions(run22a, run21, run20)
    assert len(selected) == 1
    assert excluded == []
    item = selected[0]
    assert item["transition"]["transition_decision"] == "allowed_for_future_run"
    assert item["redteam_review"]["redteam_decision"] == "caveat_only_author_input_ready"
    assert item["redteam_review"]["author_input_readiness"] == "ready_for_caveat_only_draft_input"
    assert item["packet"]["packet_type"] == "caveat_only_packet_candidate"
    assert item["packet"]["packet_decision"] == "caveat_only_packet_candidate"
    assert item["packet"]["packet_use"] == "caveat_only"


def test_missing_caveat_or_do_not_say_excludes_object(tmp_path):
    def remove_caveat(data):
        data["packet_candidates"][0]["required_caveats"] = []
        data["packet_candidates"][0]["caveat_text"] = ""

    bad_run20 = mutate_json(RUN20, tmp_path, "bad-run20.json", remove_caveat)
    result = run_cli(tmp_path, run20=bad_run20)
    assert result.returncode == 0, result.stderr
    data = load_output(tmp_path)
    assert data["draft_input_package_count"] == 0
    assert data["excluded_transition_count"] == 1
    assert data["excluded_transitions"][0]["excluded_reason"] == "missing_required_caveat"

    def remove_dns(data):
        data["packet_candidates"][0]["do_not_say"] = []

    bad_run20 = mutate_json(RUN20, tmp_path, "bad-run20-dns.json", remove_dns)
    result = run_cli(tmp_path, run20=bad_run20)
    assert result.returncode == 0, result.stderr
    data = load_output(tmp_path)
    assert data["draft_input_package_count"] == 0
    assert data["excluded_transitions"][0]["excluded_reason"] == "missing_do_not_say"


def test_unsafe_transition_and_dispositions_are_excluded(tmp_path):
    def unsafe(data):
        item = data["transition_manifest"][0]
        item["transition_decision"] = "blocked_source_context_unclear"
        item["automated_disposition"] = "source_context_unclear"
        item["proposed_next_state"] = "source_context_unclear"

    bad_run22a = mutate_json(RUN22A, tmp_path, "bad-run22a.json", unsafe)
    result = run_cli(tmp_path, run22a=bad_run22a)
    assert result.returncode == 0, result.stderr
    data = load_output(tmp_path)
    assert data["selected_transition_count"] == 0
    assert data["draft_input_package_count"] == 0
    assert data["excluded_transitions"][0]["excluded_reason"] == "transition_not_allowed_for_author_draft_input"

    def contradiction(data):
        item = data["transition_manifest"][0]
        item["transition_decision"] = "blocked_contradiction_review"
        item["automated_disposition"] = "contradiction_review_required"

    bad_run22a = mutate_json(RUN22A, tmp_path, "bad-run22a-contradiction.json", contradiction)
    result = run_cli(tmp_path, run22a=bad_run22a)
    assert result.returncode == 0, result.stderr
    data = load_output(tmp_path)
    assert data["draft_input_package_count"] == 0


def test_approval_flags_block_package_creation(tmp_path):
    for flag in ["author_allowed", "publication_approved", "eligible_for_authoring", "chapter_update_allowed"]:
        def set_flag(data, flag=flag):
            data["transition_manifest"][0][flag] = True

        bad_run22a = mutate_json(RUN22A, tmp_path, f"bad-{flag}.json", set_flag)
        result = run_cli(tmp_path, run22a=bad_run22a)
        assert result.returncode == 0, result.stderr
        data = load_output(tmp_path)
        assert data["draft_input_package_count"] == 0
        assert data["excluded_transitions"][0]["excluded_reason"] == f"unsafe_flag_{flag}"


def test_report_only_does_not_modify_db_or_protected_files(tmp_path):
    temp_db = tmp_path / "book.sqlite"
    shutil.copyfile(DB, temp_db)
    before_counts = db_counts(temp_db)
    protected = [
        ROOT / "data" / "source_registry.json",
        ROOT / "data" / "schema.sql",
        ROOT / "scripts" / "daily_book_worker.py",
    ]
    protected += sorted((ROOT / "docs" / "book").glob("*.md"))
    before_hashes = {str(p): file_hash(p) for p in protected if p.exists()}
    result = run_cli(tmp_path, db=temp_db)
    assert result.returncode == 0, result.stderr
    data = load_output(tmp_path)
    assert data["changed_db"] is False
    assert data["changed_source_notes"] is False
    assert data["changed_source_registry"] is False
    assert data["changed_raw_captures"] is False
    assert data["changed_docs_book"] is False
    assert data["changed_schema"] is False
    assert data["changed_daily_worker"] is False
    assert data["claims_inserted"] == 0
    assert data["editorial_reviews_inserted"] == 0
    assert data["source_status_changed"] is False
    assert data["claim_status_changed"] is False
    assert data["editorial_status_changed"] is False
    assert db_counts(temp_db) == before_counts
    assert {str(p): file_hash(p) for p in protected if p.exists()} == before_hashes
