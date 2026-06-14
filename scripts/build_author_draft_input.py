#!/usr/bin/env python3
"""Run 22B report-only caveat-only author-draft input package builder.

This deterministic packaging stage consumes the Run 22A state-machine transition
manifest, Run 21 packet red-team gate, and Run 20 packet candidate report. It
creates controlled draft-input metadata for a later authoring run. It does not
author prose, persist packets, write DB rows, or mutate protected publication
artifacts.
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
MODE = "build_author_draft_input"
DEFAULT_RUN22A = f"reports/editorial/{RUN_ID_DEFAULT}-closed-loop-state-machine-run22a.json"
DEFAULT_RUN21 = f"reports/editorial/{RUN_ID_DEFAULT}-packet-redteam-gate-run21.json"
DEFAULT_RUN20 = f"reports/editorial/{RUN_ID_DEFAULT}-narrative-packet-candidates-run20.json"

REQUIRED_CAVEAT = "Frame narrowly: OpenClaw documentation names Hermes in migration/setup tooling contexts; do not state that Hermes is a runtime dependency or general operating environment without additional sources."
REQUIRED_DO_NOT_SAY = [
    "Do not say Hermes is a runtime dependency of OpenClaw.",
    "Do not say Hermes is the general operating environment for OpenClaw.",
    "Do not say OpenClaw requires Hermes for web or phone access.",
    "Do not generalize beyond migration/setup/import tooling contexts unless additional sources support it.",
    "Do not use this packet as a factual claim without the caveat.",
    "Do not use this material for chapter prose before later author/red-team gates pass.",
]
RUN20_EQUIVALENT_DO_NOT_SAY = {
    "Do not use this packet for chapter prose before later author/red-team gates pass.": "Do not use this material for chapter prose before later author/red-team gates pass.",
}
FALSE_FLAGS = [
    "author_allowed",
    "publication_approved",
    "eligible_for_authoring",
    "eligible_for_publication",
    "chapter_update_allowed",
]
PACKAGE_FALSE_FLAGS = FALSE_FLAGS + ["eligible_for_claim_insertion"]
CHAPTER_READY_FIELDS = {
    "chapter_prose",
    "publishable_paragraph",
    "draft_paragraph",
    "final_prose",
    "book_text",
    "chapter_ready_prose",
    "citation_resolved_chapter_text",
}
ALLOWED_DRAFT_INPUT_TYPES = {
    "caveat_only_author_draft_input",
    "context_only_author_draft_input",
    "safe_reports_only_draft_input",
}
ALLOWED_DRAFT_INPUT_DECISIONS = {
    "draft_input_candidate",
    "caveat_only_draft_input_candidate",
    "safe_reports_only",
    "needs_more_sources",
    "source_context_unclear",
    "exclude_from_authoring",
    "contradiction_review_required",
}
ALLOWED_DRAFT_INPUT_USES = {
    "caveat_only",
    "context_only",
    "safe_reports_only",
    "not_for_authoring",
    "not_for_publication",
}


class DraftInputError(RuntimeError):
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
        raise DraftInputError(f"missing {label}: {p}")
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DraftInputError(f"invalid JSON in {label}: {exc}") from exc
    if not isinstance(data, dict):
        raise DraftInputError(f"{label} must be a JSON object")
    return data


def compact_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


def connect_readonly(path: Path) -> sqlite3.Connection:
    if not path.exists():
        raise DraftInputError(f"missing SQLite DB: {path}")
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


def find_by_id(items: list[dict[str, Any]], field: str) -> dict[str, dict[str, Any]]:
    return {item.get(field): item for item in items if isinstance(item, dict) and item.get(field)}


def normalize_do_not_say(items: list[str]) -> list[str]:
    out: list[str] = []
    for item in items:
        if item in RUN20_EQUIVALENT_DO_NOT_SAY:
            out.append(RUN20_EQUIVALENT_DO_NOT_SAY[item])
        else:
            out.append(item)
    return out


def has_required_do_not_say(items: Any) -> bool:
    if not isinstance(items, list):
        return False
    normalized = normalize_do_not_say([x for x in items if isinstance(x, str)])
    return all(req in normalized for req in REQUIRED_DO_NOT_SAY)


def has_required_caveat(packet: dict[str, Any]) -> bool:
    caveats = packet.get("required_caveats")
    if isinstance(caveats, list) and REQUIRED_CAVEAT in caveats:
        return True
    return packet.get("caveat_text") == REQUIRED_CAVEAT


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


def unsafe_flag_reason(obj: dict[str, Any], flags: list[str] = FALSE_FLAGS) -> str | None:
    for flag in flags:
        if obj.get(flag) is not False:
            return f"unsafe_flag_{flag}"
    return None


def validate_input_reports(run22a: dict[str, Any], run21: dict[str, Any], run20: dict[str, Any]) -> None:
    if run22a.get("mode") != "closed_loop_state_machine" or run22a.get("report_only") is not True:
        raise DraftInputError("Run 22A report is not a report-only closed-loop state-machine report")
    if run21.get("mode") != "llm_packet_redteam_gate" or run21.get("report_only") is not True:
        raise DraftInputError("Run 21 report is not a report-only packet red-team report")
    if run20.get("mode") != "llm_build_narrative_packets" or run20.get("report_only") is not True:
        raise DraftInputError("Run 20 report is not a report-only packet candidate report")
    for name, data, field in [
        ("Run 22A", run22a, "transition_manifest"),
        ("Run 21", run21, "packet_redteam_reviews"),
        ("Run 20", run20, "packet_candidates"),
    ]:
        if not isinstance(data.get(field), list):
            raise DraftInputError(f"{name} missing list field: {field}")


def transition_selection_reason(transition: dict[str, Any]) -> str | None:
    expected = {
        "current_state": "packet_redteam_reviewed",
        "proposed_next_state": "draft_input_candidate",
        "transition_decision": "allowed_for_future_run",
        "allowed_future_run": "build_caveat_only_author_draft_input",
        "automated_disposition": "caveat_only_author_input_ready",
    }
    for key, value in expected.items():
        if transition.get(key) != value:
            return "transition_not_allowed_for_author_draft_input"
    flag = unsafe_flag_reason(transition, FALSE_FLAGS)
    if flag:
        return flag
    return None


def redteam_reason(review: dict[str, Any] | None) -> str | None:
    if not review:
        return "missing_run21_redteam_review"
    expected = {
        "redteam_decision": "caveat_only_author_input_ready",
        "author_input_readiness": "ready_for_caveat_only_draft_input",
        "recommended_next_stage": "build_caveat_only_author_draft_input",
    }
    for key, value in expected.items():
        if review.get(key) != value:
            return f"run21_{key}_not_ready"
    flag = unsafe_flag_reason(review, PACKAGE_FALSE_FLAGS)
    if flag:
        return flag
    if REQUIRED_CAVEAT not in review.get("required_caveats", []):
        return "missing_required_caveat"
    if not has_required_do_not_say(review.get("do_not_say")):
        return "missing_do_not_say"
    return None


def packet_reason(packet: dict[str, Any] | None) -> str | None:
    if not packet:
        return "missing_run20_packet"
    expected = {
        "packet_type": "caveat_only_packet_candidate",
        "packet_decision": "caveat_only_packet_candidate",
        "packet_use": "caveat_only",
    }
    for key, value in expected.items():
        if packet.get(key) != value:
            return f"run20_{key}_not_caveat_only"
    flag = unsafe_flag_reason(packet, PACKAGE_FALSE_FLAGS)
    if flag:
        return flag
    if not has_required_caveat(packet):
        return "missing_required_caveat"
    if not has_required_do_not_say(packet.get("do_not_say")):
        return "missing_do_not_say"
    if packet.get("raw_capture_dependency") is True:
        return "raw_capture_dependency"
    if has_chapter_ready_field(packet):
        return "chapter_ready_prose_field_present"
    return None


def select_eligible_transitions(run22a: dict[str, Any], run21: dict[str, Any], run20: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    validate_input_reports(run22a, run21, run20)
    reviews = find_by_id(run21.get("packet_redteam_reviews", []), "packet_id")
    packets = find_by_id(run20.get("packet_candidates", []), "packet_id")
    selected: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for transition in run22a.get("transition_manifest", []):
        if not isinstance(transition, dict):
            continue
        object_id = transition.get("object_id")
        reason = transition_selection_reason(transition)
        review = reviews.get(object_id)
        packet = packets.get(object_id)
        if reason is None:
            reason = redteam_reason(review)
        if reason is None:
            reason = packet_reason(packet)
        if reason is None:
            selected.append({"transition": transition, "redteam_review": review, "packet": packet})
        else:
            excluded.append({
                "object_id": object_id,
                "object_type": transition.get("object_type"),
                "current_state": transition.get("current_state"),
                "proposed_next_state": transition.get("proposed_next_state"),
                "transition_decision": transition.get("transition_decision"),
                "automated_disposition": transition.get("automated_disposition"),
                "excluded_reason": reason,
            })
    return selected, excluded


def stable_id(prefix: str, value: str) -> str:
    return f"{prefix}_{sha256_text(value)[:24]}"


def build_package(bundle: dict[str, Any]) -> dict[str, Any]:
    transition = bundle["transition"]
    review = bundle["redteam_review"]
    packet = bundle["packet"]
    packet_id = packet["packet_id"]
    draft_input_id = f"draft_input_run22b_{packet_id.replace('packet_run20_', '')}"
    package = {
        "draft_input_id": draft_input_id,
        "draft_input_type": "caveat_only_author_draft_input",
        "draft_input_decision": "caveat_only_draft_input_candidate",
        "draft_input_use": "caveat_only",
        "source_packet_id": packet_id,
        "source_cluster_id": (packet.get("cluster_ids") or [None])[0],
        "source_note_ids": packet.get("note_ids", []),
        "source_review_ids": packet.get("source_review_ids", []),
        "source_ids": packet.get("source_ids", []),
        "manifest_item_ids": packet.get("manifest_item_ids", []),
        "candidate_source_ids": packet.get("candidate_source_ids", []),
        "state_machine_transition_id": stable_id("transition", compact_json(transition)),
        "state_machine_transition_reference": {
            "current_state": transition.get("current_state"),
            "proposed_next_state": transition.get("proposed_next_state"),
            "transition_decision": transition.get("transition_decision"),
            "allowed_future_run": transition.get("allowed_future_run"),
            "automated_disposition": transition.get("automated_disposition"),
        },
        "title": packet.get("title", "Caveat-only author-draft input candidate"),
        "planning_summary": "Planning-only metadata for a later controlled draft-input run: preserve a narrow caveat about Hermes being named only in OpenClaw migration/setup/import tooling contexts; do not convert this package into book prose.",
        "allowed_author_scope": [
            "Use only as caveat-only planning context in a later controlled draft-only authoring run.",
            "Frame any future mention narrowly around OpenClaw migration/setup/import tooling documentation contexts.",
            "Preserve provenance to Run 15, Run 16, manifest, source review, persisted note, candidate source identifiers, and packet/red-team reports.",
            "Treat the singleton evidence base as narrow and partially corroborated.",
        ],
        "forbidden_author_scope": [
            "No final paragraph prose.",
            "No chapter-ready prose.",
            "No claim insertion request.",
            "No publication approval.",
            "No statement that Hermes is a runtime dependency, required operating environment, web-access requirement, or phone-access requirement for OpenClaw.",
        ],
        "required_caveats": [REQUIRED_CAVEAT],
        "do_not_say": REQUIRED_DO_NOT_SAY,
        "evidence_summary": "Evidence package summary only: Run 20/21 material supports a singleton, caveat-only planning object about Hermes mentions in OpenClaw migration/setup tooling contexts.",
        "evidence_limitations": packet.get("limitations", []) + [
            "Run 22B does not resolve citations for chapter text and does not create publishable wording.",
            "Draft-input readiness remains distinct from authoring approval.",
        ],
        "residual_risk": review.get("residual_risk") or packet.get("residual_risk"),
        "confidence": "limited_caveat_only",
        "citation_requirements": packet.get("citation_requirements", []),
        "target_chapter_candidates": packet.get("target_chapter_candidates", ["not_assigned"]),
        "target_chapter_status": packet.get("target_chapter_status", "not_assigned"),
        "author_task_constraints": [
            "Future authoring run must treat this package as input metadata, not as prose.",
            "Future authoring run must keep author_allowed=false unless a separate explicit authoring gate changes it.",
            "Future red-team gate must run before any chapter-update candidate stage.",
            "No docs/book mutation may occur from this package alone.",
        ],
        "later_author_prompt_seed": "Instruction seed only, not final prose: in a later controlled draft-only run, consider whether a narrowly caveated OpenClaw/Hermes setup-tooling mention is useful; preserve the required caveat and all do-not-say constraints; do not write chapter-ready text from this seed alone.",
        "provenance_paths": packet.get("provenance_paths", []) + [
            "reports/editorial/citation-pipeline-test-20260612-narrative-packet-candidates-run20.json",
            "reports/editorial/citation-pipeline-test-20260612-packet-redteam-gate-run21.json",
            "reports/editorial/citation-pipeline-test-20260612-closed-loop-state-machine-run22a.json",
        ],
        "singleton_input": True,
        "evidence_narrowness_warning": packet.get("evidence_narrowness_warning"),
        "advisory_only": True,
        "author_allowed": False,
        "publication_approved": False,
        "eligible_for_claim_insertion": False,
        "eligible_for_authoring": False,
        "eligible_for_publication": False,
        "chapter_update_allowed": False,
    }
    validate_package(package)
    return package


def validate_package(package: dict[str, Any]) -> None:
    if package.get("draft_input_type") not in ALLOWED_DRAFT_INPUT_TYPES:
        raise DraftInputError("invalid draft_input_type")
    if package.get("draft_input_decision") not in ALLOWED_DRAFT_INPUT_DECISIONS:
        raise DraftInputError("invalid draft_input_decision")
    if package.get("draft_input_use") not in ALLOWED_DRAFT_INPUT_USES:
        raise DraftInputError("invalid draft_input_use")
    for flag in ["advisory_only"]:
        if package.get(flag) is not True:
            raise DraftInputError(f"package missing true safety flag: {flag}")
    for flag in PACKAGE_FALSE_FLAGS:
        if package.get(flag) is not False:
            raise DraftInputError(f"package safety flag must remain false: {flag}")
    if REQUIRED_CAVEAT not in package.get("required_caveats", []):
        raise DraftInputError("package missing required caveat")
    if package.get("do_not_say") != REQUIRED_DO_NOT_SAY:
        raise DraftInputError("package missing required do_not_say guidance")
    if has_chapter_ready_field(package):
        raise DraftInputError("package contains chapter-ready prose field")
    forbidden_phrases = ["approved for publication", "publication approved", "authoring approved", "approved for authoring"]
    text = compact_json(package).lower()
    for phrase in forbidden_phrases:
        if phrase in text:
            raise DraftInputError(f"package contains forbidden approval phrase: {phrase}")


def safety_flags() -> dict[str, bool]:
    return {
        "report_only": True,
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
        "chapter_prose_generated": False,
        "draft_inputs_persisted": False,
        "gpt55_advisory_is_human_or_editor_approval": False,
    }


def generate_report(args: argparse.Namespace) -> dict[str, Any]:
    run22a_path = resolve(args.state_machine_report)
    run21_path = resolve(args.packet_redteam_report)
    run20_path = resolve(args.packet_report)
    run22a = load_json(run22a_path, "Run 22A state-machine report")
    run21 = load_json(run21_path, "Run 21 packet red-team report")
    run20 = load_json(run20_path, "Run 20 packet report")
    selected, excluded = select_eligible_transitions(run22a, run21, run20)
    packages = [build_package(item) for item in selected]
    type_counts = Counter(p["draft_input_type"] for p in packages)
    decision_counts = Counter(p["draft_input_decision"] for p in packages)
    use_counts = Counter(p["draft_input_use"] for p in packages)
    chapter_counts = Counter(p["target_chapter_status"] for p in packages)
    db = db_path()
    with connect_readonly(db) as con:
        before_counts = {"source_notes": table_count(con, "source_notes"), "claims": table_count(con, "claims"), "editorial_reviews": table_count(con, "editorial_reviews")}
        before_status = status_snapshots(con)
        after_counts = {"source_notes": table_count(con, "source_notes"), "claims": table_count(con, "claims"), "editorial_reviews": table_count(con, "editorial_reviews")}
        after_status = status_snapshots(con)
    payload = {
        "run_id": args.run_id,
        "generated_at": utc_now(),
        "mode": MODE,
        "input_paths": {
            "state_machine_report": rel(run22a_path),
            "packet_redteam_report": rel(run21_path),
            "packet_report": rel(run20_path),
            "sqlite_db": rel(db),
        },
        "report_only": True,
        "llm_used": False,
        "reasoning_status": "deterministic_packaging_existing_gpt55_outputs",
        "selected_transition_count": len(selected),
        "draft_input_package_count": len(packages),
        "excluded_transition_count": len(excluded),
        "draft_input_type_counts": dict(type_counts),
        "draft_input_decision_counts": dict(decision_counts),
        "draft_input_use_counts": dict(use_counts),
        "target_chapter_status_counts": dict(chapter_counts),
        "selected_transitions": [item["transition"] for item in selected],
        "excluded_transitions": excluded,
        "draft_input_packages": packages,
        "failed_draft_input_checks": [],
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
        raise DraftInputError("forbidden DB/status delta detected during report-only draft-input packaging")
    return payload


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        f"# Run 22B author-draft input package — {payload['run_id']}",
        "",
        "## Summary",
        "",
        f"- Report-only: `{payload['report_only']}`",
        f"- LLM used: `{payload['llm_used']}`",
        f"- Reasoning status: `{payload['reasoning_status']}`",
        f"- Selected transitions: `{payload['selected_transition_count']}`",
        f"- Draft-input packages: `{payload['draft_input_package_count']}`",
        f"- Excluded transitions: `{payload['excluded_transition_count']}`",
        "",
        "## Selected state-machine transition",
        "",
    ]
    for transition in payload["selected_transitions"]:
        lines += [
            f"- `{transition.get('object_id')}`",
            f"  - current_state: `{transition.get('current_state')}`",
            f"  - proposed_next_state: `{transition.get('proposed_next_state')}`",
            f"  - transition_decision: `{transition.get('transition_decision')}`",
            f"  - allowed_future_run: `{transition.get('allowed_future_run')}`",
            "",
        ]
    lines += ["## Draft-input package created", ""]
    for package in payload["draft_input_packages"]:
        lines += [
            f"- `{package['draft_input_id']}`",
            f"  - source_packet_id: `{package['source_packet_id']}`",
            f"  - draft_input_type: `{package['draft_input_type']}`",
            f"  - draft_input_decision: `{package['draft_input_decision']}`",
            f"  - draft_input_use: `{package['draft_input_use']}`",
            f"  - target_chapter_status: `{package['target_chapter_status']}`",
            "",
        ]
    lines += [
        "## Caveat-only constraints",
        "",
        f"Required caveat: {REQUIRED_CAVEAT}",
        "",
        "## Allowed future author scope",
        "",
    ]
    for package in payload["draft_input_packages"]:
        for item in package["allowed_author_scope"]:
            lines.append(f"- {item}")
    lines += ["", "## Forbidden future author scope", ""]
    for package in payload["draft_input_packages"]:
        for item in package["forbidden_author_scope"]:
            lines.append(f"- {item}")
    lines += ["", "## Do-not-say guidance", ""]
    for item in REQUIRED_DO_NOT_SAY:
        lines.append(f"- {item}")
    lines += [
        "", "## Evidence limitations and residual risk", "",
    ]
    for package in payload["draft_input_packages"]:
        for item in package["evidence_limitations"]:
            lines.append(f"- {item}")
        lines.append(f"- residual_risk: {package['residual_risk']}")
    lines += [
        "", "## Why this is not authoring", "",
        "This package is constrained planning metadata only. It contains no final paragraph prose, no chapter-ready prose, and no authoring approval. `author_allowed` and `eligible_for_authoring` remain false.",
        "", "## Why this is not publication approval", "",
        "This package does not approve publication, does not insert claims or editorial reviews, does not persist packets, and does not update chapter files. `publication_approved`, `eligible_for_publication`, and `chapter_update_allowed` remain false.",
        "", "## Why this does not update chapters", "",
        "Run 22B is not wired into chapter synthesis or docs/book mutation paths. It writes only report artifacts under reports/editorial.",
        "", "## Recommendation for Run 23", "",
        "Proceed to a report-only author-draft construction canary or author-input red-team preflight. The next run must still avoid chapter prose/publication unless a separate explicit authoring gate is implemented and verified.",
    ]
    return "\n".join(lines) + "\n"


def write_reports(payload: dict[str, Any], output_dir: Path, suffix: str) -> dict[str, str]:
    out_dir = output_dir if output_dir.is_absolute() else ROOT / output_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{payload['run_id']}-author-draft-input-{suffix}" if suffix else f"{payload['run_id']}-author-draft-input"
    json_path = out_dir / f"{stem}.json"
    md_path = out_dir / f"{stem}.md"
    payload["output_paths"] = {"json": rel(json_path), "markdown": rel(md_path)}
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(payload), encoding="utf-8")
    return payload["output_paths"]


def parse_args(argv: list[str]) -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", default=RUN_ID_DEFAULT)
    ap.add_argument("--state-machine-report", default=DEFAULT_RUN22A)
    ap.add_argument("--packet-redteam-report", default=DEFAULT_RUN21)
    ap.add_argument("--packet-report", default=DEFAULT_RUN20)
    ap.add_argument("--output-dir", default="reports/editorial")
    ap.add_argument("--report-suffix", default="run22b")
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        payload = generate_report(args)
        write_reports(payload, resolve(args.output_dir), args.report_suffix)
        print(json.dumps({
            "ok": True,
            "output_paths": payload["output_paths"],
            "selected_transition_count": payload["selected_transition_count"],
            "draft_input_package_count": payload["draft_input_package_count"],
            "excluded_transition_count": payload["excluded_transition_count"],
            "draft_input_type_counts": payload["draft_input_type_counts"],
            "draft_input_decision_counts": payload["draft_input_decision_counts"],
            "draft_input_use_counts": payload["draft_input_use_counts"],
            "target_chapter_status_counts": payload["target_chapter_status_counts"],
        }, sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
