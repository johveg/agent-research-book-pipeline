import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "academic_introduction_developmental_review.py"


def load_module():
    spec = importlib.util.spec_from_file_location("academic_introduction_developmental_review", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def valid_draft(tmp_path: Path) -> Path:
    p = tmp_path / "draft.json"
    p.write_text(json.dumps({
        "ok": True,
        "draft_status": "introduction_draft_created",
        "draft_markdown": " ".join(["This introduction argues cautiously for governable agent loop engineering while preserving limitations."] * 180),
        "central_thesis": "Agent loops should be treated as governable engineering systems.",
        "safety_flags": {
            "advisory_only": True,
            "draft_only": True,
            "report_only": True,
            "author_allowed": False,
            "publication_approved": False,
            "eligible_for_claim_insertion": False,
            "eligible_for_authoring": False,
            "eligible_for_publication": False,
            "chapter_update_allowed": False,
        },
    }), encoding="utf-8")
    return p


def valid_review():
    return {
        "run_id": "run50",
        "review_status": "developmental_review_completed",
        "gpt55_used": True,
        "provider": "copilot",
        "model": "gpt-5.5",
        "bridge": "hermes_cli",
        "reasoning_profile": "closed_loop_editorial",
        "weak_local_fallback_used": False,
        "thesis_clear": True,
        "problem_defined": True,
        "audience_identified": True,
        "scope_and_exclusions_defined": True,
        "overclaiming_avoided": True,
        "evidence_interpretation_distinguished": True,
        "limitations_clear": True,
        "prepares_reader_for_later_chapters": True,
        "required_changes_before_publication": ["Add literature context."],
        "publication_consideration_recommendation": "candidate_for_guarded_publication_in_run51",
        "review_markdown": "The draft is a report-only candidate for guarded revision, not publication authorization.",
        "safety_flags": {
            "advisory_only": True,
            "review_only": True,
            "report_only": True,
            "author_allowed": False,
            "publication_approved": False,
            "eligible_for_claim_insertion": False,
            "eligible_for_authoring": False,
            "eligible_for_publication": False,
            "chapter_update_allowed": False,
        },
    }


def test_review_validation_accepts_safe_recommendations():
    mod = load_module()
    result = mod.parse_and_validate_review_output(json.dumps(valid_review()))
    assert result["ok"] is True
    assert result["publication_consideration_recommendation"] == "candidate_for_guarded_publication_in_run51"
    assert result["safety_flags"]["publication_approved"] is False


def test_invalid_json_and_true_flags_fail_closed():
    mod = load_module()
    assert mod.parse_and_validate_review_output("not json")["ok"] is False
    bad = valid_review()
    bad["safety_flags"]["eligible_for_publication"] = True
    result = mod.parse_and_validate_review_output(json.dumps(bad))
    assert result["ok"] is False
    assert any("eligible_for_publication" in e for e in result["errors"])


def test_review_cannot_directly_publish_or_use_fallback():
    mod = load_module()
    for key, value in [("publication_consideration_recommendation", "publish_now"), ("weak_local_fallback_used", True)]:
        bad = valid_review()
        bad[key] = value
        result = mod.parse_and_validate_review_output(json.dumps(bad))
        assert result["ok"] is False


def test_cli_missing_bridge_fails_closed(tmp_path):
    draft = valid_draft(tmp_path)
    out_json = tmp_path / "review.json"
    out_md = tmp_path / "review.md"
    proc = subprocess.run([
        sys.executable, str(SCRIPT),
        "--draft", str(draft),
        "--output-json", str(out_json),
        "--output-md", str(out_md),
        "--bridge-script", str(tmp_path / "missing_bridge.py"),
    ], text=True, capture_output=True)
    assert proc.returncode == 2
    data = json.loads(out_json.read_text(encoding="utf-8"))
    assert data["review_status"] == "developmental_review_failed_closed"
    assert data["weak_local_fallback_used"] is False
