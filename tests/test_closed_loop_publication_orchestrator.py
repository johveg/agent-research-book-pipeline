import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "closed_loop_publication_orchestrator.py"


def load_module():
    spec = importlib.util.spec_from_file_location("orchestrator", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def bridge_script(tmp_path: Path, payload: dict) -> str:
    path = tmp_path / "bridge.py"
    path.write_text("""#!/usr/bin/env python3
import json, sys
json.load(sys.stdin)
print(json.dumps(%r))
""" % payload, encoding="utf-8")
    path.chmod(0o755)
    return str(path)


def invalid_bridge(tmp_path: Path) -> str:
    path = tmp_path / "bad_bridge.py"
    path.write_text("#!/usr/bin/env python3\nprint('not json')\n", encoding="utf-8")
    path.chmod(0o755)
    return str(path)


def run43_packets(tmp_path):
    p = tmp_path / "run43.json"
    p.write_text(json.dumps({"publish_packets": [{"publish_packet_id": "run43_safe", "disposition": "safe_reports_only", "publication_readiness": {"blocked": True}}]}), encoding="utf-8")
    return p


def context_file(tmp_path):
    p = tmp_path / "context.json"
    p.write_text(json.dumps({
        "constrained_authoring_context_candidates": [{
            "context_id": "ctx1",
            "metadata_id": "meta1",
            "required_caveats": ["Narrow caveat required"],
            "provenance_paths": ["reports/editorial/prior.json"],
            "evidence_bound_atoms": ["A safe internal pipeline status can be published when substantive promotion is blocked."],
        }]
    }), encoding="utf-8")
    return p


def copy_book(tmp_path):
    docs = tmp_path / "docs" / "book"
    shutil.copytree(ROOT / "docs" / "book", docs)
    return docs


def test_consumes_run43_safe_reports_only_and_does_not_apply_it(tmp_path, monkeypatch):
    mod = load_module()
    packets = mod.load_run43_packets(run43_packets(tmp_path))
    assert mod.ready_packets(packets) == []


def test_broadens_evidence_when_no_ready_packet_exists(tmp_path):
    mod = load_module()
    evidence = mod.expand_evidence(context_file(tmp_path), limit=10)
    assert evidence["evidence_expansion_status"] == "expanded_existing_evidence"
    assert evidence["candidates_considered"] >= 1


def test_requires_gpt55_for_live_packet_generation_and_refuses_weak_fallback(tmp_path):
    mod = load_module()
    errs = mod.model_profile_errors("closed_loop_editorial", "openai", "gpt-4", True, True)
    assert any("provider" in e or "model" in e for e in errs)
    errs = mod.model_profile_errors("closed_loop_editorial", "copilot", "gpt-5.5", True, False)
    assert any("weak/local" in e for e in errs)


def test_invalid_gpt55_json_fails_closed(tmp_path, monkeypatch):
    docs = copy_book(tmp_path)
    monkeypatch.setenv("TEREFO_HIGH_REASONING_BRIDGE_COMMAND", invalid_bridge(tmp_path))
    res = subprocess.run([
        sys.executable, str(SCRIPT), "--run-id", "run44", "--run43-publish-packets", str(run43_packets(tmp_path)),
        "--run42-context", str(context_file(tmp_path)), "--author-editor-script", "scripts/closed_loop_author_editor.py",
        "--publisher-script", "scripts/closed_loop_book_publisher.py", "--model-profile", "closed_loop_editorial",
        "--provider", "copilot", "--model", "gpt-5.5", "--strict-json", "--no-weak-local-fallback",
        "--limit", "10", "--max-packets", "1", "--allow-daily-status-fallback", "--apply-if-machine-approved",
        "--docs-root", str(docs), "--output-json", str(tmp_path/'orch.json'), "--output-md", str(tmp_path/'orch.md'),
        "--evidence-expansion-json", str(tmp_path/'ev.json'), "--evidence-expansion-md", str(tmp_path/'ev.md'),
        "--publish-packets-json", str(tmp_path/'packets.json'), "--publish-packets-md", str(tmp_path/'packets.md'),
        "--patch-preview-json", str(tmp_path/'preview.json'), "--patch-preview-md", str(tmp_path/'preview.md'),
        "--publication-report-json", str(tmp_path/'pub.json'), "--publication-report-md", str(tmp_path/'pub.md')
    ], cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
    assert res.returncode == 2
    assert "failed_closed" in res.stderr


def test_selects_at_most_one_substantive_canary_and_outputs_counts(tmp_path, monkeypatch):
    payload = {"publication_status": "completed", "publish_packets": [approved_packet("a"), approved_packet("b")]}
    monkeypatch.setenv("TEREFO_HIGH_REASONING_BRIDGE_COMMAND", bridge_script(tmp_path, payload))
    docs = copy_book(tmp_path)
    out = run_orchestrator(tmp_path, docs)
    assert out.returncode == 0, out.stderr + out.stdout
    report = json.loads((tmp_path / "orch.json").read_text())
    assert report["substantive_packet_approved_count"] == 1
    assert report["publish_packet_count"] == 2
    assert report["publication_decision"] in {"substantive_canary_applied", "substantive_canary_ready"}
    assert report["target_file"] == "docs/book/03-openclaw.md"


def test_falls_back_to_daily_no_safe_promotions_when_no_packet_passes(tmp_path, monkeypatch):
    payload = {"publication_status": "completed", "publish_packets": [blocked_packet()]}
    monkeypatch.setenv("TEREFO_HIGH_REASONING_BRIDGE_COMMAND", bridge_script(tmp_path, payload))
    docs = copy_book(tmp_path)
    out = run_orchestrator(tmp_path, docs)
    assert out.returncode == 0, out.stderr + out.stdout
    report = json.loads((tmp_path / "orch.json").read_text())
    assert report["daily_status_fallback_applied"] is True
    assert report["publication_decision"] == "daily_no_safe_promotions_applied"
    assert (docs / "daily-pipeline-status.md").exists()


def test_no_human_dependency_appears_in_outputs(tmp_path, monkeypatch):
    payload = {"publication_status": "completed", "publish_packets": [blocked_packet()]}
    monkeypatch.setenv("TEREFO_HIGH_REASONING_BRIDGE_COMMAND", bridge_script(tmp_path, payload))
    docs = copy_book(tmp_path)
    out = run_orchestrator(tmp_path, docs)
    assert out.returncode == 0
    blob = "\n".join(p.read_text(errors="ignore") for p in tmp_path.glob("*.json"))
    for term in ["human_" + "review_required", "requires_" + "human_review", "manual_" + "approval_required", "editor_" + "must_review"]:
        assert term not in blob


def approved_packet(suffix="a"):
    return {
        "publish_packet_id": f"pkt_{suffix}", "source_packet_ids": ["src1", "src2"], "input_context_ids": ["ctx1"],
        "target_book_area": "OpenClaw", "target_file_suggestion": "docs/book/03-openclaw.md", "update_type": "existing_chapter_delta",
        "title": "Run44 canary", "summary": "Scoped canary", "proposed_markdown_delta": "\n\n## Run44 guarded canary\n\nA scoped machine-gated publication canary was approved.\n",
        "claim_map": [{"claim": "A scoped machine-gated publication canary was approved.", "evidence_refs": ["ev1"]}],
        "citation_map": {"ev1": ["reports/editorial/evidence.json"]}, "evidence_refs": ["ev1"],
        "source_quality_summary": "safe internal reports", "required_caveats": ["Scoped canary only"], "forbidden_claims_checked": ["raw leakage"],
        "redteam_findings": {"approved": True}, "machine_editor_findings": {"approved": True}, "disposition": "publish_packet_machine_approved",
        "publication_readiness": {"ready_for_dry_run_patch": True, "ready_for_guarded_publication": True, "blocked": False},
        "idempotency_key": f"idem_{suffix}", "human_in_loop_dependency_added": False, "raw_text_publication_allowed": False,
        "docs_book_update_applied": False, "publication_deployed": False,
    }


def blocked_packet():
    p = approved_packet("blocked")
    p["disposition"] = "safe_reports_only"
    p["update_type"] = "no_publication"
    p["publication_readiness"] = {"ready_for_dry_run_patch": False, "ready_for_guarded_publication": False, "blocked": True}
    p["redteam_findings"] = {"approved": False}
    p["machine_editor_findings"] = {"approved": False}
    return p


def run_orchestrator(tmp_path, docs):
    return subprocess.run([
        sys.executable, str(SCRIPT), "--run-id", "run44", "--run43-publish-packets", str(run43_packets(tmp_path)),
        "--run42-context", str(context_file(tmp_path)), "--author-editor-script", "scripts/closed_loop_author_editor.py",
        "--publisher-script", "scripts/closed_loop_book_publisher.py", "--model-profile", "closed_loop_editorial",
        "--provider", "copilot", "--model", "gpt-5.5", "--strict-json", "--no-weak-local-fallback",
        "--limit", "10", "--max-packets", "1", "--allow-daily-status-fallback", "--apply-if-machine-approved",
        "--docs-root", str(docs), "--output-json", str(tmp_path/'orch.json'), "--output-md", str(tmp_path/'orch.md'),
        "--evidence-expansion-json", str(tmp_path/'ev.json'), "--evidence-expansion-md", str(tmp_path/'ev.md'),
        "--publish-packets-json", str(tmp_path/'packets.json'), "--publish-packets-md", str(tmp_path/'packets.md'),
        "--patch-preview-json", str(tmp_path/'preview.json'), "--patch-preview-md", str(tmp_path/'preview.md'),
        "--publication-report-json", str(tmp_path/'pub.json'), "--publication-report-md", str(tmp_path/'pub.md')
    ], cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
