import hashlib
import importlib.util
import json
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "closed_loop_transition_engine.py"
CONFIG = ROOT / "config" / "closed_loop_state_machine.json"
RUN31 = ROOT / "reports" / "editorial" / "citation-pipeline-test-20260612-constrained-authoring-metadata-preflight-run31.json"
RUN33 = ROOT / "reports" / "editorial" / "citation-pipeline-test-20260612-promotion-contract-authoring-metadata-run33.json"
DB = ROOT / ".var" / "book.sqlite"


def load_module():
    spec = importlib.util.spec_from_file_location("closed_loop_transition_engine", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_snapshot(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    return {str(p.relative_to(path)): sha(p) for p in sorted(path.rglob("*")) if p.is_file()}


def db_counts() -> dict[str, int]:
    con = sqlite3.connect(DB)
    try:
        return {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ["source_notes", "claims", "editorial_reviews"]}
    finally:
        con.close()


def db_status_hashes() -> dict[str, str]:
    con = sqlite3.connect(DB)
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


def copy_json(tmp_path: Path, src: Path, name: str, mutator=None) -> Path:
    data = json.loads(src.read_text())
    if mutator:
        mutator(data)
    path = tmp_path / name
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    return path


def config_copy(tmp_path: Path, mutator=None) -> Path:
    return copy_json(tmp_path, CONFIG, "closed_loop_state_machine.json", mutator)


def run_cli(input_report: Path, current: str, proposed: str, output_json: Path, config: Path = CONFIG):
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--state-machine-config",
            str(config),
            "--input-report",
            str(input_report),
            "--current-state",
            current,
            "--proposed-next-state",
            proposed,
            "--output-json",
            str(output_json),
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=180,
    )


def test_valid_current_config_passes_validation():
    mod = load_module()
    config = mod.load_state_machine_config(CONFIG)
    result = mod.validate_state_machine_config(config)
    assert result["ok"] is True
    assert result["state_count"] >= 28
    assert result["transition_count"] >= 13
    assert result["disposition_count"] >= 18
    assert result["human_in_loop_dependency_added"] is False


def test_config_validation_fails_for_duplicates_missing_required_and_human_dependency(tmp_path):
    mod = load_module()
    cases = []
    cases.append(("duplicate_state", lambda c: c["states"].append(c["states"][0]), "duplicate states"))
    cases.append(("duplicate_transition", lambda c: c["transitions"].append(dict(c["transitions"][0])), "duplicate transitions"))
    cases.append(("duplicate_disposition", lambda c: c["automated_dispositions"].append(c["automated_dispositions"][0]), "duplicate dispositions"))
    cases.append(("missing_state", lambda c: c["states"].remove("authoring_metadata_promotion_contract_ready"), "missing required states"))
    cases.append(("missing_transition", lambda c: c.__setitem__("transitions", [t for t in c["transitions"] if (t.get("from_state"), t.get("to_state")) != ("constrained_authoring_metadata_preflight_passed", "authoring_metadata_promotion_contract_ready")]), "missing required transitions"))
    cases.append(("missing_disposition", lambda c: c["automated_dispositions"].remove("ready_for_promotion_contract_update"), "missing required dispositions"))
    def human(c):
        c["states"].append("human_review_required")
        c["transitions"].append({"from_state": "safe_reports_only", "to_state": "human_review_required", "transition_type": "production_dependency", "guards": [{"name": "requires_human_review", "field": "requires_human_review", "equals": True}]})
    cases.append(("human_dependency", human, "human"))
    for name, mutator, expected in cases:
        cfg = json.loads(CONFIG.read_text())
        mutator(cfg)
        result = mod.validate_state_machine_config(cfg)
        assert result["ok"] is False, name
        assert expected in " ".join(result["errors"]).lower()


def test_run31_metadata_preflight_passed_transitions_to_promotion_contract_ready(tmp_path):
    mod = load_module()
    config = mod.load_state_machine_config(CONFIG)
    report = json.loads(RUN31.read_text())
    result = mod.evaluate_transition(config, report, "constrained_authoring_metadata_preflight_passed", "authoring_metadata_promotion_contract_ready")
    assert result["ok"] is True
    assert result["transition_decision"] == "transition_allowed"
    assert result["automated_disposition"] in {"caveat_only", "ready_for_promotion_contract_update"}
    assert result["transition_type"] == "future_run_only"
    assert result["hard_invariants_preserved"] is True
    assert result["human_in_loop_dependency_added"] is False
    for flag in ["author_allowed", "publication_approved", "eligible_for_claim_insertion", "eligible_for_authoring", "eligible_for_publication", "chapter_update_allowed"]:
        assert result[flag] is False
    assert "preflight_decision_metadata_preflight_passed" in result["satisfied_guards"]


def test_future_transition_to_context_candidate_is_future_run_only_and_not_approval():
    mod = load_module()
    config = mod.load_state_machine_config(CONFIG)
    report = json.loads(RUN33.read_text())
    result = mod.evaluate_transition(config, report, "authoring_metadata_promotion_contract_ready", "constrained_authoring_context_candidate")
    assert result["ok"] is True
    assert result["transition_decision"] == "transition_allowed"
    assert result["transition_type"] == "future_run_only"
    assert result["allowed_future_run"] == "build_constrained_authoring_context_candidate"
    assert result["hard_invariants_preserved"] is True
    assert result["human_in_loop_dependency_added"] is False
    assert result["author_allowed"] is False
    assert result["publication_approved"] is False
    assert result["eligible_for_claim_insertion"] is False
    assert result["chapter_update_allowed"] is False


def test_unknown_states_and_missing_transition_fail_closed():
    mod = load_module()
    config = mod.load_state_machine_config(CONFIG)
    report = json.loads(RUN31.read_text())
    assert mod.evaluate_transition(config, report, "unknown", "authoring_metadata_promotion_contract_ready")["transition_decision"] == "invalid_input"
    assert mod.evaluate_transition(config, report, "constrained_authoring_metadata_preflight_passed", "unknown")["transition_decision"] == "invalid_input"
    missing = mod.evaluate_transition(config, report, "source_support_reviewed", "authoring_metadata_promotion_contract_ready")
    assert missing["transition_decision"] == "transition_blocked"


def test_missing_required_caveat_do_not_say_and_provenance_fail_closed(tmp_path):
    mod = load_module()
    config = mod.load_state_machine_config(CONFIG)
    cases = [
        ("missing_caveat", lambda r: r["constrained_authoring_metadata_preflight_reviews"][0].__setitem__("required_caveats", []), "blocked_by_missing_caveat"),
        ("missing_dns", lambda r: r["constrained_authoring_metadata_preflight_reviews"][0].__setitem__("do_not_say", []), "invalid_input"),
        ("missing_prov", lambda r: r["selected_metadata"][0].__setitem__("provenance_paths", []), "blocked_by_missing_provenance"),
    ]
    for name, mutator, decision in cases:
        report = json.loads(RUN31.read_text())
        mutator(report)
        result = mod.evaluate_transition(config, report, "constrained_authoring_metadata_preflight_passed", "authoring_metadata_promotion_contract_ready")
        assert result["ok"] is False, name
        assert result["transition_decision"] == decision


def test_automated_disposition_routes_are_machine_routes_not_human_review():
    mod = load_module()
    config = mod.load_state_machine_config(CONFIG)
    routes = {
        "source_context_unclear": "routed_to_source_context_unclear",
        "needs_more_sources": "routed_to_needs_more_sources",
        "needs_better_authoring_metadata": "routed_to_needs_better_metadata",
        "contradiction_review_required": "routed_to_contradiction_review",
        "exclude_from_pipeline": "routed_to_exclude_from_pipeline",
        "safe_reports_only": "routed_to_safe_reports_only",
    }
    for disposition, decision in routes.items():
        report = json.loads(RUN31.read_text())
        review = report["constrained_authoring_metadata_preflight_reviews"][0]
        review["closed_loop_disposition"] = disposition
        if disposition == "needs_more_sources":
            review["metadata_readiness"] = "needs_more_sources"
        result = mod.evaluate_transition(config, report, "constrained_authoring_metadata_preflight_passed", "authoring_metadata_promotion_contract_ready")
        assert result["transition_decision"] == decision
        assert result["human_in_loop_dependency_added"] is False
        assert "human_review_required" not in json.dumps(result).lower()


def test_unsafe_safety_flags_block_closed():
    mod = load_module()
    config = mod.load_state_machine_config(CONFIG)
    for flag in ["author_allowed", "publication_approved", "eligible_for_claim_insertion", "eligible_for_authoring", "eligible_for_publication", "chapter_update_allowed"]:
        report = json.loads(RUN31.read_text())
        report["constrained_authoring_metadata_preflight_reviews"][0][flag] = True
        result = mod.evaluate_transition(config, report, "constrained_authoring_metadata_preflight_passed", "authoring_metadata_promotion_contract_ready")
        assert result["ok"] is False, flag
        assert result["transition_decision"] == "blocked_by_safety_flag"
        assert flag in result["failed_guards"]


def test_cli_writes_report_only_json_and_markdown_without_protected_side_effects(tmp_path):
    before_counts = db_counts()
    before_status = db_status_hashes()
    before_registry = sha(ROOT / "data" / "source_registry.json")
    before_raw = tree_snapshot(ROOT / "raw")
    before_book = tree_snapshot(ROOT / "docs" / "book")
    before_entities = tree_snapshot(ROOT / "docs" / "entities")
    before_claims_md = sha(ROOT / "docs" / "research" / "claims.md")
    before_schema = sha(ROOT / "data" / "schema.sql")
    before_worker = sha(ROOT / "scripts" / "daily_book_worker.py")
    output = tmp_path / "eval.json"
    res = run_cli(RUN31, "constrained_authoring_metadata_preflight_passed", "authoring_metadata_promotion_contract_ready", output)
    assert res.returncode == 0, res.stderr + res.stdout
    report = json.loads(output.read_text())
    assert report["transition_decision"] == "transition_allowed"
    assert (tmp_path / "eval.md").exists()
    assert db_counts() == before_counts
    assert db_status_hashes() == before_status
    assert sha(ROOT / "data" / "source_registry.json") == before_registry
    assert tree_snapshot(ROOT / "raw") == before_raw
    assert tree_snapshot(ROOT / "docs" / "book") == before_book
    assert tree_snapshot(ROOT / "docs" / "entities") == before_entities
    assert sha(ROOT / "docs" / "research" / "claims.md") == before_claims_md
    assert sha(ROOT / "data" / "schema.sql") == before_schema
    assert sha(ROOT / "scripts" / "daily_book_worker.py") == before_worker
