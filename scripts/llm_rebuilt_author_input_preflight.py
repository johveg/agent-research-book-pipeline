#!/usr/bin/env python3
"""Run 27 report-only enriched author-draft input preflight gate.

Consumes Run 26 enriched caveat-only author-draft input packages and asks GPT-5.5,
through the closed_loop_editorial profile, to preflight/red-team whether the
rebuilt input is suitable for a second controlled caveat-only draft canary.

This is advisory/report-only: no draft prose, no chapter prose, no DB writes,
no source_notes/claims/editorial_reviews insertion, no source/status changes,
no docs/book mutation, no source_registry/raw/schema/daily-worker mutation, and
no authoring/publication/chapter-update approval.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from hermes_high_reasoning_json import HighReasoningError, call_high_reasoning_json  # noqa: E402
from model_profiles import ModelProfileError, load_model_profile  # noqa: E402
from research_common import DB_PATH as DEFAULT_DB_PATH, sha256_text  # noqa: E402

RUN_ID_DEFAULT = "citation-pipeline-test-20260612"
MODE = "llm_rebuilt_author_input_preflight"
DEFAULT_RUN26 = f"reports/editorial/{RUN_ID_DEFAULT}-author-draft-input-rebuild-run26.json"
REQUIRED_CAVEAT = "Frame narrowly: OpenClaw documentation names Hermes in migration/setup tooling contexts; do not state that Hermes is a runtime dependency or general operating environment without additional sources."
REQUIRED_DO_NOT_SAY = [
    "Do not say Hermes is a runtime dependency of OpenClaw.",
    "Do not say Hermes is the general operating environment for OpenClaw.",
    "Do not say OpenClaw requires Hermes for web or phone access.",
    "Do not generalize beyond migration/setup/import tooling contexts unless additional sources support it.",
    "Do not use this material as a factual claim without the caveat.",
    "Do not use this material for chapter prose before later author/red-team gates pass.",
]
FALSE_FLAGS = [
    "author_allowed",
    "publication_approved",
    "eligible_for_claim_insertion",
    "eligible_for_authoring",
    "eligible_for_publication",
    "chapter_update_allowed",
]
CHAPTER_READY_FIELDS = {
    "chapter_prose",
    "publishable_paragraph",
    "draft_paragraph",
    "final_prose",
    "book_text",
    "chapter_ready_prose",
    "citation_resolved_chapter_text",
}
ALLOWED_PREFLIGHT_DECISIONS = {
    "rebuilt_input_canary_ready",
    "still_safe_but_too_thin",
    "safe_reports_only",
    "needs_more_sources",
    "source_context_unclear",
    "exclude_from_authoring",
    "contradiction_review_required",
}
ALLOWED_CANARY_READINESS = {
    "ready_for_second_controlled_caveat_only_author_draft_canary",
    "not_ready_still_too_thin",
    "not_ready_safe_reports_only",
    "not_ready_needs_more_sources",
    "not_ready_source_context_unclear",
    "not_ready_exclude",
    "not_ready_contradiction_review",
}
ALLOWED_DISPOSITIONS = {
    "caveat_only",
    "needs_better_authoring_input",
    "safe_reports_only",
    "needs_more_sources",
    "source_context_unclear",
    "exclude_from_pipeline",
    "contradiction_review_required",
}
ALLOWED_NEXT_STAGES = {
    "run_second_controlled_caveat_only_author_draft_canary",
    "rebuild_author_draft_input_again",
    "keep_safe_reports_only",
    "run_additional_source_collection",
    "run_source_context_review",
    "exclude_from_pipeline",
    "run_contradiction_review",
}
REQUIRED_REVIEW_FIELDS = [
    "rebuilt_input_id",
    "rebuilt_input_type",
    "rebuilt_input_use",
    "preflight_decision",
    "canary_readiness",
    "closed_loop_disposition",
    "usefulness_improvement_assessment",
    "caveat_integrity_assessment",
    "do_not_say_compliance_assessment",
    "prose_containment_assessment",
    "provenance_assessment",
    "residual_risk_assessment",
    "required_caveats",
    "do_not_say",
    "limitations",
    "residual_risk",
    "recommended_next_stage",
    "advisory_only",
    "author_allowed",
    "publication_approved",
    "eligible_for_claim_insertion",
    "eligible_for_authoring",
    "eligible_for_publication",
    "chapter_update_allowed",
]


class PreflightError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def db_path() -> Path:
    override = os.environ.get("TEREFO_BOOK_DB_PATH", "").strip()
    return Path(override) if override else DEFAULT_DB_PATH


def resolve(path: str | Path) -> Path:
    p = Path(path)
    return p if p.is_absolute() else ROOT / p


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def load_json(path: str | Path, label: str) -> dict[str, Any]:
    p = resolve(path)
    if not p.exists():
        raise PreflightError(f"missing input {label}: {p}")
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PreflightError(f"invalid JSON in {label}: {exc}") from exc
    if not isinstance(data, dict):
        raise PreflightError(f"{label} must be JSON object")
    return data


def compact_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


def connect_readonly(path: Path) -> sqlite3.Connection:
    if not path.exists():
        raise PreflightError(f"missing SQLite DB: {path}")
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA query_only = ON")
    return con


def table_count(con: sqlite3.Connection, table: str) -> int:
    return int(con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def status_snapshots(con: sqlite3.Connection) -> dict[str, str]:
    specs = {
        "sources_status_hash": "SELECT id, quality_score, privacy_publication_status, duplicate_status FROM sources ORDER BY id",
        "claims_status_hash": "SELECT id, status, publication_decision, contradiction_status FROM claims ORDER BY id",
        "editorial_reviews_hash": "SELECT id, run_id, review_type, status, summary, report_path, created_at FROM editorial_reviews ORDER BY id",
    }
    return {name: sha256_text(compact_json([tuple(r) for r in con.execute(sql).fetchall()])) for name, sql in specs.items()}


def joined(value: Any) -> str:
    if isinstance(value, list):
        return "\n".join(map(str, value))
    return str(value or "")


def require_nonempty_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be non-empty string")
    return value


def require_nonempty_list(value: Any, field: str) -> list[Any]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{field} must be non-empty list")
    return value


def has_chapter_ready_field(obj: Any) -> bool:
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key in CHAPTER_READY_FIELDS:
                return True
            if has_chapter_ready_field(value):
                return True
    elif isinstance(obj, list):
        return any(has_chapter_ready_field(x) for x in obj)
    return False


def require_false_flags(obj: dict[str, Any], label: str) -> None:
    if obj.get("advisory_only") is not True:
        raise PreflightError(f"{label} safety flag invalid: advisory_only")
    for flag in FALSE_FLAGS:
        if obj.get(flag) is not False:
            raise PreflightError(f"{label} safety flag invalid: {flag}")


def require_caveat_dns(obj: dict[str, Any], label: str) -> None:
    if REQUIRED_CAVEAT not in joined(obj.get("required_caveats")):
        raise PreflightError(f"{label} missing required caveat")
    dns = joined(obj.get("do_not_say"))
    if not dns.strip():
        raise PreflightError(f"{label} missing do_not_say guidance")
    for item in REQUIRED_DO_NOT_SAY:
        if item not in dns:
            raise PreflightError(f"{label} do_not_say missing: {item}")


def validate_rebuild_report(report: dict[str, Any]) -> None:
    if report.get("mode") != "llm_rebuild_author_draft_input" or report.get("report_only") is not True:
        raise PreflightError("Run 26 rebuild report mode mismatch")
    if report.get("llm_used") is not True or report.get("provider") != "copilot" or report.get("model") != "gpt-5.5" or report.get("bridge") != "hermes_cli" or report.get("model_profile") != "closed_loop_editorial":
        raise PreflightError("Run 26 report must use GPT-5.5 closed_loop_editorial")
    if not isinstance(report.get("rebuilt_author_draft_inputs"), list):
        raise PreflightError("Run 26 report missing rebuilt_author_draft_inputs")


def validate_candidate_input(pkg: dict[str, Any]) -> None:
    rid = str(pkg.get("rebuilt_input_id") or "unknown")
    require_false_flags(pkg, f"rebuilt input {rid}")
    if pkg.get("rebuilt_input_type") != "enriched_caveat_only_author_draft_input":
        raise PreflightError("rebuilt input type is not eligible")
    if pkg.get("rebuilt_input_decision") != "rebuilt_draft_input_candidate":
        raise PreflightError("rebuilt input decision is not eligible")
    if pkg.get("rebuilt_input_use") != "caveat_only":
        raise PreflightError("rebuilt input use is not eligible")
    require_caveat_dns(pkg, f"rebuilt input {rid}")
    for field in ["evidence_bound_factual_atoms", "narrative_function_suggestions"]:
        require_nonempty_list(pkg.get(field), field)
    require_nonempty_string(pkg.get("why_prior_canary_was_not_useful"), "why_prior_canary_was_not_useful")
    require_nonempty_string(pkg.get("later_canary_instruction_seed"), "later_canary_instruction_seed")
    for field in ["prior_draft_input_id", "prior_draft_canary_id", "source_packet_id", "source_cluster_id"]:
        require_nonempty_string(pkg.get(field), field)
    for field in ["source_note_ids", "source_review_ids", "source_ids", "candidate_source_ids", "provenance_paths"]:
        require_nonempty_list(pkg.get(field), field)
    if has_chapter_ready_field(pkg):
        raise PreflightError("rebuilt input contains chapter-ready prose field")
    if pkg.get("raw_capture_dependency") is True:
        raise PreflightError("rebuilt input raw capture dependency exists")
    if pkg.get("source_context_unclear") is True:
        raise PreflightError("rebuilt input source context unclear")
    if pkg.get("needs_more_sources") is True:
        raise PreflightError("rebuilt input needs more sources")
    if pkg.get("contradiction_review_required") is True:
        raise PreflightError("rebuilt input contradiction review required")
    if pkg.get("safe_reports_only") is True:
        raise PreflightError("rebuilt input safe_reports_only")


def select_rebuilt_inputs(report: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    selected: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for item in report.get("rebuilt_author_draft_inputs", []):
        if not isinstance(item, dict):
            raise PreflightError("rebuilt input must be object")
        try:
            validate_candidate_input(item)
        except Exception as exc:
            # Hard safety flag/caveat/prose issues fail closed. Ordinary non-selection
            # states are preserved as excluded so safe reports can still describe them.
            message = str(exc)
            if any(s in message for s in ["safety flag", "missing required caveat", "missing do_not_say", "evidence_bound_factual_atoms", "narrative_function_suggestions", "later_canary_instruction_seed", "chapter-ready", "raw capture", "source context unclear", "needs more sources", "contradiction", "safe_reports_only"]):
                raise
            cp = dict(item)
            cp["excluded_reason"] = message
            excluded.append(cp)
            continue
        selected.append(dict(item))
    if not selected:
        raise PreflightError("no selected rebuilt inputs for preflight")
    return selected, excluded


def validate_review(review: dict[str, Any], selected_by_id: dict[str, dict[str, Any]]) -> None:
    if not isinstance(review, dict):
        raise ValueError("preflight review must be object")
    for field in REQUIRED_REVIEW_FIELDS:
        if field not in review:
            raise ValueError(f"preflight review missing required field: {field}")
    rid = require_nonempty_string(review.get("rebuilt_input_id"), "rebuilt_input_id")
    if rid not in selected_by_id:
        raise ValueError(f"review references unknown rebuilt_input_id: {rid}")
    src = selected_by_id[rid]
    if review.get("rebuilt_input_type") != src.get("rebuilt_input_type"):
        raise ValueError("rebuilt_input_type mismatch")
    if review.get("rebuilt_input_use") != src.get("rebuilt_input_use"):
        raise ValueError("rebuilt_input_use mismatch")
    for field, allowed in [
        ("preflight_decision", ALLOWED_PREFLIGHT_DECISIONS),
        ("canary_readiness", ALLOWED_CANARY_READINESS),
        ("closed_loop_disposition", ALLOWED_DISPOSITIONS),
        ("recommended_next_stage", ALLOWED_NEXT_STAGES),
    ]:
        value = review.get(field)
        if not isinstance(value, str):
            raise ValueError(f"{field} must be exactly one string enum value")
        if value not in allowed:
            raise ValueError(f"invalid {field}: {value}")
    for field in [
        "usefulness_improvement_assessment",
        "caveat_integrity_assessment",
        "do_not_say_compliance_assessment",
        "prose_containment_assessment",
        "provenance_assessment",
        "residual_risk_assessment",
        "residual_risk",
    ]:
        require_nonempty_string(review.get(field), field)
    for field in ["required_caveats", "do_not_say", "limitations"]:
        require_nonempty_list(review.get(field), field)
    if REQUIRED_CAVEAT not in joined(review.get("required_caveats")):
        raise ValueError("review missing required caveat")
    dns = joined(review.get("do_not_say"))
    for item in REQUIRED_DO_NOT_SAY:
        if item not in dns:
            raise ValueError(f"review do_not_say missing: {item}")
    if review.get("advisory_only") is not True:
        raise ValueError("advisory_only must be true")
    for flag in FALSE_FLAGS:
        if review.get(flag) is not False:
            raise ValueError(f"{flag} must be false")
    decision = review["preflight_decision"]
    readiness = review["canary_readiness"]
    disposition = review["closed_loop_disposition"]
    next_stage = review["recommended_next_stage"]
    if decision == "rebuilt_input_canary_ready":
        if readiness != "ready_for_second_controlled_caveat_only_author_draft_canary" or disposition != "caveat_only" or next_stage != "run_second_controlled_caveat_only_author_draft_canary":
            raise ValueError("rebuilt_input_canary_ready must route to second controlled caveat-only canary with caveat_only disposition")
    if decision == "still_safe_but_too_thin":
        if readiness != "not_ready_still_too_thin":
            raise ValueError("still_safe_but_too_thin readiness mismatch")
        if next_stage not in {"rebuild_author_draft_input_again", "keep_safe_reports_only"}:
            raise ValueError("still_safe_but_too_thin must route only to rebuild_author_draft_input_again or keep_safe_reports_only")
    decision_to_readiness = {
        "safe_reports_only": "not_ready_safe_reports_only",
        "needs_more_sources": "not_ready_needs_more_sources",
        "source_context_unclear": "not_ready_source_context_unclear",
        "exclude_from_authoring": "not_ready_exclude",
        "contradiction_review_required": "not_ready_contradiction_review",
    }
    if decision in decision_to_readiness and readiness != decision_to_readiness[decision]:
        raise ValueError(f"{decision} readiness mismatch")


def make_validator(selected: list[dict[str, Any]]):
    selected_by_id = {str(x["rebuilt_input_id"]): x for x in selected}

    def validator(obj: dict[str, Any]) -> None:
        reviews = obj.get("rebuilt_input_preflight_reviews")
        if not isinstance(reviews, list):
            raise ValueError("LLM JSON must contain rebuilt_input_preflight_reviews list")
        if len(reviews) != len(selected_by_id):
            raise ValueError(f"expected {len(selected_by_id)} preflight review(s), got {len(reviews)}")
        seen: set[str] = set()
        for review in reviews:
            validate_review(review, selected_by_id)
            rid = review["rebuilt_input_id"]
            if rid in seen:
                raise ValueError(f"duplicate rebuilt_input_id: {rid}")
            seen.add(rid)
    return validator


def build_prompt(selected: list[dict[str, Any]], excluded: list[dict[str, Any]], run_id: str) -> str:
    schema = {
        "rebuilt_input_preflight_reviews": [
            {
                "rebuilt_input_id": "string",
                "rebuilt_input_type": "enriched_caveat_only_author_draft_input",
                "rebuilt_input_use": "caveat_only",
                "preflight_decision": "choose exactly ONE string: rebuilt_input_canary_ready | still_safe_but_too_thin | safe_reports_only | needs_more_sources | source_context_unclear | exclude_from_authoring | contradiction_review_required",
                "canary_readiness": "choose exactly ONE allowed readiness string",
                "closed_loop_disposition": "choose exactly ONE allowed disposition string",
                "usefulness_improvement_assessment": "non-empty string",
                "caveat_integrity_assessment": "non-empty string",
                "do_not_say_compliance_assessment": "non-empty string",
                "prose_containment_assessment": "non-empty string",
                "provenance_assessment": "non-empty string",
                "residual_risk_assessment": "non-empty string",
                "required_caveats": [REQUIRED_CAVEAT],
                "do_not_say": REQUIRED_DO_NOT_SAY,
                "limitations": ["non-empty strings"],
                "residual_risk": "non-empty string",
                "recommended_next_stage": "choose exactly ONE allowed next-stage string",
                "advisory_only": True,
                "author_allowed": False,
                "publication_approved": False,
                "eligible_for_claim_insertion": False,
                "eligible_for_authoring": False,
                "eligible_for_publication": False,
                "chapter_update_allowed": False,
            }
        ]
    }
    payload = {
        "run_id": run_id,
        "task": "Run 27 report-only enriched author-draft input preflight gate",
        "selected_rebuilt_inputs": selected,
        "excluded_rebuilt_inputs": excluded,
        "required_caveat": REQUIRED_CAVEAT,
        "required_do_not_say": REQUIRED_DO_NOT_SAY,
        "allowed_preflight_decision_values": sorted(ALLOWED_PREFLIGHT_DECISIONS),
        "allowed_canary_readiness_values": sorted(ALLOWED_CANARY_READINESS),
        "allowed_closed_loop_disposition_values": sorted(ALLOWED_DISPOSITIONS),
        "allowed_recommended_next_stage_values": sorted(ALLOWED_NEXT_STAGES),
        "required_schema": schema,
        "instructions": [
            "Return JSON only. No markdown or prose outside JSON.",
            "Choose exactly ONE string enum value for preflight_decision, canary_readiness, closed_loop_disposition, and recommended_next_stage; do NOT return arrays or objects for these fields.",
            "Preflight/red-team whether the enriched Run 26 input is suitable for a second controlled caveat-only draft canary. Do not generate draft prose or chapter prose.",
            "Assess usefulness improvement versus Run 22B and Run 24: does it provide useful atoms and functional guidance beyond restating the caveat?",
            "Assess caveat integrity, do-not-say compliance, prose containment, provenance completeness, and residual risk.",
            "Even for a positive readiness decision, keep advisory_only=true and every author/publication/claim/chapter flag false.",
            "Do not treat GPT reasoning as human/editor approval. Do not approve authoring, publication, or chapter updates.",
        ],
    }
    return "Return strict JSON matching this schema and input:\n" + json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False)


def safety_flags() -> dict[str, bool]:
    return {
        "advisory_only": True,
        "author_allowed": False,
        "publication_approved": False,
        "eligible_for_claim_insertion": False,
        "eligible_for_authoring": False,
        "eligible_for_publication": False,
        "chapter_update_allowed": False,
        "claims_inserted": False,
        "editorial_reviews_inserted": False,
        "source_notes_written": False,
        "source_registry_promoted": False,
        "raw_content_stored": False,
        "docs_book_modified": False,
        "schema_modified": False,
        "daily_worker_modified": False,
        "gpt55_advisory_is_human_or_editor_approval": False,
        "preflight_is_authoring_approval": False,
        "preflight_is_publication_approval": False,
    }


def build_payload(args: argparse.Namespace) -> dict[str, Any]:
    rebuild_path = resolve(args.rebuild_report)
    report = load_json(rebuild_path, "Run 26 rebuild report")
    validate_rebuild_report(report)
    try:
        profile = load_model_profile(args.reasoning_profile)
    except ModelProfileError as exc:
        raise PreflightError(f"model_profile_error:{exc}") from exc
    selected, excluded = select_rebuilt_inputs(report)
    db = db_path()
    with connect_readonly(db) as con:
        before_counts = {"source_notes": table_count(con, "source_notes"), "claims": table_count(con, "claims"), "editorial_reviews": table_count(con, "editorial_reviews")}
        before_status = status_snapshots(con)
        prompt = build_prompt(selected, excluded, args.run_id)
        try:
            llm = call_high_reasoning_json(
                prompt,
                schema_name="run27_rebuilt_author_input_preflight",
                validator=make_validator(selected),
                provider=args.provider,
                model=args.model,
                timeout_seconds=args.timeout_seconds,
                reasoning_profile=args.reasoning_profile,
            )
        except HighReasoningError as exc:
            raise PreflightError(str(exc.result.get("error") or exc)) from exc
        after_counts = {"source_notes": table_count(con, "source_notes"), "claims": table_count(con, "claims"), "editorial_reviews": table_count(con, "editorial_reviews")}
        after_status = status_snapshots(con)
    reviews = llm["parsed_json"]["rebuilt_input_preflight_reviews"]
    payload = {
        "run_id": args.run_id,
        "generated_at": utc_now(),
        "mode": MODE,
        "input_paths": {
            "rebuild_report": rel(rebuild_path),
            "sqlite_db": rel(db),
        },
        "report_only": True,
        "llm_used": bool(llm.get("llm_used")),
        "reasoning_status": llm.get("reasoning_status"),
        "provider": llm.get("provider") or profile["provider"],
        "model": llm.get("model") or profile["model"],
        "bridge": llm.get("bridge") or profile["bridge"],
        "model_profile": llm.get("model_profile") or profile["profile_name"],
        "strict_json_required": bool(llm.get("strict_json_required", profile["strict_json_required"])),
        "weak_local_fallback_refused": bool(llm.get("weak_local_fallback_refused", True)),
        "selected_rebuilt_input_count": len(selected),
        "reviewed_rebuilt_input_count": len(reviews),
        "excluded_rebuilt_input_count": len(excluded),
        "preflight_decision_counts": dict(Counter(r["preflight_decision"] for r in reviews)),
        "canary_readiness_counts": dict(Counter(r["canary_readiness"] for r in reviews)),
        "closed_loop_disposition_counts": dict(Counter(r["closed_loop_disposition"] for r in reviews)),
        "recommended_next_stage_counts": dict(Counter(r["recommended_next_stage"] for r in reviews)),
        "selected_rebuilt_inputs": selected,
        "excluded_rebuilt_inputs": excluded,
        "rebuilt_input_preflight_reviews": reviews,
        "failed_preflight_checks": [],
        "llm_metadata": {k: llm.get(k) for k in ["ok", "stdout_json_valid", "exit_code", "timed_out", "elapsed_seconds", "stdout_hash", "prompt_hash", "command_shape"]},
        "changed_db": False,
        "changed_source_notes": before_counts["source_notes"] != after_counts["source_notes"],
        "changed_source_registry": False,
        "changed_raw_captures": False,
        "changed_docs_book": False,
        "changed_schema": False,
        "changed_daily_worker": False,
        "claims_inserted": max(0, after_counts["claims"] - before_counts["claims"]),
        "editorial_reviews_inserted": max(0, after_counts["editorial_reviews"] - before_counts["editorial_reviews"]),
        "source_status_changed": before_status["sources_status_hash"] != after_status["sources_status_hash"],
        "claim_status_changed": before_status["claims_status_hash"] != after_status["claims_status_hash"],
        "editorial_status_changed": before_status["editorial_reviews_hash"] != after_status["editorial_reviews_hash"],
        "source_notes_count_before": before_counts["source_notes"],
        "source_notes_count_after": after_counts["source_notes"],
        "claims_count_before": before_counts["claims"],
        "claims_count_after": after_counts["claims"],
        "editorial_reviews_count_before": before_counts["editorial_reviews"],
        "editorial_reviews_count_after": after_counts["editorial_reviews"],
        "safety_flags": safety_flags(),
    }
    if not payload["llm_used"] or payload["reasoning_status"] != "high_reasoning_used":
        raise PreflightError("high reasoning was not used")
    if payload["provider"] != "copilot" or payload["model"] != "gpt-5.5" or payload["bridge"] != "hermes_cli" or payload["model_profile"] != args.reasoning_profile:
        raise PreflightError("unexpected high-reasoning provider/model/bridge/profile")
    if payload["changed_source_notes"] or payload["claims_inserted"] or payload["editorial_reviews_inserted"] or payload["source_status_changed"] or payload["claim_status_changed"] or payload["editorial_status_changed"]:
        raise PreflightError("forbidden DB/status delta detected during report-only preflight")
    return payload


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        f"# Run 27 rebuilt author-input preflight — {payload['run_id']}", "",
        "## Summary", "",
        f"- Report-only: `{payload['report_only']}`",
        f"- GPT-5.5 used: `{payload['llm_used']}`",
        f"- Provider/model/bridge/profile: `{payload['provider']}` / `{payload['model']}` / `{payload['bridge']}` / `{payload['model_profile']}`",
        f"- Selected rebuilt inputs: `{payload['selected_rebuilt_input_count']}`",
        f"- Reviewed rebuilt inputs: `{payload['reviewed_rebuilt_input_count']}`",
        f"- Excluded rebuilt inputs: `{payload['excluded_rebuilt_input_count']}`",
        f"- Preflight decision counts: `{payload['preflight_decision_counts']}`",
        f"- Canary readiness counts: `{payload['canary_readiness_counts']}`",
        f"- Closed-loop disposition counts: `{payload['closed_loop_disposition_counts']}`",
        f"- Recommended next-stage counts: `{payload['recommended_next_stage_counts']}`",
        "", "## Rebuilt inputs reviewed", "",
    ]
    for review in payload["rebuilt_input_preflight_reviews"]:
        lines += [
            f"- rebuilt_input_id: `{review['rebuilt_input_id']}`",
            f"  - preflight_decision: `{review['preflight_decision']}`",
            f"  - canary_readiness: `{review['canary_readiness']}`",
            f"  - closed_loop_disposition: `{review['closed_loop_disposition']}`",
            f"  - recommended_next_stage: `{review['recommended_next_stage']}`",
            "", "### Usefulness improvement", "",
            review["usefulness_improvement_assessment"],
            "", "### Caveat integrity", "",
            review["caveat_integrity_assessment"],
            "", "### Do-not-say compliance", "",
            review["do_not_say_compliance_assessment"],
            "", "### Prose containment", "",
            review["prose_containment_assessment"],
            "", "### Provenance completeness", "",
            review["provenance_assessment"],
            "", "### Residual risks", "",
            review["residual_risk_assessment"],
            "", "### Limitations", "",
            *[f"- {x}" for x in review.get("limitations", [])],
            f"- Residual risk: {review['residual_risk']}", "",
        ]
    lines += [
        "## Why no claims/editorial_reviews/book/status changes were made", "",
        "Run 27 is a report-only advisory preflight. It reads the Run 26 rebuilt input, asks GPT-5.5 for a strict-JSON preflight review, and writes only reports/editorial artifacts. It does not insert claims, editorial reviews, source notes, mutate statuses, alter source_registry/raw captures, or write docs/book.",
        "", "## Why this does not approve authoring or publication", "",
        "A positive preflight decision means only that a later report-only second controlled caveat-only canary may be attempted. It is not human/editor approval, authoring approval, publication approval, claim insertion approval, or chapter-update permission. All approval and eligibility flags remain false.",
        "", "## Recommendation for Run 28", "",
    ]
    if payload["recommended_next_stage_counts"].get("run_second_controlled_caveat_only_author_draft_canary"):
        lines.append("Run 28 may run a second controlled caveat-only author-draft canary as a report-only artifact, preserving all no-publication/no-authoring/no-chapter-update constraints.")
    elif payload["recommended_next_stage_counts"].get("rebuild_author_draft_input_again"):
        lines.append("Run 28 should rebuild author-draft input again rather than generating a canary.")
    else:
        lines.append("Run 28 should follow the closed-loop recommended next stage from this preflight report, without approving authoring or publication.")
    return "\n".join(lines) + "\n"


def write_reports(payload: dict[str, Any], output_dir: Path, suffix: str) -> dict[str, str]:
    out_dir = output_dir if output_dir.is_absolute() else ROOT / output_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{payload['run_id']}-rebuilt-author-input-preflight-{suffix}" if suffix else f"{payload['run_id']}-rebuilt-author-input-preflight"
    json_path = out_dir / f"{stem}.json"
    md_path = out_dir / f"{stem}.md"
    payload["output_paths"] = {"json": rel(json_path), "markdown": rel(md_path)}
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(payload), encoding="utf-8")
    return payload["output_paths"]


def parse_args(argv: list[str]) -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", default=RUN_ID_DEFAULT)
    ap.add_argument("--rebuild-report", default=DEFAULT_RUN26)
    ap.add_argument("--output-dir", default="reports/editorial")
    ap.add_argument("--report-suffix", default="run27")
    ap.add_argument("--reasoning-profile", default="closed_loop_editorial")
    ap.add_argument("--provider", default=None)
    ap.add_argument("--model", default=None)
    ap.add_argument("--timeout-seconds", type=int, default=300)
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        payload = build_payload(args)
        write_reports(payload, resolve(args.output_dir), args.report_suffix)
        print(json.dumps({
            "ok": True,
            "output_paths": payload["output_paths"],
            "selected_rebuilt_input_count": payload["selected_rebuilt_input_count"],
            "reviewed_rebuilt_input_count": payload["reviewed_rebuilt_input_count"],
            "excluded_rebuilt_input_count": payload["excluded_rebuilt_input_count"],
            "preflight_decision_counts": payload["preflight_decision_counts"],
            "canary_readiness_counts": payload["canary_readiness_counts"],
            "closed_loop_disposition_counts": payload["closed_loop_disposition_counts"],
            "recommended_next_stage_counts": payload["recommended_next_stage_counts"],
        }, sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
