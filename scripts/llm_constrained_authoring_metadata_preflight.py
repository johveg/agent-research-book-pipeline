#!/usr/bin/env python3
"""Run 31 report-only constrained authoring-metadata preflight/red-team gate.

Consumes the Run 30 constrained authoring-metadata report and uses GPT-5.5
through the closed_loop_editorial profile via the shared strict-JSON Hermes bridge
to preflight/red-team metadata containment, caveat integrity, do-not-say
compliance, evidence use, provenance, usefulness as metadata, and residual risk.

This is advisory/report-only: no author prose, no chapter prose, no docs/book
writes, no DB persistence, no claims/editorial_reviews/source_notes, no status
changes, no source_registry/raw/schema/daily-worker mutation, and no approval of
authoring, publication, claim insertion, or chapter updates.
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
MODE = "llm_constrained_authoring_metadata_preflight"
DEFAULT_METADATA_REPORT = f"reports/editorial/{RUN_ID_DEFAULT}-constrained-authoring-metadata-run30.json"
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
REQUIRED_METADATA_FIELDS = [
    "metadata_id",
    "draft_canary_id",
    "rebuilt_input_id",
    "prior_draft_input_id",
    "metadata_type",
    "metadata_decision",
    "metadata_use",
    "canary_usefulness",
    "target_chapter_status",
    "required_caveats",
    "do_not_say",
    "unsupported_inferences",
    "promotion_blockers",
    "provenance_paths",
    "thinness_warning",
    "source_review_ids",
    "source_note_ids",
    "source_packet_id",
    "source_cluster_id",
    "advisory_only",
    "author_allowed",
    "publication_approved",
    "eligible_for_claim_insertion",
    "eligible_for_authoring",
    "eligible_for_publication",
    "chapter_update_allowed",
]
REQUIRED_REVIEW_FIELDS = [
    "metadata_id",
    "draft_canary_id",
    "rebuilt_input_id",
    "prior_draft_input_id",
    "metadata_type",
    "metadata_use",
    "preflight_decision",
    "metadata_readiness",
    "closed_loop_disposition",
    "metadata_containment_assessment",
    "caveat_integrity_assessment",
    "do_not_say_compliance_assessment",
    "evidence_use_assessment",
    "provenance_assessment",
    "usefulness_as_metadata_assessment",
    "residual_risk_assessment",
    "required_caveats",
    "do_not_say",
    "unsupported_inferences",
    "promotion_blockers",
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
ALLOWED_PREFLIGHT_DECISIONS = {
    "metadata_preflight_passed",
    "safe_but_too_thin",
    "safe_reports_only",
    "needs_more_sources",
    "needs_better_authoring_metadata",
    "source_context_unclear",
    "exclude_from_authoring",
    "contradiction_review_required",
}
ALLOWED_METADATA_READINESS = {
    "ready_for_promotion_contract_update",
    "ready_for_constrained_authoring_context_candidate",
    "not_ready_still_too_thin",
    "not_ready_safe_reports_only",
    "not_ready_needs_more_sources",
    "not_ready_needs_better_metadata",
    "not_ready_source_context_unclear",
    "not_ready_exclude",
    "not_ready_contradiction_review",
}
ALLOWED_DISPOSITIONS = {
    "caveat_only",
    "safe_reports_only",
    "needs_more_sources",
    "needs_better_authoring_metadata",
    "source_context_unclear",
    "exclude_from_pipeline",
    "contradiction_review_required",
}
ALLOWED_NEXT_STAGES = {
    "update_closed_loop_promotion_contract_for_authoring_metadata",
    "build_constrained_authoring_context_candidate",
    "rebuild_authoring_metadata",
    "keep_safe_reports_only",
    "run_additional_source_collection",
    "run_source_context_review",
    "exclude_from_pipeline",
    "run_contradiction_review",
}
DISALLOWED_PROSE_KEYS = {
    "new_draft_prose",
    "draft_prose",
    "author_prose",
    "publishable_paragraph",
    "chapter_prose",
    "chapter_ready_prose",
    "final_prose",
    "draft_paragraph",
    "paragraph",
    "chapter_ready_text",
    "book_text",
    "citation_resolved_chapter_text",
}
BAD_TEXT_PATTERNS = [
    (re.compile(r"\bHermes\s+is\s+a\s+runtime\s+dependency\s+of\s+OpenClaw\b", re.I), "runtime dependency claim"),
    (re.compile(r"\bHermes\s+is\s+the\s+general\s+operating\s+environment\s+for\s+OpenClaw\b", re.I), "general operating environment claim"),
    (re.compile(r"\bOpenClaw\s+requires\s+Hermes\s+for\s+web\s+or\s+phone\s+access\b", re.I), "web/phone access requirement claim"),
    (re.compile(r"\bapproved\s+for\s+publication\b|\bpublication\s+approved\b", re.I), "publication approval implication"),
    (re.compile(r"\bapproved\s+for\s+authoring\b|\bauthoring\s+approved\b", re.I), "authoring approval implication"),
    (re.compile(r"\bchapter[- ]ready\b|\bready\s+for\s+chapter\b", re.I), "chapter readiness implication"),
]
SECRET_PATTERNS = ["api key", "oauth", "cookie", "bearer token", "password", "secret key", "private key"]


class MetadataPreflightError(RuntimeError):
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
        raise MetadataPreflightError(f"missing input {label}: {p}")
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise MetadataPreflightError(f"invalid JSON in {label}: {exc}") from exc
    if not isinstance(data, dict):
        raise MetadataPreflightError(f"{label} must be JSON object")
    return data


def compact_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


def connect_readonly(path: Path) -> sqlite3.Connection:
    if not path.exists():
        raise MetadataPreflightError(f"missing SQLite DB: {path}")
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


def validate_metadata_report(report: dict[str, Any]) -> None:
    if report.get("mode") != "build_constrained_authoring_metadata":
        raise MetadataPreflightError("Run 30 constrained metadata report mode mismatch")
    if report.get("report_only") is not True or report.get("llm_used") is not False:
        raise MetadataPreflightError("Run 30 constrained metadata report must be deterministic report_only")
    if not isinstance(report.get("constrained_authoring_metadata_candidates"), list):
        raise MetadataPreflightError("Run 30 report missing constrained_authoring_metadata_candidates list")
    safety = report.get("safety_flags")
    if not isinstance(safety, dict):
        raise MetadataPreflightError("Run 30 report missing safety_flags")
    expected = {
        "advisory_only": True,
        "metadata_only": True,
        "new_author_prose_created": False,
        "chapter_ready_prose_created": False,
        "author_allowed": False,
        "publication_approved": False,
        "eligible_for_claim_insertion": False,
        "eligible_for_authoring": False,
        "eligible_for_publication": False,
        "chapter_update_allowed": False,
    }
    for key, value in expected.items():
        if safety.get(key) is not value:
            raise MetadataPreflightError(f"Run 30 report safety flag invalid: {key}")


def validate_caveat_and_dns(obj: dict[str, Any], label: str) -> None:
    caveats = obj.get("required_caveats")
    if not isinstance(caveats, list) or REQUIRED_CAVEAT not in joined(caveats):
        raise MetadataPreflightError(f"{label} missing required caveat")
    dns = obj.get("do_not_say")
    if not isinstance(dns, list) or not dns:
        raise MetadataPreflightError(f"{label} missing do_not_say guidance")
    dns_text = joined(dns)
    for required in REQUIRED_DO_NOT_SAY_SUBSTRINGS:
        if required not in dns_text:
            raise MetadataPreflightError(f"{label} do_not_say missing required guidance: {required}")


def text_without_negative_guardrails(text: str) -> str:
    cleaned = text.replace(REQUIRED_CAVEAT, " ")
    cleaned = re.sub(r"\bno\s+(new\s+)?(draft|author|chapter|chapter-ready|publishable)[^.?!]*(prose|wording|paragraph|text)[^.?!]*[.?!]", " ", cleaned, flags=re.I)
    cleaned = re.sub(r"\bno\s+(authoring|publication|chapter-update|claim insertion)[^.?!]*(approval|permission|request|allowed|granted)[^.?!]*[.?!]", " ", cleaned, flags=re.I)
    cleaned = re.sub(r"\bdo not (say|state|claim|use|generalize)[^.?!]*(runtime dependency|general operating environment|requires hermes for web or phone access|chapter prose|factual claim)[^.?!]*[.?!]", " ", cleaned, flags=re.I)
    return cleaned


def scan_forbidden_text(obj: dict[str, Any], label: str) -> None:
    # Negative-boundary lists intentionally contain strings like
    # "Hermes is a runtime dependency..." as unsupported inferences / do-not-say
    # guardrails.  Do not treat those guardrails as affirmative claims; scan the
    # metadata-bearing fields and any ad-hoc fields added by tests/users.
    guardrail_keys = {
        "required_caveats",
        "do_not_say",
        "unsupported_inferences",
        "promotion_blockers",
        "authoring_intent_forbidden",
        "provenance_requirements",
    }
    scanned = {k: v for k, v in obj.items() if k not in guardrail_keys}
    text = text_without_negative_guardrails(compact_json(scanned))
    lower = text.lower()
    if any(secret in lower for secret in SECRET_PATTERNS):
        raise MetadataPreflightError(f"{label} includes secret or private data marker")
    for pattern, reason in BAD_TEXT_PATTERNS:
        if pattern.search(text):
            raise MetadataPreflightError(f"{label} violation: {reason}")


def validate_metadata_candidate(item: dict[str, Any]) -> bool:
    if not isinstance(item, dict):
        raise MetadataPreflightError("metadata candidate must be object")
    for field in REQUIRED_METADATA_FIELDS:
        if field not in item:
            raise MetadataPreflightError(f"metadata candidate missing required field: {field}")
    mid = str(item.get("metadata_id", "unknown"))
    forbidden = sorted(DISALLOWED_PROSE_KEYS & set(item))
    if forbidden:
        raise MetadataPreflightError(f"metadata candidate {mid} contains forbidden prose field(s): {forbidden}")
    if item.get("advisory_only") is not True:
        raise MetadataPreflightError(f"metadata candidate {mid} safety flag invalid: advisory_only")
    for flag in FALSE_FLAGS:
        if item.get(flag) is not False:
            raise MetadataPreflightError(f"metadata candidate {mid} safety flag invalid: {flag}")
    if item.get("raw_capture_dependency") is True or item.get("raw_content_stored") is True:
        raise MetadataPreflightError(f"metadata candidate {mid} has forbidden raw capture dependency")
    validate_caveat_and_dns(item, f"metadata candidate {mid}")
    for field in ["unsupported_inferences", "promotion_blockers", "provenance_paths", "source_review_ids", "source_note_ids", "candidate_source_ids"]:
        require_list(item.get(field), field)
    require_str(item.get("source_packet_id"), "source_packet_id")
    require_str(item.get("source_cluster_id"), "source_cluster_id")
    require_str(item.get("thinness_warning"), "thinness_warning")
    scan_forbidden_text(item, f"metadata candidate {mid}")
    return (
        item.get("metadata_type") == "constrained_authoring_metadata_candidate"
        and item.get("metadata_decision") == "metadata_candidate_created"
        and item.get("metadata_use") == "caveat_only"
        and item.get("canary_usefulness") in {"improved_but_still_thin", "useful_as_caveat_only_seed"}
        and item.get("target_chapter_status") in {"suggested_only", "not_assigned"}
    )


def select_metadata(report: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    selected: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for item in report.get("constrained_authoring_metadata_candidates", []):
        if validate_metadata_candidate(item):
            selected.append(item)
        else:
            cp = dict(item)
            cp["excluded_reason"] = "does_not_match_constrained_authoring_metadata_selection_rule"
            excluded.append(cp)
    return selected, excluded


def validate_run29_crosscheck(metadata_report: dict[str, Any]) -> None:
    redteams = metadata_report.get("selected_redteams")
    if not isinstance(redteams, list) or not redteams:
        raise MetadataPreflightError("Run 30 report missing selected_redteams for Run 29 cross-check")
    for rt in redteams:
        if not isinstance(rt, dict):
            raise MetadataPreflightError("Run 29 cross-check redteam must be object")
        if rt.get("redteam_decision") != "draft_canary_v2_passed":
            raise MetadataPreflightError("Run 29 cross-check redteam_decision mismatch")
        if rt.get("canary_usefulness") not in {"improved_but_still_thin", "useful_as_caveat_only_seed"}:
            raise MetadataPreflightError("Run 29 cross-check canary_usefulness mismatch")
        if rt.get("closed_loop_disposition") != "caveat_only" or rt.get("recommended_next_stage") != "build_constrained_authoring_metadata_candidate":
            raise MetadataPreflightError("Run 29 cross-check disposition/next-stage mismatch")
        for flag in FALSE_FLAGS:
            if rt.get(flag) is not False:
                raise MetadataPreflightError(f"Run 29 cross-check safety flag invalid: {flag}")


def validate_review(review: dict[str, Any], selected_by_id: dict[str, dict[str, Any]]) -> None:
    if not isinstance(review, dict):
        raise ValueError("metadata preflight review must be object")
    for field in REQUIRED_REVIEW_FIELDS:
        if field not in review:
            raise ValueError(f"metadata preflight review missing required field: {field}")
    mid = require_str(review.get("metadata_id"), "metadata_id")
    if mid not in selected_by_id:
        raise ValueError(f"review references unknown selected metadata_id: {mid}")
    source = selected_by_id[mid]
    for field in ["draft_canary_id", "rebuilt_input_id", "prior_draft_input_id"]:
        if review.get(field) != source.get(field):
            raise ValueError(f"review {field} mismatch")
    if review.get("metadata_type") != "constrained_authoring_metadata_candidate" or review.get("metadata_use") != "caveat_only":
        raise ValueError("review must preserve constrained metadata caveat-only type/use")
    for field, allowed in [
        ("preflight_decision", ALLOWED_PREFLIGHT_DECISIONS),
        ("metadata_readiness", ALLOWED_METADATA_READINESS),
        ("closed_loop_disposition", ALLOWED_DISPOSITIONS),
        ("recommended_next_stage", ALLOWED_NEXT_STAGES),
    ]:
        value = review.get(field)
        if not isinstance(value, str):
            raise ValueError(f"{field} must be exactly one string enum value")
        if value not in allowed:
            raise ValueError(f"invalid {field}: {value}")
    for field in [
        "metadata_containment_assessment",
        "caveat_integrity_assessment",
        "do_not_say_compliance_assessment",
        "evidence_use_assessment",
        "provenance_assessment",
        "usefulness_as_metadata_assessment",
        "residual_risk_assessment",
        "residual_risk",
    ]:
        require_str(review.get(field), field)
    for field in ["required_caveats", "do_not_say", "unsupported_inferences", "promotion_blockers", "limitations"]:
        require_list(review.get(field), field)
    if review.get("advisory_only") is not True:
        raise ValueError("review advisory_only must be true")
    for flag in FALSE_FLAGS:
        if review.get(flag) is not False:
            raise ValueError(f"review {flag} must be false")
    if REQUIRED_CAVEAT not in joined(review.get("required_caveats")):
        raise ValueError("review missing required caveat")
    dns = joined(review.get("do_not_say"))
    for required in REQUIRED_DO_NOT_SAY_SUBSTRINGS:
        if required not in dns:
            raise ValueError(f"review do_not_say missing required guidance: {required}")
    decision = review["preflight_decision"]
    readiness = review["metadata_readiness"]
    next_stage = review["recommended_next_stage"]
    if decision == "metadata_preflight_passed":
        if review.get("author_allowed") is not False or review.get("eligible_for_authoring") is not False or review.get("chapter_update_allowed") is not False:
            raise ValueError("metadata_preflight_passed still requires false authoring/chapter flags")
        if readiness not in {"ready_for_promotion_contract_update", "ready_for_constrained_authoring_context_candidate"}:
            raise ValueError("metadata_preflight_passed requires ready metadata_readiness")
    if decision == "safe_but_too_thin" and next_stage not in {"rebuild_authoring_metadata", "keep_safe_reports_only"}:
        raise ValueError("safe_but_too_thin must route to rebuild_authoring_metadata or keep_safe_reports_only")
    if decision == "needs_more_sources" and next_stage != "run_additional_source_collection":
        raise ValueError("needs_more_sources must route only to run_additional_source_collection")
    if decision == "source_context_unclear" and next_stage != "run_source_context_review":
        raise ValueError("source_context_unclear must route only to run_source_context_review")


def make_validator(selected: list[dict[str, Any]]):
    selected_by_id = {str(c["metadata_id"]): c for c in selected}

    def validator(obj: dict[str, Any]) -> None:
        reviews = obj.get("constrained_authoring_metadata_preflight_reviews")
        if not isinstance(reviews, list):
            raise ValueError("LLM JSON must contain constrained_authoring_metadata_preflight_reviews list")
        if len(reviews) != len(selected_by_id):
            raise ValueError(f"expected {len(selected_by_id)} metadata preflight review(s), got {len(reviews)}")
        seen: set[str] = set()
        for review in reviews:
            validate_review(review, selected_by_id)
            mid = review["metadata_id"]
            if mid in seen:
                raise ValueError(f"duplicate metadata_id review: {mid}")
            seen.add(mid)

    return validator


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


def build_prompt(selected: list[dict[str, Any]], excluded: list[dict[str, Any]], run_id: str, supporting_inputs: dict[str, Any]) -> str:
    schema = {
        "constrained_authoring_metadata_preflight_reviews": [
            {
                "metadata_id": "string from selected_metadata",
                "draft_canary_id": "string from selected_metadata",
                "rebuilt_input_id": "string from selected_metadata",
                "prior_draft_input_id": "string from selected_metadata",
                "metadata_type": "constrained_authoring_metadata_candidate",
                "metadata_use": "caveat_only",
                "preflight_decision": "metadata_preflight_passed | safe_but_too_thin | safe_reports_only | needs_more_sources | needs_better_authoring_metadata | source_context_unclear | exclude_from_authoring | contradiction_review_required",
                "metadata_readiness": "ready_for_promotion_contract_update | ready_for_constrained_authoring_context_candidate | not_ready_still_too_thin | not_ready_safe_reports_only | not_ready_needs_more_sources | not_ready_needs_better_metadata | not_ready_source_context_unclear | not_ready_exclude | not_ready_contradiction_review",
                "closed_loop_disposition": "caveat_only | safe_reports_only | needs_more_sources | needs_better_authoring_metadata | source_context_unclear | exclude_from_pipeline | contradiction_review_required",
                "metadata_containment_assessment": "single non-empty string",
                "caveat_integrity_assessment": "single non-empty string",
                "do_not_say_compliance_assessment": "single non-empty string",
                "evidence_use_assessment": "single non-empty string",
                "provenance_assessment": "single non-empty string",
                "usefulness_as_metadata_assessment": "single non-empty string",
                "residual_risk_assessment": "single non-empty string",
                "required_caveats": [REQUIRED_CAVEAT],
                "do_not_say": ["all hard do-not-say strings"],
                "unsupported_inferences": ["strings"],
                "promotion_blockers": ["strings"],
                "limitations": ["strings"],
                "residual_risk": "single non-empty string",
                "recommended_next_stage": "update_closed_loop_promotion_contract_for_authoring_metadata | build_constrained_authoring_context_candidate | rebuild_authoring_metadata | keep_safe_reports_only | run_additional_source_collection | run_source_context_review | exclude_from_pipeline | run_contradiction_review",
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
        "task": "Run 31 report-only constrained authoring-metadata preflight and red-team gate",
        "selected_metadata": selected,
        "excluded_metadata": excluded,
        "supporting_inputs_summary": supporting_inputs,
        "required_caveat": REQUIRED_CAVEAT,
        "allowed_preflight_decision_values": sorted(ALLOWED_PREFLIGHT_DECISIONS),
        "allowed_metadata_readiness_values": sorted(ALLOWED_METADATA_READINESS),
        "allowed_closed_loop_disposition_values": sorted(ALLOWED_DISPOSITIONS),
        "allowed_recommended_next_stage_values": sorted(ALLOWED_NEXT_STAGES),
        "required_schema": schema,
        "instructions": [
            "Return JSON only. No markdown, no prose outside JSON.",
            "Assess metadata containment: this must be strictly metadata, not prose, not chapter-ready wording, not publishable wording, and not claim-insertion language.",
            "Assess caveat integrity, do-not-say compliance, evidence-use correctness, provenance sufficiency, usefulness as metadata, thinness, residual risk, and downstream prose-promotion risk.",
            "Do not force a positive outcome; choose from allowed enums based on the selected metadata.",
            "Even if metadata_preflight_passed, it means ready only for another controlled metadata/promotion-contract stage, not authoring, publication, claim insertion, or chapter update.",
            "Always set advisory_only=true, author_allowed=false, publication_approved=false, eligible_for_claim_insertion=false, eligible_for_authoring=false, eligible_for_publication=false, chapter_update_allowed=false.",
            "safe_but_too_thin may route only to rebuild_authoring_metadata or keep_safe_reports_only.",
            "needs_more_sources may route only to run_additional_source_collection.",
            "source_context_unclear may route only to run_source_context_review.",
            "Do not generate new author prose, chapter prose, publishable material, secrets, tokens, cookies, OAuth material, API keys, private data, or raw captures.",
        ],
    }
    return "Return strict JSON matching this schema and input:\n" + json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False)


def safety_flags() -> dict[str, bool]:
    return {
        "advisory_only": True,
        "metadata_only": True,
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
        "new_author_prose_created": False,
        "chapter_ready_prose_created": False,
        "gpt55_advisory_is_human_or_editor_approval": False,
        "metadata_candidate_is_publishable_material": False,
        "metadata_preflight_is_authoring_approval": False,
    }


def build_payload(args: argparse.Namespace) -> dict[str, Any]:
    metadata_path = resolve(args.metadata_report)
    metadata_report = load_json(metadata_path, "Run 30 constrained authoring metadata report")
    validate_metadata_report(metadata_report)
    validate_run29_crosscheck(metadata_report)
    try:
        profile = load_model_profile(args.reasoning_profile)
    except ModelProfileError as exc:
        raise MetadataPreflightError(f"model_profile_error:{exc}") from exc
    selected, excluded = select_metadata(metadata_report)
    if not selected:
        raise MetadataPreflightError("no selected Run 30 constrained authoring metadata candidates for preflight")
    supporting = load_supporting_inputs(args.supporting_input)
    db = db_path()
    with connect_readonly(db) as con:
        before_counts = {"source_notes": table_count(con, "source_notes"), "claims": table_count(con, "claims"), "editorial_reviews": table_count(con, "editorial_reviews")}
        before_status = status_snapshots(con)
        prompt = build_prompt(selected, excluded, args.run_id, supporting)
        try:
            llm = call_high_reasoning_json(
                prompt,
                schema_name="run31_constrained_authoring_metadata_preflight",
                validator=make_validator(selected),
                provider=args.provider,
                model=args.model,
                timeout_seconds=args.timeout_seconds,
                reasoning_profile=args.reasoning_profile,
            )
        except HighReasoningError as exc:
            raise MetadataPreflightError(str(exc.result.get("error") or exc)) from exc
        after_counts = {"source_notes": table_count(con, "source_notes"), "claims": table_count(con, "claims"), "editorial_reviews": table_count(con, "editorial_reviews")}
        after_status = status_snapshots(con)
    reviews = llm["parsed_json"]["constrained_authoring_metadata_preflight_reviews"]
    payload = {
        "run_id": args.run_id,
        "generated_at": utc_now(),
        "mode": MODE,
        "input_paths": {"metadata_report": rel(metadata_path), "supporting_inputs": list(supporting.keys()), "sqlite_db": rel(db)},
        "report_only": True,
        "llm_used": bool(llm.get("llm_used")),
        "reasoning_status": llm.get("reasoning_status"),
        "provider": llm.get("provider") or profile["provider"],
        "model": llm.get("model") or profile["model"],
        "bridge": llm.get("bridge") or profile["bridge"],
        "model_profile": llm.get("model_profile") or profile["profile_name"],
        "strict_json_required": bool(llm.get("strict_json_required", profile["strict_json_required"])),
        "weak_local_fallback_refused": bool(llm.get("weak_local_fallback_refused", True)),
        "selected_metadata_count": len(selected),
        "reviewed_metadata_count": len(reviews),
        "excluded_metadata_count": len(excluded),
        "preflight_decision_counts": dict(Counter(r["preflight_decision"] for r in reviews)),
        "metadata_readiness_counts": dict(Counter(r["metadata_readiness"] for r in reviews)),
        "closed_loop_disposition_counts": dict(Counter(r["closed_loop_disposition"] for r in reviews)),
        "recommended_next_stage_counts": dict(Counter(r["recommended_next_stage"] for r in reviews)),
        "selected_metadata": selected,
        "excluded_metadata": excluded,
        "constrained_authoring_metadata_preflight_reviews": reviews,
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
        raise MetadataPreflightError("high reasoning was not used")
    if payload["provider"] != "copilot" or payload["model"] != "gpt-5.5" or payload["bridge"] != "hermes_cli" or payload["model_profile"] != args.reasoning_profile:
        raise MetadataPreflightError("unexpected high-reasoning provider/model/bridge/profile")
    if payload["changed_source_notes"] or payload["claims_inserted"] or payload["editorial_reviews_inserted"] or payload["source_status_changed"] or payload["claim_status_changed"] or payload["editorial_status_changed"]:
        raise MetadataPreflightError("forbidden DB/status delta detected during report-only metadata preflight")
    return payload


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        f"# Run 31 constrained authoring-metadata preflight — {payload['run_id']}",
        "",
        "## Summary",
        "",
        f"- Report-only: `{payload['report_only']}`",
        f"- GPT-5.5 used: `{payload['llm_used']}`",
        f"- Provider/model/bridge/profile: `{payload['provider']}` / `{payload['model']}` / `{payload['bridge']}` / `{payload['model_profile']}`",
        f"- Selected metadata candidates: `{payload['selected_metadata_count']}`",
        f"- Reviewed metadata candidates: `{payload['reviewed_metadata_count']}`",
        f"- Excluded metadata candidates: `{payload['excluded_metadata_count']}`",
        "",
        "## Preflight decisions",
        "",
    ]
    for r in payload["constrained_authoring_metadata_preflight_reviews"]:
        lines += [
            f"- metadata_id: `{r['metadata_id']}`",
            f"  - preflight_decision: `{r['preflight_decision']}`",
            f"  - metadata_readiness: `{r['metadata_readiness']}`",
            f"  - closed_loop_disposition: `{r['closed_loop_disposition']}`",
            f"  - recommended_next_stage: `{r['recommended_next_stage']}`",
            "",
            "### Metadata containment",
            "",
            r["metadata_containment_assessment"],
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
            "### Usefulness as metadata",
            "",
            r["usefulness_as_metadata_assessment"],
            "",
            "### Thinness warning and residual risks",
            "",
            r["residual_risk_assessment"],
            "",
        ]
    lines += [
        "## Why no claims/editorial_reviews/book/status changes were made",
        "",
        "This is advisory/report-only metadata preflight. It does not generate author prose or chapter prose, write `docs/book`, insert claims, editorial_reviews, or source_notes, modify source/claim/editorial statuses, persist metadata to the database, or modify source_registry, raw captures, schema, or daily worker code.",
        "",
        "## Why this does not approve authoring or publication",
        "",
        "GPT-5.5 output is advisory and is not human/editor approval. All reviews must keep `author_allowed=false`, `publication_approved=false`, `eligible_for_claim_insertion=false`, `eligible_for_authoring=false`, `eligible_for_publication=false`, and `chapter_update_allowed=false`, even when metadata preflight passes.",
        "",
        "## Recommendation for Run 32",
        "",
        "Follow the Run 31 recommended next-stage counts. If the metadata preflight passes, Run 32 should update or test the closed-loop promotion contract for authoring metadata only, still report-only and non-publication. If it remains thin or unclear, rebuild metadata, collect sources, or run source-context review as directed.",
    ]
    return "\n".join(lines) + "\n"


def write_reports(payload: dict[str, Any], output_dir: Path, suffix: str) -> dict[str, str]:
    out_dir = output_dir if output_dir.is_absolute() else ROOT / output_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{payload['run_id']}-constrained-authoring-metadata-preflight-{suffix}" if suffix else f"{payload['run_id']}-constrained-authoring-metadata-preflight"
    json_path = out_dir / f"{stem}.json"
    md_path = out_dir / f"{stem}.md"
    payload["output_paths"] = {"json": rel(json_path), "markdown": rel(md_path)}
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(payload), encoding="utf-8")
    return payload["output_paths"]


def parse_args(argv: list[str]) -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", default=RUN_ID_DEFAULT)
    ap.add_argument("--metadata-report", default=DEFAULT_METADATA_REPORT)
    ap.add_argument("--output-dir", default="reports/editorial")
    ap.add_argument("--report-suffix", default="run31")
    ap.add_argument("--reasoning-profile", default="closed_loop_editorial")
    ap.add_argument("--provider", default=None)
    ap.add_argument("--model", default=None)
    ap.add_argument("--timeout-seconds", type=int, default=300)
    ap.add_argument(
        "--supporting-input",
        action="append",
        default=[
            "reports/editorial/citation-pipeline-test-20260612-author-draft-canary-v2-redteam-run29.json",
            "reports/editorial/citation-pipeline-test-20260612-author-draft-canary-v2-run28.json",
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
            "selected_metadata_count": payload["selected_metadata_count"],
            "reviewed_metadata_count": payload["reviewed_metadata_count"],
            "excluded_metadata_count": payload["excluded_metadata_count"],
            "preflight_decision_counts": payload["preflight_decision_counts"],
            "metadata_readiness_counts": payload["metadata_readiness_counts"],
            "closed_loop_disposition_counts": payload["closed_loop_disposition_counts"],
            "recommended_next_stage_counts": payload["recommended_next_stage_counts"],
        }, sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
