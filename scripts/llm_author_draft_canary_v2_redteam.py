#!/usr/bin/env python3
"""Run 29 report-only author-draft canary v2 red-team/usefulness review.

Consumes the Run 28 caveat-only author-draft canary v2 report and uses GPT-5.5
through the closed_loop_editorial profile via the shared strict-JSON Hermes bridge
to red-team safety containment, caveat integrity, do-not-say compliance,
evidence use, provenance sufficiency, usefulness, and residual risk.

This is advisory/report-only: no DB writes, no source_notes, no claims,
no editorial_reviews, no status changes, no docs/book writes, no source registry
writes, no raw captures, no schema changes, and no daily-worker changes.
"""
from __future__ import annotations

import argparse
import json
import os
import re
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
MODE = "llm_author_draft_canary_v2_redteam"
DEFAULT_CANARY_V2_REPORT = f"reports/editorial/{RUN_ID_DEFAULT}-author-draft-canary-v2-run28.json"
REQUIRED_CAVEAT = "Frame narrowly: OpenClaw documentation names Hermes in migration/setup tooling contexts; do not state that Hermes is a runtime dependency or general operating environment without additional sources."
REQUIRED_DO_NOT_SAY_SUBSTRINGS = [
    "runtime dependency of OpenClaw",
    "general operating environment for OpenClaw",
    "requires Hermes for web or phone access",
    "generalize beyond migration/setup/import tooling contexts",
    "factual claim without the caveat",
    "chapter prose before later author/red-team gates pass",
]
FALSE_FLAGS = [
    "author_allowed",
    "publication_approved",
    "eligible_for_claim_insertion",
    "eligible_for_authoring",
    "eligible_for_publication",
    "chapter_update_allowed",
]
REQUIRED_CANARY_FIELDS = [
    "draft_canary_id",
    "rebuilt_input_id",
    "prior_draft_input_id",
    "source_packet_id",
    "source_cluster_id",
    "source_note_ids",
    "source_review_ids",
    "source_ids",
    "candidate_source_ids",
    "draft_canary_type",
    "draft_canary_decision",
    "draft_canary_use",
    "draft_canary_text",
    "word_count",
    "required_caveats",
    "do_not_say",
    "provenance_paths",
    "advisory_only",
    "draft_canary_only",
    "author_allowed",
    "publication_approved",
    "eligible_for_claim_insertion",
    "eligible_for_authoring",
    "eligible_for_publication",
    "chapter_update_allowed",
]
REQUIRED_REVIEW_FIELDS = [
    "draft_canary_id",
    "rebuilt_input_id",
    "prior_draft_input_id",
    "draft_canary_type",
    "draft_canary_use",
    "redteam_decision",
    "canary_usefulness",
    "closed_loop_disposition",
    "safety_containment_assessment",
    "caveat_integrity_assessment",
    "do_not_say_compliance_assessment",
    "evidence_use_assessment",
    "provenance_assessment",
    "usefulness_assessment",
    "residual_risk_assessment",
    "required_caveats",
    "do_not_say",
    "limitations",
    "residual_risk",
    "recommended_next_stage",
    "advisory_only",
    "draft_canary_only",
    "author_allowed",
    "publication_approved",
    "eligible_for_claim_insertion",
    "eligible_for_authoring",
    "eligible_for_publication",
    "chapter_update_allowed",
]
ALLOWED_REDTEAM_DECISIONS = {
    "draft_canary_v2_passed",
    "safe_but_not_useful",
    "safe_reports_only",
    "needs_more_sources",
    "needs_better_authoring_input",
    "source_context_unclear",
    "exclude_from_authoring",
    "contradiction_review_required",
}
ALLOWED_USEFULNESS = {
    "useful_as_caveat_only_seed",
    "improved_but_still_thin",
    "safe_but_too_thin",
    "not_useful_restates_caveat_only",
    "not_ready_needs_more_sources",
    "not_ready_source_context_unclear",
    "not_ready_exclude",
    "not_ready_contradiction_review",
}
ALLOWED_DISPOSITIONS = {
    "caveat_only",
    "safe_reports_only",
    "needs_more_sources",
    "needs_better_authoring_input",
    "source_context_unclear",
    "exclude_from_pipeline",
    "contradiction_review_required",
}
ALLOWED_NEXT_STAGES = {
    "build_constrained_authoring_metadata_candidate",
    "keep_safe_reports_only",
    "rebuild_author_draft_input_again",
    "run_additional_source_collection",
    "run_source_context_review",
    "exclude_from_pipeline",
    "run_contradiction_review",
}
BAD_TEXT_PATTERNS = [
    (re.compile(r"\bHermes\s+is\s+a\s+runtime\s+dependency\s+of\s+OpenClaw\b", re.I), "runtime dependency claim"),
    (re.compile(r"\bHermes\s+is\s+the\s+general\s+operating\s+environment\s+for\s+OpenClaw\b", re.I), "general operating environment claim"),
    (re.compile(r"\bOpenClaw\s+requires\s+Hermes\s+for\s+web\s+or\s+phone\s+access\b", re.I), "web/phone access requirement claim"),
    (re.compile(r"\bapproved\s+for\s+publication\b|\bpublication\s+approved\b", re.I), "publication approval implication"),
    (re.compile(r"\bchapter[- ]ready\b|\bready\s+for\s+chapter\b", re.I), "chapter readiness implication"),
    (re.compile(r"\bbeyond\s+migration/setup/import\s+tooling\b|\bbeyond\s+migration\s+setup\s+import\s+tooling\b|\bbroadly\s+used\s+across\s+OpenClaw\b", re.I), "overgeneralization beyond migration/setup/import tooling"),
]
SECRET_PATTERNS = ["api key", "oauth", "cookie", "bearer token", "password", "secret key", "private key"]


