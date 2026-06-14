#!/usr/bin/env python3
"""Run 24 controlled report-only caveat-only author-draft canary.

Uses GPT-5.5 through the closed_loop_editorial profile via the shared strict-JSON
Hermes bridge to create a short, caveat-only draft canary in reports only.
This is not author approval, not publication approval, not claim insertion, not
chapter-ready prose, and never writes to docs/book.
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
MODE = "llm_author_draft_canary"
DEFAULT_PREFLIGHT_REPORT = f"reports/editorial/{RUN_ID_DEFAULT}-author-draft-input-preflight-run23.json"
DEFAULT_DRAFT_INPUT_REPORT = f"reports/editorial/{RUN_ID_DEFAULT}-author-draft-input-run22b.json"
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
ALLOWED_CANARY_TYPES = {"caveat_only_author_draft_canary", "safe_reports_only_draft_canary"}
ALLOWED_CANARY_DECISIONS = {
    "draft_canary_created",
    "safe_reports_only",
    "needs_more_sources",
    "source_context_unclear",
    "exclude_from_authoring",
    "contradiction_review_required",
}
ALLOWED_CANARY_USES = {"caveat_only", "safe_reports_only", "not_for_chapter_update", "not_for_publication"}
REQUIRED_CANARY_FIELDS = [
    "draft_canary_id",
    "draft_input_id",
    "source_packet_id",
    "source_cluster_id",
    "source_note_ids",
    "source_review_ids",
    "source_ids",
    "manifest_item_ids",
    "candidate_source_ids",
    "draft_canary_type",
    "draft_canary_decision",
    "draft_canary_use",
    "draft_canary_text",
    "word_count",
    "required_caveats",
    "do_not_say",
    "caveat_compliance_notes",
    "evidence_limitations",
    "residual_risk",
    "provenance_paths",
    "target_chapter_status",
    "singleton_canary",
    "evidence_narrowness_warning",
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
    (re.compile(r"\bbeyond\s+migration\s+setup\s+import\s+tooling\b|\bbeyond\s+migration/setup/import\s+tooling\b", re.I), "overgeneralization beyond tooling context"),
]


class AuthorDraftCanaryError(RuntimeError):
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
        raise AuthorDraftCanaryError(f"missing input {label}: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AuthorDraftCanaryError(f"invalid JSON in {label}: {exc}") from exc
    if not isinstance(data, dict):
        raise AuthorDraftCanaryError(f"{label} must be JSON object")
    return data


def compact_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


def connect_readonly(path: Path) -> sqlite3.Connection:
    if not path.exists():
        raise AuthorDraftCanaryError(f"missing SQLite DB: {path}")
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


def _as_list(value: Any, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be list")
    return value


def _as_str(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be non-empty string")
    return value


def _require_safe_flags(obj: dict[str, Any], label: str) -> None:
    if obj.get("advisory_only") is not True:
        raise AuthorDraftCanaryError(f"{label} safety flag invalid: advisory_only")
    for k in FALSE_FLAGS:
        if obj.get(k) is not False:
            raise AuthorDraftCanaryError(f"{label} safety flag invalid: {k}")


def _validate_caveat_and_dns(obj: dict[str, Any], label: str) -> None:
    caveats = obj.get("required_caveats")
    if not isinstance(caveats, list) or REQUIRED_CAVEAT not in _joined(caveats):
        raise AuthorDraftCanaryError(f"{label} missing required caveat")
    dns = obj.get("do_not_say")
    if not isinstance(dns, list) or not dns:
        raise AuthorDraftCanaryError(f"{label} missing do_not_say guidance")
    joined = _joined(dns)
    for required in REQUIRED_DO_NOT_SAY_SUBSTRINGS:
        if required not in joined:
            raise AuthorDraftCanaryError(f"{label} do_not_say missing required guidance: {required}")


def validate_reports(preflight: dict[str, Any], draft_input: dict[str, Any]) -> None:
    if preflight.get("mode") != "llm_author_draft_input_preflight":
        raise AuthorDraftCanaryError("Run 23 preflight report mode mismatch")
    if preflight.get("report_only") is not True or preflight.get("llm_used") is not True:
        raise AuthorDraftCanaryError("Run 23 preflight report must be report_only with GPT-5.5 used")
    if preflight.get("provider") != "copilot" or preflight.get("model") != "gpt-5.5" or preflight.get("bridge") != "hermes_cli" or preflight.get("model_profile") != "closed_loop_editorial":
        raise AuthorDraftCanaryError("Run 23 preflight report has unexpected model/profile metadata")
    if not isinstance(preflight.get("draft_input_preflight_reviews"), list):
        raise AuthorDraftCanaryError("Run 23 preflight report missing draft_input_preflight_reviews list")
    if draft_input.get("mode") != "build_author_draft_input":
        raise AuthorDraftCanaryError("Run 22B draft-input report mode mismatch")
    if draft_input.get("report_only") is not True:
        raise AuthorDraftCanaryError("Run 22B draft-input report must be report_only")
    if not isinstance(draft_input.get("draft_input_packages"), list):
        raise AuthorDraftCanaryError("Run 22B draft-input report missing draft_input_packages list")


def validate_draft_input_package(pkg: dict[str, Any]) -> None:
    if not isinstance(pkg, dict):
        raise AuthorDraftCanaryError("draft input package must be object")
    did = pkg.get("draft_input_id", "unknown")
    _require_safe_flags(pkg, f"draft input {did}")
    if pkg.get("raw_capture_dependency") is True or pkg.get("raw_content_stored") is True:
        raise AuthorDraftCanaryError(f"draft input {did} has forbidden raw capture dependency")
    if pkg.get("draft_input_type") != "caveat_only_author_draft_input":
        raise AuthorDraftCanaryError(f"draft input {did} type mismatch")
    if pkg.get("draft_input_decision") != "caveat_only_draft_input_candidate":
        raise AuthorDraftCanaryError(f"draft input {did} decision mismatch")
    if pkg.get("draft_input_use") != "caveat_only":
        raise AuthorDraftCanaryError(f"draft input {did} use mismatch")
    if pkg.get("target_chapter_status") != "not_assigned":
        raise AuthorDraftCanaryError(f"draft input {did} target_chapter_status must be not_assigned")
    _validate_caveat_and_dns(pkg, f"draft input {did}")


def validate_preflight_review(review: dict[str, Any]) -> None:
    if not isinstance(review, dict):
        raise AuthorDraftCanaryError("preflight review must be object")
    did = review.get("draft_input_id", "unknown")
    _require_safe_flags(review, f"preflight review {did}")
    if review.get("preflight_decision") != "draft_input_canary_ready":
        raise AuthorDraftCanaryError(f"preflight review {did} not canary-ready")
    if review.get("author_canary_readiness") != "ready_for_controlled_caveat_only_author_draft_canary":
        raise AuthorDraftCanaryError(f"preflight review {did} not ready for controlled canary")
    if review.get("closed_loop_disposition") != "caveat_only":
        raise AuthorDraftCanaryError(f"preflight review {did} disposition not caveat_only")
    if review.get("recommended_next_stage") != "run_controlled_caveat_only_author_draft_canary":
        raise AuthorDraftCanaryError(f"preflight review {did} next stage mismatch")
    _validate_caveat_and_dns(review, f"preflight review {did}")


def select_draft_inputs(preflight: dict[str, Any], draft_input: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    packages_by_id = {str(p.get("draft_input_id")): p for p in draft_input.get("draft_input_packages", []) if isinstance(p, dict)}
    selected: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for review in preflight.get("draft_input_preflight_reviews", []):
        validate_preflight_review(review)
        did = str(review.get("draft_input_id"))
        pkg = packages_by_id.get(did)
        if not pkg:
            raise AuthorDraftCanaryError(f"preflight review references missing Run 22B draft input: {did}")
        validate_draft_input_package(pkg)
        if (
            review.get("preflight_decision") == "draft_input_canary_ready"
            and review.get("author_canary_readiness") == "ready_for_controlled_caveat_only_author_draft_canary"
            and review.get("closed_loop_disposition") == "caveat_only"
            and review.get("recommended_next_stage") == "run_controlled_caveat_only_author_draft_canary"
        ):
            merged = dict(pkg)
            merged["run23_preflight_review"] = review
            selected.append(merged)
        else:
            cp = dict(review)
            cp["excluded_reason"] = "does_not_match_run24_selection_rule"
            excluded.append(cp)
    return selected, excluded


def validate_canary_text(text: str) -> int:
    if "\n" in text.strip():
        raise ValueError("draft_canary_text must be one paragraph")
    if any(line.strip().startswith(('#', '-', '*')) for line in text.splitlines()):
        raise ValueError("draft_canary_text must not contain headings or bullets")
    words = re.findall(r"\b\S+\b", text)
    if len(words) > 90:
        raise ValueError("draft_canary_text exceeds 90 words")
    if REQUIRED_CAVEAT not in text:
        raise ValueError("draft_canary_text must preserve required caveat exactly")
    lower = text.lower()
    if "secret" in lower or "api key" in lower or "oauth" in lower or "cookie" in lower:
        raise ValueError("draft_canary_text appears to include secret/private-data language")
    for pattern, reason in BAD_TEXT_PATTERNS:
        if pattern.search(text):
            raise ValueError(f"draft_canary_text violates do-not-say: {reason}")
    return len(words)


def validate_canary(canary: dict[str, Any], selected_by_id: dict[str, dict[str, Any]]) -> None:
    if not isinstance(canary, dict):
        raise ValueError("draft canary must be object")
    for field in REQUIRED_CANARY_FIELDS:
        if field not in canary:
            raise ValueError(f"draft canary missing required field: {field}")
    did = _as_str(canary.get("draft_input_id"), "draft_input_id")
    if did not in selected_by_id:
        raise ValueError(f"draft canary references unknown selected draft input: {did}")
    if canary.get("draft_canary_type") not in ALLOWED_CANARY_TYPES:
        raise ValueError(f"invalid draft_canary_type: {canary.get('draft_canary_type')}")
    if canary.get("draft_canary_decision") not in ALLOWED_CANARY_DECISIONS:
        raise ValueError(f"invalid draft_canary_decision: {canary.get('draft_canary_decision')}")
    if canary.get("draft_canary_use") not in ALLOWED_CANARY_USES:
        raise ValueError(f"invalid draft_canary_use: {canary.get('draft_canary_use')}")
    if canary.get("advisory_only") is not True or canary.get("draft_canary_only") is not True:
        raise ValueError("draft canary advisory_only and draft_canary_only must be true")
    for k in FALSE_FLAGS:
        if canary.get(k) is not False:
            raise ValueError(f"draft canary {k} must be false")
    if canary.get("singleton_canary") is not True:
        raise ValueError("singleton_canary must be true for Run 24 canary")
    for field in ["source_note_ids", "source_review_ids", "source_ids", "manifest_item_ids", "candidate_source_ids", "required_caveats", "do_not_say", "evidence_limitations", "provenance_paths"]:
        _as_list(canary.get(field), field)
    for field in ["draft_canary_id", "source_packet_id", "source_cluster_id", "draft_canary_text", "caveat_compliance_notes", "residual_risk", "target_chapter_status", "evidence_narrowness_warning"]:
        _as_str(canary.get(field), field)
    if canary.get("target_chapter_status") != "not_assigned":
        raise ValueError("target_chapter_status must remain not_assigned")
    if REQUIRED_CAVEAT not in _joined(canary.get("required_caveats")):
        raise ValueError("draft canary missing required caveat")
    dns = _joined(canary.get("do_not_say"))
    for required in REQUIRED_DO_NOT_SAY_SUBSTRINGS:
        if required not in dns:
            raise ValueError(f"draft canary do_not_say missing required guidance: {required}")
    computed = validate_canary_text(canary["draft_canary_text"])
    if canary.get("word_count") != computed:
        raise ValueError(f"draft canary word_count mismatch: expected {computed}, got {canary.get('word_count')}")
    source = selected_by_id[did]
    for field in ["source_packet_id", "source_cluster_id"]:
        if str(canary.get(field)) != str(source.get(field)):
            raise ValueError(f"draft canary {field} does not match selected input")


def make_validator(selected: list[dict[str, Any]]):
    selected_by_id = {str(p["draft_input_id"]): p for p in selected}

    def validator(obj: dict[str, Any]) -> None:
        canaries = obj.get("draft_canaries")
        if not isinstance(canaries, list):
            raise ValueError("LLM JSON must contain draft_canaries list")
        if len(canaries) != len(selected_by_id):
            raise ValueError(f"expected {len(selected_by_id)} draft canary item(s), got {len(canaries)}")
        seen = set()
        for canary in canaries:
            validate_canary(canary, selected_by_id)
            did = canary["draft_input_id"]
            if did in seen:
                raise ValueError(f"duplicate draft_input_id canary: {did}")
            seen.add(did)
    return validator


def build_prompt(selected: list[dict[str, Any]], excluded: list[dict[str, Any]], run_id: str) -> str:
    schema = {
        "draft_canaries": [
            {
                "draft_canary_id": "string",
                "draft_input_id": "string from selected_draft_inputs",
                "source_packet_id": "string from selected_draft_inputs",
                "source_cluster_id": "string from selected_draft_inputs",
                "source_note_ids": ["strings from selected_draft_inputs"],
                "source_review_ids": ["strings from selected_draft_inputs"],
                "source_ids": ["strings from selected_draft_inputs"],
                "manifest_item_ids": ["strings from selected_draft_inputs"],
                "candidate_source_ids": ["strings from selected_draft_inputs"],
                "draft_canary_type": "choose exactly one string: caveat_only_author_draft_canary | safe_reports_only_draft_canary",
                "draft_canary_decision": "choose exactly one string: draft_canary_created | safe_reports_only | needs_more_sources | source_context_unclear | exclude_from_authoring | contradiction_review_required",
                "draft_canary_use": "choose exactly one string: caveat_only | safe_reports_only | not_for_chapter_update | not_for_publication",
                "draft_canary_text": "one short paragraph string, <=90 words, no headings, no bullets, preserve required caveat exactly",
                "word_count": "integer exact count of words in draft_canary_text",
                "required_caveats": [REQUIRED_CAVEAT],
                "do_not_say": [
                    "Do not say Hermes is a runtime dependency of OpenClaw.",
                    "Do not say Hermes is the general operating environment for OpenClaw.",
                    "Do not say OpenClaw requires Hermes for web or phone access.",
                    "Do not generalize beyond migration/setup/import tooling contexts unless additional sources support it.",
                    "Do not use this material as a factual claim without the caveat.",
                    "Do not use this material for chapter prose before later author/red-team gates pass.",
                ],
                "caveat_compliance_notes": "single non-empty string, not a list",
                "evidence_limitations": ["strings"],
                "residual_risk": "single non-empty string, not a list",
                "provenance_paths": ["strings or path objects copied from selected_draft_inputs"],
                "target_chapter_status": "not_assigned",
                "singleton_canary": True,
                "evidence_narrowness_warning": "single non-empty string, not a list",
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
        "task": "Run 24 controlled report-only caveat-only author-draft canary",
        "selected_draft_inputs": selected,
        "excluded_draft_inputs": excluded,
        "required_caveat": REQUIRED_CAVEAT,
        "allowed_draft_canary_type_values": sorted(ALLOWED_CANARY_TYPES),
        "allowed_draft_canary_decision_values": sorted(ALLOWED_CANARY_DECISIONS),
        "allowed_draft_canary_use_values": sorted(ALLOWED_CANARY_USES),
        "required_schema": schema,
        "instructions": [
            "Return JSON only. No markdown, no prose outside JSON.",
            "Create at most one short controlled draft_canary_text per selected input, only inside the JSON report object.",
            "draft_canary_text must be one paragraph, no headings, no bullets, and at most 90 words.",
            "draft_canary_text must preserve the required caveat exactly or more conservatively.",
            "Do not say Hermes is a runtime dependency of OpenClaw.",
            "Do not say Hermes is the general operating environment for OpenClaw.",
            "Do not say OpenClaw requires Hermes for web or phone access.",
            "Do not generalize beyond migration/setup/import tooling contexts unless additional sources support it.",
            "Do not imply chapter readiness, publication approval, claim insertion, or authoring approval.",
            "Do not include raw capture/source text, secrets, private data, tokens, cookies, OAuth material, or API keys.",
            "Even when draft_canary_decision=draft_canary_created, set advisory_only=true, draft_canary_only=true, author_allowed=false, publication_approved=false, eligible_for_claim_insertion=false, eligible_for_authoring=false, eligible_for_publication=false, and chapter_update_allowed=false.",
            "Choose exactly ONE string enum value for draft_canary_type, draft_canary_decision, and draft_canary_use; do NOT return arrays or objects for these enum fields.",
            "If the material is not safe for a caveat-only draft canary, use safe_reports_only, needs_more_sources, source_context_unclear, exclude_from_authoring, or contradiction_review_required rather than forcing text.",
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
    preflight_path = resolve(args.preflight_report)
    draft_path = resolve(args.draft_input_report)
    preflight = load_json(preflight_path, "Run 23 preflight report")
    draft_input = load_json(draft_path, "Run 22B draft-input report")
    validate_reports(preflight, draft_input)
    try:
        profile = load_model_profile(args.reasoning_profile)
    except ModelProfileError as exc:
        raise AuthorDraftCanaryError(f"model_profile_error:{exc}") from exc
    selected, excluded = select_draft_inputs(preflight, draft_input)
    if not selected:
        raise AuthorDraftCanaryError("no selected canary-ready draft inputs")
    db = db_path()
    with connect_readonly(db) as con:
        before_counts = {"source_notes": table_count(con, "source_notes"), "claims": table_count(con, "claims"), "editorial_reviews": table_count(con, "editorial_reviews")}
        before_status = status_snapshots(con)
        prompt = build_prompt(selected, excluded, args.run_id)
        try:
            llm = call_high_reasoning_json(
                prompt,
                schema_name="run24_author_draft_canary",
                validator=make_validator(selected),
                provider=args.provider,
                model=args.model,
                timeout_seconds=args.timeout_seconds,
                reasoning_profile=args.reasoning_profile,
            )
        except HighReasoningError as exc:
            raise AuthorDraftCanaryError(str(exc.result.get("error") or exc)) from exc
        after_counts = {"source_notes": table_count(con, "source_notes"), "claims": table_count(con, "claims"), "editorial_reviews": table_count(con, "editorial_reviews")}
        after_status = status_snapshots(con)
    canaries = llm["parsed_json"]["draft_canaries"]
    payload = {
        "run_id": args.run_id,
        "generated_at": utc_now(),
        "mode": MODE,
        "input_paths": {"preflight_report": rel(preflight_path), "draft_input_report": rel(draft_path), "sqlite_db": rel(db)},
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
        "draft_canary_count": len(canaries),
        "excluded_draft_input_count": len(excluded),
        "draft_canary_type_counts": dict(Counter(c["draft_canary_type"] for c in canaries)),
        "draft_canary_decision_counts": dict(Counter(c["draft_canary_decision"] for c in canaries)),
        "draft_canary_use_counts": dict(Counter(c["draft_canary_use"] for c in canaries)),
        "target_chapter_status_counts": dict(Counter(c["target_chapter_status"] for c in canaries)),
        "selected_draft_inputs": selected,
        "excluded_draft_inputs": excluded,
        "draft_canaries": canaries,
        "failed_draft_canary_checks": [],
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
        raise AuthorDraftCanaryError("high reasoning was not used")
    if payload["provider"] != "copilot" or payload["model"] != "gpt-5.5" or payload["bridge"] != "hermes_cli" or payload["model_profile"] != args.reasoning_profile:
        raise AuthorDraftCanaryError("unexpected high-reasoning provider/model/bridge/profile")
    if payload["changed_source_notes"] or payload["claims_inserted"] or payload["editorial_reviews_inserted"] or payload["source_status_changed"] or payload["claim_status_changed"] or payload["editorial_status_changed"]:
        raise AuthorDraftCanaryError("forbidden DB/status delta detected during report-only canary")
    return payload


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        f"# Run 24 author-draft canary — {payload['run_id']}", "",
        "## Summary", "",
        f"- Report-only: `{payload['report_only']}`",
        f"- GPT-5.5 used: `{payload['llm_used']}`",
        f"- Provider/model/bridge/profile: `{payload['provider']}` / `{payload['model']}` / `{payload['bridge']}` / `{payload['model_profile']}`",
        f"- Selected draft inputs: `{payload['selected_draft_input_count']}`",
        f"- Draft canaries: `{payload['draft_canary_count']}`",
        f"- Excluded draft inputs: `{payload['excluded_draft_input_count']}`",
        "", "## Draft canary", "",
    ]
    for c in payload["draft_canaries"]:
        lines += [
            f"- draft_canary_id: `{c['draft_canary_id']}`",
            f"- draft_input_id: `{c['draft_input_id']}`",
            f"- draft_canary_type: `{c['draft_canary_type']}`",
            f"- draft_canary_decision: `{c['draft_canary_decision']}`",
            f"- draft_canary_use: `{c['draft_canary_use']}`",
            f"- word_count: `{c['word_count']}`",
            "", "### Draft canary text", "",
            f"> {c['draft_canary_text']}", "",
            "### Caveat-only constraints", "",
            "The canary is marked `draft_canary_only`, preserves the required caveat, and remains non-publication-approved. It is not a factual claim and is not final prose.", "",
            "### Do-not-say compliance", "",
            c["caveat_compliance_notes"], "",
            "### Evidence limitations and residual risk", "",
            "- " + "\n- ".join(map(str, c["evidence_limitations"])), "",
            c["residual_risk"], "",
        ]
    lines += [
        "## Why this is not claim insertion", "",
        "No claims table rows were inserted, `eligible_for_claim_insertion=false`, and the canary is advisory/report-only.", "",
        "## Why this is not publication approval", "",
        "`publication_approved=false`, `eligible_for_publication=false`, and GPT-5.5 advisory output is not human/editor approval.", "",
        "## Why this is not a chapter update", "",
        "No docs/book files are written; `chapter_update_allowed=false`, target chapter remains `not_assigned`, and the text exists only in this report artifact.", "",
        "## Recommendation for Run 25", "",
        "Run 25 should be a report-only author-draft canary red-team/containment review before any broader authoring, claim insertion, publication gate, or chapter-update candidate is considered.",
    ]
    return "\n".join(lines) + "\n"


def write_reports(payload: dict[str, Any], output_dir: Path, suffix: str) -> dict[str, str]:
    out_dir = output_dir if output_dir.is_absolute() else ROOT / output_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{payload['run_id']}-author-draft-canary-{suffix}" if suffix else f"{payload['run_id']}-author-draft-canary"
    json_path = out_dir / f"{stem}.json"
    md_path = out_dir / f"{stem}.md"
    payload["output_paths"] = {"json": rel(json_path), "markdown": rel(md_path)}
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(payload), encoding="utf-8")
    return payload["output_paths"]


def parse_args(argv: list[str]) -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", default=RUN_ID_DEFAULT)
    ap.add_argument("--preflight-report", default=DEFAULT_PREFLIGHT_REPORT)
    ap.add_argument("--draft-input-report", default=DEFAULT_DRAFT_INPUT_REPORT)
    ap.add_argument("--output-dir", default="reports/editorial")
    ap.add_argument("--report-suffix", default="run24")
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
            "draft_canary_count": payload["draft_canary_count"],
            "excluded_draft_input_count": payload["excluded_draft_input_count"],
            "draft_canary_type_counts": payload["draft_canary_type_counts"],
            "draft_canary_decision_counts": payload["draft_canary_decision_counts"],
            "draft_canary_use_counts": payload["draft_canary_use_counts"],
            "target_chapter_status_counts": payload["target_chapter_status_counts"],
        }, sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
