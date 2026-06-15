#!/usr/bin/env python3
"""Generate and validate a report-only Run 50 introduction draft via GPT-5.5."""
from __future__ import annotations

import argparse
import json
import re
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
SAFETY_FLAGS = {"advisory_only": True, "draft_only": True, "report_only": True, **FALSE_FLAGS}
REQUIRED_KEYS = [
    "run_id", "title", "draft_type", "draft_status", "gpt55_used", "provider", "model", "bridge", "reasoning_profile",
    "weak_local_fallback_used", "introduction_title", "target_audience", "central_thesis", "problem_statement",
    "contribution_statement", "scope_statement", "exclusions", "evidence_basis", "limitations", "how_to_read_this_book",
    "draft_markdown", "chapter_outline", "key_terms_to_define", "literature_support_needed", "methodology_support_needed",
    "claims_not_made", "caveats", "do_not_publish_reasons", "recommended_next_stage", "safety_flags",
]
CLAIM_ID_RE = re.compile(r"\b(?:claim|source|src|raw_capture|evidence)[_:][A-Za-z0-9_.:-]+", re.I)
STATUS_RE = re.compile(r"\b(?:weakly_supported|needs_review|source status|claim ledger|evidence status)\b", re.I)
INTERNAL_RE = re.compile(r"\b(?:Author role|Editor approval|Book role gate|machine disposition|publication pipeline status)\b", re.I)
OVERCLAIM_RE = re.compile(r"\b(?:This book proves|established discipline|broad adoption|widely adopted|strategic importance is clear)\b", re.I)
CITATION_RE = re.compile(r"\b[A-Z][A-Za-z-]+\s*\((?:19|20)\d{2}\)|\([A-Z][A-Za-z-]+(?:\s+et\s+al\.)?\s*,\s*(?:19|20)\d{2}\)|\[[0-9]+\]")


def has_uncaveated_overclaim(text: str) -> bool:
    for match in OVERCLAIM_RE.finditer(text or ""):
        start = max(0, match.start() - 80)
        context = (text[start:match.start()] or "").lower()
        if any(marker in context for marker in ["not ", "no ", "does not ", "do not ", "without ", "rather than ", "cannot ", "should not ", "is not ", "not as "]):
            continue
        return True
    return False


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def resolve(path: str | Path) -> Path:
    p = Path(path)
    return p if p.is_absolute() else ROOT / p


def word_count(text: str) -> int:
    return len(re.findall(r"\b[\w’'-]+\b", text or ""))


def fail_report(errors: list[str], *, bridge: str = "hermes_cli", provider: str = "copilot", model: str = "gpt-5.5", reasoning_profile: str = "closed_loop_editorial") -> dict[str, Any]:
    return {
        "ok": False,
        "run_id": "run50",
        "title": "Draft Introduction, thesis, scope, contribution, and limitations as report-only manuscript prose",
        "draft_type": "report_only_introduction_draft",
        "draft_status": "introduction_draft_failed_closed",
        "gpt55_used": False,
        "provider": provider,
        "model": model,
        "bridge": bridge,
        "reasoning_profile": reasoning_profile,
        "weak_local_fallback_used": False,
        "errors": errors,
        "draft_word_count": 0,
        "draft_markdown": "",
        "safety_flags": dict(SAFETY_FLAGS),
        "generated_at": utc_now(),
    }