class CanaryV2RedteamError(RuntimeError):
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
        raise CanaryV2RedteamError(f"missing input {label}: {p}")
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CanaryV2RedteamError(f"invalid JSON in {label}: {exc}") from exc
    if not isinstance(data, dict):
        raise CanaryV2RedteamError(f"{label} must be JSON object")
    return data


def compact_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


def connect_readonly(path: Path) -> sqlite3.Connection:
    if not path.exists():
        raise CanaryV2RedteamError(f"missing SQLite DB: {path}")
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


def require_str(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be non-empty string")
    return value


def require_list(value: Any, field: str) -> list[Any]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{field} must be non-empty list")
    return value


def validate_canary_v2_report(report: dict[str, Any]) -> None:
    if report.get("mode") != "llm_author_draft_canary_v2":
        raise CanaryV2RedteamError("Run 28 canary v2 report mode mismatch")
    if report.get("report_only") is not True or report.get("llm_used") is not True:
        raise CanaryV2RedteamError("Run 28 canary v2 report must be report_only with GPT-5.5 used")
    if report.get("provider") != "copilot" or report.get("model") != "gpt-5.5" or report.get("bridge") != "hermes_cli" or report.get("model_profile") != "closed_loop_editorial":
        raise CanaryV2RedteamError("Run 28 canary v2 report has unexpected model/profile metadata")
    if not isinstance(report.get("draft_canaries"), list):
        raise CanaryV2RedteamError("Run 28 canary v2 report missing draft_canaries list")


def text_without_negative_guardrails(text: str) -> str:
    cleaned = text.replace(REQUIRED_CAVEAT, " ")
    cleaned = re.sub(r"do not (say|state|claim)[^.?!]*(runtime dependency|general operating environment|requires hermes for web or phone access)[^.?!]*[.?!]", " ", cleaned, flags=re.I)
    return cleaned


def validate_caveat_and_dns(obj: dict[str, Any], label: str) -> None:
    caveats = obj.get("required_caveats")
    if not isinstance(caveats, list) or REQUIRED_CAVEAT not in joined(caveats):
        raise CanaryV2RedteamError(f"{label} missing required caveat")
    dns = obj.get("do_not_say")
    if not isinstance(dns, list) or not dns:
        raise CanaryV2RedteamError(f"{label} missing do_not_say guidance")
    dns_text = joined(dns)
    for required in REQUIRED_DO_NOT_SAY_SUBSTRINGS:
        if required not in dns_text:
            raise CanaryV2RedteamError(f"{label} do_not_say missing required guidance: {required}")


def validate_selected_canary(canary: dict[str, Any]) -> None:
    if not isinstance(canary, dict):
        raise CanaryV2RedteamError("draft canary must be object")
    for field in REQUIRED_CANARY_FIELDS:
        if field not in canary:
            raise CanaryV2RedteamError(f"draft canary missing required field: {field}")
    cid = str(canary.get("draft_canary_id", "unknown"))
    if canary.get("advisory_only") is not True:
        raise CanaryV2RedteamError(f"draft canary {cid} safety flag invalid: advisory_only")
    if canary.get("draft_canary_only") is not True:
        raise CanaryV2RedteamError(f"draft canary {cid} draft_canary_only must be true")
    for flag in FALSE_FLAGS:
        if canary.get(flag) is not False:
            raise CanaryV2RedteamError(f"draft canary {cid} safety flag invalid: {flag}")
    if canary.get("draft_canary_type") != "caveat_only_author_draft_canary_v2":
        raise CanaryV2RedteamError(f"draft canary {cid} type mismatch")
    if canary.get("draft_canary_decision") != "draft_canary_v2_created":
        raise CanaryV2RedteamError(f"draft canary {cid} decision mismatch")
    if canary.get("draft_canary_use") != "caveat_only":
        raise CanaryV2RedteamError(f"draft canary {cid} use mismatch")
    if canary.get("raw_capture_dependency") is True or canary.get("raw_content_stored") is True:
        raise CanaryV2RedteamError(f"draft canary {cid} has forbidden raw capture dependency")
    validate_caveat_and_dns(canary, f"draft canary {cid}")
    for field in ["source_note_ids", "source_review_ids", "source_ids", "candidate_source_ids", "provenance_paths"]:
        require_list(canary.get(field), field)
    text = require_str(canary.get("draft_canary_text"), "draft_canary_text")
    wc = len(re.findall(r"\b\S+\b", text))
    if wc > 110 or (isinstance(canary.get("word_count"), int) and canary.get("word_count") > 110):
        raise CanaryV2RedteamError("draft_canary_text exceeds 110 words")
    if REQUIRED_CAVEAT not in text:
        raise CanaryV2RedteamError("draft_canary_text missing required caveat")
    lower = text.lower()
    if any(secret in lower for secret in SECRET_PATTERNS):
        raise CanaryV2RedteamError("draft_canary_text includes secret or private data")
    checked = text_without_negative_guardrails(text)
    for pattern, reason in BAD_TEXT_PATTERNS:
        if pattern.search(checked):
            raise CanaryV2RedteamError(f"draft_canary_text violation: {reason}")


def select_draft_canaries(report: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    selected: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for canary in report.get("draft_canaries", []):
        validate_selected_canary(canary)
        selected.append(canary)
    return selected, excluded


def validate_review(review: dict[str, Any], selected_by_id: dict[str, dict[str, Any]]) -> None:
    if not isinstance(review, dict):
        raise ValueError("red-team review must be object")
    for field in REQUIRED_REVIEW_FIELDS:
        if field not in review:
            raise ValueError(f"red-team review missing required field: {field}")
    cid = require_str(review.get("draft_canary_id"), "draft_canary_id")
    if cid not in selected_by_id:
        raise ValueError(f"review references unknown selected draft canary: {cid}")
    source = selected_by_id[cid]
    if review.get("rebuilt_input_id") != source.get("rebuilt_input_id"):
        raise ValueError("review rebuilt_input_id mismatch")
    if review.get("prior_draft_input_id") != source.get("prior_draft_input_id"):
        raise ValueError("review prior_draft_input_id mismatch")
    if review.get("draft_canary_type") != "caveat_only_author_draft_canary_v2" or review.get("draft_canary_use") != "caveat_only":
        raise ValueError("review must preserve caveat-only canary v2 type/use")
    for field, allowed in [
        ("redteam_decision", ALLOWED_REDTEAM_DECISIONS),
        ("canary_usefulness", ALLOWED_USEFULNESS),
        ("closed_loop_disposition", ALLOWED_DISPOSITIONS),
        ("recommended_next_stage", ALLOWED_NEXT_STAGES),
    ]:
        value = review.get(field)
        if not isinstance(value, str):
            raise ValueError(f"{field} must be exactly one string enum value")
        if value not in allowed:
            raise ValueError(f"invalid {field}: {value}")
    for field in [
        "safety_containment_assessment",
        "caveat_integrity_assessment",
        "do_not_say_compliance_assessment",
        "evidence_use_assessment",
        "provenance_assessment",
        "usefulness_assessment",
        "residual_risk_assessment",
        "residual_risk",
    ]:
        require_str(review.get(field), field)
    for field in ["required_caveats", "do_not_say", "limitations"]:
        require_list(review.get(field), field)
    if review.get("advisory_only") is not True or review.get("draft_canary_only") is not True:
        raise ValueError("review advisory_only and draft_canary_only must be true")
    for flag in FALSE_FLAGS:
        if review.get(flag) is not False:
            raise ValueError(f"review {flag} must be false")
    if REQUIRED_CAVEAT not in joined(review.get("required_caveats")):
        raise ValueError("review missing required caveat")
    dns = joined(review.get("do_not_say"))
    for required in REQUIRED_DO_NOT_SAY_SUBSTRINGS:
        if required not in dns:
            raise ValueError(f"review do_not_say missing required guidance: {required}")
    decision = review["redteam_decision"]
    next_stage = review["recommended_next_stage"]
    if decision == "draft_canary_v2_passed":
        if review.get("author_allowed") is not False or review.get("eligible_for_authoring") is not False or review.get("chapter_update_allowed") is not False:
            raise ValueError("draft_canary_v2_passed still requires false authoring/chapter flags")
    if decision == "safe_but_not_useful" and next_stage not in {"rebuild_author_draft_input_again", "keep_safe_reports_only"}:
        raise ValueError("safe_but_not_useful must route to rebuild_author_draft_input_again or keep_safe_reports_only")
    if decision == "needs_more_sources" and next_stage != "run_additional_source_collection":
        raise ValueError("needs_more_sources must route only to run_additional_source_collection")
    if decision == "source_context_unclear" and next_stage != "run_source_context_review":
        raise ValueError("source_context_unclear must route only to run_source_context_review")


def make_validator(selected: list[dict[str, Any]]):
    selected_by_id = {str(c["draft_canary_id"]): c for c in selected}

    def validator(obj: dict[str, Any]) -> None:
        reviews = obj.get("draft_canary_v2_redteam_reviews")
        if not isinstance(reviews, list):
            raise ValueError("LLM JSON must contain draft_canary_v2_redteam_reviews list")
        if len(reviews) != len(selected_by_id):
            raise ValueError(f"expected {len(selected_by_id)} red-team review(s), got {len(reviews)}")
        seen: set[str] = set()
        for review in reviews:
            validate_review(review, selected_by_id)
            cid = review["draft_canary_id"]
            if cid in seen:
                raise ValueError(f"duplicate draft_canary_id review: {cid}")
            seen.add(cid)

    return validator


def build_prompt(selected: list[dict[str, Any]], excluded: list[dict[str, Any]], run_id: str, supporting_inputs: dict[str, Any]) -> str:
    schema = {
        "draft_canary_v2_redteam_reviews": [
            {
                "draft_canary_id": "string from selected_draft_canaries",
                "rebuilt_input_id": "string from selected_draft_canaries",
                "prior_draft_input_id": "string from selected_draft_canaries",
                "draft_canary_type": "caveat_only_author_draft_canary_v2",
                "draft_canary_use": "caveat_only",
                "redteam_decision": "draft_canary_v2_passed | safe_but_not_useful | safe_reports_only | needs_more_sources | needs_better_authoring_input | source_context_unclear | exclude_from_authoring | contradiction_review_required",
                "canary_usefulness": "useful_as_caveat_only_seed | improved_but_still_thin | safe_but_too_thin | not_useful_restates_caveat_only | not_ready_needs_more_sources | not_ready_source_context_unclear | not_ready_exclude | not_ready_contradiction_review",
                "closed_loop_disposition": "caveat_only | safe_reports_only | needs_more_sources | needs_better_authoring_input | source_context_unclear | exclude_from_pipeline | contradiction_review_required",
                "safety_containment_assessment": "single non-empty string",
                "caveat_integrity_assessment": "single non-empty string",
                "do_not_say_compliance_assessment": "single non-empty string",
                "evidence_use_assessment": "single non-empty string",
                "provenance_assessment": "single non-empty string",
                "usefulness_assessment": "single non-empty string",
                "residual_risk_assessment": "single non-empty string",
                "required_caveats": [REQUIRED_CAVEAT],
                "do_not_say": ["all hard do-not-say strings"],
                "limitations": ["strings"],
                "residual_risk": "single non-empty string",
                "recommended_next_stage": "build_constrained_authoring_metadata_candidate | keep_safe_reports_only | rebuild_author_draft_input_again | run_additional_source_collection | run_source_context_review | exclude_from_pipeline | run_contradiction_review",
                "advisory_only": True,
                "draft_canary_only": True,
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
        "task": "Run 29 report-only author-draft canary v2 red-team, containment, and usefulness review",
        "selected_draft_canaries": selected,
        "excluded_draft_canaries": excluded,
        "supporting_inputs_summary": supporting_inputs,
        "required_caveat": REQUIRED_CAVEAT,
        "allowed_redteam_decision_values": sorted(ALLOWED_REDTEAM_DECISIONS),
        "allowed_canary_usefulness_values": sorted(ALLOWED_USEFULNESS),
        "allowed_closed_loop_disposition_values": sorted(ALLOWED_DISPOSITIONS),
        "allowed_recommended_next_stage_values": sorted(ALLOWED_NEXT_STAGES),
        "required_schema": schema,
        "instructions": [
            "Return JSON only. No markdown, no prose outside JSON.",
            "Red-team safety containment, caveat integrity, do-not-say compliance, overclaiming, evidence-use correctness, provenance sufficiency, residual risk, prose-promotion risk, and usefulness versus Run 24.",
            "Do not force a positive outcome; choose from the allowed enums based on the canary.",
            "If the canary passes, it is safe/useful only for another constrained metadata stage, not authoring approval, publication approval, claim insertion, or chapter update.",
            "Always set advisory_only=true, draft_canary_only=true, author_allowed=false, publication_approved=false, eligible_for_claim_insertion=false, eligible_for_authoring=false, eligible_for_publication=false, chapter_update_allowed=false.",
            "safe_but_not_useful may route only to rebuild_author_draft_input_again or keep_safe_reports_only.",
            "needs_more_sources may route only to run_additional_source_collection.",
            "source_context_unclear may route only to run_source_context_review.",
            "Do not include secrets, tokens, cookies, OAuth material, API keys, private data, raw captures, or chapter-ready prose.",
        ],
    }
    return "Return strict JSON matching this schema and input:\n" + json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False)


def safety_flags() -> dict[str, bool]:
    return {
        "advisory_only": True,
        "draft_canary_only": True,
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
        "draft_canary_is_publishable_material": False,
        "draft_canary_is_chapter_update": False,
        "draft_canary_is_chapter_ready_prose": False,
    }


def load_supporting_inputs(paths: list[str]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for path in paths:
        p = resolve(path)
        if not p.exists():
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            summary[rel(p)] = {
                "mode": data.get("mode"),
                "report_only": data.get("report_only"),
                "provider": data.get("provider"),
                "model": data.get("model"),
                "counts": {k: v for k, v in data.items() if k.endswith("_count") or k.endswith("_counts")},
            }
        except Exception:
            summary[rel(p)] = {"loaded": False}
    return summary


def build_payload(args: argparse.Namespace) -> dict[str, Any]:
    canary_path = resolve(args.canary_v2_report)
    canary_report = load_json(canary_path, "Run 28 canary v2 report")
    validate_canary_v2_report(canary_report)
    try:
        profile = load_model_profile(args.reasoning_profile)
    except ModelProfileError as exc:
        raise CanaryV2RedteamError(f"model_profile_error:{exc}") from exc
    selected, excluded = select_draft_canaries(canary_report)
    if not selected:
        raise CanaryV2RedteamError("no selected Run 28 draft canary v2 objects for red-team")
    supporting = load_supporting_inputs(args.supporting_input)
    db = db_path()
    with connect_readonly(db) as con:
        before_counts = {"source_notes": table_count(con, "source_notes"), "claims": table_count(con, "claims"), "editorial_reviews": table_count(con, "editorial_reviews")}
        before_status = status_snapshots(con)
        prompt = build_prompt(selected, excluded, args.run_id, supporting)
        try:
            llm = call_high_reasoning_json(
                prompt,
                schema_name="run29_author_draft_canary_v2_redteam",
                validator=make_validator(selected),
                provider=args.provider,
                model=args.model,
                timeout_seconds=args.timeout_seconds,
                reasoning_profile=args.reasoning_profile,
            )
        except HighReasoningError as exc:
            raise CanaryV2RedteamError(str(exc.result.get("error") or exc)) from exc
        after_counts = {"source_notes": table_count(con, "source_notes"), "claims": table_count(con, "claims"), "editorial_reviews": table_count(con, "editorial_reviews")}
        after_status = status_snapshots(con)
    reviews = llm["parsed_json"]["draft_canary_v2_redteam_reviews"]
    payload = {
        "run_id": args.run_id,
        "generated_at": utc_now(),
        "mode": MODE,
        "input_paths": {"canary_v2_report": rel(canary_path), "supporting_inputs": list(supporting.keys()), "sqlite_db": rel(db)},
        "report_only": True,
        "llm_used": bool(llm.get("llm_used")),
        "reasoning_status": llm.get("reasoning_status"),
        "provider": llm.get("provider") or profile["provider"],
        "model": llm.get("model") or profile["model"],
        "bridge": llm.get("bridge") or profile["bridge"],
        "model_profile": llm.get("model_profile") or profile["profile_name"],
        "strict_json_required": bool(llm.get("strict_json_required", profile["strict_json_required"])),
        "weak_local_fallback_refused": bool(llm.get("weak_local_fallback_refused", True)),
        "selected_draft_canary_count": len(selected),
        "reviewed_draft_canary_count": len(reviews),
        "excluded_draft_canary_count": len(excluded),
        "redteam_decision_counts": dict(Counter(r["redteam_decision"] for r in reviews)),
        "canary_usefulness_counts": dict(Counter(r["canary_usefulness"] for r in reviews)),
        "closed_loop_disposition_counts": dict(Counter(r["closed_loop_disposition"] for r in reviews)),
        "recommended_next_stage_counts": dict(Counter(r["recommended_next_stage"] for r in reviews)),
        "selected_draft_canaries": selected,
        "excluded_draft_canaries": excluded,
        "draft_canary_v2_redteam_reviews": reviews,
        "failed_redteam_checks": [],
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
        raise CanaryV2RedteamError("high reasoning was not used")
    if payload["provider"] != "copilot" or payload["model"] != "gpt-5.5" or payload["bridge"] != "hermes_cli" or payload["model_profile"] != args.reasoning_profile:
        raise CanaryV2RedteamError("unexpected high-reasoning provider/model/bridge/profile")
    if payload["changed_source_notes"] or payload["claims_inserted"] or payload["editorial_reviews_inserted"] or payload["source_status_changed"] or payload["claim_status_changed"] or payload["editorial_status_changed"]:
        raise CanaryV2RedteamError("forbidden DB/status delta detected during report-only canary v2 red-team")
    return payload


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        f"# Run 29 author-draft canary v2 red-team — {payload['run_id']}",
        "",
        "## Summary",
        "",
        f"- Report-only: `{payload['report_only']}`",
        f"- GPT-5.5 used: `{payload['llm_used']}`",
        f"- Provider/model/bridge/profile: `{payload['provider']}` / `{payload['model']}` / `{payload['bridge']}` / `{payload['model_profile']}`",
        f"- Selected draft canaries: `{payload['selected_draft_canary_count']}`",
        f"- Reviewed draft canaries: `{payload['reviewed_draft_canary_count']}`",
        f"- Excluded draft canaries: `{payload['excluded_draft_canary_count']}`",
        "",
        "## Red-team decisions",
        "",
    ]
    for r in payload["draft_canary_v2_redteam_reviews"]:
        lines += [
            f"- draft_canary_id: `{r['draft_canary_id']}`",
            f"  - redteam_decision: `{r['redteam_decision']}`",
            f"  - canary_usefulness: `{r['canary_usefulness']}`",
            f"  - closed_loop_disposition: `{r['closed_loop_disposition']}`",
            f"  - recommended_next_stage: `{r['recommended_next_stage']}`",
            "",
            "### Safety containment",
            "",
            r["safety_containment_assessment"],
            "",
            "### Caveat integrity",
            "",
            r["caveat_integrity_assessment"],
            "",
            "### Do-not-say compliance",
            "",
            r["do_not_say_compliance_assessment"],
            "",
            "### Evidence-use correctness",
            "",
            r["evidence_use_assessment"],
            "",
            "### Provenance sufficiency",
            "",
            r["provenance_assessment"],
            "",
            "### Usefulness versus Run 24",
            "",
            r["usefulness_assessment"],
            "",
            "### Residual risks",
            "",
            r["residual_risk_assessment"],
            "",
        ]
    lines += [
        "## Why no claims/editorial_reviews/book/status changes were made",
        "",
        "This is advisory/report-only. It does not write `docs/book`, does not create chapter-ready prose, does not insert claims, editorial_reviews, or source_notes, does not modify source/claim/editorial statuses, and does not modify source_registry, raw captures, schema, or daily worker code.",
        "",
        "## Why this does not approve authoring or publication",
        "",
        "GPT-5.5 output is advisory and is not human/editor approval. All reviews must keep `author_allowed=false`, `publication_approved=false`, `eligible_for_claim_insertion=false`, `eligible_for_authoring=false`, `eligible_for_publication=false`, and `chapter_update_allowed=false`, even when the canary passes containment checks.",
        "",
        "## Recommendation for Run 30",
        "",
        "Follow the Run 29 recommended next-stage counts. If the canary passes, Run 30 should be a constrained authoring-metadata candidate stage only, still report-only and non-publication. If it remains thin or unclear, rebuild input, collect sources, or run source-context review as directed.",
    ]
    return "\n".join(lines) + "\n"


def write_reports(payload: dict[str, Any], output_dir: Path, suffix: str) -> dict[str, str]:
    out_dir = output_dir if output_dir.is_absolute() else ROOT / output_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{payload['run_id']}-author-draft-canary-v2-redteam-{suffix}" if suffix else f"{payload['run_id']}-author-draft-canary-v2-redteam"
    json_path = out_dir / f"{stem}.json"
    md_path = out_dir / f"{stem}.md"
    payload["output_paths"] = {"json": rel(json_path), "markdown": rel(md_path)}
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(payload), encoding="utf-8")
    return payload["output_paths"]


def parse_args(argv: list[str]) -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", default=RUN_ID_DEFAULT)
    ap.add_argument("--canary-v2-report", default=DEFAULT_CANARY_V2_REPORT)
    ap.add_argument("--output-dir", default="reports/editorial")
    ap.add_argument("--report-suffix", default="run29")
    ap.add_argument("--reasoning-profile", default="closed_loop_editorial")
    ap.add_argument("--provider", default=None)
    ap.add_argument("--model", default=None)
    ap.add_argument("--timeout-seconds", type=int, default=300)
    ap.add_argument(
        "--supporting-input",
        action="append",
        default=[
            "reports/editorial/citation-pipeline-test-20260612-rebuilt-author-input-preflight-run27.json",
            "reports/editorial/citation-pipeline-test-20260612-author-draft-input-rebuild-run26.json",
            "reports/editorial/citation-pipeline-test-20260612-author-draft-canary-redteam-run25.json",
            "reports/editorial/citation-pipeline-test-20260612-author-draft-canary-run24.json",
            "reports/editorial/citation-pipeline-test-20260612-author-draft-input-preflight-run23.json",
            "reports/editorial/citation-pipeline-test-20260612-author-draft-input-run22b.json",
            "reports/editorial/citation-pipeline-test-20260612-closed-loop-state-machine-run22a.json",
            "reports/editorial/citation-pipeline-test-20260612-packet-redteam-gate-run21.json",
            "reports/editorial/citation-pipeline-test-20260612-narrative-packet-candidates-run20.json",
            "reports/editorial/citation-pipeline-test-20260612-cluster-quality-gate-run19.json",
            "reports/editorial/citation-pipeline-test-20260612-research-object-clusters-run18.json",
            "reports/editorial/citation-pipeline-test-20260612-downstream-eligibility-manifest-run17.json",
            "reports/editorial/citation-pipeline-test-20260612-persisted-source-support-rereview-notes-run16.json",
            "reports/editorial/citation-pipeline-test-20260612-source-support-rereview-run15.json",
            "config/closed_loop_state_machine.json",
            "config/reasoning_models.json",
        ],
    )
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        payload = build_payload(args)
        write_reports(payload, resolve(args.output_dir), args.report_suffix)
        print(json.dumps({
            "ok": True,
            "output_paths": payload["output_paths"],
            "selected_draft_canary_count": payload["selected_draft_canary_count"],
            "reviewed_draft_canary_count": payload["reviewed_draft_canary_count"],
            "excluded_draft_canary_count": payload["excluded_draft_canary_count"],
            "redteam_decision_counts": payload["redteam_decision_counts"],
            "canary_usefulness_counts": payload["canary_usefulness_counts"],
            "closed_loop_disposition_counts": payload["closed_loop_disposition_counts"],
            "recommended_next_stage_counts": payload["recommended_next_stage_counts"],
        }, sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
