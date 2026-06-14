#!/usr/bin/env python3
"""Run 30 report-only constrained authoring-metadata candidate builder.

This deterministic packaging stage consumes Run 29 red-team output, cross-checks
Run 28 canary output and Run 26 rebuilt input, and emits structured metadata
only. It does not call an LLM, author prose, mutate docs/book, write DB rows,
promote statuses, or approve publication/authoring/chapter updates.
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
MODE = "build_constrained_authoring_metadata"
DEFAULT_RUN29 = f"reports/editorial/{RUN_ID_DEFAULT}-author-draft-canary-v2-redteam-run29.json"
DEFAULT_RUN28 = f"reports/editorial/{RUN_ID_DEFAULT}-author-draft-canary-v2-run28.json"
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
TRUE_FLAGS = ["advisory_only", "draft_canary_only"]

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
ALLOWED_CANARY_USEFULNESS = {
    "useful_as_caveat_only_seed",
    "improved_but_still_thin",
    "safe_but_too_thin",
    "not_useful_restates_caveat_only",
    "not_ready_needs_more_sources",
    "not_ready_source_context_unclear",
    "not_ready_exclude",
    "not_ready_contradiction_review",
}
ALLOWED_CLOSED_LOOP_DISPOSITIONS = {
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

ALLOWED_METADATA_TYPES = {
    "constrained_authoring_metadata_candidate",
    "safe_reports_only_metadata",
    "needs_more_sources_metadata",
    "excluded_metadata",
}
ALLOWED_METADATA_DECISIONS = {
    "metadata_candidate_created",
    "safe_reports_only",
    "needs_more_sources",
    "source_context_unclear",
    "exclude_from_authoring",
    "contradiction_review_required",
}
ALLOWED_METADATA_USES = {
    "caveat_only",
    "context_only",
    "safe_reports_only",
    "not_for_authoring",
    "not_for_publication",
}

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

SUPPORTING_INPUTS = [
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
]


class MetadataError(RuntimeError):
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


def load_json(path: str | Path, label: str) -> dict[str, Any]:
    p = resolve(path)
    if not p.exists():
        raise MetadataError(f"missing {label}: {p}")
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise MetadataError(f"invalid JSON in {label}: {exc}") from exc
    if not isinstance(data, dict):
        raise MetadataError(f"{label} must be a JSON object")
    return data


def compact_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


def connect_readonly(path: Path) -> sqlite3.Connection:
    if not path.exists():
        raise MetadataError(f"missing SQLite DB: {path}")
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


def has_required_do_not_say(items: Any) -> bool:
    return isinstance(items, list) and all(req in items for req in REQUIRED_DO_NOT_SAY)


def require_no_chapter_prose_fields(obj: Any, path: str = "root") -> None:
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key in CHAPTER_PROSE_KEYS:
                raise MetadataError(f"chapter-ready/new prose field is forbidden: {path}.{key}")
            require_no_chapter_prose_fields(value, f"{path}.{key}")
    elif isinstance(obj, list):
        for idx, value in enumerate(obj):
            require_no_chapter_prose_fields(value, f"{path}[{idx}]")


def safety_flag_error(obj: dict[str, Any], label: str) -> str | None:
    for flag in TRUE_FLAGS:
        if obj.get(flag) is not True:
            return f"{label} missing safety flag {flag}=true"
    for flag in FALSE_FLAGS:
        if obj.get(flag) is not False:
            return f"{label} safety flag {flag} must be false"
    return None


def require_safety_flags(obj: dict[str, Any], label: str) -> None:
    err = safety_flag_error(obj, label)
    if err:
        raise MetadataError(err)


def validate_report_headers(run29: dict[str, Any], run28: dict[str, Any], run26: dict[str, Any]) -> None:
    if run29.get("mode") != "llm_author_draft_canary_v2_redteam" or run29.get("report_only") is not True:
        raise MetadataError("Run 29 report mode/report_only invalid")
    if run28.get("mode") != "llm_author_draft_canary_v2" or run28.get("report_only") is not True:
        raise MetadataError("Run 28 report mode/report_only invalid")
    if run26.get("mode") != "llm_rebuild_author_draft_input" or run26.get("report_only") is not True:
        raise MetadataError("Run 26 report mode/report_only invalid")
    for label, data, field in [
        ("Run 29", run29, "draft_canary_v2_redteam_reviews"),
        ("Run 28", run28, "draft_canaries"),
        ("Run 26", run26, "rebuilt_author_draft_inputs"),
    ]:
        if not isinstance(data.get(field), list):
            raise MetadataError(f"{label} missing list field: {field}")
    require_no_chapter_prose_fields(run29, "run29")
    require_no_chapter_prose_fields(run28, "run28")
    require_no_chapter_prose_fields(run26, "run26")


def review_validation_error(review: dict[str, Any]) -> str | None:
    for key, allowed in [
        ("redteam_decision", ALLOWED_REDTEAM_DECISIONS),
        ("canary_usefulness", ALLOWED_CANARY_USEFULNESS),
        ("closed_loop_disposition", ALLOWED_CLOSED_LOOP_DISPOSITIONS),
        ("recommended_next_stage", ALLOWED_NEXT_STAGES),
    ]:
        value = review.get(key)
        if value not in allowed:
            return f"invalid enum {key}: {value}"
    flag = safety_flag_error(review, "Run 29 review")
    if flag:
        return flag
    if REQUIRED_CAVEAT not in review.get("required_caveats", []):
        return "Run 29 review missing required caveat"
    if not has_required_do_not_say(review.get("do_not_say")):
        return "Run 29 review missing do_not_say guidance"
    return None


def select_reason(review: dict[str, Any]) -> str | None:
    err = review_validation_error(review)
    if err:
        raise MetadataError(err)
    if review.get("redteam_decision") != "draft_canary_v2_passed":
        return "redteam_decision_not_passed"
    if review.get("canary_usefulness") not in {"improved_but_still_thin", "useful_as_caveat_only_seed"}:
        return "canary_usefulness_not_metadata_ready"
    if review.get("closed_loop_disposition") != "caveat_only":
        return "closed_loop_disposition_not_caveat_only"
    if review.get("recommended_next_stage") != "build_constrained_authoring_metadata_candidate":
        return "recommended_next_stage_not_metadata_candidate"
    return None


def find_by_id(items: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    return {item[key]: item for item in items if isinstance(item, dict) and item.get(key)}


def validate_run28_canary(canary: dict[str, Any] | None) -> dict[str, Any]:
    if not canary:
        raise MetadataError("missing Run 28 canary cross-check")
    expected = {
        "draft_canary_type": "caveat_only_author_draft_canary_v2",
        "draft_canary_decision": "draft_canary_v2_created",
        "draft_canary_use": "caveat_only",
    }
    for key, value in expected.items():
        if canary.get(key) != value:
            raise MetadataError(f"Run 28 canary {key} invalid: {canary.get(key)}")
    require_safety_flags(canary, "Run 28 canary")
    if not isinstance(canary.get("draft_canary_text"), str) or not canary["draft_canary_text"].strip():
        raise MetadataError("Run 28 canary missing draft_canary_text")
    if int(canary.get("word_count") or 999999) > 110:
        raise MetadataError("Run 28 canary word_count exceeds 110")
    if REQUIRED_CAVEAT not in canary.get("required_caveats", []):
        raise MetadataError("Run 28 canary missing required caveat")
    if not has_required_do_not_say(canary.get("do_not_say")):
        raise MetadataError("Run 28 canary missing do_not_say guidance")
    if not canary.get("provenance_paths"):
        raise MetadataError("Run 28 canary missing provenance paths")
    if canary.get("raw_capture_dependency"):
        raise MetadataError("Run 28 canary has raw capture dependency")
    return canary


def validate_run26_rebuild(rebuilt: dict[str, Any] | None) -> dict[str, Any]:
    if not rebuilt:
        raise MetadataError("missing Run 26 rebuilt input cross-check")
    expected = {
        "rebuilt_input_type": "enriched_caveat_only_author_draft_input",
        "rebuilt_input_decision": "rebuilt_draft_input_candidate",
        "rebuilt_input_use": "caveat_only",
    }
    for key, value in expected.items():
        if rebuilt.get(key) != value:
            raise MetadataError(f"Run 26 rebuilt input {key} invalid: {rebuilt.get(key)}")
    # Run 26 uses singleton_input instead of draft_canary_only; require all false flags and advisory_only.
    if rebuilt.get("advisory_only") is not True:
        raise MetadataError("Run 26 rebuilt input missing advisory_only safety flag")
    for flag in FALSE_FLAGS:
        if rebuilt.get(flag) is not False:
            raise MetadataError(f"Run 26 rebuilt input safety flag {flag} must be false")
    required_nonempty = [
        "evidence_bound_factual_atoms",
        "allowed_author_scope",
        "forbidden_author_scope",
        "narrative_function_suggestions",
        "later_canary_instruction_seed",
        "why_prior_canary_was_not_useful",
    ]
    for key in required_nonempty:
        value = rebuilt.get(key)
        if not value:
            raise MetadataError(f"Run 26 rebuilt input missing {key}")
    if REQUIRED_CAVEAT not in rebuilt.get("required_caveats", []):
        raise MetadataError("Run 26 rebuilt input missing required caveat")
    if not has_required_do_not_say(rebuilt.get("do_not_say")):
        raise MetadataError("Run 26 rebuilt input missing do_not_say guidance")
    return rebuilt


def metadata_id_for(canary: dict[str, Any]) -> str:
    cluster = str(canary.get("source_cluster_id") or "unknown_cluster")
    if cluster.startswith("cluster_"):
        suffix = cluster.removeprefix("cluster_")
    else:
        suffix = sha256_text(cluster)[:24]
    return f"metadata_run30_constrained_authoring_{suffix}"


def build_candidate(review: dict[str, Any], canary: dict[str, Any], rebuilt: dict[str, Any]) -> dict[str, Any]:
    unsupported = [
        "Hermes is a runtime dependency of OpenClaw.",
        "Hermes is the general operating environment for OpenClaw.",
        "OpenClaw requires Hermes for web or phone access.",
        "Migration/setup/import tooling adjacency proves architectural dependency.",
        "The canary is publishable or chapter-ready.",
        "The canary can be inserted as a claim without later gates.",
    ]
    promotion_blockers = [
        "No authoring approval has been granted.",
        "No publication approval has been granted.",
        "No claim insertion is allowed.",
        "No chapter update is allowed.",
        "Evidence remains singleton/narrow and caveat-only.",
        "Later gates must prevent prose-promotion from tooling adjacency into dependency or operating-environment claims.",
    ]
    thinness_warning = (
        f"Run 29 canary_usefulness={review['canary_usefulness']}; the canary is improved over Run 24 but still thin, "
        "singleton/narrow, and usable only as caveat-only metadata for later constrained review."
    )
    provenance_paths = list(dict.fromkeys(
        [*canary.get("provenance_paths", []), *rebuilt.get("provenance_paths", []),
         "reports/editorial/citation-pipeline-test-20260612-author-draft-canary-v2-run28.json",
         "reports/editorial/citation-pipeline-test-20260612-author-draft-canary-v2-redteam-run29.json"]
    ))
    candidate = {
        "metadata_id": metadata_id_for(canary),
        "draft_canary_id": canary["draft_canary_id"],
        "rebuilt_input_id": review["rebuilt_input_id"],
        "prior_draft_input_id": review["prior_draft_input_id"],
        "source_packet_id": canary.get("source_packet_id") or rebuilt.get("source_packet_id"),
        "source_cluster_id": canary.get("source_cluster_id") or rebuilt.get("source_cluster_id"),
        "source_note_ids": canary.get("source_note_ids") or rebuilt.get("source_note_ids") or [],
        "source_review_ids": canary.get("source_review_ids") or rebuilt.get("source_review_ids") or [],
        "source_ids": canary.get("source_ids") or rebuilt.get("source_ids") or [],
        "manifest_item_ids": canary.get("manifest_item_ids") or rebuilt.get("manifest_item_ids") or [],
        "candidate_source_ids": canary.get("candidate_source_ids") or rebuilt.get("candidate_source_ids") or [],
        "metadata_type": "constrained_authoring_metadata_candidate",
        "metadata_decision": "metadata_candidate_created",
        "metadata_use": "caveat_only",
        "canary_usefulness": review["canary_usefulness"],
        "thinness_warning": thinness_warning,
        "canary_text_quoted": f"REPORT-ONLY CANARY TEXT, NOT AUTHORING OR PUBLICATION APPROVAL: {canary['draft_canary_text']}",
        "authoring_intent_allowed": [
            "Intent metadata only for later constrained review.",
            "Use to preserve narrow ecosystem/tooling-adjacency context.",
            "Use to carry caveat, provenance, and negative-boundary constraints forward.",
            "Use only as a planning/index object until later author/red-team gates pass.",
        ],
        "authoring_intent_forbidden": [
            "No new draft prose.",
            "No expanded paragraph prose.",
            "No chapter-ready prose.",
            "No publishable wording.",
            "No claim insertion request.",
            "No citation-resolved chapter text.",
            "No docs/book integration.",
            "No authoring approval.",
            "No publication approval.",
            "No chapter-update permission.",
        ],
        "evidence_bound_factual_atoms_allowed": rebuilt.get("evidence_bound_factual_atoms", []),
        "unsupported_inferences": unsupported,
        "required_caveats": [REQUIRED_CAVEAT],
        "do_not_say": REQUIRED_DO_NOT_SAY,
        "provenance_requirements": [
            "Retain source review, source note, manifest, cluster, packet, rebuilt input, canary, and red-team identifiers.",
            "Retain candidate source IDs where available.",
            "Do not use this metadata as resolved citation support for chapter prose.",
            "Any later factual consideration must cite upstream source/review artifacts and preserve the caveat.",
        ],
        "target_chapter_candidates": rebuilt.get("target_chapter_candidates") or canary.get("target_chapter_candidates") or [
            "ecosystem/tooling adjacency context",
            "migration/setup tooling context",
            "internal evidence map context",
        ],
        "target_chapter_status": canary.get("target_chapter_status") or rebuilt.get("target_chapter_status") or "suggested_only",
        "promotion_blockers": promotion_blockers,
        "next_stage_options": [
            "run_authoring_metadata_preflight",
            "run_additional_source_collection",
            "run_source_context_review",
            "keep_safe_reports_only",
        ],
        "residual_risk": review.get("residual_risk") or canary.get("residual_risk") or rebuilt.get("residual_risk"),
        "confidence": rebuilt.get("confidence", "limited_caveat_only"),
        "provenance_paths": provenance_paths,
        "singleton_metadata_candidate": True,
        "evidence_narrowness_warning": rebuilt.get("evidence_narrowness_warning") or canary.get("evidence_narrowness_warning"),
        "advisory_only": True,
        "author_allowed": False,
        "publication_approved": False,
        "eligible_for_claim_insertion": False,
        "eligible_for_authoring": False,
        "eligible_for_publication": False,
        "chapter_update_allowed": False,
    }
    validate_metadata_candidate(candidate)
    return candidate


def validate_metadata_candidate(candidate: dict[str, Any]) -> None:
    if candidate.get("metadata_type") not in ALLOWED_METADATA_TYPES:
        raise MetadataError("metadata candidate invalid metadata_type")
    if candidate.get("metadata_decision") not in ALLOWED_METADATA_DECISIONS:
        raise MetadataError("metadata candidate invalid metadata_decision")
    if candidate.get("metadata_use") not in ALLOWED_METADATA_USES:
        raise MetadataError("metadata candidate invalid metadata_use")
    for flag in FALSE_FLAGS:
        if candidate.get(flag) is not False:
            raise MetadataError(f"metadata candidate safety flag {flag} must be false")
    if candidate.get("advisory_only") is not True or candidate.get("singleton_metadata_candidate") is not True:
        raise MetadataError("metadata candidate missing advisory/singleton flags")
    for key in [
        "unsupported_inferences",
        "promotion_blockers",
        "thinness_warning",
        "evidence_bound_factual_atoms_allowed",
        "required_caveats",
        "do_not_say",
        "provenance_requirements",
        "provenance_paths",
    ]:
        if not candidate.get(key):
            raise MetadataError(f"metadata candidate missing {key}")
    if REQUIRED_CAVEAT not in candidate["required_caveats"]:
        raise MetadataError("metadata candidate missing required caveat")
    if not has_required_do_not_say(candidate.get("do_not_say")):
        raise MetadataError("metadata candidate missing do_not_say guidance")
    require_no_chapter_prose_fields(candidate, "metadata_candidate")
    forbidden_text = json.dumps(candidate, ensure_ascii=False).lower()
    forbidden_approval_phrases = [
        "approved for publication",
        "approved for authoring",
        "eligible for publication: true",
        "eligible for authoring: true",
        "chapter update allowed: true",
    ]
    for phrase in forbidden_approval_phrases:
        if phrase in forbidden_text:
            raise MetadataError(f"metadata candidate contains forbidden approval phrase: {phrase}")


def build_report(run_id: str, redteam_path: Path, canary_path: Path, rebuild_path: Path, report_suffix: str) -> dict[str, Any]:
    run29 = load_json(redteam_path, "Run 29 red-team report")
    run28 = load_json(canary_path, "Run 28 canary report")
    run26 = load_json(rebuild_path, "Run 26 rebuild report")
    validate_report_headers(run29, run28, run26)

    con = connect_readonly(db_path())
    try:
        counts_before = {t: table_count(con, t) for t in ["source_notes", "claims", "editorial_reviews"]}
        statuses_before = status_snapshots(con)
    finally:
        con.close()

    canaries = find_by_id(run28["draft_canaries"], "draft_canary_id")
    rebuilt_inputs = find_by_id(run26["rebuilt_author_draft_inputs"], "rebuilt_input_id")
    selected: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    failed_checks: list[str] = []

    for review in run29["draft_canary_v2_redteam_reviews"]:
        if not isinstance(review, dict):
            raise MetadataError("Run 29 review must be object")
        reason = select_reason(review)
        if reason:
            excluded.append({
                "draft_canary_id": review.get("draft_canary_id"),
                "rebuilt_input_id": review.get("rebuilt_input_id"),
                "reason": reason,
            })
            continue
        canary = validate_run28_canary(canaries.get(review["draft_canary_id"]))
        rebuilt = validate_run26_rebuild(rebuilt_inputs.get(review["rebuilt_input_id"]))
        selected.append(review)
        candidates.append(build_candidate(review, canary, rebuilt))

    con = connect_readonly(db_path())
    try:
        counts_after = {t: table_count(con, t) for t in ["source_notes", "claims", "editorial_reviews"]}
        statuses_after = status_snapshots(con)
    finally:
        con.close()

    changed_db = counts_before != counts_after or statuses_before != statuses_after
    source_status_changed = statuses_before["sources_status_hash"] != statuses_after["sources_status_hash"]
    claim_status_changed = statuses_before["claims_status_hash"] != statuses_after["claims_status_hash"]
    editorial_status_changed = statuses_before["editorial_reviews_hash"] != statuses_after["editorial_reviews_hash"]

    metadata_type_counts = Counter(c["metadata_type"] for c in candidates)
    metadata_decision_counts = Counter(c["metadata_decision"] for c in candidates)
    metadata_use_counts = Counter(c["metadata_use"] for c in candidates)
    canary_usefulness_counts = Counter(c["canary_usefulness"] for c in candidates)
    target_chapter_status_counts = Counter(c["target_chapter_status"] for c in candidates)

    return {
        "run_id": run_id,
        "mode": MODE,
        "generated_at": utc_now(),
        "input_paths": {
            "redteam_report": rel(resolve(redteam_path)),
            "canary_v2_report": rel(resolve(canary_path)),
            "rebuild_report": rel(resolve(rebuild_path)),
            "sqlite_db": rel(db_path()),
            "supporting_inputs": SUPPORTING_INPUTS,
        },
        "report_only": True,
        "llm_used": False,
        "provider": None,
        "model": None,
        "bridge": None,
        "model_profile": None,
        "reasoning_status": "deterministic_packaging_only",
        "strict_json_required": False,
        "weak_local_fallback_refused": True,
        "selected_redteam_count": len(selected),
        "metadata_candidate_count": len(candidates),
        "excluded_redteam_count": len(excluded),
        "metadata_type_counts": dict(sorted(metadata_type_counts.items())),
        "metadata_decision_counts": dict(sorted(metadata_decision_counts.items())),
        "metadata_use_counts": dict(sorted(metadata_use_counts.items())),
        "canary_usefulness_counts": dict(sorted(canary_usefulness_counts.items())),
        "target_chapter_status_counts": dict(sorted(target_chapter_status_counts.items())),
        "selected_redteams": selected,
        "excluded_redteams": excluded,
        "constrained_authoring_metadata_candidates": candidates,
        "failed_metadata_checks": failed_checks,
        "changed_db": changed_db,
        "changed_source_notes": counts_before["source_notes"] != counts_after["source_notes"],
        "changed_source_registry": False,
        "changed_raw_captures": False,
        "changed_docs_book": False,
        "changed_schema": False,
        "changed_daily_worker": False,
        "claims_inserted": max(0, counts_after["claims"] - counts_before["claims"]),
        "editorial_reviews_inserted": max(0, counts_after["editorial_reviews"] - counts_before["editorial_reviews"]),
        "source_status_changed": source_status_changed,
        "claim_status_changed": claim_status_changed,
        "editorial_status_changed": editorial_status_changed,
        "source_notes_count_before": counts_before["source_notes"],
        "source_notes_count_after": counts_after["source_notes"],
        "claims_count_before": counts_before["claims"],
        "claims_count_after": counts_after["claims"],
        "editorial_reviews_count_before": counts_before["editorial_reviews"],
        "editorial_reviews_count_after": counts_after["editorial_reviews"],
        "safety_flags": {
            "advisory_only": True,
            "metadata_only": True,
            "new_author_prose_created": False,
            "chapter_ready_prose_created": False,
            "docs_book_modified": False,
            "source_notes_written": False,
            "claims_inserted": False,
            "editorial_reviews_inserted": False,
            "source_registry_promoted": False,
            "raw_content_stored": False,
            "schema_modified": False,
            "daily_worker_modified": False,
            "gpt55_advisory_is_human_or_editor_approval": False,
            "author_allowed": False,
            "publication_approved": False,
            "eligible_for_claim_insertion": False,
            "eligible_for_authoring": False,
            "eligible_for_publication": False,
            "chapter_update_allowed": False,
        },
    }


def write_markdown(report: dict[str, Any], path: Path) -> None:
    lines = [
        f"# Run 30 constrained authoring-metadata candidate — {report['run_id']}",
        "",
        "This is a report-only deterministic metadata packaging run. GPT-5.5 was not called; it packages prior GPT-5.5 outputs from Runs 26–29.",
        "",
        "## Summary",
        "",
        f"- selected Run 29 red-team results: {report['selected_redteam_count']}",
        f"- metadata candidates created: {report['metadata_candidate_count']}",
        f"- excluded red-team results: {report['excluded_redteam_count']}",
        f"- metadata type counts: `{json.dumps(report['metadata_type_counts'], sort_keys=True)}`",
        f"- metadata decision counts: `{json.dumps(report['metadata_decision_counts'], sort_keys=True)}`",
        f"- metadata use counts: `{json.dumps(report['metadata_use_counts'], sort_keys=True)}`",
        f"- canary usefulness counts: `{json.dumps(report['canary_usefulness_counts'], sort_keys=True)}`",
        f"- target chapter status counts: `{json.dumps(report['target_chapter_status_counts'], sort_keys=True)}`",
        "",
        "## GPT/profile use",
        "",
        "- GPT-5.5 used in Run 30: false",
        "- provider/model/bridge/profile: not applicable; deterministic packaging only",
        "- weak/local fallback: refused/not used",
        "",
    ]
    for candidate in report["constrained_authoring_metadata_candidates"]:
        lines.extend([
            f"## Metadata candidate `{candidate['metadata_id']}`",
            "",
            f"- draft canary: `{candidate['draft_canary_id']}`",
            f"- rebuilt input: `{candidate['rebuilt_input_id']}`",
            f"- metadata type: `{candidate['metadata_type']}`",
            f"- metadata decision: `{candidate['metadata_decision']}`",
            f"- metadata use: `{candidate['metadata_use']}`",
            f"- canary usefulness: `{candidate['canary_usefulness']}`",
            f"- thinness warning: {candidate['thinness_warning']}",
            f"- target chapter status: `{candidate['target_chapter_status']}`",
            "",
            "### Allowed authoring intent metadata",
            "",
            *[f"- {item}" for item in candidate["authoring_intent_allowed"]],
            "",
            "### Forbidden authoring intent metadata",
            "",
            *[f"- {item}" for item in candidate["authoring_intent_forbidden"]],
            "",
            "### Evidence atoms allowed",
            "",
            *[f"- {item}" for item in candidate["evidence_bound_factual_atoms_allowed"]],
            "",
            "### Unsupported inferences",
            "",
            *[f"- {item}" for item in candidate["unsupported_inferences"]],
            "",
            "### Caveat-only constraints",
            "",
            *[f"- {item}" for item in candidate["required_caveats"]],
            "",
            "### Do-not-say guidance",
            "",
            *[f"- {item}" for item in candidate["do_not_say"]],
            "",
            "### Provenance requirements",
            "",
            *[f"- {item}" for item in candidate["provenance_requirements"]],
            "",
            "### Residual risks and promotion blockers",
            "",
            f"- residual risk: {candidate['residual_risk']}",
            f"- evidence narrowness warning: {candidate['evidence_narrowness_warning']}",
            *[f"- {item}" for item in candidate["promotion_blockers"]],
            "",
        ])
    lines.extend([
        "## Why this is not authoring/publication/chapter update",
        "",
        "- The output is structured metadata only, not new author prose.",
        "- `author_allowed`, `publication_approved`, `eligible_for_claim_insertion`, `eligible_for_authoring`, `eligible_for_publication`, and `chapter_update_allowed` remain false.",
        "- No docs/book files are written.",
        "- No claims, editorial reviews, source notes, statuses, source registry, raw captures, schema, or daily worker files are modified.",
        "",
        "## Recommendation for Run 31",
        "",
        "Run a report-only constrained authoring-metadata preflight/red-team gate. It should verify that this metadata object is useful and safe as metadata only before any later author-facing stage, while preserving all approval/publication/chapter flags as false.",
        "",
    ])
    path.write_text("\n".join(lines), encoding="utf-8")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", default=RUN_ID_DEFAULT)
    parser.add_argument("--redteam-report", default=DEFAULT_RUN29)
    parser.add_argument("--canary-v2-report", default=DEFAULT_RUN28)
    parser.add_argument("--rebuild-report", default=DEFAULT_RUN26)
    parser.add_argument("--output-dir", default="reports/editorial")
    parser.add_argument("--report-suffix", default="run30")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        report = build_report(
            run_id=args.run_id,
            redteam_path=resolve(args.redteam_report),
            canary_path=resolve(args.canary_v2_report),
            rebuild_path=resolve(args.rebuild_report),
            report_suffix=args.report_suffix,
        )
        out_dir = resolve(args.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        json_path = out_dir / f"{args.run_id}-constrained-authoring-metadata-{args.report_suffix}.json"
        md_path = out_dir / f"{args.run_id}-constrained-authoring-metadata-{args.report_suffix}.md"
        report["output_paths"] = {"json": rel(json_path), "markdown": rel(md_path)}
        json_path.write_text(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
        write_markdown(report, md_path)
        print(json.dumps({
            "ok": True,
            "json": rel(json_path),
            "markdown": rel(md_path),
            "selected_redteam_count": report["selected_redteam_count"],
            "metadata_candidate_count": report["metadata_candidate_count"],
            "excluded_redteam_count": report["excluded_redteam_count"],
            "metadata_type_counts": report["metadata_type_counts"],
            "metadata_decision_counts": report["metadata_decision_counts"],
            "metadata_use_counts": report["metadata_use_counts"],
            "canary_usefulness_counts": report["canary_usefulness_counts"],
            "target_chapter_status_counts": report["target_chapter_status_counts"],
        }, sort_keys=True))
        return 0
    except MetadataError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
