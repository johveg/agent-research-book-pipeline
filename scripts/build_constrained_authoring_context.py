#!/usr/bin/env python3
"""Run 42 report-only constrained authoring-context candidate builder.

Consumes the promotion-contract report and reusable transition-engine report that
authorize only a future context-metadata run. Emits constrained authoring context
metadata for later gates; it does not create author prose, mutate docs/book, write
SQLite rows, promote statuses, or approve authoring/publication/chapter updates.
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
MODE = "build_constrained_authoring_context"
DEFAULT_CONTRACT = f"reports/editorial/{RUN_ID_DEFAULT}-promotion-contract-authoring-metadata-run33.json"
DEFAULT_TRANSITION = f"reports/editorial/{RUN_ID_DEFAULT}-transition-engine-evaluation-run34.json"
FALSE_FLAGS = [
    "author_allowed",
    "publication_approved",
    "eligible_for_claim_insertion",
    "eligible_for_authoring",
    "eligible_for_publication",
    "chapter_update_allowed",
]
CHAPTER_PROSE_KEYS = {
    "draft_prose",
    "new_draft_prose",
    "chapter_ready_prose",
    "chapter_prose",
    "publishable_wording",
    "citation_resolved_chapter_text",
    "expanded_paragraph",
    "author_paragraph",
    "final_prose",
    "book_text",
}


class ContextError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def resolve(path: str | Path) -> Path:
    p = Path(path)
    return p if p.is_absolute() else ROOT / p


def rel(path: str | Path) -> str:
    p = resolve(path)
    try:
        return str(p.relative_to(ROOT))
    except ValueError:
        return str(p)


def db_path() -> Path:
    override = os.environ.get("TEREFO_BOOK_DB_PATH", "").strip()
    return Path(override) if override else DEFAULT_DB_PATH


def load_json(path: str | Path, label: str) -> dict[str, Any]:
    p = resolve(path)
    if not p.exists():
        raise ContextError(f"missing {label}: {p}")
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ContextError(f"invalid JSON in {label}: {exc}") from exc
    if not isinstance(data, dict):
        raise ContextError(f"{label} must be a JSON object")
    return data


def compact_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


def connect_readonly(path: Path) -> sqlite3.Connection:
    if not path.exists():
        raise ContextError(f"missing SQLite DB: {path}")
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA query_only = ON")
    return con


def counts_and_status(path: Path) -> tuple[dict[str, int], dict[str, str]]:
    con = connect_readonly(path)
    try:
        counts = {table: int(con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]) for table in ["source_notes", "claims", "editorial_reviews"]}
        specs = {
            "sources_status_hash": "SELECT id, quality_score, privacy_publication_status, duplicate_status FROM sources ORDER BY id",
            "claims_status_hash": "SELECT id, status, publication_decision, contradiction_status FROM claims ORDER BY id",
            "editorial_reviews_hash": "SELECT id, run_id, review_type, status, summary, report_path, created_at FROM editorial_reviews ORDER BY id",
            "source_notes_hash": "SELECT id, source_id, note_type, created_at FROM source_notes ORDER BY id",
        }
        status = {name: sha256_text(compact_json([tuple(r) for r in con.execute(sql).fetchall()])) for name, sql in specs.items()}
        return counts, status
    finally:
        con.close()


def require_no_chapter_prose_fields(obj: Any, path: str = "root") -> None:
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key in CHAPTER_PROSE_KEYS:
                raise ContextError(f"chapter-ready/new prose field is forbidden: {path}.{key}")
            require_no_chapter_prose_fields(value, f"{path}.{key}")
    elif isinstance(obj, list):
        for idx, value in enumerate(obj):
            require_no_chapter_prose_fields(value, f"{path}[{idx}]")


def require_false_flags(obj: dict[str, Any], label: str) -> None:
    if obj.get("advisory_only") is not True:
        raise ContextError(f"{label} missing advisory_only=true")
    for flag in FALSE_FLAGS:
        if obj.get(flag) is not False:
            raise ContextError(f"{label} safety flag {flag} must be false")


def validate_headers(contract: dict[str, Any], transition: dict[str, Any]) -> None:
    if contract.get("mode") != "update_closed_loop_promotion_contract" or contract.get("report_only") is not True:
        raise ContextError("promotion-contract report mode/report_only invalid")
    if transition.get("mode") != "closed_loop_transition_engine" or transition.get("report_only") is not True:
        raise ContextError("transition report mode/report_only invalid")
    require_no_chapter_prose_fields(contract, "promotion_contract")
    require_no_chapter_prose_fields(transition, "transition")
    if transition.get("ok") is not True or transition.get("transition_decision") != "transition_allowed":
        raise ContextError("transition report is not transition_allowed")
    if transition.get("current_state") != "constrained_authoring_metadata_preflight_passed":
        raise ContextError("transition current_state is not constrained_authoring_metadata_preflight_passed")
    if transition.get("proposed_next_state") != "authoring_metadata_promotion_contract_ready":
        raise ContextError("transition proposed_next_state is not authoring_metadata_promotion_contract_ready")
    if transition.get("hard_invariants_preserved") is not True:
        raise ContextError("transition hard invariants are not preserved")
    for flag in FALSE_FLAGS:
        if transition.get(flag) is not False:
            raise ContextError(f"transition safety flag {flag} must be false")


def _first_by_metadata_id(items: Any, metadata_id: str) -> dict[str, Any]:
    if not isinstance(items, list):
        return {}
    for item in items:
        if isinstance(item, dict) and item.get("metadata_id") == metadata_id:
            return item
    return {}


def _require_nonempty_list(item: dict[str, Any], key: str, label: str) -> list[Any]:
    value = item.get(key)
    if not isinstance(value, list) or not value:
        raise ContextError(f"{label} missing {key}")
    return value


def build_context_candidate(candidate: dict[str, Any], review: dict[str, Any], contract_path: str, transition_path: str) -> dict[str, Any]:
    require_false_flags(candidate, "promotion-contract candidate")
    require_false_flags(review, "selected metadata preflight")
    if candidate.get("promotion_contract_decision") not in {"promotion_contract_already_satisfied", "promotion_contract_candidate_created", "config_update_needed"}:
        raise ContextError("promotion-contract candidate decision invalid")
    if candidate.get("current_state") != "constrained_authoring_metadata_preflight_passed":
        raise ContextError("promotion-contract candidate current_state invalid")
    if candidate.get("proposed_next_state") != "authoring_metadata_promotion_contract_ready":
        raise ContextError("promotion-contract candidate proposed_next_state invalid")
    if candidate.get("recommended_next_stage") != "build_constrained_authoring_context_candidate":
        raise ContextError("promotion-contract candidate recommended next stage is not context candidate")
    if candidate.get("automated_disposition") != "caveat_only":
        raise ContextError("promotion-contract candidate disposition is not caveat_only")
    if candidate.get("hard_invariants_preserved") is not True:
        raise ContextError("promotion-contract candidate hard invariants not preserved")

    required_caveats = _require_nonempty_list(review, "required_caveats", "selected metadata preflight")
    do_not_say = _require_nonempty_list(review, "do_not_say", "selected metadata preflight")
    unsupported = _require_nonempty_list(review, "unsupported_inferences", "selected metadata preflight")
    blockers = _require_nonempty_list(review, "promotion_blockers", "selected metadata preflight")
    provenance = review.get("provenance_paths")
    if isinstance(provenance, list) and not provenance:
        raise ContextError("selected metadata preflight missing provenance_paths")
    if not isinstance(provenance, list):
        metadata_report_path = candidate.get("metadata_report_path")
        preflight_report_path = candidate.get("preflight_report_path")
        if metadata_report_path and preflight_report_path and review.get("provenance_assessment"):
            provenance = [metadata_report_path, preflight_report_path]
        else:
            raise ContextError("selected metadata preflight missing provenance_paths")
    atoms = review.get("evidence_bound_factual_atoms_allowed") or review.get("evidence_bound_factual_atoms")
    if not isinstance(atoms, list) or not atoms:
        atoms = [review.get("evidence_use_assessment"), review.get("metadata_containment_assessment"), review.get("usefulness_as_metadata_assessment")]
        atoms = [x for x in atoms if isinstance(x, str) and x.strip()]
    if not atoms:
        raise ContextError("selected metadata preflight missing evidence context atoms")

    metadata_id = candidate["metadata_id"]
    context_id = "context_run42_constrained_authoring_" + sha256_text(compact_json({"metadata_id": metadata_id, "contract": candidate.get("contract_candidate_id")}))[:24]
    return {
        "context_id": context_id,
        "context_type": "constrained_authoring_context_candidate",
        "context_decision": "context_candidate_created",
        "context_use": "caveat_only_authoring_context",
        "metadata_id": metadata_id,
        "contract_candidate_id": candidate.get("contract_candidate_id"),
        "draft_canary_id": review.get("draft_canary_id"),
        "rebuilt_input_id": review.get("rebuilt_input_id"),
        "prior_draft_input_id": review.get("prior_draft_input_id"),
        "source_state": "authoring_metadata_promotion_contract_ready",
        "target_state": "constrained_authoring_context_candidate",
        "transition_decision": "future_context_metadata_packaged",
        "automated_disposition": "caveat_only",
        "advisory_only": True,
        "author_allowed": False,
        "publication_approved": False,
        "eligible_for_claim_insertion": False,
        "eligible_for_authoring": False,
        "eligible_for_publication": False,
        "chapter_update_allowed": False,
        "required_caveats": required_caveats,
        "do_not_say": do_not_say,
        "unsupported_inferences": unsupported,
        "promotion_blockers": blockers,
        "evidence_context_atoms": atoms,
        "limitations": list(candidate.get("limitations") or review.get("limitations") or []),
        "residual_risk": candidate.get("residual_risk") or review.get("residual_risk"),
        "author_context_constraints": {
            "allowed_scope": [
                "Use as structured context metadata only.",
                "Preserve the mandatory caveat and negative boundaries.",
                "Treat tooling-adjacency material as caveat-only planning context.",
            ],
            "forbidden_scope": [
                "No chapter prose.",
                "No publishable wording.",
                "No claim insertion.",
                "No docs/book integration.",
                "No authoring or publication approval.",
            ],
        },
        "provenance_paths": [*provenance, contract_path, transition_path],
        "source_report_paths": {
            "promotion_contract_report": contract_path,
            "transition_engine_report": transition_path,
            "metadata_report": candidate.get("metadata_report_path"),
            "preflight_report": candidate.get("preflight_report_path"),
        },
    }


def build_report(contract: dict[str, Any], transition: dict[str, Any], contract_path: str, transition_path: str, db: Path) -> dict[str, Any]:
    validate_headers(contract, transition)
    before_counts, before_status = counts_and_status(db)
    candidates = contract.get("promotion_contract_candidates")
    if not isinstance(candidates, list):
        raise ContextError("promotion-contract report missing promotion_contract_candidates")

    selected: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    contexts: list[dict[str, Any]] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        if candidate.get("recommended_next_stage") != "build_constrained_authoring_context_candidate" or candidate.get("automated_disposition") != "caveat_only":
            excluded.append({"metadata_id": candidate.get("metadata_id"), "excluded_reason": candidate.get("recommended_next_stage") or candidate.get("automated_disposition") or "not_context_candidate"})
            continue
        metadata_id = str(candidate.get("metadata_id") or "")
        review = _first_by_metadata_id(contract.get("selected_metadata_preflights"), metadata_id)
        if not review:
            raise ContextError(f"missing selected metadata preflight provenance for {metadata_id}")
        contexts.append(build_context_candidate(candidate, review, contract_path, transition_path))
        selected.append(candidate)

    after_counts, after_status = counts_and_status(db)
    decision_counts = Counter(item["context_decision"] for item in contexts)
    return {
        "mode": MODE,
        "run_id": RUN_ID_DEFAULT,
        "generated_at": utc_now(),
        "report_only": True,
        "llm_used": False,
        "provider": None,
        "model": None,
        "bridge": None,
        "model_profile": None,
        "reasoning_status": "deterministic_context_packaging_only",
        "input_paths": {"promotion_contract_report": contract_path, "transition_report": transition_path, "sqlite_db": rel(db)},
        "selected_contract_count": len(selected),
        "excluded_contract_count": len(excluded),
        "context_candidate_count": len(contexts),
        "context_decision_counts": dict(decision_counts),
        "constrained_authoring_context_candidates": contexts,
        "excluded_contracts": excluded,
        "claims_count_before": before_counts["claims"],
        "claims_count_after": after_counts["claims"],
        "source_notes_count_before": before_counts["source_notes"],
        "source_notes_count_after": after_counts["source_notes"],
        "editorial_reviews_count_before": before_counts["editorial_reviews"],
        "editorial_reviews_count_after": after_counts["editorial_reviews"],
        "changed_db": before_counts != after_counts or before_status != after_status,
        "changed_source_notes": before_counts["source_notes"] != after_counts["source_notes"] or before_status.get("source_notes_hash") != after_status.get("source_notes_hash"),
        "claims_inserted": after_counts["claims"] - before_counts["claims"],
        "editorial_reviews_inserted": after_counts["editorial_reviews"] - before_counts["editorial_reviews"],
        "claim_status_changed": before_status.get("claims_status_hash") != after_status.get("claims_status_hash"),
        "editorial_status_changed": before_status.get("editorial_reviews_hash") != after_status.get("editorial_reviews_hash"),
        "changed_source_registry": False,
        "changed_raw_captures": False,
        "changed_docs_book": False,
        "changed_schema": False,
        "changed_daily_worker": False,
        "safety_flags": {
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
            "docs_book_modified": False,
            "schema_modified": False,
            "daily_worker_modified": False,
            "new_author_prose_created": False,
            "chapter_ready_prose_created": False,
            "context_metadata_only": True,
        },
        "recommended_next_stage": "run_constrained_authoring_context_preflight" if contexts else "keep_safe_reports_only",
    }


def write_reports(report: dict[str, Any], output_json: Path) -> dict[str, str]:
    output_json.parent.mkdir(parents=True, exist_ok=True)
    md = output_json.with_suffix(".md")
    report["output_paths"] = {"json": rel(output_json), "markdown": rel(md)}
    output_json.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    lines = [
        "# Run 42 constrained authoring-context candidate",
        "",
        f"Generated: {report['generated_at']}",
        "",
        f"- Context candidates: `{report['context_candidate_count']}`",
        f"- Selected contracts: `{report['selected_contract_count']}`",
        f"- Excluded contracts: `{report['excluded_contract_count']}`",
        f"- LLM used: `{report['llm_used']}`",
        f"- Changed DB: `{report['changed_db']}`",
        f"- Claims inserted: `{report['claims_inserted']}`",
        f"- Editorial reviews inserted: `{report['editorial_reviews_inserted']}`",
        f"- Docs/book changed: `{report['changed_docs_book']}`",
        f"- Recommended next stage: `{report['recommended_next_stage']}`",
        "",
        "This report is constrained context metadata only. It is not authoring approval, publication approval, claim insertion, or docs/book update permission.",
    ]
    md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report["output_paths"]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build report-only constrained authoring-context metadata")
    ap.add_argument("--promotion-contract-report", default=DEFAULT_CONTRACT)
    ap.add_argument("--transition-report", default=DEFAULT_TRANSITION)
    ap.add_argument("--output-dir", default="reports/editorial")
    ap.add_argument("--report-suffix", default="run42")
    args = ap.parse_args(argv)
    try:
        contract = load_json(args.promotion_contract_report, "promotion-contract report")
        transition = load_json(args.transition_report, "transition report")
        report = build_report(contract, transition, rel(args.promotion_contract_report), rel(args.transition_report), db_path())
        out = resolve(args.output_dir) / f"{RUN_ID_DEFAULT}-constrained-authoring-context-{args.report_suffix}.json"
        paths = write_reports(report, out)
        print(json.dumps({"ok": True, "context_candidate_count": report["context_candidate_count"], "output_json": paths["json"]}, sort_keys=True))
        return 0
    except ContextError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
