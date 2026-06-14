#!/usr/bin/env python3
"""Run 32 report-only closed-loop promotion-contract update/test.

This deterministic control-plane script consumes the Run 31 constrained
authoring-metadata preflight report plus the Run 30 metadata report, validates
that the reviewed object satisfies machine-checkable guards, and emits a
report-only promotion-contract update plan. By default it does not modify
configuration. If --write-config is explicitly provided, it updates only the
closed-loop state-machine config with deterministic/idempotent authoring-metadata
states, dispositions, and transitions.

No LLM is called, no DB rows are written, no docs/book files are changed, and no
authoring/publication/claim/chapter approvals are granted.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from research_common import DB_PATH as DEFAULT_DB_PATH, sha256_text  # noqa: E402

RUN_ID_DEFAULT = "citation-pipeline-test-20260612"
MODE = "update_closed_loop_promotion_contract"
DEFAULT_RUN31 = f"reports/editorial/{RUN_ID_DEFAULT}-constrained-authoring-metadata-preflight-run31.json"
DEFAULT_RUN30 = f"reports/editorial/{RUN_ID_DEFAULT}-constrained-authoring-metadata-run30.json"
DEFAULT_CONFIG = "config/closed_loop_state_machine.json"
REQUIRED_CAVEAT = "Frame narrowly: OpenClaw documentation names Hermes in migration/setup tooling contexts; do not state that Hermes is a runtime dependency or general operating environment without additional sources."
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
    "advisory_only",
    *FALSE_FLAGS,
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
    "recommended_next_stage",
    "required_caveats",
    "do_not_say",
    "unsupported_inferences",
    "promotion_blockers",
    "advisory_only",
    *FALSE_FLAGS,
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
ALLOWED_PROMOTION_DECISIONS = {
    "promotion_contract_candidate_created",
    "promotion_contract_already_satisfied",
    "config_update_needed",
    "safe_reports_only",
    "needs_more_sources",
    "needs_better_authoring_metadata",
    "source_context_unclear",
    "exclude_from_pipeline",
    "contradiction_review_required",
}
ALLOWED_TRANSITION_DECISIONS = {
    "allowed_for_future_promotion_contract_update",
    "already_represented_in_contract",
    "blocked_safe_reports_only",
    "blocked_needs_more_sources",
    "blocked_needs_better_authoring_metadata",
    "blocked_source_context_unclear",
    "blocked_invalid_safety_flags",
    "blocked_missing_provenance",
    "blocked_contradiction_review",
    "excluded_from_pipeline",
}
ALLOWED_RECOMMENDED_NEXT = {
    "run_config_write_promotion_contract_update",
    "build_constrained_authoring_context_candidate",
    "keep_safe_reports_only",
    "rebuild_authoring_metadata",
    "run_additional_source_collection",
    "run_source_context_review",
    "exclude_from_pipeline",
    "run_contradiction_review",
}
REQUIRED_STATES = [
    "constrained_authoring_metadata_candidate",
    "constrained_authoring_metadata_preflight_passed",
    "authoring_metadata_promotion_contract_ready",
    "constrained_authoring_context_candidate",
    "safe_reports_only",
    "needs_more_sources",
    "needs_better_authoring_metadata",
    "source_context_unclear",
    "exclude_from_pipeline",
    "contradiction_review_required",
    "blocked_for_publication_by_policy",
]
REQUIRED_DISPOSITIONS = [
    "caveat_only",
    "metadata_preflight_passed",
    "ready_for_promotion_contract_update",
    "update_closed_loop_promotion_contract_for_authoring_metadata",
    "safe_reports_only",
    "needs_more_sources",
    "needs_better_authoring_metadata",
    "source_context_unclear",
    "exclude_from_pipeline",
    "contradiction_review_required",
]
REQUIRED_TRANSITIONS = [
    {
        "from_state": "constrained_authoring_metadata_candidate",
        "to_state": "constrained_authoring_metadata_preflight_passed",
        "transition_type": "current_or_past_stage",
        "guards": [
            {"name": "metadata_type_constrained_authoring_metadata_candidate", "field": "metadata_type", "equals": "constrained_authoring_metadata_candidate"},
            {"name": "metadata_decision_metadata_candidate_created", "field": "metadata_decision", "equals": "metadata_candidate_created"},
            {"name": "metadata_use_caveat_only", "field": "metadata_use", "equals": "caveat_only"},
            {"name": "required_caveat_exists", "field": "required_caveat_exists", "equals": True},
            {"name": "do_not_say_exists", "field": "do_not_say_exists", "equals": True},
            {"name": "unsupported_inferences_exist", "field": "unsupported_inferences_exist", "equals": True},
            {"name": "promotion_blockers_exist", "field": "promotion_blockers_exist", "equals": True},
            {"name": "provenance_paths_exist", "field": "provenance_paths_exist", "equals": True},
            {"name": "advisory_only_true", "field": "advisory_only", "equals": True},
            {"name": "author_allowed_false", "field": "author_allowed", "equals": False},
            {"name": "publication_approved_false", "field": "publication_approved", "equals": False},
            {"name": "eligible_for_claim_insertion_false", "field": "eligible_for_claim_insertion", "equals": False},
            {"name": "eligible_for_authoring_false", "field": "eligible_for_authoring", "equals": False},
            {"name": "eligible_for_publication_false", "field": "eligible_for_publication", "equals": False},
            {"name": "chapter_update_allowed_false", "field": "chapter_update_allowed", "equals": False},
        ],
    },
    {
        "from_state": "constrained_authoring_metadata_preflight_passed",
        "to_state": "authoring_metadata_promotion_contract_ready",
        "transition_type": "future_run_only",
        "allowed_future_run": "update_closed_loop_promotion_contract_for_authoring_metadata",
        "guards": [
            {"name": "preflight_decision_metadata_preflight_passed", "field": "preflight_decision", "equals": "metadata_preflight_passed"},
            {"name": "metadata_readiness_ready_for_promotion_contract_update", "field": "metadata_readiness", "equals": "ready_for_promotion_contract_update"},
            {"name": "closed_loop_disposition_caveat_only", "field": "closed_loop_disposition", "equals": "caveat_only"},
            {"name": "recommended_next_stage_update_contract", "field": "recommended_next_stage", "equals": "update_closed_loop_promotion_contract_for_authoring_metadata"},
            {"name": "advisory_only_true", "field": "advisory_only", "equals": True},
            {"name": "author_allowed_false", "field": "author_allowed", "equals": False},
            {"name": "publication_approved_false", "field": "publication_approved", "equals": False},
            {"name": "eligible_for_claim_insertion_false", "field": "eligible_for_claim_insertion", "equals": False},
            {"name": "eligible_for_authoring_false", "field": "eligible_for_authoring", "equals": False},
            {"name": "eligible_for_publication_false", "field": "eligible_for_publication", "equals": False},
            {"name": "chapter_update_allowed_false", "field": "chapter_update_allowed", "equals": False},
        ],
    },
    {
        "from_state": "authoring_metadata_promotion_contract_ready",
        "to_state": "constrained_authoring_context_candidate",
        "transition_type": "future_run_only",
        "allowed_future_run": "build_constrained_authoring_context_candidate",
        "guards": [
            {"name": "later_run_builds_context_metadata", "field": "later_run_builds_context_metadata", "equals": True},
            {"name": "authoring_approval_not_implied", "field": "author_allowed", "equals": False},
            {"name": "publication_approval_not_implied", "field": "publication_approved", "equals": False},
            {"name": "claim_insertion_not_implied", "field": "eligible_for_claim_insertion", "equals": False},
            {"name": "docs_book_update_not_implied", "field": "chapter_update_allowed", "equals": False},
        ],
    },
]
FORBIDDEN_PRODUCTION_DEPENDENCY_TERMS = ["human_review_required", "requires_human_review", "human review required"]
PROTECTED_PATHS = {
    "source_registry": ROOT / "data" / "source_registry.json",
    "raw_captures": ROOT / "raw",
    "docs_book": ROOT / "docs" / "book",
    "schema": ROOT / "data" / "schema.sql",
    "daily_worker": ROOT / "scripts" / "daily_book_worker.py",
}


class PromotionContractError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def resolve(path: str | Path) -> Path:
    p = Path(path)
    return p if p.is_absolute() else ROOT / p


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def db_path() -> Path:
    override = os.environ.get("TEREFO_BOOK_DB_PATH", "").strip()
    return Path(override) if override else DEFAULT_DB_PATH


def compact_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


def load_json(path: str | Path, label: str) -> dict[str, Any]:
    p = resolve(path)
    if not p.exists():
        raise PromotionContractError(f"missing {label}: {p}")
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PromotionContractError(f"invalid JSON in {label}: {exc}") from exc
    if not isinstance(data, dict):
        raise PromotionContractError(f"{label} must be JSON object")
    return data


def sha_file(path: Path) -> str | None:
    return sha256_text(path.read_text(encoding="utf-8", errors="replace")) if path.exists() and path.is_file() else None


def tree_snapshot(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    return {str(p.relative_to(path)): sha_file(p) or "" for p in sorted(path.rglob("*")) if p.is_file()}


def snapshot_protected() -> dict[str, Any]:
    return {
        "source_registry_hash": sha_file(PROTECTED_PATHS["source_registry"]),
        "raw_captures_hashes": tree_snapshot(PROTECTED_PATHS["raw_captures"]),
        "docs_book_hashes": tree_snapshot(PROTECTED_PATHS["docs_book"]),
        "schema_hash": sha_file(PROTECTED_PATHS["schema"]),
        "daily_worker_hash": sha_file(PROTECTED_PATHS["daily_worker"]),
    }


def protected_delta(before: dict[str, Any], after: dict[str, Any]) -> dict[str, bool]:
    return {
        "changed_source_registry": before["source_registry_hash"] != after["source_registry_hash"],
        "changed_raw_captures": before["raw_captures_hashes"] != after["raw_captures_hashes"],
        "changed_docs_book": before["docs_book_hashes"] != after["docs_book_hashes"],
        "changed_schema": before["schema_hash"] != after["schema_hash"],
        "changed_daily_worker": before["daily_worker_hash"] != after["daily_worker_hash"],
    }


def connect_readonly(path: Path) -> sqlite3.Connection:
    if not path.exists():
        raise PromotionContractError(f"missing SQLite DB: {path}")
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


def db_snapshot(path: Path) -> dict[str, Any]:
    con = connect_readonly(path)
    try:
        snap = {
            "source_notes_count": table_count(con, "source_notes"),
            "claims_count": table_count(con, "claims"),
            "editorial_reviews_count": table_count(con, "editorial_reviews"),
        }
        snap.update(status_snapshots(con))
        return snap
    finally:
        con.close()


def guard_no_human_loop_dependency(config: dict[str, Any]) -> None:
    text = json.dumps(config, sort_keys=True, ensure_ascii=False).lower()
    for term in FORBIDDEN_PRODUCTION_DEPENDENCY_TERMS:
        if term in text:
            raise PromotionContractError("human-in-loop production dependency is forbidden")


def validate_config_shape(config: dict[str, Any]) -> None:
    if not isinstance(config.get("states"), list) or not all(isinstance(x, str) for x in config.get("states", [])):
        raise PromotionContractError("state-machine config states must be a list of strings")
    if not isinstance(config.get("automated_dispositions"), list) or not all(isinstance(x, str) for x in config.get("automated_dispositions", [])):
        raise PromotionContractError("state-machine config automated_dispositions must be a list of strings")
    if not isinstance(config.get("transitions"), list) or not all(isinstance(x, dict) for x in config.get("transitions", [])):
        raise PromotionContractError("state-machine config transitions must be a list of objects")
    if not isinstance(config.get("hard_invariants"), dict):
        raise PromotionContractError("state-machine config hard_invariants must be an object")
    states = config["states"]
    if len(states) != len(set(states)):
        raise PromotionContractError("state-machine config has duplicate states")
    dispositions = config["automated_dispositions"]
    if len(dispositions) != len(set(dispositions)):
        raise PromotionContractError("state-machine config has duplicate automated_dispositions")
    pairs = [(t.get("from_state"), t.get("to_state")) for t in config["transitions"]]
    if len(pairs) != len(set(pairs)):
        raise PromotionContractError("state-machine config has duplicate transitions")
    guard_no_human_loop_dependency(config)
    invariants = config["hard_invariants"]
    for key in [
        "author_allowed_until_explicit_authoring_gate",
        "publication_approved_until_explicit_publication_gate",
        "eligible_for_publication_until_publication_gate",
        "chapter_update_allowed_until_chapter_update_integration_gate",
        "gpt55_advisory_is_human_or_editor_approval",
        "blocked_editorial_state_allows_chapter_mutation",
        "weak_or_local_fallback_allowed_for_safety_critical_editorial_reasoning",
    ]:
        if invariants.get(key) is not False:
            raise PromotionContractError(f"hard invariant must remain false: {key}")


def required_caveat_present(items: Any) -> bool:
    return isinstance(items, list) and REQUIRED_CAVEAT in items


def require_nonempty_list(obj: dict[str, Any], key: str, label: str) -> None:
    if not isinstance(obj.get(key), list) or not obj.get(key):
        raise PromotionContractError(f"{label} missing {key}")


def require_safety_flags(obj: dict[str, Any], label: str) -> None:
    if obj.get("advisory_only") is not True:
        raise PromotionContractError(f"{label} missing safety flag advisory_only=true")
    for flag in FALSE_FLAGS:
        if obj.get(flag) is not False:
            raise PromotionContractError(f"{label} safety flag {flag} must be false")


def validate_preflight_report(report: dict[str, Any]) -> None:
    if report.get("mode") != "llm_constrained_authoring_metadata_preflight":
        raise PromotionContractError("preflight report mode mismatch")
    if report.get("report_only") is not True:
        raise PromotionContractError("preflight report must be report_only=true")
    reviews = report.get("constrained_authoring_metadata_preflight_reviews")
    if not isinstance(reviews, list):
        raise PromotionContractError("preflight report reviews must be a list")
    for review in reviews:
        if not isinstance(review, dict):
            raise PromotionContractError("preflight review must be object")
        for field in REQUIRED_REVIEW_FIELDS:
            if field not in review:
                raise PromotionContractError(f"preflight review missing required field {field}")
        if review["preflight_decision"] not in ALLOWED_PREFLIGHT_DECISIONS:
            raise PromotionContractError(f"invalid preflight_decision: {review['preflight_decision']}")
        if review["metadata_readiness"] not in ALLOWED_METADATA_READINESS:
            raise PromotionContractError(f"invalid metadata_readiness: {review['metadata_readiness']}")
        if review["closed_loop_disposition"] not in ALLOWED_DISPOSITIONS:
            raise PromotionContractError(f"invalid closed_loop_disposition: {review['closed_loop_disposition']}")
        if review["recommended_next_stage"] not in ALLOWED_NEXT_STAGES:
            raise PromotionContractError(f"invalid recommended_next_stage: {review['recommended_next_stage']}")
        require_safety_flags(review, "preflight review")
        if not required_caveat_present(review.get("required_caveats")):
            raise PromotionContractError("preflight review missing required caveat")
        require_nonempty_list(review, "do_not_say", "preflight review")
        require_nonempty_list(review, "unsupported_inferences", "preflight review")
        require_nonempty_list(review, "promotion_blockers", "preflight review")


def validate_metadata_report(report: dict[str, Any]) -> None:
    if report.get("mode") != "build_constrained_authoring_metadata":
        raise PromotionContractError("metadata report mode mismatch")
    candidates = report.get("constrained_authoring_metadata_candidates")
    if not isinstance(candidates, list):
        raise PromotionContractError("metadata report candidates must be a list")
    for meta in candidates:
        if not isinstance(meta, dict):
            raise PromotionContractError("metadata candidate must be object")
        for field in REQUIRED_METADATA_FIELDS:
            if field not in meta:
                raise PromotionContractError(f"metadata candidate missing required field {field}")
        require_safety_flags(meta, "metadata candidate")
        if not required_caveat_present(meta.get("required_caveats")):
            raise PromotionContractError("metadata candidate missing required caveat")
        require_nonempty_list(meta, "do_not_say", "metadata candidate")
        require_nonempty_list(meta, "unsupported_inferences", "metadata candidate")
        require_nonempty_list(meta, "promotion_blockers", "metadata candidate")
        require_nonempty_list(meta, "provenance_paths", "metadata candidate provenance")


def metadata_by_id(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {m["metadata_id"]: m for m in report.get("constrained_authoring_metadata_candidates", [])}


def list_additions(existing: list[str], required: list[str]) -> list[str]:
    existing_set = set(existing)
    return [x for x in required if x not in existing_set]


def transition_key(t: dict[str, Any]) -> tuple[str, str]:
    return (str(t.get("from_state")), str(t.get("to_state")))


def transition_additions(existing: list[dict[str, Any]]) -> list[dict[str, Any]]:
    existing_pairs = {transition_key(t) for t in existing}
    return [deepcopy(t) for t in REQUIRED_TRANSITIONS if transition_key(t) not in existing_pairs]


def additions_for_config(config: dict[str, Any]) -> dict[str, Any]:
    return {
        "states": list_additions(config["states"], REQUIRED_STATES),
        "automated_dispositions": list_additions(config["automated_dispositions"], REQUIRED_DISPOSITIONS),
        "transitions": transition_additions(config["transitions"]),
    }


def deterministic_config(config: dict[str, Any]) -> dict[str, Any]:
    cfg = deepcopy(config)
    # Preserve existing sequence, append missing in required order, then sort appended-safe vocabulary for deterministic files.
    cfg["states"] = sorted(dict.fromkeys(cfg["states"]))
    cfg["automated_dispositions"] = sorted(dict.fromkeys(cfg["automated_dispositions"]))
    cfg["transitions"] = sorted(cfg["transitions"], key=lambda t: (str(t.get("from_state")), str(t.get("to_state")), str(t.get("transition_type", ""))))
    return cfg


def apply_additions(config: dict[str, Any], additions: dict[str, Any]) -> dict[str, Any]:
    cfg = deepcopy(config)
    cfg["states"].extend(additions["states"])
    cfg["automated_dispositions"].extend(additions["automated_dispositions"])
    cfg["transitions"].extend(additions["transitions"])
    cfg = deterministic_config(cfg)
    validate_config_shape(cfg)
    # No required production dependency should ever be represented after write.
    guard_no_human_loop_dependency(cfg)
    return cfg


def transition_context_from_metadata(meta: dict[str, Any]) -> dict[str, Any]:
    return {
        "metadata_type": meta.get("metadata_type"),
        "metadata_decision": meta.get("metadata_decision"),
        "metadata_use": meta.get("metadata_use"),
        "required_caveat_exists": required_caveat_present(meta.get("required_caveats")),
        "do_not_say_exists": isinstance(meta.get("do_not_say"), list) and bool(meta.get("do_not_say")),
        "unsupported_inferences_exist": isinstance(meta.get("unsupported_inferences"), list) and bool(meta.get("unsupported_inferences")),
        "promotion_blockers_exist": isinstance(meta.get("promotion_blockers"), list) and bool(meta.get("promotion_blockers")),
        "provenance_paths_exist": isinstance(meta.get("provenance_paths"), list) and bool(meta.get("provenance_paths")),
        "advisory_only": meta.get("advisory_only"),
        **{flag: meta.get(flag) for flag in FALSE_FLAGS},
    }


def transition_context_from_review(review: dict[str, Any]) -> dict[str, Any]:
    return {
        "preflight_decision": review.get("preflight_decision"),
        "metadata_readiness": review.get("metadata_readiness"),
        "closed_loop_disposition": review.get("closed_loop_disposition"),
        "recommended_next_stage": review.get("recommended_next_stage"),
        "advisory_only": review.get("advisory_only"),
        **{flag: review.get(flag) for flag in FALSE_FLAGS},
    }


def evaluate_guards(guards: list[dict[str, Any]], context: dict[str, Any]) -> tuple[list[str], list[str]]:
    satisfied: list[str] = []
    failed: list[str] = []
    for guard in guards:
        name = str(guard.get("name"))
        field = str(guard.get("field"))
        value = context.get(field)
        if "equals" in guard:
            ok = value == guard["equals"]
        elif "in" in guard:
            ok = value in guard["in"]
        else:
            ok = False
        (satisfied if ok else failed).append(name)
    return satisfied, failed


def select_preflight_reviews(preflight_report: dict[str, Any], metadata_report: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    metas = metadata_by_id(metadata_report)
    selected: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for review in preflight_report.get("constrained_authoring_metadata_preflight_reviews", []):
        meta = metas.get(review["metadata_id"])
        if meta is None:
            raise PromotionContractError(f"metadata provenance missing for {review['metadata_id']}")
        if (
            review["preflight_decision"] == "metadata_preflight_passed"
            and review["metadata_readiness"] == "ready_for_promotion_contract_update"
            and review["closed_loop_disposition"] == "caveat_only"
            and review["recommended_next_stage"] == "update_closed_loop_promotion_contract_for_authoring_metadata"
            and meta.get("metadata_type") == "constrained_authoring_metadata_candidate"
            and meta.get("metadata_decision") == "metadata_candidate_created"
            and meta.get("metadata_use") == "caveat_only"
        ):
            selected.append({"review": review, "metadata": meta})
        else:
            excluded.append({
                "metadata_id": review.get("metadata_id"),
                "preflight_decision": review.get("preflight_decision"),
                "metadata_readiness": review.get("metadata_readiness"),
                "automated_disposition": review.get("closed_loop_disposition"),
                "recommended_next_stage": review.get("recommended_next_stage"),
                "reason": "not_routed_to_promotion_contract_update",
                "advisory_only": True,
                **{flag: False for flag in FALSE_FLAGS},
            })
    return selected, excluded


def build_candidate(selected: dict[str, Any], config_additions: dict[str, Any], represented: bool, preflight_path: Path, metadata_path: Path) -> dict[str, Any]:
    review = selected["review"]
    meta = selected["metadata"]
    first_ctx = transition_context_from_metadata(meta)
    second_ctx = transition_context_from_review(review)
    first_satisfied, first_failed = evaluate_guards(REQUIRED_TRANSITIONS[0]["guards"], first_ctx)
    second_satisfied, second_failed = evaluate_guards(REQUIRED_TRANSITIONS[1]["guards"], second_ctx)
    failed = first_failed + second_failed
    if failed:
        raise PromotionContractError(f"promotion contract guards failed: {failed}")
    decision = "promotion_contract_already_satisfied" if represented else "config_update_needed"
    transition_decision = "already_represented_in_contract" if represented else "allowed_for_future_promotion_contract_update"
    next_stage = "build_constrained_authoring_context_candidate" if represented else "run_config_write_promotion_contract_update"
    return {
        "contract_candidate_id": f"contract_run32_authoring_metadata_{review['metadata_id'].removeprefix('metadata_run30_constrained_authoring_')}",
        "metadata_id": review["metadata_id"],
        "preflight_report_path": rel(preflight_path),
        "metadata_report_path": rel(metadata_path),
        "current_state": "constrained_authoring_metadata_preflight_passed",
        "proposed_next_state": "authoring_metadata_promotion_contract_ready",
        "promotion_contract_decision": decision,
        "transition_decision": transition_decision,
        "required_states": REQUIRED_STATES,
        "required_transitions": [{"from_state": t["from_state"], "to_state": t["to_state"], "transition_type": t["transition_type"]} for t in REQUIRED_TRANSITIONS],
        "required_dispositions": REQUIRED_DISPOSITIONS,
        "satisfied_guards": first_satisfied + second_satisfied,
        "failed_guards": failed,
        "hard_invariants_preserved": True,
        "human_in_loop_dependency_added": False,
        "automated_disposition": review["closed_loop_disposition"],
        "recommended_next_stage": next_stage,
        "limitations": [
            "This is a report-only promotion-contract control object.",
            "It does not approve authoring, publication, claim insertion, or docs/book updates.",
            "Future constrained_authoring_context_candidate transition is reserved for a later run.",
            "The evidence remains narrow, singleton-derived, and caveat-only.",
        ],
        "residual_risk": "Downstream stages could overpromote tooling-adjacency metadata into dependency or operating-environment language if later gates strip the mandatory caveat.",
        "advisory_only": True,
        **{flag: False for flag in FALSE_FLAGS},
    }


def write_markdown(report: dict[str, Any], path: Path) -> None:
    lines = [
        f"# Run 32 promotion-contract authoring metadata report — {report['run_id']}",
        "",
        "## Summary",
        f"- Report only: `{report['report_only']}`",
        f"- LLM used: `{report['llm_used']}`",
        f"- Selected metadata preflights: `{report['selected_metadata_preflight_count']}`",
        f"- Promotion contract candidates: `{report['promotion_contract_candidate_count']}`",
        f"- Excluded metadata preflights: `{report['excluded_metadata_preflight_count']}`",
        f"- Config update needed: `{report['config_update_needed']}`",
        f"- Config updated: `{report['config_updated']}`",
        f"- Human-in-loop dependency added: `{report['human_in_loop_dependency_added']}`",
        "",
        "## Decisions",
        f"- Promotion contract decision counts: `{json.dumps(report['promotion_contract_decision_counts'], sort_keys=True)}`",
        f"- Transition decision counts: `{json.dumps(report['transition_decision_counts'], sort_keys=True)}`",
        f"- Recommended next-stage counts: `{json.dumps(report['recommended_next_stage_counts'], sort_keys=True)}`",
        "",
        "## Proposed states/transitions/dispositions",
        f"- Proposed states: `{json.dumps(report['proposed_config_additions']['states'], sort_keys=True)}`",
        f"- Proposed dispositions: `{json.dumps(report['proposed_config_additions']['automated_dispositions'], sort_keys=True)}`",
        f"- Proposed transitions: `{json.dumps([{k: t[k] for k in ['from_state','to_state','transition_type'] if k in t} for t in report['proposed_config_additions']['transitions']], sort_keys=True)}`",
        "",
        "## Contract candidates",
    ]
    if report["promotion_contract_candidates"]:
        for candidate in report["promotion_contract_candidates"]:
            lines += [
                f"### {candidate['metadata_id']}",
                f"- Current state: `{candidate['current_state']}`",
                f"- Proposed next state: `{candidate['proposed_next_state']}`",
                f"- Promotion decision: `{candidate['promotion_contract_decision']}`",
                f"- Transition decision: `{candidate['transition_decision']}`",
                f"- Automated disposition: `{candidate['automated_disposition']}`",
                f"- Recommended next stage: `{candidate['recommended_next_stage']}`",
                f"- Hard invariants preserved: `{candidate['hard_invariants_preserved']}`",
                f"- Human-in-loop dependency added: `{candidate['human_in_loop_dependency_added']}`",
                f"- Residual risk: {candidate['residual_risk']}",
                "",
            ]
    else:
        lines.append("- No promotion-contract candidate was created.")
    lines += [
        "",
        "## Hard invariants",
        "- Authoring remains disallowed.",
        "- Publication remains disallowed.",
        "- Claim insertion remains disallowed.",
        "- Chapter updates remain disallowed.",
        "- GPT-5.5 advisory output is not human/editor approval.",
        "- Routine production routing uses automated dispositions, not a required human stop.",
        "",
        "## Why no publication artifacts changed",
        "This run only validates or proposes closed-loop state/promotion-contract vocabulary and transitions. It does not generate prose, persist metadata to the database, write reports into docs/book, or modify publication/status artifacts.",
        "",
        "## Recommendation for Run 33",
        "If config update is needed, run an explicit config-write promotion-contract update. If already represented, proceed to a report-only constrained authoring-context candidate stage while preserving all hard safety flags as false.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def run(args: argparse.Namespace) -> dict[str, Any]:
    preflight_path = resolve(args.preflight_report)
    metadata_path = resolve(args.metadata_report)
    config_path = resolve(args.state_machine_config)
    protected_before = snapshot_protected()
    db_before = db_snapshot(db_path())
    config = load_json(config_path, "closed-loop state-machine config")
    validate_config_shape(config)
    preflight = load_json(preflight_path, "Run 31 metadata preflight report")
    metadata = load_json(metadata_path, "Run 30 metadata report")
    validate_preflight_report(preflight)
    validate_metadata_report(metadata)
    selected, excluded = select_preflight_reviews(preflight, metadata)

    additions = additions_for_config(config)
    config_update_needed = bool(additions["states"] or additions["automated_dispositions"] or additions["transitions"])
    state_count_before = len(config["states"])
    transition_count_before = len(config["transitions"])
    disposition_count_before = len(config["automated_dispositions"])
    represented = not config_update_needed
    applied_additions = {"states": [], "automated_dispositions": [], "transitions": []}
    config_updated = False
    config_after = config
    if args.write_config and config_update_needed:
        config_after = apply_additions(config, additions)
        config_path.write_text(json.dumps(config_after, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        applied_additions = additions
        config_updated = True
    elif args.write_config and not config_update_needed:
        config_after = config
    else:
        config_after = config

    state_count_after = len(config_after["states"])
    transition_count_after = len(config_after["transitions"])
    disposition_count_after = len(config_after["automated_dispositions"])
    represented_for_candidates = represented or config_updated
    candidates = [build_candidate(s, additions, represented_for_candidates, preflight_path, metadata_path) for s in selected]

    for candidate in candidates:
        if candidate["promotion_contract_decision"] not in ALLOWED_PROMOTION_DECISIONS:
            raise PromotionContractError(f"invalid promotion_contract_decision: {candidate['promotion_contract_decision']}")
        if candidate["transition_decision"] not in ALLOWED_TRANSITION_DECISIONS:
            raise PromotionContractError(f"invalid transition_decision: {candidate['transition_decision']}")
        if candidate["recommended_next_stage"] not in ALLOWED_RECOMMENDED_NEXT:
            raise PromotionContractError(f"invalid recommended_next_stage: {candidate['recommended_next_stage']}")

    db_after = db_snapshot(db_path())
    protected_after = snapshot_protected()
    protected_changes = protected_delta(protected_before, protected_after)
    db_changed = db_before != db_after
    output_base = resolve(args.output_dir) / f"{args.run_id}-promotion-contract-authoring-metadata-{args.report_suffix}"
    report = {
        "run_id": args.run_id,
        "generated_at": utc_now(),
        "mode": MODE,
        "input_paths": {
            "preflight_report": rel(preflight_path),
            "metadata_report": rel(metadata_path),
            "state_machine_config": rel(config_path),
            "sqlite_db": rel(db_path()),
            "supporting_inputs": [
                "reports/editorial/citation-pipeline-test-20260612-author-draft-canary-v2-redteam-run29.json",
                "reports/editorial/citation-pipeline-test-20260612-author-draft-canary-v2-run28.json",
                "reports/editorial/citation-pipeline-test-20260612-rebuilt-author-input-preflight-run27.json",
                "reports/editorial/citation-pipeline-test-20260612-author-draft-input-rebuild-run26.json",
                "reports/editorial/citation-pipeline-test-20260612-author-draft-canary-redteam-run25.json",
                "reports/editorial/citation-pipeline-test-20260612-author-draft-canary-run24.json",
                "reports/editorial/citation-pipeline-test-20260612-author-draft-input-preflight-run23.json",
                "reports/editorial/citation-pipeline-test-20260612-author-draft-input-run22b.json",
                "reports/editorial/citation-pipeline-test-20260612-closed-loop-state-machine-run22a.json",
                "config/reasoning_models.json",
            ],
        },
        "report_only": True,
        "llm_used": False,
        "provider": None,
        "model": None,
        "bridge": None,
        "model_profile": None,
        "selected_metadata_preflight_count": len(selected),
        "promotion_contract_candidate_count": len(candidates),
        "excluded_metadata_preflight_count": len(excluded),
        "config_update_needed": config_update_needed,
        "config_updated": config_updated,
        "state_count_before": state_count_before,
        "state_count_after": state_count_after,
        "transition_count_before": transition_count_before,
        "transition_count_after": transition_count_after,
        "disposition_count_before": disposition_count_before,
        "disposition_count_after": disposition_count_after,
        "promotion_contract_decision_counts": dict(Counter(c["promotion_contract_decision"] for c in candidates)),
        "transition_decision_counts": dict(Counter(c["transition_decision"] for c in candidates)),
        "recommended_next_stage_counts": dict(Counter(c["recommended_next_stage"] for c in candidates)),
        "selected_metadata_preflights": [s["review"] for s in selected],
        "excluded_metadata_preflights": excluded,
        "promotion_contract_candidates": candidates,
        "proposed_config_additions": additions,
        "applied_config_additions": applied_additions,
        "failed_contract_checks": [],
        "human_in_loop_dependency_added": False,
        "changed_db": db_changed,
        "changed_source_notes": db_before["source_notes_count"] != db_after["source_notes_count"],
        **protected_changes,
        "claims_inserted": db_after["claims_count"] - db_before["claims_count"],
        "editorial_reviews_inserted": db_after["editorial_reviews_count"] - db_before["editorial_reviews_count"],
        "source_notes_count_before": db_before["source_notes_count"],
        "source_notes_count_after": db_after["source_notes_count"],
        "claims_count_before": db_before["claims_count"],
        "claims_count_after": db_after["claims_count"],
        "editorial_reviews_count_before": db_before["editorial_reviews_count"],
        "editorial_reviews_count_after": db_after["editorial_reviews_count"],
        "source_status_changed": db_before["sources_status_hash"] != db_after["sources_status_hash"],
        "claim_status_changed": db_before["claims_status_hash"] != db_after["claims_status_hash"],
        "editorial_status_changed": db_before["editorial_reviews_hash"] != db_after["editorial_reviews_hash"],
        "safety_flags": {
            "report_only": True,
            "deterministic_contract_work": True,
            "weak_local_fallback_refused": True,
            "new_author_prose_created": False,
            "chapter_ready_prose_created": False,
            "docs_book_modified": False,
            "claims_inserted": False,
            "editorial_reviews_inserted": False,
            "source_notes_written": False,
            "metadata_persisted_to_db": False,
            "source_registry_promoted": False,
            "raw_content_stored": False,
            "schema_modified": False,
            "daily_worker_modified": False,
            "author_allowed": False,
            "publication_approved": False,
            "eligible_for_claim_insertion": False,
            "eligible_for_authoring": False,
            "eligible_for_publication": False,
            "chapter_update_allowed": False,
            "gpt55_advisory_is_human_or_editor_approval": False,
            "required_production_human_stop_added": False,
            "blocked_editorial_state_dominates_chapter_mutation": True,
        },
        "weak_local_fallback_refused": True,
        "output_paths": {"json": rel(output_base.with_suffix(".json")), "markdown": rel(output_base.with_suffix(".md"))},
    }
    output_base.parent.mkdir(parents=True, exist_ok=True)
    output_base.with_suffix(".json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_markdown(report, output_base.with_suffix(".md"))
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", default=RUN_ID_DEFAULT)
    parser.add_argument("--preflight-report", default=DEFAULT_RUN31)
    parser.add_argument("--metadata-report", default=DEFAULT_RUN30)
    parser.add_argument("--state-machine-config", default=DEFAULT_CONFIG)
    parser.add_argument("--output-dir", default="reports/editorial")
    parser.add_argument("--report-suffix", default="run32")
    parser.add_argument("--write-config", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        report = run(args)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({
        "ok": True,
        "selected_metadata_preflight_count": report["selected_metadata_preflight_count"],
        "promotion_contract_candidate_count": report["promotion_contract_candidate_count"],
        "excluded_metadata_preflight_count": report["excluded_metadata_preflight_count"],
        "config_update_needed": report["config_update_needed"],
        "config_updated": report["config_updated"],
        "output_json": report["output_paths"]["json"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
