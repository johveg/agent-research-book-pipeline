#!/usr/bin/env python3
"""Run 6 reviewer-quality gate for high-reasoning source-card and semantic-object drafts.

Safety model:
- Inputs are existing Run 5 high-reasoning JSON reports only.
- Default output is report-only; this script never writes SQLite or protected docs.
- `--no-llm` runs deterministic structural checks for tests/audits.
- `--require-high-reasoning` calls GPT-5.5 through the shared Hermes CLI JSON bridge
  and marks reviewer reasoning as live only after strict JSON validates.
- No raw captures, vector DB chunks, chapter prose, narrative packets, status
  updates, schema migrations, daily-worker wiring, commit allowlist changes, or
  publication/author approvals.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from research_common import ROOT as REPO_ROOT, sha256_text, write_json  # noqa: E402
from hermes_high_reasoning_json import HighReasoningError, call_high_reasoning_json  # noqa: E402

MODE = "quality_gate_report_only"
DEFAULT_PROVIDER = os.environ.get("TEREFO_LLM_PROVIDER", "copilot")
DEFAULT_MODEL = os.environ.get("TEREFO_LLM_REASONING_MODEL", "gpt-5.5")
DEFAULT_SOURCE_CARD_REPORT = "reports/editorial/citation-pipeline-test-20260612-source-card-drafts-high-reasoning.json"
DEFAULT_SEMANTIC_OBJECT_REPORT = "reports/editorial/citation-pipeline-test-20260612-semantic-object-drafts-high-reasoning.json"
DECISION_MAPPING = {"ready_for_editor_review": "pass", "needs_revision": "warn", "blocked": "fail"}
REVERSE_MAPPING = {v: k for k, v in DECISION_MAPPING.items()}
DECISIONS = set(DECISION_MAPPING.values())
LEGACY_DECISIONS = set(DECISION_MAPPING)
RAW_ID_RE = re.compile(r"\b(?:src|claim)_[0-9a-f]{8,}\b")
SECRET_RE = re.compile(r"(?i)(api[_-]?key|token|secret|password|credential|bearer|oauth|cookie)\s*[:=]\s*\S+")
REQUIRED_SOURCE_CARD_FIELDS = {
    "card_id", "source_id", "run_id", "advisory_only", "llm_used", "confidence", "recommended_use",
    "evidence_strength", "privacy_publication_status", "risk_flags", "do_not_publish_reason",
    "safe_summary", "main_thesis", "card_output_hash",
}
REQUIRED_SEMANTIC_OBJECT_FIELDS = {
    "semantic_object_id", "object_type", "source_id", "source_note_id", "source_card_id", "run_id", "text",
    "advisory_only", "author_allowed", "publication_approved", "paraphrase_only", "evidence_basis",
    "evidence_strength", "recommended_use", "risk_flags", "do_not_publish_reason", "llm_used",
    "confidence", "object_output_hash",
}


class QualityGateError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def today_yyyymmdd() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d")


def repo_relative(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def clean_text(text: Any, max_len: int) -> str:
    text = str(text or "")
    text = SECRET_RE.sub("[REDACTED]", text)
    text = re.sub(r"https?://\S+", "[url]", text)
    text = RAW_ID_RE.sub("[internal-id]", text)
    text = re.sub(r"\burn:[\w:.-]+", "[internal-ref]", text, flags=re.I)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > max_len:
        return text[: max_len - 1].rstrip() + "…"
    return text


def listify(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise QualityGateError(f"Could not read JSON report {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise QualityGateError(f"JSON report must be an object: {path}")
    return data


def require_high_reasoning_report(report: dict[str, Any], label: str) -> None:
    if report.get("llm_used") is not True or report.get("reasoning_status") != "high_reasoning_used":
        raise QualityGateError(f"{label} report is not high-reasoning output; refusing quality gate over weak/no-LLM drafts")
    if report.get("provider") != "copilot":
        raise QualityGateError(f"{label} report used unapproved provider {report.get('provider')!r}; expected copilot")
    if report.get("model") != "gpt-5.5":
        raise QualityGateError(f"{label} report used unapproved model {report.get('model')!r}; expected gpt-5.5")
    if report.get("db_modified") is True:
        raise QualityGateError(f"{label} input report appears to be a DB-write run; expected report-only Run 5 output")


def bool_issue(cond: bool, message: str, issues: list[str]) -> None:
    if cond:
        issues.append(message)


def legacy_to_decision(legacy: str) -> str:
    return DECISION_MAPPING.get(legacy, "fail")


def next_stage(decision: str) -> str:
    return {
        "pass": "human_editor_review",
        "warn": "revise_high_reasoning_drafts",
        "fail": "blocked_until_schema_or_safety_fix",
    }[decision]


def eligibility(decision: str) -> str:
    return {
        "pass": "eligible_for_human_editor_review",
        "warn": "revise_before_editor_review",
        "fail": "ineligible",
    }[decision]


def finalize_review(review: dict[str, Any]) -> dict[str, Any]:
    tmp = dict(review)
    tmp.pop("output_hash", None)
    review["output_hash"] = sha256_text(json.dumps(tmp, sort_keys=True, ensure_ascii=False))
    return review


def review_from_parts(
    *,
    target_type: str,
    target_id: str,
    source_id: str,
    source_card_id: str,
    input_obj: dict[str, Any],
    legacy_decision: str,
    issues: list[str],
    positives: list[str],
    max_chars: int,
    reviewer_model: str,
) -> dict[str, Any]:
    decision = legacy_to_decision(legacy_decision)
    issue_text = "; ".join(issues[:3]) if issues else "Schema, linkage, and safety metadata are present; still advisory-only."
    scores = {
        "schema": 0 if any("missing required" in i for i in issues) else 1,
        "safety": 0 if any("secret-like" in i or "approval" in i or "not false" in i for i in issues) else 1,
        "linkage": 0 if any("not found" in i or "no linked" in i for i in issues) else 1,
        "editorial_readiness": {"pass": 2, "warn": 1, "fail": 0}[decision],
    }
    review = {
        "target_type": target_type,
        "target_id": target_id,
        "source_id": source_id,
        "source_card_id": source_card_id,
        "decision": decision,
        "legacy_decision": legacy_decision,
        "decision_mapping_note": f"{legacy_decision} -> {decision}",
        "downstream_eligibility": eligibility(decision),
        "recommended_next_stage": next_stage(decision),
        "scores": scores,
        "rule_results": {
            "missing_required_fields": [i for i in issues if i.startswith("missing required fields")],
            "privacy_or_publication_review_required": any("privacy" in i.lower() or "publication" in i.lower() for i in issues),
            "reject_or_do_not_use": any("do_not_use" in i or "reject" in i for i in issues),
            "linked_to_source_card": not any("not found" in i or "no linked" in i for i in issues),
        },
        "strengths": [clean_text(p, max_chars) for p in positives],
        "weaknesses": [clean_text(i, max_chars) for i in issues],
        "required_fixes": [clean_text(i, max_chars) for i in issues],
        "risk_flags": [clean_text(x, 100) for x in listify(input_obj.get("risk_flags"))[:10]],
        "review_summary": clean_text(issue_text, max_chars),
        "author_allowed": False,
        "publication_approved": False,
        "advisory_only": True,
        "input_hash": sha256_text(json.dumps(input_obj, sort_keys=True, ensure_ascii=False)),
        "output_hash": "",
        "reviewer_model": reviewer_model,
        # Backwards-compatible aliases from the first Run 6 attempt.
        "item_type": target_type,
        "item_id": target_id,
        "issues": [clean_text(i, max_chars) for i in issues],
        "positive_signals": [clean_text(p, max_chars) for p in positives],
        "rationale": clean_text(issue_text, max_chars),
        "review_hash": "",
    }
    finalize_review(review)
    review["review_hash"] = review["output_hash"]
    return review


def source_card_review(card: dict[str, Any], semantic_by_card: dict[str, list[dict[str, Any]]], max_chars: int, reviewer_model: str) -> dict[str, Any]:
    issues: list[str] = []
    positives: list[str] = []
    missing = sorted(REQUIRED_SOURCE_CARD_FIELDS - set(card))
    if missing:
        issues.append("missing required fields: " + ", ".join(missing))
    bool_issue(card.get("advisory_only") is not True, "advisory_only is not true", issues)
    bool_issue(card.get("llm_used") is not True, "card was not generated by high-reasoning LLM", issues)
    bool_issue(card.get("confidence") != "high", "confidence is not high", issues)
    bool_issue(len(str(card.get("safe_summary") or "")) > 500, "safe_summary is too long", issues)
    bool_issue(len(str(card.get("main_thesis") or "")) > 500, "main_thesis is too long", issues)
    bool_issue(bool(SECRET_RE.search(json.dumps(card, ensure_ascii=False))), "secret-like text detected", issues)
    if card.get("recommended_use") == "do_not_use":
        issues.append("recommended_use is do_not_use; keep blocked from downstream use")
    if card.get("evidence_strength") == "reject":
        issues.append("evidence_strength is reject; not suitable for filing/novelty work")
    if card.get("privacy_publication_status") in {"human_review", "private", "do_not_publish"}:
        issues.append("privacy/publication status requires human review")
    if not semantic_by_card.get(str(card.get("card_id") or "")):
        issues.append("no linked semantic object found in semantic report")
    if card.get("card_output_hash"):
        positives.append("stable card_output_hash present")
    if card.get("llm_used") is True and card.get("confidence") == "high":
        positives.append("Run 5 high-reasoning metadata present")
    if semantic_by_card.get(str(card.get("card_id") or "")):
        positives.append("linked semantic object exists")

    blocking = any(marker in issue for issue in issues for marker in ["missing required", "secret-like", "not generated", "advisory_only"])
    legacy = "blocked" if blocking else "needs_revision" if issues else "ready_for_editor_review"
    return review_from_parts(
        target_type="source_card",
        target_id=str(card.get("card_id") or ""),
        source_id=str(card.get("source_id") or ""),
        source_card_id=str(card.get("card_id") or ""),
        input_obj=card,
        legacy_decision=legacy,
        issues=issues,
        positives=positives,
        max_chars=max_chars,
        reviewer_model=reviewer_model,
    )


def semantic_object_review(obj: dict[str, Any], source_card_ids: set[str], max_chars: int, reviewer_model: str) -> dict[str, Any]:
    issues: list[str] = []
    positives: list[str] = []
    missing = sorted(REQUIRED_SEMANTIC_OBJECT_FIELDS - set(obj))
    if missing:
        issues.append("missing required fields: " + ", ".join(missing))
    bool_issue(obj.get("advisory_only") is not True, "advisory_only is not true", issues)
    bool_issue(obj.get("author_allowed") is not False, "author_allowed is not false", issues)
    bool_issue(obj.get("publication_approved") is not False, "publication_approved is not false", issues)
    bool_issue(obj.get("paraphrase_only") is not True, "paraphrase_only is not true", issues)
    bool_issue(obj.get("evidence_basis") != "source_card_draft", "evidence_basis is not source_card_draft", issues)
    bool_issue(obj.get("llm_used") is not True, "semantic object was not generated by high-reasoning LLM", issues)
    bool_issue(obj.get("confidence") != "high", "confidence is not high", issues)
    bool_issue(len(str(obj.get("text") or "")) > 500, "semantic text is too long", issues)
    bool_issue(bool(SECRET_RE.search(json.dumps(obj, ensure_ascii=False))), "secret-like text detected", issues)
    source_card_id = str(obj.get("source_card_id") or "")
    if source_card_id not in source_card_ids:
        issues.append(f"source_card_id not found in source-card report: {source_card_id}")
    if obj.get("recommended_use") == "do_not_use":
        issues.append("recommended_use is do_not_use; keep blocked from downstream use")
    if obj.get("evidence_strength") == "reject":
        issues.append("evidence_strength is reject; not suitable for filing/novelty work")
    if obj.get("object_output_hash"):
        positives.append("stable object_output_hash present")
    if source_card_id in source_card_ids:
        positives.append("source_card_id links to reviewed source-card report")
    if obj.get("author_allowed") is False and obj.get("publication_approved") is False:
        positives.append("publication/author approval remains false")

    blocking = any(marker in issue for issue in issues for marker in ["missing required", "secret-like", "not generated", "not found", "publication_approved is not false", "author_allowed is not false"])
    legacy = "blocked" if blocking else "needs_revision" if issues else "ready_for_editor_review"
    return review_from_parts(
        target_type="semantic_object",
        target_id=str(obj.get("semantic_object_id") or ""),
        source_id=str(obj.get("source_id") or ""),
        source_card_id=source_card_id,
        input_obj=obj,
        legacy_decision=legacy,
        issues=issues,
        positives=positives,
        max_chars=max_chars,
        reviewer_model=reviewer_model,
    )


def validate_reviewer_json(obj: dict[str, Any]) -> None:
    if "reviews" not in obj or not isinstance(obj["reviews"], list):
        raise ValueError("missing reviews array")
    for r in obj["reviews"]:
        if not isinstance(r, dict):
            raise ValueError("review entries must be objects")
        if r.get("decision") not in DECISIONS:
            raise ValueError("review decision must be pass/warn/fail")
        if r.get("author_allowed", False) is not False:
            raise ValueError("review author_allowed must be false")
        if r.get("publication_approved", False) is not False:
            raise ValueError("review publication_approved must be false")
        if r.get("advisory_only", True) is not True:
            raise ValueError("review advisory_only must be true")


def reviewer_prompt(preflight_reviews: list[dict[str, Any]], max_chars: int) -> str:
    compact = []
    for r in preflight_reviews:
        compact.append({
            "target_type": r["target_type"],
            "target_id": r["target_id"],
            "source_id": r["source_id"],
            "preflight_decision": r["decision"],
            "weaknesses": r["weaknesses"][:5],
            "strengths": r["strengths"][:5],
            "risk_flags": r["risk_flags"][:8],
        })
    return "\n".join([
        "You are GPT-5.5 acting as a reviewer-quality gate for advisory Terefo Heal Reboa source-card and semantic-object drafts.",
        "Return JSON only. No markdown. No prose outside JSON.",
        "Use only the provided preflight review data. Do not use raw captures or vector DB chunks. Do not invent facts or sources.",
        "Do not create chapter prose, narrative packets, publication approvals, author-use approvals, claim rows, or downstream automation.",
        "Decision vocabulary is exactly pass, warn, fail. Preserve author_allowed=false, publication_approved=false, advisory_only=true.",
        "Return shape: {\"overall_summary\": string, \"reviews\": [{\"target_type\": \"source_card|semantic_object\", \"target_id\": string, \"decision\": \"pass|warn|fail\", \"strengths\": [string], \"weaknesses\": [string], \"required_fixes\": [string], \"risk_flags\": [string], \"review_summary\": string, \"scores\": object, \"author_allowed\": false, \"publication_approved\": false, \"advisory_only\": true}]}",
        f"Limit review_summary and list items to {max_chars} characters.",
        json.dumps({"preflight_reviews": compact}, ensure_ascii=False, sort_keys=True),
    ])


def apply_llm_reviews(preflight: list[dict[str, Any]], bridge: dict[str, Any], max_chars: int, model: str) -> list[dict[str, Any]]:
    by_id = {str(r.get("target_id")): r for r in listify(bridge.get("parsed_json", {}).get("reviews")) if isinstance(r, dict)}
    out: list[dict[str, Any]] = []
    for base in preflight:
        merged = dict(base)
        candidate = by_id.get(base["target_id"])
        if candidate:
            decision = candidate.get("decision") if candidate.get("decision") in DECISIONS else base["decision"]
            # GPT may downgrade/upgrade within the explicit vocabulary, but safety failures keep fail.
            if base["decision"] == "fail" and decision != "fail":
                decision = "fail"
            merged["decision"] = decision
            merged["legacy_decision"] = REVERSE_MAPPING[decision]
            merged["decision_mapping_note"] = f"{merged['legacy_decision']} -> {decision}"
            merged["downstream_eligibility"] = eligibility(decision)
            merged["recommended_next_stage"] = next_stage(decision)
            for key in ["strengths", "weaknesses", "required_fixes", "risk_flags"]:
                if isinstance(candidate.get(key), list):
                    merged[key] = [clean_text(x, max_chars if key != "risk_flags" else 100) for x in candidate[key][:8]]
            if isinstance(candidate.get("scores"), dict):
                merged["scores"] = candidate["scores"]
            if candidate.get("review_summary"):
                merged["review_summary"] = clean_text(candidate.get("review_summary"), max_chars)
                merged["rationale"] = merged["review_summary"]
            merged["author_allowed"] = False
            merged["publication_approved"] = False
            merged["advisory_only"] = True
        merged["reviewer_model"] = model
        merged["issues"] = merged.get("required_fixes", [])
        merged["positive_signals"] = merged.get("strengths", [])
        merged["item_type"] = merged["target_type"]
        merged["item_id"] = merged["target_id"]
        merged["output_hash"] = ""
        finalize_review(merged)
        merged["review_hash"] = merged["output_hash"]
        out.append(merged)
    return out


def build_payload(args: argparse.Namespace, source_report: dict[str, Any], semantic_report: dict[str, Any]) -> dict[str, Any]:
    source_cards = listify(source_report.get("source_cards"))[: args.limit]
    semantic_objects = listify(semantic_report.get("semantic_objects"))[: args.limit]
    run_id = source_report.get("run_id") or semantic_report.get("run_id") or args.run_id or "unknown"
    if args.run_id not in {"latest", ""}:
        run_id = args.run_id
    source_card_ids = {str(c.get("card_id") or "") for c in source_cards}
    semantic_by_card: dict[str, list[dict[str, Any]]] = {}
    for obj in semantic_objects:
        semantic_by_card.setdefault(str(obj.get("source_card_id") or ""), []).append(obj)

    reviewer_model = "none" if args.no_llm else args.model
    card_reviews = [source_card_review(c, semantic_by_card, args.max_review_text_chars, reviewer_model) for c in source_cards]
    object_reviews = [semantic_object_review(o, source_card_ids, args.max_review_text_chars, reviewer_model) for o in semantic_objects]
    preflight_reviews = [*card_reviews, *object_reviews]

    bridge_result: dict[str, Any] = {}
    llm_used = False
    reasoning_status = "no_llm_structural_only"
    provider = "none"
    model = "none"
    bridge = "none"
    reviewer_note = "Deterministic structural preflight only; GPT-5.5 reviewer reasoning was not requested."
    if args.require_high_reasoning and not args.no_llm:
        if args.provider != "copilot" or args.model != "gpt-5.5":
            raise QualityGateError("GPT-5.5 reviewer mode requires provider=copilot model=gpt-5.5; weak/local fallback refused")
        prompt = reviewer_prompt(preflight_reviews, args.max_review_text_chars)
        bridge_result = call_high_reasoning_json(prompt, "quality_gate_reviews", validator=validate_reviewer_json, provider=args.provider, model=args.model)
        preflight_reviews = apply_llm_reviews(preflight_reviews, bridge_result, args.max_review_text_chars, args.model)
        card_reviews = [r for r in preflight_reviews if r["target_type"] == "source_card"]
        object_reviews = [r for r in preflight_reviews if r["target_type"] == "semantic_object"]
        llm_used = True
        reasoning_status = "high_reasoning_used"
        provider = args.provider
        model = args.model
        bridge = "hermes_cli"
        reviewer_note = "GPT-5.5 reviewer-quality gate ran through Hermes CLI bridge and returned strict schema-valid JSON."

    decisions = Counter(r["decision"] for r in preflight_reviews)
    legacy_decisions = Counter(r["legacy_decision"] for r in preflight_reviews)
    downstream_eligible_count = int(decisions.get("pass", 0))
    next_allowed = "human_editor_review" if decisions.get("fail", 0) == 0 and decisions.get("warn", 0) == 0 else "revise_high_reasoning_drafts"
    payload = {
        "run_id": run_id,
        "generated_at": utc_now(),
        "mode": MODE,
        "llm_used": llm_used,
        "quality_gate_llm_used": llm_used,
        "provider": provider,
        "model": model,
        "bridge": bridge,
        "reasoning_status": reasoning_status,
        "quality_gate_reasoning_status": reasoning_status,
        "reviewer_note": reviewer_note,
        "decision_vocabulary": ["pass", "warn", "fail"],
        "decision_mapping": DECISION_MAPPING,
        "input_reports": {
            "source_cards": {"path": args.source_card_report, "run_id": source_report.get("run_id"), "llm_used": source_report.get("llm_used"), "reasoning_status": source_report.get("reasoning_status"), "provider": source_report.get("provider"), "model": source_report.get("model"), "count": len(source_cards)},
            "semantic_objects": {"path": args.semantic_object_report, "run_id": semantic_report.get("run_id"), "llm_used": semantic_report.get("llm_used"), "reasoning_status": semantic_report.get("reasoning_status"), "provider": semantic_report.get("provider"), "model": semantic_report.get("model"), "count": len(semantic_objects)},
        },
        "source_cards_reviewed": len(card_reviews),
        "semantic_objects_reviewed": len(object_reviews),
        "source_card_reviews": card_reviews,
        "semantic_object_reviews": object_reviews,
        "decision_counts": {k: int(decisions.get(k, 0)) for k in ["pass", "warn", "fail"]},
        "counts_by_decision": {k: int(legacy_decisions.get(k, 0)) for k in ["blocked", "needs_revision", "ready_for_editor_review"]},
        "downstream_eligible_count": downstream_eligible_count,
        "ready_for_editor_review_count": int(legacy_decisions.get("ready_for_editor_review", 0)),
        "revision_issue_count": int(legacy_decisions.get("needs_revision", 0)),
        "blocking_issue_count": int(legacy_decisions.get("blocked", 0)),
        "max_review_text_chars": args.max_review_text_chars,
        "db_modified": False,
        "db_write_scope": "none",
        "chapters_modified": False,
        "statuses_modified": False,
        "schema_modified": False,
        "daily_worker_modified": False,
        "commit_allowlist_modified": False,
        "raw_or_vector_authority_used": False,
        "narrative_packets_created": False,
        "chapter_prose_generated": False,
        "publication_approval_granted": False,
        "long_source_excerpt_written": False,
        "raw_private_material_written": False,
        "high_reasoning_bridge": bridge_result,
        "recommendation": {
            "next_allowed_stage": next_allowed,
            "summary": "Proceed only to human/editor review; do not wire downstream automation." if next_allowed == "human_editor_review" else "Revise high-reasoning drafts before any downstream stage.",
            "run7_candidate": "revise high-reasoning drafts or select a safer/public-source sample, then rerun this quality gate; do not proceed to Run 7 automation yet.",
        },
        "audit": {
            "prior_run6_assessment": "partially_valid_but_misaligned",
            "matched_intended_run6": [
                "Read Run 5 high-reasoning source-card and semantic-object JSON reports.",
                "Verified input llm_used/reasoning_status/provider/model.",
                "Produced report-only safety decisions with no DB/chapter/status/schema/daily-worker/allowlist writes.",
            ],
            "did_not_match_intended_run6": [
                "Previous quality gate did not call GPT-5.5 for reviewer-quality judgment; it used deterministic reviewer rules only.",
                "Previous item schema lacked explicit pass/warn/fail compatibility fields and several required reviewer fields.",
                "Existing Run 5 evidence map path is miswritten with Run 2 placeholder content; this correction did not overwrite it.",
            ],
            "patched": [
                "Added --no-llm deterministic mode and --require-high-reasoning GPT-5.5 reviewer mode.",
                "Added pass/warn/fail decisions with explicit legacy mapping.",
                "Added downstream eligibility, recommended stage, scores/rules, strengths/weaknesses/fixes/risks, safety booleans, and input/output hashes per item.",
                "Changed generated report names to *-quality-gate-corrected.* for this correction/audit run.",
            ],
            "intentionally_left_unchanged": [
                "Run 5 JSON reports.",
                "Existing Run 6 reports and evidence map.",
                "Miswritten Run 5 evidence map, to avoid overwriting prior evidence further.",
                "DB, docs/book, raw captures, schema, daily worker, commit allowlist.",
            ],
        },
        "risks": [
            "Reviewer gate checks draft quality and safety; it does not prove factual truth.",
            "Run 5 GPT-5.5 drafts remain advisory-only and not publication-approved.",
            "Social/private-adjacent sources require human review before any use.",
            "No raw captures or vector DB chunks were consulted by this quality gate.",
        ],
        "output_paths": {},
        "verification": {},
    }
    return payload


def md_cell(x: Any, max_len: int = 90) -> str:
    return clean_text(x, max_len).replace("|", "\\|")


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        f"# Run 6 Correction/audit reviewer quality gate: {payload['run_id']}", "",
        "## Executive summary", "",
        f"- Run ID: `{payload['run_id']}`",
        f"- Generated at: {payload['generated_at']}",
        f"- LLM used: {payload['llm_used']}",
        f"- Provider/model/bridge: `{payload['provider']}` / `{payload['model']}` / `{payload['bridge']}`",
        f"- Reasoning status: `{payload['reasoning_status']}`",
        f"- Source cards reviewed: {payload['source_cards_reviewed']}",
        f"- Semantic objects reviewed: {payload['semantic_objects_reviewed']}",
        f"- Decision counts: `{payload['decision_counts']}`",
        f"- Legacy mapping counts: `{payload['counts_by_decision']}`",
        f"- Downstream eligible count: {payload['downstream_eligible_count']}",
        f"- Next allowed stage: `{payload['recommendation']['next_allowed_stage']}`", "",
        "## Decision mapping", "",
        "- `ready_for_editor_review -> pass`", "- `needs_revision -> warn`", "- `blocked -> fail`", "",
        "## Audit findings", "",
        f"- Prior Run 6 assessment: `{payload['audit']['prior_run6_assessment']}`", "",
        "Matched intended Run 6:",
    ]
    for item in payload["audit"]["matched_intended_run6"]:
        lines.append(f"- {item}")
    lines.append("")
    lines.append("Did not match intended Run 6:")
    for item in payload["audit"]["did_not_match_intended_run6"]:
        lines.append(f"- {item}")
    lines.append("")
    lines.append("Patched:")
    for item in payload["audit"]["patched"]:
        lines.append(f"- {item}")
    lines.append("")
    lines.append("## Source-card reviews")
    lines += ["", "| target_id | source_id | decision | downstream eligibility | required fixes |", "|---|---|---|---|---|"]
    for r in payload["source_card_reviews"]:
        lines.append("| " + " | ".join([md_cell(r["target_id"]), md_cell(r["source_id"]), md_cell(r["decision"]), md_cell(r["downstream_eligibility"]), md_cell("; ".join(r["required_fixes"]))]) + " |")
    lines += ["", "## Semantic-object reviews", "", "| target_id | source_id | source_card_id | decision | downstream eligibility | required fixes |", "|---|---|---|---|---|---|"]
    for r in payload["semantic_object_reviews"]:
        lines.append("| " + " | ".join([md_cell(r["target_id"]), md_cell(r["source_id"]), md_cell(r["source_card_id"]), md_cell(r["decision"]), md_cell(r["downstream_eligibility"]), md_cell("; ".join(r["required_fixes"]))]) + " |")
    lines += ["", "## Safety assessment", ""]
    for key in ["db_modified", "chapters_modified", "statuses_modified", "schema_modified", "daily_worker_modified", "commit_allowlist_modified", "raw_or_vector_authority_used", "narrative_packets_created", "chapter_prose_generated", "publication_approval_granted", "long_source_excerpt_written"]:
        lines.append(f"- {key}: `{payload[key]}`")
    lines += ["", "## Run 7 recommendation", "", payload["recommendation"]["summary"], "", f"Candidate: {payload['recommendation']['run7_candidate']}", ""]
    return "\n".join(lines)


def render_evidence_placeholder(payload: dict[str, Any]) -> str:
    return "\n".join([
        f"# Run 6 quality gate correction evidence map — {today_yyyymmdd()}", "",
        "Generated placeholder from `scripts/llm_quality_gate.py`; final verification details should be expanded after checks.", "",
        f"- Run ID: `{payload['run_id']}`",
        f"- LLM used: {payload['llm_used']}",
        f"- Provider/model/bridge: `{payload['provider']}` / `{payload['model']}` / `{payload['bridge']}`",
        f"- Source cards reviewed: {payload['source_cards_reviewed']}",
        f"- Semantic objects reviewed: {payload['semantic_objects_reviewed']}",
        f"- Decision counts: `{payload['decision_counts']}`",
        f"- DB write scope: `{payload['db_write_scope']}`", "",
    ])


def write_reports(payload: dict[str, Any], output_dir: Path, json_only: bool, markdown_only: bool, report_suffix: str = "") -> dict[str, str]:
    output_dir = output_dir if output_dir.is_absolute() else REPO_ROOT / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    q_suffix = f"quality-gate-{report_suffix}" if report_suffix else "quality-gate-corrected"
    md_path = output_dir / f"{payload['run_id']}-{q_suffix}.md"
    json_path = output_dir / f"{payload['run_id']}-{q_suffix}.json"
    arch_dir = REPO_ROOT / "reports" / "architecture"
    arch_dir.mkdir(parents=True, exist_ok=True)
    evidence_name = "run7-better-source-regeneration-evidence-map" if report_suffix.startswith("run7") else "run6-quality-gate-correction-evidence-map"
    ev_path = arch_dir / f"{evidence_name}-{today_yyyymmdd()}.md"
    outputs = {"markdown": repo_relative(md_path), "json": repo_relative(json_path), "evidence_map": repo_relative(ev_path)}
    payload["output_paths"] = outputs
    if not markdown_only:
        write_json(json_path, payload)
    if not json_only:
        md_path.write_text(render_markdown(payload), encoding="utf-8")
    if not ev_path.exists():
        ev_path.write_text(render_evidence_placeholder(payload), encoding="utf-8")
    return outputs


def parse_args(argv: list[str]) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Report-only reviewer quality gate for Run 5 high-reasoning drafts.")
    ap.add_argument("--run-id", default="latest")
    ap.add_argument("--source-card-report", default=DEFAULT_SOURCE_CARD_REPORT)
    ap.add_argument("--semantic-object-report", default=DEFAULT_SEMANTIC_OBJECT_REPORT)
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--output-dir", default="reports/editorial")
    ap.add_argument("--provider", default=DEFAULT_PROVIDER)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--no-llm", action="store_true", help="Deterministic structural checks only; no live GPT-5.5 reviewer call.")
    ap.add_argument("--require-high-reasoning", action="store_true", help="Require live GPT-5.5 reviewer call through Hermes CLI bridge.")
    ap.add_argument("--json-only", action="store_true")
    ap.add_argument("--markdown-only", action="store_true")
    ap.add_argument("--max-review-text-chars", type=int, default=180)
    ap.add_argument("--report-suffix", default="", help="Optional suffix for output filenames, e.g. run7")
    args = ap.parse_args(argv)
    if args.json_only and args.markdown_only:
        raise QualityGateError("--json-only and --markdown-only are mutually exclusive")
    if args.max_review_text_chars < 80 or args.max_review_text_chars > 500:
        raise QualityGateError("--max-review-text-chars must be between 80 and 500")
    if args.limit < 0:
        raise QualityGateError("--limit must be non-negative")
    if args.no_llm and args.require_high_reasoning:
        raise QualityGateError("--no-llm and --require-high-reasoning are mutually exclusive")
    return args


def main(argv: list[str] | None = None) -> int:
    try:
        args = parse_args(argv or sys.argv[1:])
        source_path = Path(args.source_card_report)
        semantic_path = Path(args.semantic_object_report)
        if not source_path.is_absolute():
            source_path = REPO_ROOT / source_path
        if not semantic_path.is_absolute():
            semantic_path = REPO_ROOT / semantic_path
        source_report = load_json(source_path)
        semantic_report = load_json(semantic_path)
        require_high_reasoning_report(source_report, "source-card")
        require_high_reasoning_report(semantic_report, "semantic-object")
        payload = build_payload(args, source_report, semantic_report)
        outputs = write_reports(payload, Path(args.output_dir), args.json_only, args.markdown_only, args.report_suffix)
        result = {
            "status": "ok",
            "run_id": payload["run_id"],
            "outputs": outputs,
            "decision_counts": payload["decision_counts"],
            "counts_by_decision": payload["counts_by_decision"],
            "downstream_eligible_count": payload["downstream_eligible_count"],
            "llm_used": payload["llm_used"],
            "provider": payload["provider"],
            "model": payload["model"],
            "bridge": payload["bridge"],
            "db_modified": payload["db_modified"],
        }
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except HighReasoningError as exc:
        print("ERROR: high-reasoning bridge failed; weak/local fallback refused; no DB writes attempted", file=sys.stderr)
        print(json.dumps(exc.result, sort_keys=True), file=sys.stderr)
        return 2
    except QualityGateError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
