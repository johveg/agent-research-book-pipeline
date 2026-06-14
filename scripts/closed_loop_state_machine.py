#!/usr/bin/env python3
"""Closed-loop state machine and promotion contract for Terefo Heal Reboa.

Run 22A is a deterministic control-plane/configuration stage. It validates a
machine-readable state machine, classifies the Run 21 packet red-team result,
and emits a report-only transition manifest. It does not call an LLM and does
not mutate DB/protected publication artifacts.
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

from research_common import DB_PATH as DEFAULT_DB_PATH, sha256_text  # noqa: E402

RUN_ID_DEFAULT = "citation-pipeline-test-20260612"
MODE = "closed_loop_state_machine"
DEFAULT_CONFIG = "config/closed_loop_state_machine.json"
DEFAULT_RUN21 = f"reports/editorial/{RUN_ID_DEFAULT}-packet-redteam-gate-run21.json"

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
    "contradiction_review_required",
    "blocked_for_publication_by_policy",
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
}
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
FALSE_FLAGS = [
    "author_allowed",
    "publication_approved",
    "eligible_for_authoring",
    "eligible_for_publication",
    "chapter_update_allowed",
]


class StateMachineError(RuntimeError):
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


def load_json(path: Path, label: str) -> dict[str, Any]:
    if not path.exists():
        raise StateMachineError(f"missing {label}: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise StateMachineError(f"invalid JSON in {label}: {exc}") from exc
    if not isinstance(data, dict):
        raise StateMachineError(f"{label} must be a JSON object")
    return data


def load_state_machine_config(path: str | Path = DEFAULT_CONFIG) -> dict[str, Any]:
    return load_json(resolve(path), "closed-loop state-machine config")


def validate_state_machine_config(config: dict[str, Any]) -> None:
    states = config.get("states")
    dispositions = config.get("automated_dispositions")
    transitions = config.get("transitions")
    invariants = config.get("hard_invariants")
    if not isinstance(states, list) or not all(isinstance(x, str) for x in states):
        raise StateMachineError("state-machine config states must be a list of strings")
    if not isinstance(dispositions, list) or not all(isinstance(x, str) for x in dispositions):
        raise StateMachineError("state-machine config automated_dispositions must be a list of strings")
    if not isinstance(transitions, list) or not all(isinstance(x, dict) for x in transitions):
        raise StateMachineError("state-machine config transitions must be a list of objects")
    if not isinstance(invariants, dict):
        raise StateMachineError("state-machine config hard_invariants must be an object")
    missing_states = sorted(REQUIRED_STATES - set(states))
    if missing_states:
        raise StateMachineError(f"state-machine config missing required states: {missing_states}")
    missing_dispositions = sorted(REQUIRED_DISPOSITIONS - set(dispositions))
    if missing_dispositions:
        raise StateMachineError(f"state-machine config missing required dispositions: {missing_dispositions}")
    transition_pairs = {(t.get("from_state"), t.get("to_state")) for t in transitions}
    missing_transitions = sorted(REQUIRED_TRANSITIONS - transition_pairs)
    if missing_transitions:
        raise StateMachineError(f"state-machine config missing required transitions: {missing_transitions}")
    unknown_transition_states = []
    allowed_sources = set(states) | {"any"}
    for t in transitions:
        if t.get("from_state") not in allowed_sources or t.get("to_state") not in set(states):
            unknown_transition_states.append((t.get("from_state"), t.get("to_state")))
        guards = t.get("guards", t.get("guards_any"))
        if not isinstance(guards, list) or not guards:
            raise StateMachineError(f"transition {t.get('from_state')}->{t.get('to_state')} missing guards")
    if unknown_transition_states:
        raise StateMachineError(f"state-machine config transitions reference unknown states: {unknown_transition_states}")
    for key in FALSE_INVARIANT_FIELDS:
        if invariants.get(key) is not False:
            raise StateMachineError(f"hard invariant must be false: {key}")


def compact_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


def connect_readonly(path: Path) -> sqlite3.Connection:
    if not path.exists():
        raise StateMachineError(f"missing SQLite DB: {path}")
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


def find_transition(from_state: str, to_state: str, config: dict[str, Any]) -> dict[str, Any]:
    for transition in config["transitions"]:
        if transition.get("from_state") == from_state and transition.get("to_state") == to_state:
            return transition
    for transition in config["transitions"]:
        if transition.get("from_state") == "any" and transition.get("to_state") == to_state:
            return transition
    raise StateMachineError(f"transition not defined: {from_state}->{to_state}")


def guard_satisfied(guard: dict[str, Any], context: dict[str, Any]) -> bool:
    field = guard.get("field")
    if not isinstance(field, str):
        return False
    value = context.get(field)
    if "equals" in guard:
        return value == guard["equals"]
    if "in" in guard:
        allowed = guard["in"]
        return isinstance(allowed, list) and value in allowed
    if "exists" in guard:
        return (field in context and context.get(field) not in (None, "", [], {})) == bool(guard["exists"])
    return False


def validate_transition(from_state: str, to_state: str, context: dict[str, Any], config: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = config or load_state_machine_config()
    validate_state_machine_config(cfg)
    transition = find_transition(from_state, to_state, cfg)
    guards = transition.get("guards") or []
    guards_any = transition.get("guards_any") or []
    satisfied: list[str] = []
    failed: list[str] = []
    required_guards = [g.get("name") for g in (guards or guards_any)]
    if guards:
        for guard in guards:
            name = str(guard.get("name"))
            if guard_satisfied(guard, context):
                satisfied.append(name)
            else:
                failed.append(name)
        allowed = not failed
    else:
        any_ok = False
        for guard in guards_any:
            name = str(guard.get("name"))
            if guard_satisfied(guard, context):
                satisfied.append(name)
                any_ok = True
            else:
                failed.append(name)
        allowed = any_ok
        if allowed:
            failed = []
    return {
        "allowed": allowed,
        "from_state": from_state,
        "to_state": to_state,
        "transition_type": transition.get("transition_type"),
        "allowed_future_run": transition.get("allowed_future_run"),
        "required_guards": required_guards,
        "satisfied_guards": satisfied,
        "failed_guards": failed,
    }


def classify_report_object(report_object: dict[str, Any]) -> dict[str, str]:
    disposition = report_object.get("closed_loop_disposition")
    redteam = report_object.get("redteam_decision")
    if disposition == "source_context_unclear" or redteam == "source_context_unclear":
        return {"current_state": "source_context_unclear", "automated_disposition": "source_context_unclear"}
    if disposition == "contradiction_review_required" or redteam == "contradiction_review_required":
        return {"current_state": "contradiction_review_required", "automated_disposition": "contradiction_review_required"}
    if disposition == "safe_reports_only" or redteam == "safe_reports_only":
        return {"current_state": "safe_reports_only", "automated_disposition": "safe_reports_only"}
    if disposition == "exclude_from_pipeline" or redteam == "exclude_from_authoring":
        return {"current_state": "excluded_from_pipeline", "automated_disposition": "exclude_from_pipeline"}
    if redteam == "caveat_only_author_input_ready" and disposition == "caveat_only":
        return {"current_state": "packet_redteam_reviewed", "automated_disposition": "caveat_only_author_input_ready"}
    if report_object.get("packet_type") == "caveat_only_packet_candidate":
        return {"current_state": "caveat_only_packet_candidate", "automated_disposition": "caveat_only"}
    return {"current_state": "safe_reports_only", "automated_disposition": "safe_reports_only"}


def validate_run21_report(report: dict[str, Any]) -> None:
    if report.get("mode") != "llm_packet_redteam_gate":
        raise StateMachineError("Run 21 report mode mismatch")
    if report.get("report_only") is not True:
        raise StateMachineError("Run 21 report must be report_only")
    if not isinstance(report.get("packet_redteam_reviews"), list):
        raise StateMachineError("Run 21 report missing packet_redteam_reviews")
    safety = report.get("safety_flags")
    if not isinstance(safety, dict):
        raise StateMachineError("Run 21 report missing safety_flags")
    for key in ["author_allowed", "publication_approved", "eligible_for_authoring", "eligible_for_publication", "chapter_update_allowed"]:
        if safety.get(key) is not False:
            raise StateMachineError(f"Run 21 safety flag invalid: {key}")


def context_from_review(review: dict[str, Any]) -> dict[str, Any]:
    return {
        "redteam_decision": review.get("redteam_decision"),
        "author_allowed": review.get("author_allowed"),
        "publication_approved": review.get("publication_approved"),
        "eligible_for_authoring": review.get("eligible_for_authoring"),
        "eligible_for_publication": review.get("eligible_for_publication"),
        "chapter_update_allowed": review.get("chapter_update_allowed"),
    }


def transition_decision_from_validation(validation: dict[str, Any], review: dict[str, Any], classification: dict[str, str]) -> str:
    if validation["allowed"] and validation.get("transition_type") == "future_run_only":
        return "allowed_for_future_run"
    disposition = classification["automated_disposition"]
    if disposition == "source_context_unclear":
        return "blocked_source_context_unclear"
    if disposition == "contradiction_review_required":
        return "blocked_contradiction_review"
    if disposition == "safe_reports_only":
        return "blocked_safe_reports_only"
    if disposition == "needs_more_sources" or review.get("redteam_decision") == "needs_more_sources":
        return "blocked_needs_more_sources"
    if disposition == "exclude_from_pipeline":
        return "excluded_from_pipeline"
    if any(review.get(k) is not False for k in FALSE_FLAGS):
        return "blocked_invalid_safety_flags"
    return "blocked_missing_provenance" if "provenance_complete" in validation.get("failed_guards", []) else "blocked_invalid_safety_flags"


def evaluate_run21_packet_transition(report: dict[str, Any], config: dict[str, Any]) -> list[dict[str, Any]]:
    validate_run21_report(report)
    manifest: list[dict[str, Any]] = []
    selected_by_packet = {p.get("packet_id"): p for p in report.get("selected_packets", []) if isinstance(p, dict)}
    for review in report["packet_redteam_reviews"]:
        source_packet = selected_by_packet.get(review.get("packet_id"), {})
        classification = classify_report_object(review)
        current_state = classification["current_state"]
        proposed_next_state = "draft_input_candidate" if current_state == "packet_redteam_reviewed" else current_state
        validation = validate_transition("caveat_only_packet_candidate", "draft_input_candidate", context_from_review(review), config) if current_state == "packet_redteam_reviewed" else {
            "allowed": False,
            "required_guards": [],
            "satisfied_guards": [],
            "failed_guards": ["not_packet_redteam_reviewed"],
            "allowed_future_run": None,
        }
        decision = transition_decision_from_validation(validation, review, classification)
        item = {
            "object_id": review.get("packet_id"),
            "object_type": "narrative_packet_candidate",
            "current_state": current_state,
            "proposed_next_state": proposed_next_state,
            "transition_decision": decision,
            "allowed_future_run": validation.get("allowed_future_run") if decision == "allowed_for_future_run" else None,
            "required_guards": validation.get("required_guards", []),
            "satisfied_guards": validation.get("satisfied_guards", []),
            "failed_guards": validation.get("failed_guards", []),
            "hard_invariants_preserved": {k: True for k in FALSE_INVARIANT_FIELDS},
            "automated_disposition": classification["automated_disposition"],
            "advisory_only": review.get("advisory_only"),
            "author_allowed": review.get("author_allowed"),
            "publication_approved": review.get("publication_approved"),
            "eligible_for_authoring": review.get("eligible_for_authoring"),
            "eligible_for_publication": review.get("eligible_for_publication"),
            "chapter_update_allowed": review.get("chapter_update_allowed"),
            "provenance_paths": source_packet.get("provenance_paths", []),
            "limitations": review.get("limitations", []),
            "residual_risk": review.get("residual_risk"),
        }
        manifest.append(item)
    return manifest


def safety_flags() -> dict[str, bool]:
    return {
        "report_only": True,
        "advisory_only": True,
        "author_allowed": False,
        "publication_approved": False,
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
        "chapter_prose_generated": False,
        "gpt55_advisory_is_human_or_editor_approval": False,
    }


def generate_run22a_report(args: argparse.Namespace) -> dict[str, Any]:
    cfg_path = resolve(args.state_machine_config)
    run21_path = resolve(args.packet_redteam_report)
    cfg = load_state_machine_config(cfg_path)
    validate_state_machine_config(cfg)
    run21 = load_json(run21_path, "Run 21 packet red-team report")
    db = db_path()
    with connect_readonly(db) as con:
        before_counts = {"source_notes": table_count(con, "source_notes"), "claims": table_count(con, "claims"), "editorial_reviews": table_count(con, "editorial_reviews")}
        before_status = status_snapshots(con)
        manifest = evaluate_run21_packet_transition(run21, cfg)
        after_counts = {"source_notes": table_count(con, "source_notes"), "claims": table_count(con, "claims"), "editorial_reviews": table_count(con, "editorial_reviews")}
        after_status = status_snapshots(con)
    decision_counts = Counter(item["transition_decision"] for item in manifest)
    next_state_counts = Counter(item["proposed_next_state"] for item in manifest)
    payload = {
        "run_id": args.run_id,
        "generated_at": utc_now(),
        "mode": MODE,
        "input_paths": {"packet_redteam_report": rel(run21_path), "sqlite_db": rel(db)},
        "report_only": True,
        "state_machine_config_path": rel(cfg_path),
        "states_count": len(cfg["states"]),
        "transitions_count": len(cfg["transitions"]),
        "dispositions_count": len(cfg["automated_dispositions"]),
        "hard_invariants": cfg["hard_invariants"],
        "current_object_count": len(manifest),
        "transition_manifest": manifest,
        "transition_decision_counts": dict(decision_counts),
        "proposed_next_state_counts": dict(next_state_counts),
        "blocked_count": sum(1 for item in manifest if item["transition_decision"] != "allowed_for_future_run"),
        "allowed_for_future_run_count": decision_counts.get("allowed_for_future_run", 0),
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
    if payload["changed_source_notes"] or payload["claims_inserted"] or payload["editorial_reviews_inserted"] or payload["source_status_changed"] or payload["claim_status_changed"] or payload["editorial_status_changed"]:
        raise StateMachineError("forbidden DB/status delta detected during report-only state-machine evaluation")
    return payload


def render_markdown(payload: dict[str, Any], cfg: dict[str, Any]) -> str:
    lines = [
        f"# Run 22A closed-loop state machine — {payload['run_id']}", "",
        "## Summary", "",
        f"- Report-only: `{payload['report_only']}`",
        f"- State machine config: `{payload['state_machine_config_path']}`",
        f"- States: `{payload['states_count']}`",
        f"- Transitions: `{payload['transitions_count']}`",
        f"- Automated dispositions: `{payload['dispositions_count']}`",
        f"- Current objects: `{payload['current_object_count']}`",
        f"- Allowed for future run: `{payload['allowed_for_future_run_count']}`",
        f"- Blocked: `{payload['blocked_count']}`",
        "", "## States", "",
    ]
    for state in cfg["states"]:
        lines.append(f"- `{state}`")
    lines += ["", "## Automated dispositions", ""]
    for disp in cfg["automated_dispositions"]:
        lines.append(f"- `{disp}`")
    lines += ["", "## Hard invariants", ""]
    for k, v in payload["hard_invariants"].items():
        lines.append(f"- `{k}`: `{v}`")
    lines += ["", "## Current Run 21 packet classification", ""]
    for item in payload["transition_manifest"]:
        lines += [
            f"- `{item['object_id']}`",
            f"  - current_state: `{item['current_state']}`",
            f"  - proposed_next_state: `{item['proposed_next_state']}`",
            f"  - transition_decision: `{item['transition_decision']}`",
            f"  - allowed_future_run: `{item['allowed_future_run']}`",
            f"  - automated_disposition: `{item['automated_disposition']}`",
            f"  - failed_guards: `{', '.join(item['failed_guards'])}`",
            "",
        ]
    lines += [
        "## Why authoring/publication remain blocked", "",
        "Run 22A creates a control-plane state machine and evaluates only future eligibility. It does not create draft-input packages, author prose, chapter prose, claims, editorial reviews, source notes, or publication approvals. `author_allowed`, `publication_approved`, `eligible_for_authoring`, `eligible_for_publication`, and `chapter_update_allowed` remain false.",
        "", "## No-write statement", "",
        "No DB/source/book/status/schema/daily-worker changes were made by this report-only control-plane run.",
        "", "## Recommendation for next run", "",
        "Proceed to Run 22B as report-only caveat-only author-draft input package construction using this state-machine contract. Run 22B should produce draft-input package metadata only and must not author prose or approve publication.",
    ]
    return "\n".join(lines) + "\n"


def write_reports(payload: dict[str, Any], output_dir: Path, suffix: str, cfg: dict[str, Any]) -> dict[str, str]:
    out_dir = output_dir if output_dir.is_absolute() else ROOT / output_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{payload['run_id']}-closed-loop-state-machine-{suffix}" if suffix else f"{payload['run_id']}-closed-loop-state-machine"
    json_path = out_dir / f"{stem}.json"
    md_path = out_dir / f"{stem}.md"
    payload["output_paths"] = {"json": rel(json_path), "markdown": rel(md_path)}
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(payload, cfg), encoding="utf-8")
    return payload["output_paths"]


def parse_args(argv: list[str]) -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", default=RUN_ID_DEFAULT)
    ap.add_argument("--state-machine-config", default=DEFAULT_CONFIG)
    ap.add_argument("--packet-redteam-report", default=DEFAULT_RUN21)
    ap.add_argument("--output-dir", default="reports/editorial")
    ap.add_argument("--report-suffix", default="run22a")
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        cfg = load_state_machine_config(args.state_machine_config)
        validate_state_machine_config(cfg)
        payload = generate_run22a_report(args)
        write_reports(payload, resolve(args.output_dir), args.report_suffix, cfg)
        print(json.dumps({
            "ok": True,
            "output_paths": payload["output_paths"],
            "states_count": payload["states_count"],
            "transitions_count": payload["transitions_count"],
            "dispositions_count": payload["dispositions_count"],
            "current_object_count": payload["current_object_count"],
            "transition_decision_counts": payload["transition_decision_counts"],
            "proposed_next_state_counts": payload["proposed_next_state_counts"],
            "blocked_count": payload["blocked_count"],
            "allowed_for_future_run_count": payload["allowed_for_future_run_count"],
        }, sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