def validate_draft_payload(data: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    for key in REQUIRED_KEYS:
        if key not in data:
            errors.append(f"missing_required_key:{key}")
    draft_type = str(data.get("draft_type") or "")
    if draft_type not in {"report_only_introduction_draft", "introduction_draft"} and not ("introduction" in draft_type or "report_only" in draft_type or "draft" in draft_type):
        errors.append("invalid_draft_type")
    if data.get("weak_local_fallback_used") is not False:
        errors.append("weak_local_fallback_used_refused")
    flags = data.get("safety_flags") if isinstance(data.get("safety_flags"), dict) else {}
    for key, expected in SAFETY_FLAGS.items():
        if flags.get(key) is not expected:
            errors.append(f"missing_or_invalid_safety_flag:{key}")
    if data.get("provider") != "copilot" or data.get("model") != "gpt-5.5" or data.get("bridge") != "hermes_cli":
        errors.append("wrong_provider_model_or_bridge")
    draft = str(data.get("draft_markdown") or "")
    wc = word_count(draft)
    if wc < 1200 or wc > 2500:
        errors.append(f"draft_word_count_out_of_bounds:{wc}")
    if CLAIM_ID_RE.search(draft):
        errors.append("claim_or_source_id_in_draft")
    if STATUS_RE.search(draft):
        errors.append("status_label_in_draft")
    if INTERNAL_RE.search(draft):
        errors.append("internal_workflow_language_in_draft")
    if has_uncaveated_overclaim(draft):
        errors.append("overclaiming_pattern")
    if CITATION_RE.search(draft):
        errors.append("invented_citation_marker")
    required_phrases = ["practitioner", "emerging"]
    lower = draft.lower()
    for phrase in required_phrases:
        if phrase not in lower:
            errors.append(f"missing_required_distinction:{phrase}")
    if errors:
        report = fail_report(errors)
        report["parsed_payload_preview"] = {k: data.get(k) for k in ["draft_status", "central_thesis", "introduction_title"]}
        return report
    data = dict(data)
    data["ok"] = True
    data["draft_type"] = "report_only_introduction_draft"
    data["draft_status"] = "introduction_draft_created"
    data["draft_word_count"] = wc
    data["generated_at"] = data.get("generated_at") or utc_now()
    return data


def parse_and_validate_gpt_output(raw: str) -> dict[str, Any]:
    try:
        data = json.loads(raw)
    except Exception as exc:
        return fail_report([f"invalid_json:{type(exc).__name__}"])
    if isinstance(data, dict) and isinstance(data.get("parsed_json"), dict):
        data = data["parsed_json"]
    if not isinstance(data, dict):
        return fail_report(["invalid_json:not_object"])
    return validate_draft_payload(data)


def build_prompt(packet: dict[str, Any], contract: dict[str, Any]) -> str:
    instruction = {
        "task": "Draft a report-only academic/professional book Introduction. Return strict JSON only, no markdown fence.",
        "provider": "copilot", "model": "gpt-5.5", "bridge": "hermes_cli", "reasoning_profile": "closed_loop_editorial",
        "strict_json": True, "weak_local_fallback": False,
        "required_output_keys": REQUIRED_KEYS,
        "required_safety_flags": SAFETY_FLAGS,
        "word_count_bounds": [1200, 2500],
        "must_not": ["invent citations", "use claim/source IDs", "claim loop engineering is established", "overclaim Hermes/OpenClaw", "authorize publication", "use internal workflow language in draft_markdown"],
        "input_packet": packet,
        "quality_contract": contract,
    }
    return json.dumps(instruction, ensure_ascii=False, sort_keys=True)


def call_gpt55(prompt: str, bridge_script: Path, timeout_seconds: int, reasoning_profile: str) -> str:
    if not bridge_script.exists():
        raise RuntimeError("gpt55_bridge_missing")
    proc = subprocess.run([
        sys.executable, str(bridge_script), "--prompt", prompt, "--schema-name", "run50_introduction_draft", "--provider", "copilot", "--model", "gpt-5.5", "--reasoning-profile", reasoning_profile, "--timeout-seconds", str(timeout_seconds)
    ], text=True, capture_output=True, timeout=timeout_seconds + 20, cwd=ROOT)
    if proc.returncode != 0:
        raise RuntimeError("gpt55_bridge_failed_closed")
    return proc.stdout


def write_reports(report: dict[str, Any], output_json: str | Path, output_md: str | Path) -> None:
    outj, outm = resolve(output_json), resolve(output_md)
    outj.parent.mkdir(parents=True, exist_ok=True)
    outm.parent.mkdir(parents=True, exist_ok=True)
    outj.write_text(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    md = ["# Run 50 introduction thesis draft", "", f"- ok: `{report.get('ok')}`", f"- draft_status: `{report.get('draft_status')}`", f"- GPT-5.5 used: `{report.get('gpt55_used')}`", f"- draft word count: `{report.get('draft_word_count')}`", f"- central thesis: {report.get('central_thesis', '')}", "", "## Draft", "", str(report.get("draft_markdown") or ""), "", "## Safety", "", "Report-only draft. Publication, authoring, claim insertion, and docs/book updates remain false.", ""]
    if report.get("errors"):
        md.insert(8, "- errors: `" + json.dumps(report.get("errors"), ensure_ascii=False) + "`")
    outm.write_text("\n".join(md), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input-packet", default="reports/editorial/run50-introduction-input-packet.json")
    ap.add_argument("--quality-contract", default="config/academic_book_quality_contract.json")
    ap.add_argument("--output-json", default="reports/editorial/run50-introduction-thesis-draft.json")
    ap.add_argument("--output-md", default="reports/editorial/run50-introduction-thesis-draft.md")
    ap.add_argument("--bridge-script", default="scripts/hermes_high_reasoning_json.py")
    ap.add_argument("--reasoning-profile", default="closed_loop_editorial")
    ap.add_argument("--timeout-seconds", type=int, default=300)
    args = ap.parse_args(argv)
    try:
        packet = json.loads(resolve(args.input_packet).read_text(encoding="utf-8"))
        contract = json.loads(resolve(args.quality_contract).read_text(encoding="utf-8"))
        if packet.get("publication_safety_flags") != FALSE_FLAGS:
            raise RuntimeError("input_packet_safety_flags_invalid")
        raw = call_gpt55(build_prompt(packet, contract), resolve(args.bridge_script), args.timeout_seconds, args.reasoning_profile)
        report = parse_and_validate_gpt_output(raw)
    except Exception as exc:
        report = fail_report([str(exc)], reasoning_profile=args.reasoning_profile)
    write_reports(report, args.output_json, args.output_md)
    print(json.dumps({"ok": report.get("ok"), "draft_status": report.get("draft_status"), "draft_word_count": report.get("draft_word_count", 0), "output_json": str(resolve(args.output_json))}, sort_keys=True))
    return 0 if report.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
