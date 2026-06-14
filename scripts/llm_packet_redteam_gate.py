#!/usr/bin/env python3
"""Run 21 report-only packet safety and red-team gate.

Uses the closed_loop_editorial GPT-5.5 profile through the shared strict-JSON
Hermes bridge to red-team Run 20 packet candidates. This is advisory/report-only:
no authoring, no publication approval, no chapter prose, no persistence.
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
MODE = "llm_packet_redteam_gate"
DEFAULT_PACKET_REPORT = f"reports/editorial/{RUN_ID_DEFAULT}-narrative-packet-candidates-run20.json"
REQUIRED_CAVEAT = "Frame narrowly: OpenClaw documentation names Hermes in migration/setup tooling contexts; do not state that Hermes is a runtime dependency or general operating environment without additional sources."

ALLOWED_REDTEAM_DECISIONS = {
    "caveat_only_author_input_ready",
    "safe_reports_only",
    "needs_more_sources",
    "source_context_unclear",
    "exclude_from_authoring",
    "contradiction_review_required",
}
ALLOWED_AUTHOR_INPUT_READINESS = {
    "ready_for_caveat_only_draft_input",
    "not_ready_safe_reports_only",
    "not_ready_needs_more_sources",
    "not_ready_source_context_unclear",
    "not_ready_exclude",
    "not_ready_contradiction_review",
}
ALLOWED_DISPOSITIONS = {
    "caveat_only",
    "safe_reports_only",
    "needs_more_sources",
    "source_context_unclear",
    "exclude_from_pipeline",
    "contradiction_review_required",
}
ALLOWED_NEXT_STAGES = {
    "build_caveat_only_author_draft_input",
    "keep_safe_reports_only",
    "run_additional_source_collection",
    "run_source_context_review",
    "exclude_from_pipeline",
    "run_contradiction_review",
}
FALSE_FLAGS = [
    "author_allowed",
    "publication_approved",
    "eligible_for_claim_insertion",
    "eligible_for_authoring",
    "eligible_for_publication",
    "chapter_update_allowed",
]
REQUIRED_REVIEW_FIELDS = [
    "packet_id", "packet_type", "packet_use", "redteam_decision",
    "author_input_readiness", "closed_loop_disposition",
    "caveat_integrity_assessment", "do_not_say_compliance_assessment",
    "provenance_assessment", "residual_risk_assessment",
    "author_input_readiness_assessment", "required_caveats", "do_not_say",
    "limitations", "residual_risk", "recommended_next_stage", "advisory_only",
    "author_allowed", "publication_approved", "eligible_for_claim_insertion",
    "eligible_for_authoring", "eligible_for_publication", "chapter_update_allowed",
]
DISALLOWED_PROSE_KEYS = {
    "publishable_paragraph", "chapter_prose", "final_prose", "draft_paragraph",
    "paragraph", "chapter_ready_prose", "book_text",
}
REQUIRED_DO_NOT_SAY_SUBSTRINGS = [
    "runtime dependency of OpenClaw",
    "general operating environment for OpenClaw",
    "requires Hermes for web or phone access",
    "generalize beyond migration/setup/import tooling contexts",
    "factual claim without the caveat",
    "chapter prose before later author/red-team gates pass",
]


class PacketRedteamError(RuntimeError):
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
        raise PacketRedteamError(f"missing input {label}: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PacketRedteamError(f"invalid JSON in {label}: {exc}") from exc
    if not isinstance(data, dict):
        raise PacketRedteamError(f"{label} must be a JSON object")
    return data


def compact_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


def connect_readonly(path: Path) -> sqlite3.Connection:
    if not path.exists():
        raise PacketRedteamError(f"missing SQLite DB: {path}")
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


def validate_packet_report(report: dict[str, Any]) -> None:
    if report.get("mode") != "llm_build_narrative_packets":
        raise PacketRedteamError("Run 20 packet report mode mismatch")
    if report.get("report_only") is not True:
        raise PacketRedteamError("Run 20 packet report must be report_only")
    if report.get("llm_used") is not True or report.get("reasoning_status") != "high_reasoning_used":
        raise PacketRedteamError("Run 20 packet report must contain live high-reasoning output")
    if not isinstance(report.get("packet_candidates"), list):
        raise PacketRedteamError("Run 20 packet report missing packet_candidates list")
    safety = report.get("safety_flags")
    if not isinstance(safety, dict):
        raise PacketRedteamError("Run 20 packet report missing safety_flags")
    expected = {
        "advisory_only": True,
        "author_allowed": False,
        "publication_approved": False,
        "eligible_for_claim_insertion": False,
        "eligible_for_authoring": False,
        "eligible_for_publication": False,
        "chapter_update_allowed": False,
        "chapter_prose_generated": False,
        "source_notes_written": False,
    }
    for k, v in expected.items():
        if safety.get(k) is not v:
            raise PacketRedteamError(f"Run 20 packet report safety flag invalid: {k}")


def validate_packet_input(packet: dict[str, Any]) -> None:
    pid = packet.get("packet_id")
    if not isinstance(packet, dict):
        raise PacketRedteamError("packet candidate must be object")
    forbidden = sorted(DISALLOWED_PROSE_KEYS & set(packet))
    if forbidden:
        raise PacketRedteamError(f"packet {pid} contains forbidden chapter-ready prose field(s): {forbidden}")
    if packet.get("advisory_only") is not True:
        raise PacketRedteamError(f"packet {pid} safety flag invalid: advisory_only")
    for k in FALSE_FLAGS:
        if packet.get(k) is not False:
            raise PacketRedteamError(f"packet {pid} safety flag invalid: {k}")
    if packet.get("raw_capture_dependency") is True or packet.get("raw_content_stored") is True:
        raise PacketRedteamError(f"packet {pid} has forbidden raw capture dependency")
    caveats = packet.get("required_caveats")
    caveat_text = packet.get("caveat_text") or ""
    if not isinstance(caveats, list) or REQUIRED_CAVEAT not in "\n".join(map(str, caveats)) or REQUIRED_CAVEAT not in str(caveat_text):
        raise PacketRedteamError(f"packet {pid} missing required caveat")
    dns = packet.get("do_not_say")
    if not isinstance(dns, list) or not dns:
        raise PacketRedteamError(f"packet {pid} missing do_not_say guidance")
    joined = "\n".join(map(str, dns))
    for required in REQUIRED_DO_NOT_SAY_SUBSTRINGS:
        if required not in joined:
            raise PacketRedteamError(f"packet {pid} do_not_say missing required guidance: {required}")


def select_packets(report: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    selected: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for packet in report.get("packet_candidates", []):
        validate_packet_input(packet)
        if (
            packet.get("packet_type") == "caveat_only_packet_candidate"
            and packet.get("packet_decision") == "caveat_only_packet_candidate"
            and packet.get("packet_use") == "caveat_only"
        ):
            selected.append(packet)
        else:
            cp = dict(packet)
            cp["excluded_reason"] = "does_not_match_caveat_only_packet_selection_rule"
            excluded.append(cp)
    return selected, excluded


def as_str(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be non-empty string")
    return value


def as_list(value: Any, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be list")
    return value


def validate_review(review: dict[str, Any], selected_by_packet: dict[str, dict[str, Any]]) -> None:
    if not isinstance(review, dict):
        raise ValueError("packet redteam review must be object")
    for k in REQUIRED_REVIEW_FIELDS:
        if k not in review:
            raise ValueError(f"review missing required field: {k}")
    pid = as_str(review.get("packet_id"), "packet_id")
    if pid not in selected_by_packet:
        raise ValueError(f"review references unknown selected packet: {pid}")
    for field, allowed in [
        ("redteam_decision", ALLOWED_REDTEAM_DECISIONS),
        ("author_input_readiness", ALLOWED_AUTHOR_INPUT_READINESS),
        ("closed_loop_disposition", ALLOWED_DISPOSITIONS),
        ("recommended_next_stage", ALLOWED_NEXT_STAGES),
    ]:
        value = review.get(field)
        if not isinstance(value, str):
            raise ValueError(f"{field} must be exactly one string enum value")
        if value not in allowed:
            raise ValueError(f"invalid {field}: {value}")
    if review.get("packet_type") != "caveat_only_packet_candidate" or review.get("packet_use") != "caveat_only":
        raise ValueError("review must preserve caveat-only packet type/use")
    for field in [
        "caveat_integrity_assessment", "do_not_say_compliance_assessment", "provenance_assessment",
        "residual_risk_assessment", "author_input_readiness_assessment", "residual_risk",
    ]:
        as_str(review.get(field), field)
    for field in ["required_caveats", "do_not_say", "limitations"]:
        as_list(review.get(field), field)
    if review.get("advisory_only") is not True:
        raise ValueError("review advisory_only must be true")
    for k in FALSE_FLAGS:
        if review.get(k) is not False:
            raise ValueError(f"review {k} must be false")
    if REQUIRED_CAVEAT not in "\n".join(map(str, review.get("required_caveats", []))):
        raise ValueError("review missing required caveat")
    dns = "\n".join(map(str, review.get("do_not_say", [])))
    for required in REQUIRED_DO_NOT_SAY_SUBSTRINGS:
        if required not in dns:
            raise ValueError(f"review do_not_say missing required guidance: {required}")
    if review.get("redteam_decision") == "caveat_only_author_input_ready":
        if review.get("author_allowed") is not False or review.get("eligible_for_authoring") is not False:
            raise ValueError("caveat_only_author_input_ready still requires author_allowed=false and eligible_for_authoring=false")


def make_validator(selected: list[dict[str, Any]]):
    selected_by_packet = {str(p["packet_id"]): p for p in selected}

    def validator(obj: dict[str, Any]) -> None:
        reviews = obj.get("packet_redteam_reviews")
        if not isinstance(reviews, list):
            raise ValueError("LLM JSON must contain packet_redteam_reviews list")
        if len(reviews) != len(selected_by_packet):
            raise ValueError(f"expected {len(selected_by_packet)} redteam review(s), got {len(reviews)}")
        seen = set()
        for review in reviews:
            validate_review(review, selected_by_packet)
            pid = review["packet_id"]
            if pid in seen:
                raise ValueError(f"duplicate packet_id review: {pid}")
            seen.add(pid)
    return validator


def build_prompt(selected: list[dict[str, Any]], excluded: list[dict[str, Any]], run_id: str) -> str:
    schema = {
        "packet_redteam_reviews": [
            {
                "packet_id": "string",
                "packet_type": "caveat_only_packet_candidate",
                "packet_use": "caveat_only",
                "redteam_decision": "choose exactly one string: caveat_only_author_input_ready | safe_reports_only | needs_more_sources | source_context_unclear | exclude_from_authoring | contradiction_review_required",
                "author_input_readiness": "choose exactly one string: ready_for_caveat_only_draft_input | not_ready_safe_reports_only | not_ready_needs_more_sources | not_ready_source_context_unclear | not_ready_exclude | not_ready_contradiction_review",
                "closed_loop_disposition": "choose exactly one string: caveat_only | safe_reports_only | needs_more_sources | source_context_unclear | exclude_from_pipeline | contradiction_review_required",
                "caveat_integrity_assessment": "string",
                "do_not_say_compliance_assessment": "string",
                "provenance_assessment": "string",
                "residual_risk_assessment": "string",
                "author_input_readiness_assessment": "string",
                "required_caveats": [REQUIRED_CAVEAT],
                "do_not_say": [
                    "Do not say Hermes is a runtime dependency of OpenClaw.",
                    "Do not say Hermes is the general operating environment for OpenClaw.",
                    "Do not say OpenClaw requires Hermes for web or phone access.",
                    "Do not generalize beyond migration/setup/import tooling contexts unless additional sources support it.",
                    "Do not use this packet as a factual claim without the caveat.",
                    "Do not use this packet for chapter prose before later author/red-team gates pass.",
                ],
                "limitations": ["string"],
                "residual_risk": "string",
                "recommended_next_stage": "choose exactly one string: build_caveat_only_author_draft_input | keep_safe_reports_only | run_additional_source_collection | run_source_context_review | exclude_from_pipeline | run_contradiction_review",
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
        "task": "Run 21 report-only packet safety and red-team gate",
        "selected_packets": selected,
        "excluded_packets": excluded,
        "required_caveat": REQUIRED_CAVEAT,
        "allowed_schema": schema,
        "instructions": [
            "Return JSON only. No markdown, no prose outside JSON.",
            "Choose exactly ONE string enum value for redteam_decision, author_input_readiness, closed_loop_disposition, and recommended_next_stage; do NOT return arrays or objects for these fields.",
            "Assess caveat integrity, do-not-say compliance, provenance completeness, residual risk, and readiness for a later draft-input construction run.",
            "Do not author. Do not create chapter prose. Do not approve publication. Do not treat GPT-5.5 as human/editor approval.",
            "Even if redteam_decision is caveat_only_author_input_ready, set author_allowed=false, eligible_for_authoring=false, publication_approved=false, eligible_for_publication=false, and chapter_update_allowed=false.",
            "Do not force a positive result; safe_reports_only, needs_more_sources, source_context_unclear, exclude_from_authoring, or contradiction_review_required are allowed.",
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
        "packets_persisted": False,
        "chapter_prose_generated": False,
        "packet_is_chapter_ready": False,
        "gpt55_is_human_or_editor_approval": False,
    }


def build_payload(args: argparse.Namespace) -> dict[str, Any]:
    packet_path = resolve(args.packet_report)
    report = load_json(packet_path, "Run 20 packet report")
    validate_packet_report(report)
    try:
        profile = load_model_profile(args.reasoning_profile)
    except ModelProfileError as exc:
        raise PacketRedteamError(f"model_profile_error:{exc}") from exc
    selected, excluded = select_packets(report)
    if not selected:
        raise PacketRedteamError("no selected packets for redteam gate")
    db = db_path()
    with connect_readonly(db) as con:
        before_counts = {"source_notes": table_count(con, "source_notes"), "claims": table_count(con, "claims"), "editorial_reviews": table_count(con, "editorial_reviews")}
        before_status = status_snapshots(con)
        prompt = build_prompt(selected, excluded, args.run_id)
        try:
            llm = call_high_reasoning_json(
                prompt,
                schema_name="run21_packet_redteam_gate",
                validator=make_validator(selected),
                provider=args.provider,
                model=args.model,
                timeout_seconds=args.timeout_seconds,
                reasoning_profile=args.reasoning_profile,
            )
        except HighReasoningError as exc:
            raise PacketRedteamError(str(exc.result.get("error") or exc)) from exc
        after_counts = {"source_notes": table_count(con, "source_notes"), "claims": table_count(con, "claims"), "editorial_reviews": table_count(con, "editorial_reviews")}
        after_status = status_snapshots(con)
    reviews = llm["parsed_json"]["packet_redteam_reviews"]
    payload = {
        "run_id": args.run_id,
        "generated_at": utc_now(),
        "mode": MODE,
        "input_paths": {"packet_report": rel(packet_path), "sqlite_db": rel(db)},
        "report_only": True,
        "llm_used": bool(llm.get("llm_used")),
        "reasoning_status": llm.get("reasoning_status"),
        "provider": llm.get("provider") or profile["provider"],
        "model": llm.get("model") or profile["model"],
        "bridge": llm.get("bridge") or profile["bridge"],
        "model_profile": llm.get("model_profile") or profile["profile_name"],
        "strict_json_required": bool(llm.get("strict_json_required", profile["strict_json_required"])),
        "weak_local_fallback_refused": bool(llm.get("weak_local_fallback_refused", True)),
        "selected_packet_count": len(selected),
        "reviewed_packet_count": len(reviews),
        "excluded_packet_count": len(excluded),
        "redteam_decision_counts": dict(Counter(r["redteam_decision"] for r in reviews)),
        "author_input_readiness_counts": dict(Counter(r["author_input_readiness"] for r in reviews)),
        "closed_loop_disposition_counts": dict(Counter(r["closed_loop_disposition"] for r in reviews)),
        "recommended_next_stage_counts": dict(Counter(r["recommended_next_stage"] for r in reviews)),
        "selected_packets": selected,
        "excluded_packets": excluded,
        "packet_redteam_reviews": reviews,
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
        raise PacketRedteamError("high reasoning was not used")
    if payload["provider"] != "copilot" or payload["model"] != "gpt-5.5" or payload["bridge"] != "hermes_cli" or payload["model_profile"] != args.reasoning_profile:
        raise PacketRedteamError("unexpected high-reasoning provider/model/bridge/profile")
    if payload["changed_source_notes"] or payload["claims_inserted"] or payload["editorial_reviews_inserted"] or payload["source_status_changed"] or payload["claim_status_changed"] or payload["editorial_status_changed"]:
        raise PacketRedteamError("forbidden DB/status delta detected during report-only redteam gate")
    return payload


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        f"# Run 21 packet red-team gate — {payload['run_id']}", "",
        "## Summary", "",
        f"- Report-only: `{payload['report_only']}`",
        f"- GPT-5.5 used: `{payload['llm_used']}`",
        f"- Provider/model/bridge/profile: `{payload['provider']}` / `{payload['model']}` / `{payload['bridge']}` / `{payload['model_profile']}`",
        f"- Selected packets: `{payload['selected_packet_count']}`",
        f"- Reviewed packets: `{payload['reviewed_packet_count']}`",
        f"- Excluded packets: `{payload['excluded_packet_count']}`",
        "", "## Red-team decisions", "",
    ]
    for r in payload["packet_redteam_reviews"]:
        lines += [
            f"- `{r['packet_id']}`",
            f"  - redteam_decision: `{r['redteam_decision']}`",
            f"  - author_input_readiness: `{r['author_input_readiness']}`",
            f"  - closed_loop_disposition: `{r['closed_loop_disposition']}`",
            f"  - recommended_next_stage: `{r['recommended_next_stage']}`",
            "",
            "### Caveat integrity", "", r["caveat_integrity_assessment"], "",
            "### Do-not-say compliance", "", r["do_not_say_compliance_assessment"], "",
            "### Provenance", "", r["provenance_assessment"], "",
            "### Residual risk", "", r["residual_risk_assessment"], "",
        ]
    lines += [
        "## Safety", "",
        "This run does not insert claims or editorial_reviews, does not write source_notes, does not persist packets, does not modify source/claim/editorial statuses, source_registry, raw captures, docs/book, schema, or the daily worker, and does not approve authoring or publication.",
        "", "## Recommendation for Run 22", "",
        "Run 22 should follow the red-team disposition. If ready, build a report-only caveat-only author-draft input package; otherwise keep safe reports only or run the recommended source/context/contradiction step.",
    ]
    return "\n".join(lines) + "\n"


def write_reports(payload: dict[str, Any], output_dir: Path, suffix: str) -> dict[str, str]:
    out_dir = output_dir if output_dir.is_absolute() else ROOT / output_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{payload['run_id']}-packet-redteam-gate-{suffix}" if suffix else f"{payload['run_id']}-packet-redteam-gate"
    json_path = out_dir / f"{stem}.json"
    md_path = out_dir / f"{stem}.md"
    payload["output_paths"] = {"json": rel(json_path), "markdown": rel(md_path)}
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(payload), encoding="utf-8")
    return payload["output_paths"]


def parse_args(argv: list[str]) -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", default=RUN_ID_DEFAULT)
    ap.add_argument("--packet-report", default=DEFAULT_PACKET_REPORT)
    ap.add_argument("--output-dir", default="reports/editorial")
    ap.add_argument("--report-suffix", default="run21")
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
            "selected_packet_count": payload["selected_packet_count"],
            "reviewed_packet_count": payload["reviewed_packet_count"],
            "excluded_packet_count": payload["excluded_packet_count"],
            "redteam_decision_counts": payload["redteam_decision_counts"],
            "author_input_readiness_counts": payload["author_input_readiness_counts"],
            "closed_loop_disposition_counts": payload["closed_loop_disposition_counts"],
            "recommended_next_stage_counts": payload["recommended_next_stage_counts"],
        }, sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
