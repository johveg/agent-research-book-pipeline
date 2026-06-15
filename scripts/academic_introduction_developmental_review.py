#!/usr/bin/env python3
"""Run GPT-5.5 developmental review for the Run 50 report-only introduction draft."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
FALSE_FLAGS = {
    "author_allowed": False,
    "publication_approved": False,
    "eligible_for_claim_insertion": False,
    "eligible_for_authoring": False,
    "eligible_for_publication": False,
    "chapter_update_allowed": False,
}
SAFETY_FLAGS = {"advisory_only": True, "review_only": True, "report_only": True, **FALSE_FLAGS}
ALLOWED_RECOMMENDATIONS = {"revise_before_publication", "candidate_for_guarded_publication_in_run51", "needs_literature_context_first", "needs_methodology_first", "safe_reports_only"}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def resolve(path: str | Path) -> Path:
    p = Path(path)
    return p if p.is_absolute() else ROOT / p


def fail_report(errors: list[str], *, reasoning_profile: str = "closed_loop_editorial") -> dict[str, Any]:
    return {
        "ok": False,
        "run_id": "run50",
        "review_status": "developmental_review_failed_closed",
        "gpt55_used": False,
        "provider": "copilot",
        "model": "gpt-5.5",
        "bridge": "hermes_cli",
        "reasoning_profile": reasoning_profile,
        "weak_local_fallback_used": False,
        "errors": errors,
        "publication_consideration_recommendation": "safe_reports_only",
        "safety_flags": dict(SAFETY_FLAGS),
        "generated_at": utc_now(),
    }


def validate_review_payload(data: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    if data.get("weak_local_fallback_used", False) is not False:
        errors.append("weak_local_fallback_refused")
    if data.get("provider", "copilot") != "copilot" or data.get("model", "gpt-5.5") != "gpt-5.5" or data.get("bridge", "hermes_cli") != "hermes_cli":
        errors.append("wrong_provider_model_or_bridge")
    flags = data.get("safety_flags") if isinstance(data.get("safety_flags"), dict) else {}
    for key, expected in SAFETY_FLAGS.items():
        if flags.get(key) is not expected:
            errors.append(f"missing_or_invalid_safety_flag:{key}")
    rec = data.get("publication_consideration_recommendation") or data.get("recommendation") or data.get("recommended_next_stage")
    if rec not in ALLOWED_RECOMMENDATIONS:
        errors.append("invalid_or_publish_authorizing_recommendation")
    normalized_bools = {}
    for key in ["thesis_clear", "problem_defined", "audience_identified", "scope_and_exclusions_defined", "overclaiming_avoided", "evidence_interpretation_distinguished", "limitations_clear", "prepares_reader_for_later_chapters"]:
        value = data.get(key)
        if isinstance(value, dict) and isinstance(value.get("status"), bool):
            value = value["status"]
        if not isinstance(value, bool):
            errors.append(f"missing_boolean_assessment:{key}")
        else:
            normalized_bools[key] = value
    if errors:
        return fail_report(errors)
    data = dict(data)
    data.update(normalized_bools)
    data["provider"] = "copilot"
    data["model"] = "gpt-5.5"
    data["bridge"] = "hermes_cli"
    data["weak_local_fallback_used"] = False
    data["publication_consideration_recommendation"] = rec
    data["ok"] = True
    data["review_status"] = "developmental_review_completed"
    data["generated_at"] = data.get("generated_at") or utc_now()
    return data


def parse_and_validate_review_output(raw: str) -> dict[str, Any]:
    try:
        data = json.loads(raw)
    except Exception as exc:
        return fail_report([f"invalid_json:{type(exc).__name__}"])
    if isinstance(data, dict) and isinstance(data.get("parsed_json"), dict):
        data = data["parsed_json"]
    if not isinstance(data, dict):
        return fail_report(["invalid_json:not_object"])
    return validate_review_payload(data)


def build_prompt(draft: dict[str, Any]) -> str:
    prompt = {
        "task": "Developmentally review a report-only Introduction draft. Return strict JSON only.",
        "provider": "copilot", "model": "gpt-5.5", "bridge": "hermes_cli", "reasoning_profile": "closed_loop_editorial", "weak_local_fallback": False,
        "must_assess": ["clear thesis", "problem definition", "audience", "scope/exclusions", "overclaiming", "evidence vs interpretation", "limitations", "preparation for methodology/literature/conceptual chapters"],
        "allowed_recommendations": sorted(ALLOWED_RECOMMENDATIONS),
        "required_output_keys": [
            "run_id", "review_status", "gpt55_used", "provider", "model", "bridge", "reasoning_profile", "weak_local_fallback_used",
            "thesis_clear", "problem_defined", "audience_identified", "scope_and_exclusions_defined", "overclaiming_avoided",
            "evidence_interpretation_distinguished", "limitations_clear", "prepares_reader_for_later_chapters",
            "required_changes_before_publication", "publication_consideration_recommendation", "review_markdown", "safety_flags"
        ],
        "required_safety_flags": SAFETY_FLAGS,
        "must_not_authorize_publication": True,
        "draft": draft,
    }
    return json.dumps(prompt, ensure_ascii=False, sort_keys=True)


def call_gpt55(prompt: str, bridge_script: Path, timeout_seconds: int, reasoning_profile: str) -> str:
    if not bridge_script.exists():
        raise RuntimeError("gpt55_bridge_missing")
    proc = subprocess.run([
        sys.executable, str(bridge_script), "--prompt", prompt, "--schema-name", "run50_introduction_developmental_review", "--provider", "copilot", "--model", "gpt-5.5", "--reasoning-profile", reasoning_profile, "--timeout-seconds", str(timeout_seconds)
    ], text=True, capture_output=True, timeout=timeout_seconds + 20, cwd=ROOT)
    if proc.returncode != 0:
        raise RuntimeError("gpt55_bridge_failed_closed")
    return proc.stdout


def write_reports(report: dict[str, Any], output_json: str | Path, output_md: str | Path) -> None:
    outj, outm = resolve(output_json), resolve(output_md)
    outj.parent.mkdir(parents=True, exist_ok=True)
    outm.parent.mkdir(parents=True, exist_ok=True)
    outj.write_text(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    lines = ["# Run 50 developmental review", "", f"- ok: `{report.get('ok')}`", f"- review_status: `{report.get('review_status')}`", f"- GPT-5.5 used: `{report.get('gpt55_used')}`", f"- recommendation: `{report.get('publication_consideration_recommendation')}`", "", "## Review", "", str(report.get("review_markdown") or ""), "", "## Safety", "", "Advisory report only. The review cannot approve publication or docs/book mutation.", ""]
    if report.get("errors"):
        lines.insert(6, "- errors: `" + json.dumps(report.get("errors"), ensure_ascii=False) + "`")
    outm.write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--draft", default="reports/editorial/run50-introduction-thesis-draft.json")
    ap.add_argument("--output-json", default="reports/editorial/run50-introduction-developmental-review.json")
    ap.add_argument("--output-md", default="reports/editorial/run50-introduction-developmental-review.md")
    ap.add_argument("--bridge-script", default="scripts/hermes_high_reasoning_json.py")
    ap.add_argument("--reasoning-profile", default="closed_loop_editorial")
    ap.add_argument("--timeout-seconds", type=int, default=300)
    args = ap.parse_args(argv)
    try:
        draft = json.loads(resolve(args.draft).read_text(encoding="utf-8"))
        flags = draft.get("safety_flags") or {}
        for key, expected in {"author_allowed": False, "publication_approved": False, "eligible_for_publication": False, "chapter_update_allowed": False}.items():
            if flags.get(key) is not expected:
                raise RuntimeError("draft_safety_flags_invalid")
        raw = call_gpt55(build_prompt(draft), resolve(args.bridge_script), args.timeout_seconds, args.reasoning_profile)
        report = parse_and_validate_review_output(raw)
    except Exception as exc:
        report = fail_report([str(exc)], reasoning_profile=args.reasoning_profile)
    write_reports(report, args.output_json, args.output_md)
    print(json.dumps({"ok": report.get("ok"), "review_status": report.get("review_status"), "recommendation": report.get("publication_consideration_recommendation"), "output_json": str(resolve(args.output_json))}, sort_keys=True))
    return 0 if report.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
