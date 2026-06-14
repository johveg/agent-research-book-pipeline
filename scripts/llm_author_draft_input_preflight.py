#!/usr/bin/env python3
"""Run 23 report-only author-draft input quality/preflight gate.

Uses the closed_loop_editorial GPT-5.5 profile through the shared strict-JSON
Hermes bridge to preflight Run 22B draft-input packages. This is advisory and
report-only: no authoring, no publication approval, no chapter prose, no DB
persistence, and no protected-file mutation.
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
MODE = "llm_author_draft_input_preflight"
DEFAULT_DRAFT_INPUT_REPORT = f"reports/editorial/{RUN_ID_DEFAULT}-author-draft-input-run22b.json"
REQUIRED_CAVEAT = "Frame narrowly: OpenClaw documentation names Hermes in migration/setup tooling contexts; do not state that Hermes is a runtime dependency or general operating environment without additional sources."

ALLOWED_PREFLIGHT_DECISIONS = {
    "draft_input_canary_ready",
    "safe_reports_only",
    "needs_more_sources",
    "source_context_unclear",
    "exclude_from_authoring",
    "contradiction_review_required",
}
ALLOWED_AUTHOR_CANARY_READINESS = {
    "ready_for_controlled_caveat_only_author_draft_canary",
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
    "run_controlled_caveat_only_author_draft_canary",
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
    "draft_input_id", "draft_input_type", "draft_input_use", "preflight_decision",
    "author_canary_readiness", "closed_loop_disposition",
    "state_machine_consistency_assessment", "caveat_integrity_assessment",
    "do_not_say_compliance_assessment", "prose_containment_assessment",
    "provenance_assessment", "residual_risk_assessment", "required_caveats",
    "do_not_say", "limitations", "residual_risk", "recommended_next_stage",
    "advisory_only", "author_allowed", "publication_approved",
    "eligible_for_claim_insertion", "eligible_for_authoring",
    "eligible_for_publication", "chapter_update_allowed",
]
DISALLOWED_PROSE_KEYS = {
    "publishable_paragraph", "chapter_prose", "final_prose", "draft_paragraph",
    "paragraph", "chapter_ready_prose", "book_text", "citation_resolved_chapter_text",
    "chapter_ready_text", "final_paragraph_prose",
}
REQUIRED_DO_NOT_SAY_SUBSTRINGS = [
    "runtime dependency of OpenClaw",
    "general operating environment for OpenClaw",
    "requires Hermes for web or phone access",
    "generalize beyond migration/setup/import tooling contexts",
    "factual claim without the caveat",
    "chapter prose before later author/red-team gates pass",
]


class AuthorDraftInputPreflightError(RuntimeError):
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
        raise AuthorDraftInputPreflightError(f"missing input {label}: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AuthorDraftInputPreflightError(f"invalid JSON in {label}: {exc}") from exc
    if not isinstance(data, dict):
        raise AuthorDraftInputPreflightError(f"{label} must be a JSON object")
    return data


def compact_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


def connect_readonly(path: Path) -> sqlite3.Connection:
    if not path.exists():
        raise AuthorDraftInputPreflightError(f"missing SQLite DB: {path}")
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


def validate_draft_input_report(report: dict[str, Any]) -> None:
    if report.get("mode") != "build_author_draft_input":
        raise AuthorDraftInputPreflightError("Run 22B draft-input report mode mismatch")
    if report.get("report_only") is not True:
        raise AuthorDraftInputPreflightError("Run 22B draft-input report must be report_only")
    if report.get("llm_used") is not False:
        raise AuthorDraftInputPreflightError("Run 22B draft-input report should be deterministic/no-LLM")
    if not isinstance(report.get("draft_input_packages"), list):
        raise AuthorDraftInputPreflightError("Run 22B draft-input report missing draft_input_packages list")
    safety = report.get("safety_flags")
    if not isinstance(safety, dict):
        raise AuthorDraftInputPreflightError("Run 22B draft-input report missing safety_flags")
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
        "draft_inputs_persisted": False,
    }
    for k, v in expected.items():
        if safety.get(k) is not v:
            raise AuthorDraftInputPreflightError(f"Run 22B draft-input report safety flag invalid: {k}")


def _joined(values: Any) -> str:
    if isinstance(values, list):
        return "\n".join(map(str, values))
    return str(values or "")


def _contains_approval_language(pkg: dict[str, Any]) -> bool:
    text = compact_json(pkg).lower()
    forbidden = [
        "approved for publication",
        "publication approved",
        "approved for authoring",
        "authoring approved",
        "eligible for authoring: true",
        "chapter update allowed",
    ]
    return any(s in text for s in forbidden)


def validate_draft_input_package(pkg: dict[str, Any]) -> None:
    if not isinstance(pkg, dict):
        raise AuthorDraftInputPreflightError("draft-input package must be object")
    did = pkg.get("draft_input_id")
    forbidden = sorted(DISALLOWED_PROSE_KEYS & set(pkg))
    if forbidden:
        raise AuthorDraftInputPreflightError(f"draft input {did} contains forbidden chapter-ready prose field(s): {forbidden}")
    if pkg.get("advisory_only") is not True:
        raise AuthorDraftInputPreflightError(f"draft input {did} safety flag invalid: advisory_only")
    for k in FALSE_FLAGS:
        if pkg.get(k) is not False:
            raise AuthorDraftInputPreflightError(f"draft input {did} safety flag invalid: {k}")
    if pkg.get("raw_capture_dependency") is True or pkg.get("raw_content_stored") is True:
        raise AuthorDraftInputPreflightError(f"draft input {did} has forbidden raw capture dependency")
    caveats = pkg.get("required_caveats")
    if not isinstance(caveats, list) or REQUIRED_CAVEAT not in _joined(caveats):
        raise AuthorDraftInputPreflightError(f"draft input {did} missing required caveat")
    dns = pkg.get("do_not_say")
    if not isinstance(dns, list) or not dns:
        raise AuthorDraftInputPreflightError(f"draft input {did} missing do_not_say guidance")
    joined = _joined(dns)
    for required in REQUIRED_DO_NOT_SAY_SUBSTRINGS:
        if required not in joined:
            raise AuthorDraftInputPreflightError(f"draft input {did} do_not_say missing required guidance: {required}")
    if _contains_approval_language(pkg):
        raise AuthorDraftInputPreflightError(f"draft input {did} contains forbidden approval language")


def select_draft_inputs(report: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    selected: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for pkg in report.get("draft_input_packages", []):
        validate_draft_input_package(pkg)
        if (
            pkg.get("draft_input_type") == "caveat_only_author_draft_input"
            and pkg.get("draft_input_decision") == "caveat_only_draft_input_candidate"
            and pkg.get("draft_input_use") == "caveat_only"
        ):
            selected.append(pkg)
        else:
            cp = dict(pkg)
            cp["excluded_reason"] = "does_not_match_caveat_only_draft_input_selection_rule"
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


def validate_review(review: dict[str, Any], selected_by_id: dict[str, dict[str, Any]]) -> None:
    if not isinstance(review, dict):
        raise ValueError("draft input preflight review must be object")
    for k in REQUIRED_REVIEW_FIELDS:
        if k not in review:
            raise ValueError(f"review missing required field: {k}")
    did = as_str(review.get("draft_input_id"), "draft_input_id")
    if did not in selected_by_id:
        raise ValueError(f"review references unknown selected draft input: {did}")
    for field, allowed in [
        ("preflight_decision", ALLOWED_PREFLIGHT_DECISIONS),
        ("author_canary_readiness", ALLOWED_AUTHOR_CANARY_READINESS),
        ("closed_loop_disposition", ALLOWED_DISPOSITIONS),
        ("recommended_next_stage", ALLOWED_NEXT_STAGES),
    ]:
        value = review.get(field)
        if not isinstance(value, str):
            raise ValueError(f"{field} must be exactly one string enum value")
        if value not in allowed:
            raise ValueError(f"invalid {field}: {value}")
    if review.get("draft_input_type") != "caveat_only_author_draft_input" or review.get("draft_input_use") != "caveat_only":
        raise ValueError("review must preserve caveat-only draft-input type/use")
    for field in [
        "state_machine_consistency_assessment", "caveat_integrity_assessment",
        "do_not_say_compliance_assessment", "prose_containment_assessment",
        "provenance_assessment", "residual_risk_assessment", "residual_risk",
    ]:
        as_str(review.get(field), field)
    for field in ["required_caveats", "do_not_say", "limitations"]:
        as_list(review.get(field), field)
    if review.get("advisory_only") is not True:
        raise ValueError("review advisory_only must be true")
    for k in FALSE_FLAGS:
        if review.get(k) is not False:
            raise ValueError(f"review {k} must be false")
    if REQUIRED_CAVEAT not in _joined(review.get("required_caveats", [])):
        raise ValueError("review missing required caveat")
    dns = _joined(review.get("do_not_say", []))
    for required in REQUIRED_DO_NOT_SAY_SUBSTRINGS:
        if required not in dns:
            raise ValueError(f"review do_not_say missing required guidance: {required}")
    if review.get("preflight_decision") == "draft_input_canary_ready":
        if review.get("author_allowed") is not False or review.get("eligible_for_authoring") is not False or review.get("chapter_update_allowed") is not False:
            raise ValueError("draft_input_canary_ready still requires author_allowed=false, eligible_for_authoring=false, chapter_update_allowed=false")


def make_validator(selected: list[dict[str, Any]]):
    selected_by_id = {str(p["draft_input_id"]): p for p in selected}

    def validator(obj: dict[str, Any]) -> None:
        reviews = obj.get("draft_input_preflight_reviews")
        if not isinstance(reviews, list):
            raise ValueError("LLM JSON must contain draft_input_preflight_reviews list")
        if len(reviews) != len(selected_by_id):
            raise ValueError(f"expected {len(selected_by_id)} preflight review(s), got {len(reviews)}")
        seen = set()
        for review in reviews:
            validate_review(review, selected_by_id)
            did = review["draft_input_id"]
            if did in seen:
                raise ValueError(f"duplicate draft_input_id review: {did}")
            seen.add(did)
    return validator


def build_prompt(selected: list[dict[str, Any]], excluded: list[dict[str, Any]], run_id: str) -> str:
    schema = {
        "draft_input_preflight_reviews": [
            {
                "draft_input_id": "string",
                "draft_input_type": "caveat_only_author_draft_input",
                "draft_input_use": "caveat_only",
                "preflight_decision": "choose exactly one string: draft_input_canary_ready | safe_reports_only | needs_more_sources | source_context_unclear | exclude_from_authoring | contradiction_review_required",
                "author_canary_readiness": "choose exactly one string: ready_for_controlled_caveat_only_author_draft_canary | not_ready_safe_reports_only | not_ready_needs_more_sources | not_ready_source_context_unclear | not_ready_exclude | not_ready_contradiction_review",
                "closed_loop_disposition": "choose exactly one string: caveat_only | safe_reports_only | needs_more_sources | source_context_unclear | exclude_from_pipeline | contradiction_review_required",
                "state_machine_consistency_assessment": "string",
                "caveat_integrity_assessment": "string",
                "do_not_say_compliance_assessment": "string",
                "prose_containment_assessment": "string",
                "provenance_assessment": "string",
                "residual_risk_assessment": "string",
                "required_caveats": [REQUIRED_CAVEAT],
                "do_not_say": [
                    "Do not say Hermes is a runtime dependency of OpenClaw.",
                    "Do not say Hermes is the general operating environment for OpenClaw.",
                    "Do not say OpenClaw requires Hermes for web or phone access.",
                    "Do not generalize beyond migration/setup/import tooling contexts unless additional sources support it.",
                    "Do not use this material as a factual claim without the caveat.",
                    "Do not use this material for chapter prose before later author/red-team gates pass.",
                ],
                "limitations": ["string"],
                "residual_risk": "string",
                "recommended_next_stage": "choose exactly one string: run_controlled_caveat_only_author_draft_canary | keep_safe_reports_only | run_additional_source_collection | run_source_context_review | exclude_from_pipeline | run_contradiction_review",
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
        "task": "Run 23 report-only author-draft input quality/preflight gate",
        "selected_draft_inputs": selected,
        "excluded_draft_inputs": excluded,
        "required_caveat": REQUIRED_CAVEAT,
        "allowed_schema": schema,
        "instructions": [
            "Return JSON only. No markdown, no prose outside JSON.",
            "Choose exactly ONE string enum value for preflight_decision, author_canary_readiness, closed_loop_disposition, and recommended_next_stage; do NOT return arrays or objects for these fields.",
            "Assess state-machine consistency, caveat integrity, do-not-say compliance, prose containment, provenance completeness, and residual risk.",
            "Do not author. Do not create chapter prose. Do not approve authoring. Do not approve publication. Do not allow chapter updates. Do not treat GPT-5.5 advisory reasoning as human/editor approval.",
            "Even if preflight_decision is draft_input_canary_ready, set author_allowed=false, eligible_for_authoring=false, publication_approved=false, eligible_for_publication=false, and chapter_update_allowed=false.",
            "A positive decision means only ready for a later controlled caveat-only author-draft canary, not immediate authoring/publication/chapter update.",
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
        "draft_inputs_persisted": False,
        "author_prose_generated": False,
        "chapter_prose_generated": False,
        "gpt55_advisory_is_human_or_editor_approval": False,
    }


def build_payload(args: argparse.Namespace) -> dict[str, Any]:
    draft_path = resolve(args.draft_input_report)
    report = load_json(draft_path, "Run 22B draft-input report")
    validate_draft_input_report(report)
    try:
        profile = load_model_profile(args.reasoning_profile)
    except ModelProfileError as exc:
        raise AuthorDraftInputPreflightError(f"model_profile_error:{exc}") from exc
    selected, excluded = select_draft_inputs(report)
    if not selected:
        raise AuthorDraftInputPreflightError("no selected draft-input packages for preflight gate")
    db = db_path()
    with connect_readonly(db) as con:
        before_counts = {"source_notes": table_count(con, "source_notes"), "claims": table_count(con, "claims"), "editorial_reviews": table_count(con, "editorial_reviews")}
        before_status = status_snapshots(con)
        prompt = build_prompt(selected, excluded, args.run_id)
        try:
            llm = call_high_reasoning_json(
                prompt,
                schema_name="run23_author_draft_input_preflight",
                validator=make_validator(selected),
                provider=args.provider,
                model=args.model,
                timeout_seconds=args.timeout_seconds,
                reasoning_profile=args.reasoning_profile,
            )
        except HighReasoningError as exc:
            raise AuthorDraftInputPreflightError(str(exc.result.get("error") or exc)) from exc
        after_counts = {"source_notes": table_count(con, "source_notes"), "claims": table_count(con, "claims"), "editorial_reviews": table_count(con, "editorial_reviews")}
        after_status = status_snapshots(con)
    reviews = llm["parsed_json"]["draft_input_preflight_reviews"]
    payload = {
        "run_id": args.run_id,
        "generated_at": utc_now(),
        "mode": MODE,
        "input_paths": {"draft_input_report": rel(draft_path), "sqlite_db": rel(db)},
        "report_only": True,
        "llm_used": bool(llm.get("llm_used")),
        "reasoning_status": llm.get("reasoning_status"),
        "provider": llm.get("provider") or profile["provider"],
        "model": llm.get("model") or profile["model"],
        "bridge": llm.get("bridge") or profile["bridge"],
        "model_profile": llm.get("model_profile") or profile["profile_name"],
        "strict_json_required": bool(llm.get("strict_json_required", profile["strict_json_required"])),
        "weak_local_fallback_refused": bool(llm.get("weak_local_fallback_refused", True)),
        "selected_draft_input_count": len(selected),
        "reviewed_draft_input_count": len(reviews),
        "excluded_draft_input_count": len(excluded),
        "preflight_decision_counts": dict(Counter(r["preflight_decision"] for r in reviews)),
        "author_canary_readiness_counts": dict(Counter(r["author_canary_readiness"] for r in reviews)),
        "closed_loop_disposition_counts": dict(Counter(r["closed_loop_disposition"] for r in reviews)),
        "recommended_next_stage_counts": dict(Counter(r["recommended_next_stage"] for r in reviews)),
        "selected_draft_inputs": selected,
        "excluded_draft_inputs": excluded,
        "draft_input_preflight_reviews": reviews,
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
        raise AuthorDraftInputPreflightError("high reasoning was not used")
    if payload["provider"] != "copilot" or payload["model"] != "gpt-5.5" or payload["bridge"] != "hermes_cli" or payload["model_profile"] != args.reasoning_profile:
        raise AuthorDraftInputPreflightError("unexpected high-reasoning provider/model/bridge/profile")
    if payload["changed_source_notes"] or payload["claims_inserted"] or payload["editorial_reviews_inserted"] or payload["source_status_changed"] or payload["claim_status_changed"] or payload["editorial_status_changed"]:
        raise AuthorDraftInputPreflightError("forbidden DB/status delta detected during report-only preflight gate")
    return payload


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        f"# Run 23 author-draft input preflight — {payload['run_id']}", "",
        "## Summary", "",
        f"- Report-only: `{payload['report_only']}`",
        f"- GPT-5.5 used: `{payload['llm_used']}`",
        f"- Provider/model/bridge/profile: `{payload['provider']}` / `{payload['model']}` / `{payload['bridge']}` / `{payload['model_profile']}`",
        f"- Selected draft inputs: `{payload['selected_draft_input_count']}`",
        f"- Reviewed draft inputs: `{payload['reviewed_draft_input_count']}`",
        f"- Excluded draft inputs: `{payload['excluded_draft_input_count']}`",
        "", "## Preflight decisions", "",
    ]
    for r in payload["draft_input_preflight_reviews"]:
        lines += [
            f"- `{r['draft_input_id']}`",
            f"  - preflight_decision: `{r['preflight_decision']}`",
            f"  - author_canary_readiness: `{r['author_canary_readiness']}`",
            f"  - closed_loop_disposition: `{r['closed_loop_disposition']}`",
            f"  - recommended_next_stage: `{r['recommended_next_stage']}`",
            "",
            "### State-machine consistency", "", r["state_machine_consistency_assessment"], "",
            "### Caveat integrity", "", r["caveat_integrity_assessment"], "",
            "### Do-not-say compliance", "", r["do_not_say_compliance_assessment"], "",
            "### Prose containment", "", r["prose_containment_assessment"], "",
            "### Provenance completeness", "", r["provenance_assessment"], "",
            "### Residual risk", "", r["residual_risk_assessment"], "",
        ]
    lines += [
        "## Safety", "",
        "This run is advisory/report-only. It does not generate author prose or chapter prose, does not persist draft inputs, does not insert claims or editorial_reviews, does not write source_notes, does not modify source/claim/editorial statuses, source_registry, raw captures, docs/book, schema, or the daily worker, and does not approve authoring or publication.",
        "", "Even a `draft_input_canary_ready` result means only readiness for a later controlled caveat-only author-draft canary; it is not immediate authoring approval, publication approval, or chapter-update permission.",
        "", "## Recommendation for Run 24", "",
        "Run 24 should follow the preflight disposition. If ready, run a controlled report-only caveat-only author-draft canary that still writes no docs/book content and keeps all authoring/publication/chapter-update approval flags false unless a later explicit gate is designed and verified.",
    ]
    return "\n".join(lines) + "\n"


def write_reports(payload: dict[str, Any], output_dir: Path, suffix: str) -> dict[str, str]:
    out_dir = output_dir if output_dir.is_absolute() else ROOT / output_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{payload['run_id']}-author-draft-input-preflight-{suffix}" if suffix else f"{payload['run_id']}-author-draft-input-preflight"
    json_path = out_dir / f"{stem}.json"
    md_path = out_dir / f"{stem}.md"
    payload["output_paths"] = {"json": rel(json_path), "markdown": rel(md_path)}
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(payload), encoding="utf-8")
    return payload["output_paths"]


def parse_args(argv: list[str]) -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", default=RUN_ID_DEFAULT)
    ap.add_argument("--draft-input-report", default=DEFAULT_DRAFT_INPUT_REPORT)
    ap.add_argument("--output-dir", default="reports/editorial")
    ap.add_argument("--report-suffix", default="run23")
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
            "selected_draft_input_count": payload["selected_draft_input_count"],
            "reviewed_draft_input_count": payload["reviewed_draft_input_count"],
            "excluded_draft_input_count": payload["excluded_draft_input_count"],
            "preflight_decision_counts": payload["preflight_decision_counts"],
            "author_canary_readiness_counts": payload["author_canary_readiness_counts"],
            "closed_loop_disposition_counts": payload["closed_loop_disposition_counts"],
            "recommended_next_stage_counts": payload["recommended_next_stage_counts"],
        }, sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
