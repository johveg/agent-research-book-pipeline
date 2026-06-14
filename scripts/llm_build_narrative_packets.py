#!/usr/bin/env python3
"""Run 20 report-only caveat-only narrative packet candidate construction.

This stage calls the closed_loop_editorial GPT-5.5 profile through the shared
Hermes strict-JSON bridge and creates advisory packet candidates only. Packet
candidates are planning structures, not chapter prose, authoring approval,
publication approval, claims, source notes, or editorial reviews.
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
MODE = "llm_build_narrative_packets"
DEFAULT_QUALITY_REPORT = f"reports/editorial/{RUN_ID_DEFAULT}-cluster-quality-gate-run19.json"
REQUIRED_CAVEAT = "Frame narrowly: OpenClaw documentation names Hermes in migration/setup tooling contexts; do not state that Hermes is a runtime dependency or general operating environment without additional sources."

READY_RULE = {
    "quality_gate_decision": "caveat_only_packet_candidate_ready",
    "packet_readiness": "ready_for_caveat_only_packet",
    "closed_loop_disposition": "caveat_only",
    "recommended_next_stage": "build_caveat_only_packet_candidate",
}
EXCLUDE_DECISIONS = {
    "needs_more_sources",
    "source_context_unclear",
    "safe_reports_only",
    "exclude_from_packetization",
    "contradiction_review_required",
    "exclude_from_pipeline",
    "do_not_use",
}
ALLOWED_PACKET_TYPES = {
    "caveat_only_packet_candidate",
    "context_only_packet_candidate",
    "safe_reports_only_packet_candidate",
}
ALLOWED_PACKET_DECISIONS = {
    "packet_candidate",
    "caveat_only_packet_candidate",
    "safe_reports_only",
    "needs_more_sources",
    "source_context_unclear",
    "exclude_from_packetization",
    "contradiction_review_required",
}
ALLOWED_PACKET_USES = {
    "caveat_only",
    "context_only",
    "safe_reports_only",
    "not_for_authoring",
    "not_for_publication",
}
ALLOWED_TARGET_CHAPTER_STATUS = {"suggested_only", "uncertain", "not_assigned"}
FALSE_FLAGS = [
    "author_allowed",
    "publication_approved",
    "eligible_for_claim_insertion",
    "eligible_for_authoring",
    "eligible_for_publication",
    "chapter_update_allowed",
]
REQUIRED_PACKET_FIELDS = [
    "packet_id",
    "packet_type",
    "packet_decision",
    "packet_use",
    "title",
    "packet_summary",
    "packet_angle",
    "target_chapter_candidates",
    "target_chapter_status",
    "target_section_candidates",
    "cluster_ids",
    "source_ids",
    "note_ids",
    "manifest_item_ids",
    "source_review_ids",
    "candidate_source_ids",
    "support_decisions",
    "corroboration_decisions",
    "evidence_use_decisions",
    "quality_gate_decision",
    "packet_readiness",
    "required_caveats",
    "caveat_text",
    "limitations",
    "residual_risk",
    "do_not_say",
    "author_guidance",
    "citation_requirements",
    "provenance_paths",
    "singleton_packet",
    "evidence_narrowness_warning",
    "advisory_only",
    "author_allowed",
    "publication_approved",
    "eligible_for_claim_insertion",
    "eligible_for_authoring",
    "eligible_for_publication",
    "chapter_update_allowed",
]
DISALLOWED_PROSE_KEYS = {
    "publishable_paragraph",
    "chapter_prose",
    "final_prose",
    "draft_paragraph",
    "paragraph",
    "chapter_ready_prose",
    "book_text",
}
REQUIRED_DO_NOT_SAY_SUBSTRINGS = [
    "runtime dependency of OpenClaw",
    "general operating environment for OpenClaw",
    "requires Hermes for web or phone access",
    "generalize beyond migration/setup/import tooling contexts",
    "factual claim without the caveat",
    "chapter prose before later author/red-team gates pass",
]


class NarrativePacketError(RuntimeError):
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
        raise NarrativePacketError(f"missing input {label}: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise NarrativePacketError(f"invalid JSON in {label}: {exc}") from exc
    if not isinstance(data, dict):
        raise NarrativePacketError(f"{label} must be a JSON object")
    return data


def compact_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


def connect_readonly(path: Path) -> sqlite3.Connection:
    if not path.exists():
        raise NarrativePacketError(f"missing SQLite DB: {path}")
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


def validate_quality_report(report: dict[str, Any]) -> None:
    if report.get("mode") != "llm_cluster_quality_gate":
        raise NarrativePacketError("Run 19 quality-gate report mode mismatch")
    if report.get("report_only") is not True:
        raise NarrativePacketError("Run 19 quality-gate report must be report_only")
    if report.get("llm_used") is not True or report.get("reasoning_status") != "high_reasoning_used":
        raise NarrativePacketError("Run 19 quality-gate report must contain live high-reasoning output")
    if not isinstance(report.get("cluster_reviews"), list):
        raise NarrativePacketError("Run 19 quality-gate report missing cluster_reviews list")
    if not isinstance(report.get("selected_clusters"), list):
        raise NarrativePacketError("Run 19 quality-gate report missing selected_clusters list")
    if not isinstance(report.get("excluded_clusters"), list):
        raise NarrativePacketError("Run 19 quality-gate report missing excluded_clusters list")
    safety = report.get("safety_flags")
    if not isinstance(safety, dict):
        raise NarrativePacketError("Run 19 quality-gate report missing safety_flags")
    expected = {
        "advisory_only": True,
        "author_allowed": False,
        "publication_approved": False,
        "eligible_for_claim_insertion": False,
        "eligible_for_authoring": False,
        "eligible_for_publication": False,
        "narrative_packets_created": False,
        "chapter_prose_generated": False,
        "source_notes_written": False,
    }
    for key, expected_value in expected.items():
        if safety.get(key) is not expected_value:
            raise NarrativePacketError(f"Run 19 quality-gate report safety flag invalid: {key}")


def validate_review_safety(review: dict[str, Any]) -> None:
    if review.get("advisory_only") is not True:
        raise NarrativePacketError(f"cluster review {review.get('cluster_id')} safety flag invalid: advisory_only")
    for key in FALSE_FLAGS[:-1]:
        if review.get(key) is not False:
            raise NarrativePacketError(f"cluster review {review.get('cluster_id')} safety flag invalid: {key}")
    if review.get("raw_capture_dependency") is True or review.get("raw_content_stored") is True:
        raise NarrativePacketError(f"cluster review {review.get('cluster_id')} has forbidden raw capture dependency")
    caveats = review.get("required_caveats")
    caveat_text = review.get("caveat_text") or ""
    combined = "\n".join(caveats if isinstance(caveats, list) else []) + "\n" + str(caveat_text)
    if REQUIRED_CAVEAT not in combined:
        raise NarrativePacketError(f"cluster review {review.get('cluster_id')} missing required caveat")


def select_reviews(report: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    selected: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    selected_clusters = {c.get("cluster_id"): c for c in report.get("selected_clusters", []) if isinstance(c, dict)}
    for review in report.get("cluster_reviews", []):
        if not isinstance(review, dict):
            raise NarrativePacketError("cluster review must be object")
        validate_review_safety(review)
        cid = review.get("cluster_id")
        enriched = dict(review)
        if cid in selected_clusters:
            enriched["source_cluster"] = selected_clusters[cid]
        if any(review.get(k) in EXCLUDE_DECISIONS for k in ["quality_gate_decision", "packet_readiness", "closed_loop_disposition", "recommended_next_stage"]):
            enriched["exclusion_decision"] = str(review.get("quality_gate_decision"))
            enriched["excluded_reason"] = "blocked_or_not_packet_ready"
            excluded.append(enriched)
            continue
        if all(review.get(k) == v for k, v in READY_RULE.items()):
            selected.append(enriched)
        else:
            enriched["exclusion_decision"] = str(review.get("quality_gate_decision") or "not_selected")
            enriched["excluded_reason"] = "does_not_match_caveat_only_packet_ready_rule"
            excluded.append(enriched)
    for item in report.get("excluded_clusters", []):
        if not isinstance(item, dict):
            raise NarrativePacketError("excluded cluster item must be object")
        copy = dict(item)
        copy.setdefault("exclusion_decision", item.get("exclusion_decision") or item.get("quality_gate_decision") or item.get("downstream_manifest_decision") or item.get("closed_loop_disposition") or "upstream_excluded")
        copy.setdefault("excluded_reason", "upstream_excluded_from_run19_quality_gate")
        excluded.append(copy)
    return selected, excluded


def as_str(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be non-empty string")
    return value


def as_list(value: Any, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be list")
    return value


def validate_packet(packet: dict[str, Any], selected_by_cluster: dict[str, dict[str, Any]]) -> None:
    if not isinstance(packet, dict):
        raise ValueError("packet candidate must be object")
    forbidden = sorted(DISALLOWED_PROSE_KEYS & set(packet))
    if forbidden:
        raise ValueError(f"packet contains forbidden chapter-ready prose field(s): {forbidden}")
    for field in REQUIRED_PACKET_FIELDS:
        if field not in packet:
            raise ValueError(f"packet missing required field: {field}")
    as_str(packet.get("packet_id"), "packet_id")
    for field, allowed in [
        ("packet_type", ALLOWED_PACKET_TYPES),
        ("packet_decision", ALLOWED_PACKET_DECISIONS),
        ("packet_use", ALLOWED_PACKET_USES),
        ("target_chapter_status", ALLOWED_TARGET_CHAPTER_STATUS),
    ]:
        value = packet.get(field)
        if not isinstance(value, str):
            raise ValueError(f"{field} must be exactly one string enum value")
        if value not in allowed:
            raise ValueError(f"invalid {field}: {value}")
    for field in [
        "target_chapter_candidates",
        "target_section_candidates",
        "cluster_ids",
        "source_ids",
        "note_ids",
        "manifest_item_ids",
        "source_review_ids",
        "candidate_source_ids",
        "support_decisions",
        "corroboration_decisions",
        "evidence_use_decisions",
        "required_caveats",
        "limitations",
        "do_not_say",
        "author_guidance",
        "citation_requirements",
        "provenance_paths",
    ]:
        as_list(packet.get(field), field)
    for field in ["title", "packet_summary", "packet_angle", "caveat_text", "residual_risk", "evidence_narrowness_warning"]:
        as_str(packet.get(field), field)
    if packet.get("advisory_only") is not True:
        raise ValueError("packet advisory_only must be true")
    for key in FALSE_FLAGS:
        if packet.get(key) is not False:
            raise ValueError(f"packet {key} must be false")
    if packet.get("packet_type") != "caveat_only_packet_candidate" or packet.get("packet_decision") != "caveat_only_packet_candidate" or packet.get("packet_use") != "caveat_only":
        raise ValueError("selected Run 20 packet must remain caveat-only")
    if packet.get("quality_gate_decision") != READY_RULE["quality_gate_decision"] or packet.get("packet_readiness") != READY_RULE["packet_readiness"]:
        raise ValueError("packet does not preserve Run 19 quality-gate readiness")
    cluster_ids = packet.get("cluster_ids")
    if not cluster_ids or any(not isinstance(cid, str) for cid in cluster_ids):
        raise ValueError("packet cluster_ids must be non-empty list of strings")
    if any(cid not in selected_by_cluster for cid in cluster_ids):
        raise ValueError("packet references unknown selected cluster")
    for cid in cluster_ids:
        source = selected_by_cluster[cid]
        source_cluster = source.get("source_cluster") or {}
        if source_cluster.get("singleton_cluster") is True and packet.get("singleton_packet") is not True:
            raise ValueError("singleton source cluster must produce singleton packet")
    required_caveats_text = "\n".join(str(x) for x in packet.get("required_caveats", []))
    if REQUIRED_CAVEAT not in required_caveats_text:
        raise ValueError("packet required caveats missing required caveat")
    if REQUIRED_CAVEAT not in str(packet.get("caveat_text", "")):
        raise ValueError("packet caveat_text missing required caveat")
    do_not_say = "\n".join(str(x) for x in packet.get("do_not_say", []))
    for required in REQUIRED_DO_NOT_SAY_SUBSTRINGS:
        if required not in do_not_say:
            raise ValueError(f"packet do_not_say missing required guidance: {required}")
    # Keep planning text visibly non-publishable and short enough to avoid chapter-ready prose.
    if len(packet.get("packet_summary", "")) > 300:
        raise ValueError("packet_summary is too long for non-publishable planning summary")
    if len(packet.get("packet_angle", "")) > 300:
        raise ValueError("packet_angle is too long for non-publishable planning angle")


def make_validator(selected: list[dict[str, Any]]):
    selected_by_cluster = {str(r["cluster_id"]): r for r in selected}

    def validator(obj: dict[str, Any]) -> None:
        packets = obj.get("packet_candidates")
        if not isinstance(packets, list):
            raise ValueError("LLM JSON must contain packet_candidates list")
        if len(packets) != len(selected_by_cluster):
            raise ValueError(f"expected {len(selected_by_cluster)} packet candidate(s), got {len(packets)}")
        seen = set()
        for packet in packets:
            validate_packet(packet, selected_by_cluster)
            pid = packet["packet_id"]
            if not isinstance(pid, str):
                raise ValueError("packet_id must be string")
            if pid in seen:
                raise ValueError(f"duplicate packet_id: {pid}")
            seen.add(pid)
    return validator


def build_prompt(selected: list[dict[str, Any]], excluded: list[dict[str, Any]], run_id: str) -> str:
    schema = {
        "packet_candidates": [
            {
                "packet_id": "string",
                "packet_type": "choose exactly one string: caveat_only_packet_candidate | context_only_packet_candidate | safe_reports_only_packet_candidate",
                "packet_decision": "choose exactly one string: packet_candidate | caveat_only_packet_candidate | safe_reports_only | needs_more_sources | source_context_unclear | exclude_from_packetization | contradiction_review_required",
                "packet_use": "choose exactly one string: caveat_only | context_only | safe_reports_only | not_for_authoring | not_for_publication",
                "title": "short planning title, not prose",
                "packet_summary": "short non-publishable planning summary, <= 300 chars",
                "packet_angle": "editorial planning angle, <= 300 chars, not final prose",
                "target_chapter_candidates": ["string"],
                "target_chapter_status": "choose exactly one string: suggested_only | uncertain | not_assigned",
                "target_section_candidates": ["string"],
                "cluster_ids": ["string"],
                "source_ids": ["string"],
                "note_ids": ["string"],
                "manifest_item_ids": ["string"],
                "source_review_ids": ["string"],
                "candidate_source_ids": ["string"],
                "support_decisions": ["string"],
                "corroboration_decisions": ["string"],
                "evidence_use_decisions": ["string"],
                "quality_gate_decision": READY_RULE["quality_gate_decision"],
                "packet_readiness": READY_RULE["packet_readiness"],
                "required_caveats": [REQUIRED_CAVEAT],
                "caveat_text": REQUIRED_CAVEAT,
                "limitations": ["string"],
                "residual_risk": "string",
                "do_not_say": [
                    "Do not say Hermes is a runtime dependency of OpenClaw.",
                    "Do not say Hermes is the general operating environment for OpenClaw.",
                    "Do not say OpenClaw requires Hermes for web or phone access.",
                    "Do not generalize beyond migration/setup/import tooling contexts unless additional sources support it.",
                    "Do not use this packet as a factual claim without the caveat.",
                    "Do not use this packet for chapter prose before later author/red-team gates pass.",
                ],
                "author_guidance": ["planning guidance only, no paragraphs"],
                "citation_requirements": ["string"],
                "provenance_paths": ["object or string"],
                "singleton_packet": True,
                "evidence_narrowness_warning": "string",
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
        "task": "Run 20 report-only caveat-only narrative packet candidate construction",
        "strict_json_required": True,
        "selected_cluster_reviews": selected,
        "excluded_cluster_reviews": excluded,
        "required_caveat": REQUIRED_CAVEAT,
        "allowed_schema": schema,
        "instructions": [
            "Return JSON only. No markdown, no prose outside JSON.",
            "For every enum field, choose exactly ONE allowed string; do NOT return arrays or objects for packet_type, packet_decision, packet_use, target_chapter_status, quality_gate_decision, or packet_readiness.",
            "Build exactly one packet candidate for each selected cluster review.",
            "This is packet construction for later review/gating, not authoring and not chapter prose.",
            "Do not include publishable paragraph fields such as publishable_paragraph, chapter_prose, final_prose, draft_paragraph, paragraph, chapter_ready_prose, or book_text.",
            "packet_summary must be short and non-publishable; packet_angle must be an editorial planning angle, not final prose.",
            "Preserve the required caveat exactly or more conservatively.",
            "Use exactly the required do_not_say guidance items.",
            "Set author_allowed, publication_approved, eligible_for_claim_insertion, eligible_for_authoring, eligible_for_publication, and chapter_update_allowed to false.",
            "Do not treat GPT-5.5 advisory reasoning as human/editor approval.",
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
        "narrative_packets_persisted": False,
        "chapter_prose_generated": False,
        "packet_candidates_are_chapter_ready": False,
        "gpt55_is_human_or_editor_approval": False,
    }


def build_payload(args: argparse.Namespace) -> dict[str, Any]:
    quality_path = resolve(args.quality_gate_report)
    report = load_json(quality_path, "Run 19 quality-gate report")
    validate_quality_report(report)
    try:
        profile = load_model_profile(args.reasoning_profile)
    except ModelProfileError as exc:
        raise NarrativePacketError(f"model_profile_error:{exc}") from exc
    selected, excluded = select_reviews(report)
    if not selected:
        raise NarrativePacketError("no selected cluster reviews for narrative packet construction")
    db = db_path()
    with connect_readonly(db) as con:
        before_counts = {"source_notes": table_count(con, "source_notes"), "claims": table_count(con, "claims"), "editorial_reviews": table_count(con, "editorial_reviews")}
        before_status = status_snapshots(con)
        prompt = build_prompt(selected, excluded, args.run_id)
        try:
            llm = call_high_reasoning_json(
                prompt,
                schema_name="run20_narrative_packet_candidates",
                validator=make_validator(selected),
                provider=args.provider,
                model=args.model,
                timeout_seconds=args.timeout_seconds,
                reasoning_profile=args.reasoning_profile,
            )
        except HighReasoningError as exc:
            raise NarrativePacketError(str(exc.result.get("error") or exc)) from exc
        after_counts = {"source_notes": table_count(con, "source_notes"), "claims": table_count(con, "claims"), "editorial_reviews": table_count(con, "editorial_reviews")}
        after_status = status_snapshots(con)

    packets = llm["parsed_json"]["packet_candidates"]
    packet_type_counts = Counter(p["packet_type"] for p in packets)
    packet_decision_counts = Counter(p["packet_decision"] for p in packets)
    packet_use_counts = Counter(p["packet_use"] for p in packets)
    target_chapter_status_counts = Counter(p["target_chapter_status"] for p in packets)
    changed_source_notes = before_counts["source_notes"] != after_counts["source_notes"]
    payload = {
        "run_id": args.run_id,
        "generated_at": utc_now(),
        "mode": MODE,
        "input_paths": {"quality_gate_report": rel(quality_path), "sqlite_db": rel(db)},
        "report_only": True,
        "llm_used": bool(llm.get("llm_used")),
        "reasoning_status": llm.get("reasoning_status"),
        "provider": llm.get("provider") or profile["provider"],
        "model": llm.get("model") or profile["model"],
        "bridge": llm.get("bridge") or profile["bridge"],
        "model_profile": llm.get("model_profile") or profile["profile_name"],
        "strict_json_required": bool(llm.get("strict_json_required", profile["strict_json_required"])),
        "weak_local_fallback_refused": bool(llm.get("weak_local_fallback_refused", True)),
        "selected_cluster_review_count": len(selected),
        "packet_candidate_count": len(packets),
        "excluded_cluster_review_count": len(excluded),
        "packet_type_counts": dict(packet_type_counts),
        "packet_decision_counts": dict(packet_decision_counts),
        "packet_use_counts": dict(packet_use_counts),
        "target_chapter_status_counts": dict(target_chapter_status_counts),
        "selected_cluster_reviews": selected,
        "excluded_cluster_reviews": excluded,
        "packet_candidates": packets,
        "failed_packet_checks": [],
        "llm_metadata": {k: llm.get(k) for k in ["ok", "stdout_json_valid", "exit_code", "timed_out", "elapsed_seconds", "stdout_hash", "prompt_hash", "command_shape"]},
        "changed_db": False,
        "changed_source_notes": changed_source_notes,
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
        raise NarrativePacketError("high reasoning was not used")
    if payload["provider"] != "copilot" or payload["model"] != "gpt-5.5" or payload["bridge"] != "hermes_cli" or payload["model_profile"] != args.reasoning_profile:
        raise NarrativePacketError("unexpected high-reasoning provider/model/bridge/profile")
    if payload["changed_source_notes"] or payload["claims_inserted"] or payload["editorial_reviews_inserted"] or payload["source_status_changed"] or payload["claim_status_changed"] or payload["editorial_status_changed"]:
        raise NarrativePacketError("forbidden DB/status delta detected during report-only narrative packet construction")
    return payload


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        f"# Run 20 narrative packet candidates — {payload['run_id']}", "",
        "## Summary", "",
        f"- Report-only: `{payload['report_only']}`",
        f"- GPT-5.5 used: `{payload['llm_used']}`",
        f"- Provider/model/bridge/profile: `{payload['provider']}` / `{payload['model']}` / `{payload['bridge']}` / `{payload['model_profile']}`",
        f"- Selected cluster reviews: `{payload['selected_cluster_review_count']}`",
        f"- Packet candidates: `{payload['packet_candidate_count']}`",
        f"- Excluded cluster reviews/items: `{payload['excluded_cluster_review_count']}`",
        "", "## Selected cluster review", "",
    ]
    for r in payload["selected_cluster_reviews"]:
        lines += [
            f"- `{r['cluster_id']}`",
            f"  - quality_gate_decision: `{r['quality_gate_decision']}`",
            f"  - packet_readiness: `{r['packet_readiness']}`",
            f"  - recommended_next_stage: `{r['recommended_next_stage']}`",
            "",
        ]
    lines += ["## Packet candidates", ""]
    for p in payload["packet_candidates"]:
        lines += [
            f"- `{p['packet_id']}` — {p['title']}",
            f"  - type/decision/use: `{p['packet_type']}` / `{p['packet_decision']}` / `{p['packet_use']}`",
            f"  - target_chapter_status: `{p['target_chapter_status']}`",
            f"  - target_chapter_candidates: `{', '.join(p.get('target_chapter_candidates') or [])}`",
            f"  - singleton_packet: `{p['singleton_packet']}`",
            f"  - summary: {p['packet_summary']}",
            f"  - angle: {p['packet_angle']}",
            "",
        ]
    lines += ["## Caveat-only constraints", ""]
    for p in payload["packet_candidates"]:
        lines += [f"- `{p['packet_id']}` caveat: {p['caveat_text']}", ""]
    lines += ["## Do-not-say guidance", ""]
    for p in payload["packet_candidates"]:
        for item in p.get("do_not_say") or []:
            lines.append(f"- {item}")
    lines += [
        "", "## Safety", "",
        "This is not claim insertion, not authoring, not publication approval, and not a chapter update. Packet summaries and angles are planning metadata only, not publishable prose. No DB writes, source-registry/raw-capture changes, docs/book changes, schema changes, daily-worker changes, claims, editorial reviews, or source notes were produced.",
        "", "## Limitations and residual risk", "",
        "The packet is singleton and caveat-only. It must not be generalized beyond migration/setup/import tooling contexts without additional sources and later review gates.",
        "", "## Recommendation for Run 21", "",
        "Run 21 should perform a report-only packet safety/red-team gate over the Run 20 packet candidate before any persistence, authoring, or publication path is considered.",
    ]
    return "\n".join(lines) + "\n"


def write_reports(payload: dict[str, Any], output_dir: Path, suffix: str) -> dict[str, str]:
    out_dir = output_dir if output_dir.is_absolute() else ROOT / output_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{payload['run_id']}-narrative-packet-candidates-{suffix}" if suffix else f"{payload['run_id']}-narrative-packet-candidates"
    json_path = out_dir / f"{stem}.json"
    md_path = out_dir / f"{stem}.md"
    payload["output_paths"] = {"json": rel(json_path), "markdown": rel(md_path)}
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(payload), encoding="utf-8")
    return payload["output_paths"]


def parse_args(argv: list[str]) -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", default=RUN_ID_DEFAULT)
    ap.add_argument("--quality-gate-report", default=DEFAULT_QUALITY_REPORT)
    ap.add_argument("--output-dir", default="reports/editorial")
    ap.add_argument("--report-suffix", default="run20")
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
            "selected_cluster_review_count": payload["selected_cluster_review_count"],
            "packet_candidate_count": payload["packet_candidate_count"],
            "excluded_cluster_review_count": payload["excluded_cluster_review_count"],
            "packet_type_counts": payload["packet_type_counts"],
            "packet_decision_counts": payload["packet_decision_counts"],
            "packet_use_counts": payload["packet_use_counts"],
            "target_chapter_status_counts": payload["target_chapter_status_counts"],
        }, sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
