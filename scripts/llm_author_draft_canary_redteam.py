#!/usr/bin/env python3
"""Run 25 report-only author-draft canary red-team and usefulness gate.

Uses GPT-5.5 through the closed_loop_editorial profile via the shared strict-JSON
Hermes bridge to red-team Run 24 draft canaries for safety containment and
usefulness. This is advisory/report-only: no docs/book writes, no DB writes, no
claim insertion, no authoring approval, no publication approval, and no chapter
update permission.
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
MODE = "llm_author_draft_canary_redteam"
DEFAULT_CANARY_REPORT = f"reports/editorial/{RUN_ID_DEFAULT}-author-draft-canary-run24.json"
REQUIRED_CAVEAT = "Frame narrowly: OpenClaw documentation names Hermes in migration/setup tooling contexts; do not state that Hermes is a runtime dependency or general operating environment without additional sources."

FALSE_FLAGS = [
    "author_allowed",
    "publication_approved",
    "eligible_for_claim_insertion",
    "eligible_for_authoring",
    "eligible_for_publication",
    "chapter_update_allowed",
]
REQUIRED_DO_NOT_SAY_SUBSTRINGS = [
    "runtime dependency of OpenClaw",
    "general operating environment for OpenClaw",
    "requires Hermes for web or phone access",
    "generalize beyond migration/setup/import tooling contexts",
    "factual claim without the caveat",
    "chapter prose before later author/red-team gates pass",
]
ALLOWED_REDTEAM_DECISIONS = {
    "draft_canary_passed",
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
    "run_controlled_caveat_only_draft_expansion",
    "rebuild_author_draft_input",
    "keep_safe_reports_only",
    "run_additional_source_collection",
    "run_source_context_review",
    "exclude_from_pipeline",
    "run_contradiction_review",
}
REQUIRED_REVIEW_FIELDS = [
    "draft_canary_id",
    "draft_input_id",
    "draft_canary_type",
    "draft_canary_use",
    "redteam_decision",
    "canary_usefulness",
    "closed_loop_disposition",
    "safety_containment_assessment",
    "caveat_integrity_assessment",
    "do_not_say_compliance_assessment",
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
BAD_TEXT_PATTERNS = [
    (re.compile(r"\bHermes\s+is\s+a\s+runtime\s+dependency\s+of\s+OpenClaw\b", re.I), "runtime dependency claim"),
    (re.compile(r"\bHermes\s+is\s+the\s+general\s+operating\s+environment\s+for\s+OpenClaw\b", re.I), "general operating environment claim"),
    (re.compile(r"\bOpenClaw\s+requires\s+Hermes\s+for\s+web\s+or\s+phone\s+access\b", re.I), "web/phone access requirement claim"),
    (re.compile(r"\bapproved\s+for\s+publication\b|\bpublication\s+approved\b", re.I), "publication approval implication"),
    (re.compile(r"\bchapter[- ]ready\b|\bready\s+for\s+chapter\b", re.I), "chapter readiness implication"),
    (re.compile(r"\bbeyond\s+migration\s+setup\s+import\s+tooling\b|\bbroadly\s+used\s+across\s+OpenClaw\b", re.I), "overgeneralization beyond tooling context"),
]


class AuthorDraftCanaryRedteamError(RuntimeError):
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


def load_json(path: Path, label: str) -> dict[str, Any]:
    if not path.exists():
        raise AuthorDraftCanaryRedteamError(f"missing input {label}: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AuthorDraftCanaryRedteamError(f"invalid JSON in {label}: {exc}") from exc
    if not isinstance(data, dict):
        raise AuthorDraftCanaryRedteamError(f"{label} must be JSON object")
    return data


def compact_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


def connect_readonly(path: Path) -> sqlite3.Connection:
    if not path.exists():
        raise AuthorDraftCanaryRedteamError(f"missing SQLite DB: {path}")
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


def _joined(values: Any) -> str:
    if isinstance(values, list):
        return "\n".join(map(str, values))
    return str(values or "")


def as_str(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be non-empty string")
    return value


def as_list(value: Any, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be list")
    return value


def require_safe_flags(obj: dict[str, Any], label: str) -> None:
    if obj.get("advisory_only") is not True:
        raise AuthorDraftCanaryRedteamError(f"{label} safety flag invalid: advisory_only")
    if obj.get("draft_canary_only") is not True:
        raise AuthorDraftCanaryRedteamError(f"{label} draft_canary_only must be true")
    for k in FALSE_FLAGS:
        if obj.get(k) is not False:
            raise AuthorDraftCanaryRedteamError(f"{label} safety flag invalid: {k}")


def validate_caveat_and_dns(obj: dict[str, Any], label: str) -> None:
    caveats = obj.get("required_caveats")
    if not isinstance(caveats, list) or REQUIRED_CAVEAT not in _joined(caveats):
        raise AuthorDraftCanaryRedteamError(f"{label} missing required caveat")
    dns = obj.get("do_not_say")
    if not isinstance(dns, list) or not dns:
        raise AuthorDraftCanaryRedteamError(f"{label} missing do_not_say guidance")
    joined = _joined(dns)
    for required in REQUIRED_DO_NOT_SAY_SUBSTRINGS:
        if required not in joined:
            raise AuthorDraftCanaryRedteamError(f"{label} do_not_say missing required guidance: {required}")


def validate_canary_text(canary: dict[str, Any]) -> None:
    text = canary.get("draft_canary_text")
    if not isinstance(text, str) or not text.strip():
        raise AuthorDraftCanaryRedteamError("draft_canary_text missing")
    words = re.findall(r"\b\S+\b", text)
    if len(words) > 90 or canary.get("word_count") > 90:
        raise AuthorDraftCanaryRedteamError("draft_canary_text exceeds 90 words")
    if REQUIRED_CAVEAT not in text:
        raise AuthorDraftCanaryRedteamError("draft_canary_text missing required caveat")
    lower = text.lower()
    if "secret" in lower or "api key" in lower or "oauth" in lower or "cookie" in lower:
        raise AuthorDraftCanaryRedteamError("draft_canary_text includes secrets or private data language")
    for pattern, reason in BAD_TEXT_PATTERNS:
        if pattern.search(text):
            raise AuthorDraftCanaryRedteamError(f"draft_canary_text violation: {reason}")
    if canary.get("word_count") != len(words):
        raise AuthorDraftCanaryRedteamError("draft_canary_text word_count mismatch")


def validate_canary_report(report: dict[str, Any]) -> None:
    if report.get("mode") != "llm_author_draft_canary":
        raise AuthorDraftCanaryRedteamError("Run 24 canary report mode mismatch")
    if report.get("report_only") is not True or report.get("llm_used") is not True:
        raise AuthorDraftCanaryRedteamError("Run 24 canary report must be report_only with GPT-5.5 used")
    if report.get("provider") != "copilot" or report.get("model") != "gpt-5.5" or report.get("bridge") != "hermes_cli" or report.get("model_profile") != "closed_loop_editorial":
        raise AuthorDraftCanaryRedteamError("Run 24 canary report has unexpected model/profile metadata")
    if not isinstance(report.get("draft_canaries"), list):
        raise AuthorDraftCanaryRedteamError("Run 24 canary report missing draft_canaries list")


def validate_selected_canary(canary: dict[str, Any]) -> None:
    if not isinstance(canary, dict):
        raise AuthorDraftCanaryRedteamError("draft canary must be object")
    cid = canary.get("draft_canary_id", "unknown")
    require_safe_flags(canary, f"draft canary {cid}")
    if canary.get("draft_canary_type") != "caveat_only_author_draft_canary":
        raise AuthorDraftCanaryRedteamError(f"draft canary {cid} type mismatch")
    if canary.get("draft_canary_decision") != "draft_canary_created":
        raise AuthorDraftCanaryRedteamError(f"draft canary {cid} decision mismatch")
    if canary.get("draft_canary_use") != "caveat_only":
        raise AuthorDraftCanaryRedteamError(f"draft canary {cid} use mismatch")
    if canary.get("raw_capture_dependency") is True or canary.get("raw_content_stored") is True:
        raise AuthorDraftCanaryRedteamError(f"draft canary {cid} has forbidden raw capture dependency")
    validate_caveat_and_dns(canary, f"draft canary {cid}")
    validate_canary_text(canary)


def select_draft_canaries(report: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    selected: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for canary in report.get("draft_canaries", []):
        validate_selected_canary(canary)
        if (
            canary.get("draft_canary_type") == "caveat_only_author_draft_canary"
            and canary.get("draft_canary_decision") == "draft_canary_created"
            and canary.get("draft_canary_use") == "caveat_only"
        ):
            selected.append(canary)
        else:
            cp = dict(canary)
            cp["excluded_reason"] = "does_not_match_run25_selection_rule"
            excluded.append(cp)
    return selected, excluded


def validate_review(review: dict[str, Any], selected_by_id: dict[str, dict[str, Any]]) -> None:
    if not isinstance(review, dict):
        raise ValueError("red-team review must be object")
    for field in REQUIRED_REVIEW_FIELDS:
        if field not in review:
            raise ValueError(f"red-team review missing required field: {field}")
    cid = as_str(review.get("draft_canary_id"), "draft_canary_id")
    if cid not in selected_by_id:
        raise ValueError(f"review references unknown selected draft canary: {cid}")
    if review.get("draft_input_id") != selected_by_id[cid].get("draft_input_id"):
        raise ValueError("review draft_input_id mismatch")
    if review.get("draft_canary_type") != "caveat_only_author_draft_canary" or review.get("draft_canary_use") != "caveat_only":
        raise ValueError("review must preserve caveat-only canary type/use")
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
        "safety_containment_assessment", "caveat_integrity_assessment", "do_not_say_compliance_assessment",
        "provenance_assessment", "usefulness_assessment", "residual_risk_assessment", "residual_risk",
    ]:
        as_str(review.get(field), field)
    for field in ["required_caveats", "do_not_say", "limitations"]:
        as_list(review.get(field), field)
    if review.get("advisory_only") is not True or review.get("draft_canary_only") is not True:
        raise ValueError("review advisory_only and draft_canary_only must be true")
    for k in FALSE_FLAGS:
        if review.get(k) is not False:
            raise ValueError(f"review {k} must be false")
    if REQUIRED_CAVEAT not in _joined(review.get("required_caveats")):
        raise ValueError("review missing required caveat")
    dns = _joined(review.get("do_not_say"))
    for required in REQUIRED_DO_NOT_SAY_SUBSTRINGS:
        if required not in dns:
            raise ValueError(f"review do_not_say missing required guidance: {required}")
    if review.get("redteam_decision") == "draft_canary_passed":
        if review.get("author_allowed") is not False or review.get("eligible_for_authoring") is not False or review.get("chapter_update_allowed") is not False:
            raise ValueError("draft_canary_passed still requires author_allowed=false, eligible_for_authoring=false, chapter_update_allowed=false")
    if review.get("redteam_decision") == "safe_but_not_useful" and review.get("recommended_next_stage") not in {"rebuild_author_draft_input", "keep_safe_reports_only"}:
        raise ValueError("safe_but_not_useful must route to rebuild_author_draft_input or keep_safe_reports_only")


def make_validator(selected: list[dict[str, Any]]):
    selected_by_id = {str(c["draft_canary_id"]): c for c in selected}

    def validator(obj: dict[str, Any]) -> None:
        reviews = obj.get("draft_canary_redteam_reviews")
        if not isinstance(reviews, list):
            raise ValueError("LLM JSON must contain draft_canary_redteam_reviews list")
        if len(reviews) != len(selected_by_id):
            raise ValueError(f"expected {len(selected_by_id)} red-team review(s), got {len(reviews)}")
        seen = set()
        for review in reviews:
            validate_review(review, selected_by_id)
            cid = review["draft_canary_id"]
            if cid in seen:
                raise ValueError(f"duplicate draft_canary_id review: {cid}")
            seen.add(cid)
    return validator


def build_prompt(selected: list[dict[str, Any]], excluded: list[dict[str, Any]], run_id: str) -> str:
    schema = {
        "draft_canary_redteam_reviews": [
            {
                "draft_canary_id": "string",
                "draft_input_id": "string",
                "draft_canary_type": "caveat_only_author_draft_canary",
                "draft_canary_use": "caveat_only",
                "redteam_decision": "choose exactly one string: draft_canary_passed | safe_but_not_useful | safe_reports_only | needs_more_sources | needs_better_authoring_input | source_context_unclear | exclude_from_authoring | contradiction_review_required",
                "canary_usefulness": "choose exactly one string: useful_as_caveat_only_seed | safe_but_too_thin | not_useful_restates_caveat_only | not_ready_needs_more_sources | not_ready_source_context_unclear | not_ready_exclude | not_ready_contradiction_review",
                "closed_loop_disposition": "choose exactly one string: caveat_only | safe_reports_only | needs_more_sources | needs_better_authoring_input | source_context_unclear | exclude_from_pipeline | contradiction_review_required",
                "safety_containment_assessment": "single non-empty string",
                "caveat_integrity_assessment": "single non-empty string",
                "do_not_say_compliance_assessment": "single non-empty string",
                "provenance_assessment": "single non-empty string",
                "usefulness_assessment": "single non-empty string",
                "residual_risk_assessment": "single non-empty string",
                "required_caveats": [REQUIRED_CAVEAT],
                "do_not_say": [
                    "Do not say Hermes is a runtime dependency of OpenClaw.",
                    "Do not say Hermes is the general operating environment for OpenClaw.",
                    "Do not say OpenClaw requires Hermes for web or phone access.",
                    "Do not generalize beyond migration/setup/import tooling contexts unless additional sources support it.",
                    "Do not use this material as a factual claim without the caveat.",
                    "Do not use this material for chapter prose before later author/red-team gates pass.",
                ],
                "limitations": ["strings"],
                "residual_risk": "single non-empty string",
                "recommended_next_stage": "choose exactly one string: run_controlled_caveat_only_draft_expansion | rebuild_author_draft_input | keep_safe_reports_only | run_additional_source_collection | run_source_context_review | exclude_from_pipeline | run_contradiction_review",
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
        "task": "Run 25 report-only author-draft canary red-team and usefulness gate",
        "selected_draft_canaries": selected,
        "excluded_draft_canaries": excluded,
        "required_caveat": REQUIRED_CAVEAT,
        "allowed_redteam_decision_values": sorted(ALLOWED_REDTEAM_DECISIONS),
        "allowed_canary_usefulness_values": sorted(ALLOWED_USEFULNESS),
        "allowed_closed_loop_disposition_values": sorted(ALLOWED_DISPOSITIONS),
        "allowed_recommended_next_stage_values": sorted(ALLOWED_NEXT_STAGES),
        "required_schema": schema,
        "instructions": [
            "Return JSON only. No markdown, no prose outside JSON.",
            "Red-team safety containment, caveat integrity, do-not-say compliance, provenance sufficiency, residual risk, prose-promotion risk, and usefulness as a later author-draft seed.",
            "Do not assume the canary is useful merely because it is safe; explicitly decide whether it is too thin or merely restates the caveat.",
            "Choose exactly ONE string enum value for redteam_decision, canary_usefulness, closed_loop_disposition, and recommended_next_stage; do NOT return arrays or objects for these enum fields.",
            "Do not approve authoring. Do not approve publication. Do not allow chapter updates. Do not treat GPT-5.5 advisory reasoning as human/editor approval.",
            "Even if redteam_decision=draft_canary_passed, set author_allowed=false, publication_approved=false, eligible_for_authoring=false, eligible_for_publication=false, and chapter_update_allowed=false.",
            "If the canary is just the required caveat restated, use safe_but_not_useful with not_useful_restates_caveat_only and recommend rebuild_author_draft_input or keep_safe_reports_only.",
            "Do not force a positive outcome; safe reports, more sources, better authoring input, source context review, exclusion, and contradiction review are allowed.",
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
    }


def build_payload(args: argparse.Namespace) -> dict[str, Any]:
    canary_path = resolve(args.canary_report)
    canary_report = load_json(canary_path, "Run 24 canary report")
    validate_canary_report(canary_report)
    try:
        profile = load_model_profile(args.reasoning_profile)
    except ModelProfileError as exc:
        raise AuthorDraftCanaryRedteamError(f"model_profile_error:{exc}") from exc
    selected, excluded = select_draft_canaries(canary_report)
    if not selected:
        raise AuthorDraftCanaryRedteamError("no selected Run 24 draft canaries for red-team")
    db = db_path()
    with connect_readonly(db) as con:
        before_counts = {"source_notes": table_count(con, "source_notes"), "claims": table_count(con, "claims"), "editorial_reviews": table_count(con, "editorial_reviews")}
        before_status = status_snapshots(con)
        prompt = build_prompt(selected, excluded, args.run_id)
        try:
            llm = call_high_reasoning_json(
                prompt,
                schema_name="run25_author_draft_canary_redteam",
                validator=make_validator(selected),
                provider=args.provider,
                model=args.model,
                timeout_seconds=args.timeout_seconds,
                reasoning_profile=args.reasoning_profile,
            )
        except HighReasoningError as exc:
            raise AuthorDraftCanaryRedteamError(str(exc.result.get("error") or exc)) from exc
        after_counts = {"source_notes": table_count(con, "source_notes"), "claims": table_count(con, "claims"), "editorial_reviews": table_count(con, "editorial_reviews")}
        after_status = status_snapshots(con)
    reviews = llm["parsed_json"]["draft_canary_redteam_reviews"]
    payload = {
        "run_id": args.run_id,
        "generated_at": utc_now(),
        "mode": MODE,
        "input_paths": {"canary_report": rel(canary_path), "sqlite_db": rel(db)},
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
        "draft_canary_redteam_reviews": reviews,
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
        raise AuthorDraftCanaryRedteamError("high reasoning was not used")
    if payload["provider"] != "copilot" or payload["model"] != "gpt-5.5" or payload["bridge"] != "hermes_cli" or payload["model_profile"] != args.reasoning_profile:
        raise AuthorDraftCanaryRedteamError("unexpected high-reasoning provider/model/bridge/profile")
    if payload["changed_source_notes"] or payload["claims_inserted"] or payload["editorial_reviews_inserted"] or payload["source_status_changed"] or payload["claim_status_changed"] or payload["editorial_status_changed"]:
        raise AuthorDraftCanaryRedteamError("forbidden DB/status delta detected during report-only red-team")
    return payload


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        f"# Run 25 author-draft canary red-team — {payload['run_id']}", "",
        "## Summary", "",
        f"- Report-only: `{payload['report_only']}`",
        f"- GPT-5.5 used: `{payload['llm_used']}`",
        f"- Provider/model/bridge/profile: `{payload['provider']}` / `{payload['model']}` / `{payload['bridge']}` / `{payload['model_profile']}`",
        f"- Selected draft canaries: `{payload['selected_draft_canary_count']}`",
        f"- Reviewed draft canaries: `{payload['reviewed_draft_canary_count']}`",
        f"- Excluded draft canaries: `{payload['excluded_draft_canary_count']}`",
        "", "## Red-team decisions", "",
    ]
    for r in payload["draft_canary_redteam_reviews"]:
        lines += [
            f"- draft_canary_id: `{r['draft_canary_id']}`",
            f"  - redteam_decision: `{r['redteam_decision']}`",
            f"  - canary_usefulness: `{r['canary_usefulness']}`",
            f"  - closed_loop_disposition: `{r['closed_loop_disposition']}`",
            f"  - recommended_next_stage: `{r['recommended_next_stage']}`",
            "", "### Safety containment", "", r["safety_containment_assessment"], "",
            "### Caveat integrity", "", r["caveat_integrity_assessment"], "",
            "### Do-not-say compliance", "", r["do_not_say_compliance_assessment"], "",
            "### Provenance sufficiency", "", r["provenance_assessment"], "",
            "### Usefulness as author-draft canary", "", r["usefulness_assessment"], "",
            "### Residual risk", "", r["residual_risk_assessment"], "",
        ]
    lines += [
        "## No side effects", "",
        "No claims, editorial_reviews, source_notes, source/claim/editorial statuses, source_registry, raw captures, docs/book, schema, or daily-worker files were changed. This report does not approve authoring or publication and does not permit chapter updates.",
        "", "## Recommendation for Run 26", "",
        "Follow the red-team disposition. If the canary is safe but not useful, rebuild or enrich the author-draft input in report-only mode before attempting controlled expansion. If it passes as useful, run only a controlled report-only caveat-only draft expansion gate; do not write docs/book or approve publication.",
    ]
    return "\n".join(lines) + "\n"


def write_reports(payload: dict[str, Any], output_dir: Path, suffix: str) -> dict[str, str]:
    out_dir = output_dir if output_dir.is_absolute() else ROOT / output_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{payload['run_id']}-author-draft-canary-redteam-{suffix}" if suffix else f"{payload['run_id']}-author-draft-canary-redteam"
    json_path = out_dir / f"{stem}.json"
    md_path = out_dir / f"{stem}.md"
    payload["output_paths"] = {"json": rel(json_path), "markdown": rel(md_path)}
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(payload), encoding="utf-8")
    return payload["output_paths"]


def parse_args(argv: list[str]) -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", default=RUN_ID_DEFAULT)
    ap.add_argument("--canary-report", default=DEFAULT_CANARY_REPORT)
    ap.add_argument("--output-dir", default="reports/editorial")
    ap.add_argument("--report-suffix", default="run25")
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
