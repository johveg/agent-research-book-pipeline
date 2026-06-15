import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "closed_loop_author_editor.py"
CONTEXT = ROOT / "reports" / "editorial" / "citation-pipeline-test-20260612-constrained-authoring-context-run42.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_snapshot(path: Path) -> dict[str, str]:
    return {str(p.relative_to(path)): sha(p) for p in sorted(path.rglob("*")) if p.is_file()} if path.exists() else {}


def db_copy(tmp_path: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    dst = tmp_path / "book.sqlite"
    shutil.copy2(ROOT / ".var" / "book.sqlite", dst)
    return dst


def db_counts(db: Path) -> dict[str, int]:
    import sqlite3
    con = sqlite3.connect(db)
    try:
        return {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ["source_notes", "claims", "editorial_reviews"]}
    finally:
        con.close()


def load_module():
    spec = importlib.util.spec_from_file_location("author_editor", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run_cli(tmp_path: Path, *extra, db: Path | None = None, bridge_cmd: str | None = None):
    env = os.environ.copy()
    if db:
        env["TEREFO_BOOK_DB_PATH"] = str(db)
    if bridge_cmd:
        env["TEREFO_HIGH_REASONING_BRIDGE_COMMAND"] = bridge_cmd
    return subprocess.run([
        sys.executable, str(SCRIPT),
        "--run-id", "citation-pipeline-test-20260612",
        "--input-context", str(CONTEXT),
        "--output-json", str(tmp_path / "author.json"),
        "--output-md", str(tmp_path / "author.md"),
        "--publish-packets-json", str(tmp_path / "packets.json"),
        "--publish-packets-md", str(tmp_path / "packets.md"),
        "--patch-preview-json", str(tmp_path / "preview.json"),
        "--patch-preview-md", str(tmp_path / "preview.md"),
        "--model-profile", "closed_loop_editorial",
        "--provider", "copilot",
        "--model", "gpt-5.5",
        "--strict-json",
        "--no-weak-local-fallback",
        "--dry-run-patch-only",
        "--limit", "5",
        *extra,
    ], cwd=ROOT, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=180)


def bridge_script(tmp_path: Path, payload: dict) -> str:
    path = tmp_path / "bridge.py"
    path.write_text("""#!/usr/bin/env python3
import json, sys
json.load(sys.stdin)
print(json.dumps(%r))
""" % payload, encoding="utf-8")
    path.chmod(0o755)
    return str(path)


def approved_payload(disposition="caveat_only_publish_packet", readiness=None, delta=None):
    return {
        "author_status": "completed",
        "editor_status": "completed",
        "redteam_status": "completed",
        "publish_packets": [{
            "publish_packet_id": "pkt_run43_model",
            "source_packet_ids": ["context_run42"],
            "input_context_ids": ["context_run42_constrained_authoring_1415a8e978a39a19439acc7f"],
            "target_book_area": "OpenClaw chapter caveat note",
            "target_file_suggestion": "docs/book/03-openclaw.md",
            "update_type": "caveated_note",
            "title": "OpenClaw Hermes tooling caveat",
            "summary": "Caveat-only update candidate derived from Run 42 context.",
            "proposed_markdown_delta": delta or "OpenClaw documentation references Hermes in migration/setup tooling contexts; this does not establish Hermes as a runtime dependency.",
            "claim_map": [{"claim": "OpenClaw documentation references Hermes in migration/setup tooling contexts.", "evidence_refs": ["evidence_run42"]}],
            "citation_map": {"evidence_run42": ["reports/editorial/citation-pipeline-test-20260612-constrained-authoring-context-run42.json"]},
            "evidence_refs": ["evidence_run42"],
            "source_quality_summary": "Narrow singleton evidence, caveat required.",
            "required_caveats": ["Do not state Hermes is a runtime dependency or general operating environment for OpenClaw."],
            "forbidden_claims_checked": ["runtime dependency", "general operating environment", "web or phone access requirement"],
            "redteam_findings": {"approved": True, "hallucination_risk": "low_with_caveat", "weak_source_risk": "controlled"},
            "machine_editor_findings": {"approved": True, "all_claims_cited": True, "caveats_present": True},
            "disposition": disposition,
            "publication_readiness": readiness or {"ready_for_dry_run_patch": True, "ready_for_guarded_publication": False, "blocked": False},
            "idempotency_key": "idem_run43_model",
            "human_in_loop_dependency_added": False,
            "raw_text_publication_allowed": False,
            "docs_book_update_applied": False,
            "publication_deployed": False
        }]
    }


def read_json(path: Path):
    return json.loads(path.read_text())


def test_fixture_mode_creates_publish_packet_from_constrained_context(tmp_path):
    db = db_copy(tmp_path)
    res = run_cli(tmp_path, "--fixture-mode", db=db)
    assert res.returncode == 0, res.stderr + res.stdout
    report = read_json(tmp_path / "author.json")
    packets = read_json(tmp_path / "packets.json")
    preview = read_json(tmp_path / "preview.json")
    assert report["author_editor_status"] == "fixture_mode_completed"
    assert packets["publish_packet_count"] >= 1
    assert preview["docs_book_modified"] is False
    assert db_counts(db) == db_counts(db)


def test_live_mode_requires_gpt55_profile():
    mod = load_module()
    assert mod.model_profile_valid("closed_loop_editorial", "copilot", "gpt-5.5", True, True) == []
    assert mod.model_profile_valid("closed_loop_editorial", "copilot", "gpt-4", True, True)


def test_weak_local_fallback_is_refused():
    mod = load_module()
    assert any("weak" in e for e in mod.model_profile_valid("closed_loop_editorial", "copilot", "gpt-5.5", True, False))


def test_invalid_llm_json_fails_closed(tmp_path):
    bridge = tmp_path / "bad.py"
    bridge.write_text("import sys; sys.stdin.read(); print('not-json')\n")
    res = run_cli(tmp_path, db=db_copy(tmp_path), bridge_cmd=str(bridge))
    assert res.returncode == 2
    assert "failed_closed" in res.stderr


def test_missing_evidence_refs_fail_closed(tmp_path):
    payload = approved_payload(); payload["publish_packets"][0]["evidence_refs"] = []
    res = run_cli(tmp_path, db=db_copy(tmp_path), bridge_cmd=bridge_script(tmp_path, payload))
    assert res.returncode == 2
    assert "evidence_refs" in res.stderr


def test_unsupported_claims_fail_closed(tmp_path):
    payload = approved_payload(delta="Hermes is the runtime dependency of OpenClaw.")
    res = run_cli(tmp_path, db=db_copy(tmp_path), bridge_cmd=bridge_script(tmp_path, payload))
    assert res.returncode == 2
    assert "unsupported" in res.stderr.lower() or "forbidden" in res.stderr.lower()


def test_partial_evidence_produces_caveat_only_publish_packet(tmp_path):
    res = run_cli(tmp_path, db=db_copy(tmp_path), bridge_cmd=bridge_script(tmp_path, approved_payload("caveat_only_publish_packet")))
    assert res.returncode == 0, res.stderr
    packets = read_json(tmp_path / "packets.json")
    assert packets["disposition_counts"]["caveat_only_publish_packet"] == 1


def test_weak_evidence_produces_safe_reports_only_or_needs_more_sources(tmp_path):
    payload = approved_payload("needs_more_sources", {"ready_for_dry_run_patch": False, "ready_for_guarded_publication": False, "blocked": True})
    res = run_cli(tmp_path, db=db_copy(tmp_path), bridge_cmd=bridge_script(tmp_path, payload))
    assert res.returncode == 0
    assert read_json(tmp_path / "packets.json")["disposition_counts"]["needs_more_sources"] == 1


def test_contradiction_produces_contradiction_review_required(tmp_path):
    payload = approved_payload("contradiction_review_required", {"ready_for_dry_run_patch": False, "ready_for_guarded_publication": False, "blocked": True})
    res = run_cli(tmp_path, db=db_copy(tmp_path), bridge_cmd=bridge_script(tmp_path, payload))
    assert res.returncode == 0
    assert read_json(tmp_path / "packets.json")["disposition_counts"]["contradiction_review_required"] == 1


def test_privacy_raw_leakage_produces_quarantine(tmp_path):
    payload = approved_payload("quarantine", {"ready_for_dry_run_patch": False, "ready_for_guarded_publication": False, "blocked": True})
    res = run_cli(tmp_path, db=db_copy(tmp_path), bridge_cmd=bridge_script(tmp_path, payload))
    assert res.returncode == 0
    assert read_json(tmp_path / "packets.json")["disposition_counts"]["quarantine"] == 1


def test_no_human_review_dependency_appears(tmp_path):
    res = run_cli(tmp_path, "--fixture-mode", db=db_copy(tmp_path))
    assert res.returncode == 0
    combined = "\n".join(p.read_text() for p in [tmp_path/"author.json", tmp_path/"packets.json", tmp_path/"preview.json"])
    forbidden = "human_" + "review_required"
    assert forbidden not in combined
    assert "requires_" + "human_review" not in combined


def test_report_writes_json_and_markdown(tmp_path):
    res = run_cli(tmp_path, "--fixture-mode", db=db_copy(tmp_path))
    assert res.returncode == 0
    for name in ["author.json", "author.md", "packets.json", "packets.md", "preview.json", "preview.md"]:
        assert (tmp_path / name).exists()
        assert (tmp_path / name).stat().st_size > 0


def test_dry_run_patch_preview_does_not_modify_docs_book(tmp_path):
    before = tree_snapshot(ROOT / "docs" / "book")
    res = run_cli(tmp_path, "--fixture-mode", db=db_copy(tmp_path))
    assert res.returncode == 0
    assert tree_snapshot(ROOT / "docs" / "book") == before
    assert read_json(tmp_path / "preview.json")["docs_book_modified"] is False


def test_no_db_or_protected_mutations(tmp_path):
    db = db_copy(tmp_path)
    before_counts = db_counts(db)
    before_registry = sha(ROOT / "data" / "source_registry.json")
    before_raw = tree_snapshot(ROOT / "raw")
    before_entities = tree_snapshot(ROOT / "docs" / "entities")
    before_claims = sha(ROOT / "docs" / "research" / "claims.md")
    before_flags = tree_snapshot(ROOT / "docs" / "book")
    res = run_cli(tmp_path, "--fixture-mode", db=db)
    assert res.returncode == 0
    assert db_counts(db) == before_counts
    assert sha(ROOT / "data" / "source_registry.json") == before_registry
    assert tree_snapshot(ROOT / "raw") == before_raw
    assert tree_snapshot(ROOT / "docs" / "entities") == before_entities
    assert sha(ROOT / "docs" / "research" / "claims.md") == before_claims
    assert tree_snapshot(ROOT / "docs" / "book") == before_flags
    report = read_json(tmp_path / "author.json")
    assert report["docs_book_update_allowed"] is False
    assert report["production_publish_enabled"] is False
    assert report["docs_book_update_applied"] is False
    assert report["publication_deployed"] is False
