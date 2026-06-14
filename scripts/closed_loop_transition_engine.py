#!/usr/bin/env python3
"""Reusable closed-loop transition engine for Terefo Heal Reboa.

Run 34 control-plane stage: evaluate configured state transitions against
report-only pipeline artifacts. This module is deterministic and report-only by
default. It does not write SQLite, source registries, raw captures, docs/book,
claims, source notes, editorial reviews, schema, or daily-worker files.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_STATES = {
    "raw_discovery_signal",
    "source_card_draft",
    "semantic_object_draft",
    "source_support_reviewed",
    "corroboration_needed",
    "source_context_unclear",
    "review_note_persisted",
    "downstream_manifest_eligible",
    "caveat_only_cluster_candidate",
    "support_cluster_candidate",
    "cluster_quality_reviewed",
    "caveat_only_packet_candidate",
    "packet_redteam_reviewed",
    "draft_input_candidate",
    "author_draft_candidate",
    "draft_redteam_reviewed",
    "chapter_update_candidate",
    "safe_reports_only",
    "excluded_from_pipeline",
    "exclude_from_pipeline",
    "contradiction_review_required",
    "blocked_for_publication_by_policy",
    "constrained_authoring_metadata_candidate",
    "constrained_authoring_metadata_preflight_passed",
    "authoring_metadata_promotion_contract_ready",
    "constrained_authoring_context_candidate",
    "needs_more_sources",
    "needs_better_authoring_metadata",
}

REQUIRED_DISPOSITIONS = {
    "auto_quarantine",
    "discovery_only",
    "needs_more_sources",
    "caveat_only",
    "exclude_from_pipeline",
    "contradiction_review_required",
    "safe_reports_only",
    "eligible_for_review_note_persistence",
    "eligible_for_clustering",
    "caveat_only_cluster_candidate",
    "eligible_for_packet_candidate",
    "caveat_only_author_input_ready",
    "blocked_for_publication_by_policy",
    "source_context_unclear",
    "metadata_preflight_passed",
    "ready_for_promotion_contract_update",
    "update_closed_loop_promotion_contract_for_authoring_metadata",
    "needs_better_authoring_metadata",
}

REQUIRED_TRANSITIONS = {
    ("source_support_reviewed", "review_note_persisted"),
    ("review_note_persisted", "downstream_manifest_eligible"),
    ("downstream_manifest_eligible", "caveat_only_cluster_candidate"),
    ("caveat_only_cluster_candidate", "caveat_only_packet_candidate"),
    ("caveat_only_packet_candidate", "draft_input_candidate"),
    ("draft_input_candidate", "author_draft_candidate"),
    ("author_draft_candidate", "draft_redteam_reviewed"),
    ("draft_redteam_reviewed", "chapter_update_candidate"),
    ("constrained_authoring_metadata_candidate", "constrained_authoring_metadata_preflight_passed"),
    ("constrained_authoring_metadata_preflight_passed", "authoring_metadata_promotion_contract_ready"),
    ("authoring_metadata_promotion_contract_ready", "constrained_authoring_context_candidate"),
}

FORBIDDEN_HUMAN_DEPENDENCY_TERMS = {
    "human_review_required",
    "requires_human_review",
    "human review required",
}

SAFETY_FALSE_FLAGS = [
    "author_allowed",
    "publication_approved",
    "eligible_for_claim_insertion",
    "eligible_for_authoring",
    "eligible_for_publication",
    "chapter_update_allowed",
]

FALSE_INVARIANT_FIELDS = {
    "author_allowed_until_explicit_authoring_gate",
    "publication_approved_until_explicit_publication_gate",
    "eligible_for_publication_until_publication_gate",
    "chapter_update_allowed_until_chapter_update_integration_gate",
    "gpt55_advisory_is_human_or_editor_approval",
    "report_files_imply_persistence",
    "persistence_implies_authoring",
    "packets_imply_prose",
    "draft_input_readiness_implies_authoring_approval",
    "author_draft_implies_publication",
    "blocked_editorial_state_allows_chapter_mutation",
    "weak_or_local_fallback_allowed_for_safety_critical_editorial_reasoning",
}

ROUTE_DECISIONS = {
    "safe_reports_only": "routed_to_safe_reports_only",
    "needs_more_sources": "routed_to_needs_more_sources",
    "needs_better_authoring_metadata": "routed_to_needs_better_metadata",
    "source_context_unclear": "routed_to_source_context_unclear",
    "contradiction_review_required": "routed_to_contradiction_review",
    "exclude_from_pipeline": "routed_to_exclude_from_pipeline",
    "excluded_from_pipeline": "routed_to_exclude_from_pipeline",
}


class TransitionEngineError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def resolve(path: str | Path) -> Path:
    p = Path(path)
    return p if p.is_absolute() else ROOT / p


def load_json(path: str | Path, label: str) -> dict[str, Any]:
    p = resolve(path)
    if not p.exists():
        raise TransitionEngineError(f"missing {label}: {p}")
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise TransitionEngineError(f"invalid JSON in {label}: {exc}") from exc
    if not isinstance(data, dict):
        raise TransitionEngineError(f"{label} must be a JSON object")
    return data


def load_state_machine_config(path: str | Path) -> dict[str, Any]:
    return load_json(path, "closed-loop state-machine config")


def _dupes(items: list[Any]) -> list[Any]:
    seen: set[Any] = set()
    dupes: list[Any] = []
    for item in items:
        key = json.dumps(item, sort_keys=True, default=str) if isinstance(item, (dict, list)) else item
        if key in seen and item not in dupes:
            dupes.append(item)
        seen.add(key)
    return dupes


def validate_state_machine_config(config: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    states = config.get("states")
    transitions = config.get("transitions")
    dispositions = config.get("automated_dispositions")
    invariants = config.get("hard_invariants")

    if not isinstance(states, list) or not all(isinstance(x, str) for x in states):
        errors.append("states must be a list of strings")
        states = []
    if not isinstance(transitions, list) or not all(isinstance(x, dict) for x in transitions):
        errors.append("transitions must be a list of objects")
        transitions = []
    if not isinstance(dispositions, list) or not all(isinstance(x, str) for x in dispositions):
        errors.append("automated_dispositions must be a list of strings")
        dispositions = []
    if not isinstance(invariants, dict):
        errors.append("hard_invariants must be an object")
        invariants = {}

    if _dupes(states):
        errors.append(f"duplicate states: {_dupes(states)}")
    if _dupes(dispositions):
        errors.append(f"duplicate dispositions: {_dupes(dispositions)}")

    pairs = [(t.get("from_state"), t.get("to_state")) for t in transitions]
    duplicate_pairs = [p for p in pairs if pairs.count(p) > 1]
    if duplicate_pairs:
        errors.append(f"duplicate transitions: {sorted(set(duplicate_pairs))}")

    missing_states = sorted(REQUIRED_STATES - set(states))
    if missing_states:
        errors.append(f"missing required states: {missing_states}")
    missing_dispositions = sorted(REQUIRED_DISPOSITIONS - set(dispositions))
    if missing_dispositions:
        errors.append(f"missing required dispositions: {missing_dispositions}")
    missing_transitions = sorted(REQUIRED_TRANSITIONS - set(pairs))
    if missing_transitions:
        errors.append(f"missing required transitions: {missing_transitions}")

    allowed_from = set(states) | {"any"}
    for t in transitions:
        if t.get("from_state") not in allowed_from or t.get("to_state") not in set(states):
            errors.append(f"transition references unknown state: {t.get('from_state')}->{t.get('to_state')}")
        guards = t.get("guards", t.get("guards_any"))
        if not isinstance(guards, list) or not guards:
            errors.append(f"transition missing guards: {t.get('from_state')}->{t.get('to_state')}")

    for key in FALSE_INVARIANT_FIELDS:
        if key in invariants and invariants.get(key) is not False:
            errors.append(f"hard invariant must be false: {key}")

    blob = json.dumps(config, sort_keys=True, default=str).lower()
    forbidden = sorted(term for term in FORBIDDEN_HUMAN_DEPENDENCY_TERMS if term in blob)
    if forbidden:
        errors.append(f"forbidden human-in-loop production dependency: {forbidden}")

    return {
        "ok": not errors,
        "errors": errors,
        "state_count": len(states),
        "transition_count": len(transitions),
        "disposition_count": len(dispositions),
        "human_in_loop_dependency_added": bool(forbidden),
    }


def _first_list_item(report: dict[str, Any], keys: list[str]) -> dict[str, Any]:
    for key in keys:
        value = report.get(key)
        if isinstance(value, list) and value and isinstance(value[0], dict):
            return value[0]
    return {}


def _extract_context(report: dict[str, Any], current_state: str, proposed_next_state: str) -> dict[str, Any]:
    candidate: dict[str, Any] = {}
    # Merge in increasing specificity. Run 33 has both selected_metadata_preflights
    # with caveat/provenance content and promotion_contract_candidates with the
    # next-state recommendation; both are part of one transition context.
    for key in [
        "selected_metadata",
        "selected_metadata_preflights",
        "constrained_authoring_metadata_preflight_reviews",
        "transition_manifest",
        "promotion_contract_candidates",
    ]:
        item = _first_list_item(report, [key])
        if item:
            candidate.update(item)
    safety_flags = report.get("safety_flags")
    if isinstance(safety_flags, dict):
        # Item-level values win if present; otherwise inherit report safety flags.
        for key, value in safety_flags.items():
            candidate.setdefault(key, value)

    # Derived guard booleans for generic config guards.
    candidate["required_caveat_exists"] = bool(candidate.get("required_caveats") or candidate.get("required_caveat") or candidate.get("required_caveat_exists") is True)
    candidate["do_not_say_exists"] = bool(candidate.get("do_not_say") or candidate.get("do_not_say_exists") is True)
    candidate["unsupported_inferences_exist"] = bool(candidate.get("unsupported_inferences") or candidate.get("unsupported_inferences_exist") is True)
    candidate["promotion_blockers_exist"] = bool(candidate.get("promotion_blockers") or candidate.get("promotion_blockers_exist") is True)
    candidate["provenance_paths_exist"] = bool(candidate.get("provenance_paths") or candidate.get("provenance_paths_exist") is True)
    if (
        current_state == "authoring_metadata_promotion_contract_ready"
        and proposed_next_state == "constrained_authoring_context_candidate"
        and (candidate.get("metadata_report_path") or candidate.get("preflight_report_path"))
    ):
        candidate["provenance_paths_exist"] = True

    # Run 33 report represents readiness for the later context-building run; the
    # transition remains future-run-only and this derived field does not approve
    # authoring/publication/claim insertion/docs-book updates.
    if current_state == "authoring_metadata_promotion_contract_ready" and proposed_next_state == "constrained_authoring_context_candidate":
        if candidate.get("recommended_next_stage") == "build_constrained_authoring_context_candidate":
            candidate["later_run_builds_context_metadata"] = True

    return candidate


def evaluate_safety_flags(context: dict[str, Any]) -> dict[str, Any]:
    failed = [flag for flag in SAFETY_FALSE_FLAGS if context.get(flag) is True]
    return {"ok": not failed, "failed_flags": failed}


def evaluate_required_fields(context: dict[str, Any]) -> dict[str, Any]:
    missing: list[str] = []
    if not context.get("required_caveat_exists"):
        missing.append("required_caveat")
    if not context.get("do_not_say_exists"):
        missing.append("do_not_say")
    if not context.get("provenance_paths_exist"):
        missing.append("provenance")
    return {"ok": not missing, "missing_fields": missing}


def route_failed_transition(context: dict[str, Any]) -> str | None:
    disposition = context.get("closed_loop_disposition") or context.get("automated_disposition") or context.get("metadata_readiness")
    if disposition in ROUTE_DECISIONS:
        return ROUTE_DECISIONS[disposition]
    if context.get("source_context_unclear") is True:
        return "routed_to_source_context_unclear"
    if context.get("needs_more_sources") is True:
        return "routed_to_needs_more_sources"
    if context.get("contradiction_review_required") is True or context.get("contradiction_unresolved") is True:
        return "routed_to_contradiction_review"
    return None


def _find_transition(config: dict[str, Any], current_state: str, proposed_next_state: str) -> dict[str, Any] | None:
    for transition in config.get("transitions", []):
        if transition.get("from_state") == current_state and transition.get("to_state") == proposed_next_state:
            return transition
    return None


def _guard_satisfied(guard: dict[str, Any], context: dict[str, Any]) -> bool:
    field = guard.get("field")
    value = context.get(field)
    if "equals" in guard:
        return value == guard["equals"]
    if "in" in guard:
        return value in guard["in"]
    return bool(value)


def _base_result(current_state: str, proposed_next_state: str) -> dict[str, Any]:
    return {
        "ok": False,
        "current_state": current_state,
        "proposed_next_state": proposed_next_state,
        "transition_decision": "transition_blocked",
        "automated_disposition": "safe_reports_only",
        "satisfied_guards": [],
        "failed_guards": [],
        "hard_invariants_preserved": False,
        "human_in_loop_dependency_added": False,
        "author_allowed": False,
        "publication_approved": False,
        "eligible_for_claim_insertion": False,
        "eligible_for_authoring": False,
        "eligible_for_publication": False,
        "chapter_update_allowed": False,
        "report_only": True,
        "llm_used": False,
    }


def evaluate_transition(config: dict[str, Any], input_report: dict[str, Any], current_state: str, proposed_next_state: str) -> dict[str, Any]:
    result = _base_result(current_state, proposed_next_state)
    validation = validate_state_machine_config(config)
    result["config_validation"] = validation
    if not validation["ok"]:
        result["transition_decision"] = "invalid_config"
        result["failed_guards"] = validation["errors"]
        result["human_in_loop_dependency_added"] = validation["human_in_loop_dependency_added"]
        return result

    states = set(config["states"])
    if current_state not in states or proposed_next_state not in states:
        result["transition_decision"] = "invalid_input"
        result["failed_guards"] = ["unknown_current_state" if current_state not in states else "unknown_proposed_next_state"]
        return result

    context = _extract_context(input_report, current_state, proposed_next_state)
    for flag in SAFETY_FALSE_FLAGS:
        result[flag] = bool(context.get(flag, False)) if context.get(flag) is True else False

    route = route_failed_transition(context)
    if route and context.get("closed_loop_disposition") not in {"caveat_only", "ready_for_promotion_contract_update"}:
        result["transition_decision"] = route
        result["automated_disposition"] = context.get("closed_loop_disposition") or context.get("automated_disposition") or "safe_reports_only"
        result["hard_invariants_preserved"] = evaluate_safety_flags(context)["ok"]
        return result

    safety = evaluate_safety_flags(context)
    if not safety["ok"]:
        result["transition_decision"] = "blocked_by_safety_flag"
        result["failed_guards"] = safety["failed_flags"]
        result["automated_disposition"] = "safe_reports_only"
        return result

    required = evaluate_required_fields(context)
    if not required["ok"]:
        missing = required["missing_fields"]
        if "required_caveat" in missing:
            decision = "blocked_by_missing_caveat"
        elif "provenance" in missing:
            decision = "blocked_by_missing_provenance"
        else:
            decision = "invalid_input"
        result["transition_decision"] = decision
        result["failed_guards"] = missing
        return result

    transition = _find_transition(config, current_state, proposed_next_state)
    if transition is None:
        result["transition_decision"] = "transition_blocked"
        result["failed_guards"] = ["missing_configured_transition"]
        return result

    guards = transition.get("guards", [])
    satisfied: list[str] = []
    failed: list[str] = []
    for guard in guards:
        name = str(guard.get("name") or guard.get("field") or "unnamed_guard")
        if _guard_satisfied(guard, context):
            satisfied.append(name)
        else:
            failed.append(name)

    result["transition_type"] = transition.get("transition_type")
    result["allowed_future_run"] = transition.get("allowed_future_run")
    result["satisfied_guards"] = satisfied
    result["failed_guards"] = failed
    result["automated_disposition"] = context.get("closed_loop_disposition") or context.get("automated_disposition") or context.get("metadata_readiness") or "safe_reports_only"
    result["hard_invariants_preserved"] = not failed and safety["ok"] and validation["ok"]
    if failed:
        result["transition_decision"] = route_failed_transition(context) or "transition_blocked"
        return result

    result["ok"] = True
    result["transition_decision"] = "transition_allowed"
    result["human_in_loop_dependency_added"] = False
    for flag in SAFETY_FALSE_FLAGS:
        result[flag] = False
    return result


def write_transition_report(evaluation: dict[str, Any], output_json: str | Path) -> dict[str, str]:
    json_path = resolve(output_json)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(evaluation)
    payload.setdefault("generated_at", utc_now())
    payload.setdefault("mode", "closed_loop_transition_engine")
    payload.setdefault("changed_db", False)
    payload.setdefault("changed_source_notes", False)
    payload.setdefault("claims_inserted", 0)
    payload.setdefault("editorial_reviews_inserted", 0)
    payload.setdefault("changed_source_registry", False)
    payload.setdefault("changed_raw_captures", False)
    payload.setdefault("changed_docs_book", False)
    payload.setdefault("changed_schema", False)
    payload.setdefault("changed_daily_worker", False)
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    md_path = json_path.with_suffix(".md")
    lines = [
        "# Closed-loop transition engine evaluation",
        "",
        f"Generated: {payload['generated_at']}",
        "",
        f"- Current state: `{payload.get('current_state')}`",
        f"- Proposed next state: `{payload.get('proposed_next_state')}`",
        f"- Transition decision: `{payload.get('transition_decision')}`",
        f"- Automated disposition: `{payload.get('automated_disposition')}`",
        f"- Transition type: `{payload.get('transition_type')}`",
        f"- Allowed future run: `{payload.get('allowed_future_run')}`",
        f"- Hard invariants preserved: `{payload.get('hard_invariants_preserved')}`",
        f"- Human-in-loop dependency added: `{payload.get('human_in_loop_dependency_added')}`",
        "",
        "This report is control-plane/report-only output. It is not authoring approval, publication approval, claim insertion, or docs/book update permission.",
    ]
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"json": str(json_path), "markdown": str(md_path)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate a closed-loop transition from state-machine config")
    parser.add_argument("--state-machine-config", required=True)
    parser.add_argument("--input-report", required=True)
    parser.add_argument("--current-state", required=True)
    parser.add_argument("--proposed-next-state", required=True)
    parser.add_argument("--output-json", required=True)
    args = parser.parse_args(argv)
    try:
        config = load_state_machine_config(args.state_machine_config)
        report = load_json(args.input_report, "input report")
        evaluation = evaluate_transition(config, report, args.current_state, args.proposed_next_state)
        evaluation["input_paths"] = {
            "state_machine_config": str(args.state_machine_config),
            "input_report": str(args.input_report),
        }
        paths = write_transition_report(evaluation, args.output_json)
        evaluation["output_paths"] = paths
        # Rewrite once to include output paths.
        Path(paths["json"]).write_text(json.dumps({**evaluation, "generated_at": utc_now(), "mode": "closed_loop_transition_engine"}, indent=2, sort_keys=True), encoding="utf-8")
        print(json.dumps({"ok": evaluation["ok"], "transition_decision": evaluation["transition_decision"], "output_json": paths["json"]}, sort_keys=True))
        return 0 if evaluation["transition_decision"] not in {"invalid_config", "invalid_input", "blocked_by_forbidden_human_dependency"} else 2
    except TransitionEngineError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
