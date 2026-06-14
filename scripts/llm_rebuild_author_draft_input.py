#!/usr/bin/env python3
"""Run 26 report-only enriched caveat-only author-draft input rebuild.

Consumes Run 25 safe-but-not-useful canary red-team output plus Run 24/23/22B
lineage and asks GPT-5.5, through the closed_loop_editorial profile, to rebuild
a richer author-draft input package. This is input rebuilding only: no authoring,
no draft prose, no claims/editorial_reviews/source_notes writes, no docs/book
mutation, no approval, and no chapter-update permission.
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
MODE = "llm_rebuild_author_draft_input"
DEFAULT_RUN25 = f"reports/editorial/{RUN_ID_DEFAULT}-author-draft-canary-redteam-run25.json"
DEFAULT_RUN24 = f"reports/editorial/{RUN_ID_DEFAULT}-author-draft-canary-run24.json"
DEFAULT_RUN23 = f"reports/editorial/{RUN_ID_DEFAULT}-author-draft-input-preflight-run23.json"
DEFAULT_RUN22B = f"reports/editorial/{RUN_ID_DEFAULT}-author-draft-input-run22b.json"
REQUIRED_CAVEAT = "Frame narrowly: OpenClaw documentation names Hermes in migration/setup tooling contexts; do not state that Hermes is a runtime dependency or general operating environment without additional sources."
REQUIRED_DO_NOT_SAY = [
    "Do not say Hermes is a runtime dependency of OpenClaw.",
    "Do not say Hermes is the general operating environment for OpenClaw.",
    "Do not say OpenClaw requires Hermes for web or phone access.",
    "Do not generalize beyond migration/setup/import tooling contexts unless additional sources support it.",
    "Do not use this material as a factual claim without the caveat.",
    "Do not use this material for chapter prose before later author/red-team gates pass.",
]
DO_NOT_SAY_EQUIVALENTS = {
    "Do not use this packet as a factual claim without the caveat.": "Do not use this material as a factual claim without the caveat.",
}
FALSE_FLAGS = [
    "author_allowed",
    "publication_approved",
    "eligible_for_claim_insertion",
    "eligible_for_authoring",
    "eligible_for_publication",
    "chapter_update_allowed",
]
CHAPTER_READY_FIELDS = {
    "chapter_prose",
    "publishable_paragraph",
    "draft_paragraph",
    "final_prose",
    "book_text",
    "chapter_ready_prose",
    "citation_resolved_chapter_text",
}
ALLOWED_TYPES = {
    "enriched_caveat_only_author_draft_input",
    "safe_reports_only_author_input",
    "needs_more_sources_author_input",
    "excluded_author_input",
}
ALLOWED_DECISIONS = {
    "rebuilt_draft_input_candidate",
    "safe_reports_only",
    "needs_more_sources",
    "source_context_unclear",
    "exclude_from_authoring",
    "contradiction_review_required",
}
ALLOWED_USES = {
    "caveat_only",
    "context_only",
    "safe_reports_only",
    "not_for_authoring",
    "not_for_publication",
}
ALLOWED_TARGET_STATUS = {"not_assigned", "suggested_only"}
REQUIRED_PACKAGE_FIELDS = [
    "rebuilt_input_id",
    "prior_draft_input_id",
    "prior_draft_canary_id",
    "source_packet_id",
    "source_cluster_id",
    "source_note_ids",
    "source_review_ids",
    "source_ids",
    "manifest_item_ids",
    "candidate_source_ids",
    "rebuilt_input_type",
    "rebuilt_input_decision",
    "rebuilt_input_use",
    "title",
    "authoring_purpose",
    "evidence_bound_factual_atoms",
    "allowed_author_scope",
    "forbidden_author_scope",
    "narrative_function_suggestions",
    "placement_suggestions",
    "target_chapter_candidates",
    "target_chapter_status",
    "required_caveats",
    "do_not_say",
    "evidence_summary",
    "evidence_limitations",
    "residual_risk",
    "confidence",
    "citation_requirements",
    "later_canary_instruction_seed",
    "usefulness_improvement_notes",
    "why_prior_canary_was_not_useful",
    "provenance_paths",
    "singleton_input",
    "evidence_narrowness_warning",
    "advisory_only",
    "author_allowed",
    "publication_approved",
    "eligible_for_claim_insertion",
    "eligible_for_authoring",
    "eligible_for_publication",
    "chapter_update_allowed",
]
FORBIDDEN_TEXT_PATTERNS = [
    (re.compile(r"\bHermes\s+is\s+a\s+runtime\s+dependency\s+of\s+OpenClaw\b", re.I), "runtime dependency claim"),
    (re.compile(r"\bHermes\s+is\s+the\s+general\s+operating\s+environment\s+for\s+OpenClaw\b", re.I), "general operating environment claim"),
    (re.compile(r"\bOpenClaw\s+requires\s+Hermes\s+for\s+web\s+or\s+phone\s+access\b", re.I), "web/phone access requirement claim"),
    (re.compile(r"\bapproved\s+for\s+publication\b|\bpublication\s+approved\b|\bauthoring\s+approved\b|\bapproved\s+for\s+authoring\b", re.I), "approval language"),
    (re.compile(r"\bchapter[- ]ready\b|\bpublishable\s+paragraph\b|\bfinal\s+paragraph\b|\bfinal\s+prose\b", re.I), "chapter-ready/final prose language"),
]


class RebuildInputError(RuntimeError):
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


def load_json(path: str | Path, label: str) -> dict[str, Any]:
    p = resolve(path)
    if not p.exists():
        raise RebuildInputError(f"missing input {label}: {p}")
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RebuildInputError(f"invalid JSON in {label}: {exc}") from exc
    if not isinstance(data, dict):
        raise RebuildInputError(f"{label} must be JSON object")
    return data


def compact_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


def connect_readonly(path: Path) -> sqlite3.Connection:
    if not path.exists():
        raise RebuildInputError(f"missing SQLite DB: {path}")
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


def joined(value: Any) -> str:
    if isinstance(value, list):
        return "\n".join(map(str, value))
    return str(value or "")


def as_str(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be non-empty string")
    return value


def as_list(value: Any, field: str) -> list[Any]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{field} must be non-empty list")
    return value


def require_false_flags(obj: dict[str, Any], label: str) -> None:
    if obj.get("advisory_only") is not True:
        raise RebuildInputError(f"{label} safety flag invalid: advisory_only")
    for flag in FALSE_FLAGS:
        if obj.get(flag) is not False:
            raise RebuildInputError(f"{label} safety flag invalid: {flag}")


def normalized_do_not_say(value: Any) -> list[str]:
    if isinstance(value, list):
        raw = [str(item) for item in value]
    else:
        raw = [str(value or "")]
    return [DO_NOT_SAY_EQUIVALENTS.get(item, item) for item in raw]


def require_caveat_dns(obj: dict[str, Any], label: str) -> None:
    if REQUIRED_CAVEAT not in joined(obj.get("required_caveats")):
        raise RebuildInputError(f"{label} missing required caveat")
    dns = joined(normalized_do_not_say(obj.get("do_not_say")))
    if not dns:
        raise RebuildInputError(f"{label} missing do_not_say guidance")
    for item in REQUIRED_DO_NOT_SAY:
        if item not in dns:
            raise RebuildInputError(f"{label} do_not_say missing: {item}")


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


def iter_strings(obj: Any):
    if isinstance(obj, dict):
        for value in obj.values():
            yield from iter_strings(value)
    elif isinstance(obj, list):
        for value in obj:
            yield from iter_strings(value)
    elif isinstance(obj, str):
        yield obj


def is_negative_guardrail_text(text: str) -> bool:
    low = text.strip().lower()
    return (
        low.startswith("do not ")
        or low.startswith("no ")
        or "does not establish" in low
        or "does not support" in low
        or "do not cite as" in low
        or "do not write final prose" in low
        or "not prose" in low
        or "not final prose" in low
        or "not chapter-ready" in low
        or "forbidden" in low
    )


def validate_no_prose_or_approval(obj: dict[str, Any], label: str) -> None:
    if has_chapter_ready_field(obj):
        raise ValueError(f"{label} contains chapter-ready prose field")
    for text in iter_strings(obj):
        if "```" in text:
            raise ValueError(f"{label} contains formatted prose block")
        if is_negative_guardrail_text(text):
            continue
        for pattern, reason in FORBIDDEN_TEXT_PATTERNS:
            if pattern.search(text):
                raise ValueError(f"{label} contains forbidden {reason}")


def validate_input_reports(run25: dict[str, Any], run24: dict[str, Any], run23: dict[str, Any], run22b: dict[str, Any]) -> None:
    if run25.get("mode") != "llm_author_draft_canary_redteam" or run25.get("report_only") is not True:
        raise RebuildInputError("Run 25 report mode mismatch")
    if run25.get("llm_used") is not True or run25.get("provider") != "copilot" or run25.get("model") != "gpt-5.5" or run25.get("bridge") != "hermes_cli" or run25.get("model_profile") != "closed_loop_editorial":
        raise RebuildInputError("Run 25 report must use GPT-5.5 closed_loop_editorial")
    if not isinstance(run25.get("draft_canary_redteam_reviews"), list):
        raise RebuildInputError("Run 25 report missing draft_canary_redteam_reviews")
    if run24.get("mode") != "llm_author_draft_canary" or run24.get("report_only") is not True:
        raise RebuildInputError("Run 24 canary report mode mismatch")
    if not isinstance(run24.get("draft_canaries"), list):
        raise RebuildInputError("Run 24 report missing draft_canaries")
    if run23.get("mode") != "llm_author_draft_input_preflight" or run23.get("report_only") is not True:
        raise RebuildInputError("Run 23 preflight report mode mismatch")
    if run22b.get("mode") != "build_author_draft_input" or run22b.get("report_only") is not True:
        raise RebuildInputError("Run 22B draft-input report mode mismatch")
    if not isinstance(run22b.get("draft_input_packages"), list):
        raise RebuildInputError("Run 22B report missing draft_input_packages")


def index_by(items: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    return {str(item.get(key)): item for item in items if isinstance(item, dict) and item.get(key)}


def validate_run24_canary(canary: dict[str, Any]) -> None:
    require_false_flags(canary, f"Run 24 canary {canary.get('draft_canary_id')}")
    if canary.get("draft_canary_only") is not True:
        raise RebuildInputError("Run 24 canary draft_canary_only invalid")
    if canary.get("draft_canary_decision") != "draft_canary_created" or canary.get("draft_canary_use") != "caveat_only":
        raise RebuildInputError("Run 24 canary decision/use mismatch")
    if canary.get("word_count", 999) > 90:
        raise RebuildInputError("Run 24 canary exceeds 90 words")
    require_caveat_dns(canary, "Run 24 canary")


def validate_run22b_package(pkg: dict[str, Any]) -> None:
    require_false_flags(pkg, f"Run 22B package {pkg.get('draft_input_id')}")
    if pkg.get("draft_input_type") != "caveat_only_author_draft_input" or pkg.get("draft_input_decision") != "caveat_only_draft_input_candidate" or pkg.get("draft_input_use") != "caveat_only":
        raise RebuildInputError("Run 22B package type/decision/use mismatch")
    require_caveat_dns(pkg, "Run 22B package")
    if has_chapter_ready_field(pkg):
        raise RebuildInputError("Run 22B package contains chapter-ready prose field")


def select_redteams(run25: dict[str, Any], run24: dict[str, Any], run22b: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    canary_by_id = index_by(run24.get("draft_canaries", []), "draft_canary_id")
    input_by_id = index_by(run22b.get("draft_input_packages", []), "draft_input_id")
    selected: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for review in run25.get("draft_canary_redteam_reviews", []):
        if not isinstance(review, dict):
            raise RebuildInputError("Run 25 review must be object")
        rid = review.get("draft_canary_id", "unknown")
        require_false_flags(review, f"Run 25 redteam {rid}")
        if review.get("draft_canary_only") is not True:
            raise RebuildInputError("Run 25 review draft_canary_only invalid")
        require_caveat_dns(review, f"Run 25 redteam {rid}")
        canary = canary_by_id.get(str(rid))
        if not canary:
            raise RebuildInputError(f"Run 25 review missing Run 24 canary linkage: {rid}")
        validate_run24_canary(canary)
        draft_input_id = str(review.get("draft_input_id"))
        pkg = input_by_id.get(draft_input_id)
        if not pkg:
            raise RebuildInputError(f"Run 25 review missing Run 22B draft-input linkage: {draft_input_id}")
        validate_run22b_package(pkg)
        if (
            review.get("redteam_decision") == "safe_but_not_useful"
            and review.get("canary_usefulness") == "not_useful_restates_caveat_only"
            and review.get("closed_loop_disposition") == "needs_better_authoring_input"
            and review.get("recommended_next_stage") == "rebuild_author_draft_input"
        ):
            enriched = dict(review)
            enriched["run24_draft_canary"] = canary
            enriched["run22b_draft_input_package"] = pkg
            selected.append(enriched)
        else:
            cp = dict(review)
            cp["excluded_reason"] = "does_not_match_rebuild_selection_rule"
            excluded.append(cp)
    if not selected:
        raise RebuildInputError("no selected canary redteam results for rebuild")
    return selected, excluded


def validate_rebuilt_package(pkg: dict[str, Any], selected_by_input: dict[str, dict[str, Any]]) -> None:
    if not isinstance(pkg, dict):
        raise ValueError("rebuilt input must be object")
    for field in REQUIRED_PACKAGE_FIELDS:
        if field not in pkg:
            raise ValueError(f"rebuilt input missing required field: {field}")
    prior_id = as_str(pkg.get("prior_draft_input_id"), "prior_draft_input_id")
    if prior_id not in selected_by_input:
        raise ValueError(f"rebuilt input references unknown prior_draft_input_id: {prior_id}")
    selected = selected_by_input[prior_id]
    if pkg.get("prior_draft_canary_id") != selected.get("draft_canary_id"):
        raise ValueError("prior_draft_canary_id mismatch")
    for field, allowed in [
        ("rebuilt_input_type", ALLOWED_TYPES),
        ("rebuilt_input_decision", ALLOWED_DECISIONS),
        ("rebuilt_input_use", ALLOWED_USES),
        ("target_chapter_status", ALLOWED_TARGET_STATUS),
    ]:
        value = pkg.get(field)
        if not isinstance(value, str):
            raise ValueError(f"{field} must be exactly one string enum value")
        if value not in allowed:
            raise ValueError(f"invalid {field}: {value}")
    for field in ["title", "authoring_purpose", "evidence_summary", "residual_risk", "confidence", "later_canary_instruction_seed", "usefulness_improvement_notes", "why_prior_canary_was_not_useful", "evidence_narrowness_warning"]:
        as_str(pkg.get(field), field)
    for field in ["source_note_ids", "source_review_ids", "source_ids", "manifest_item_ids", "candidate_source_ids", "evidence_bound_factual_atoms", "allowed_author_scope", "forbidden_author_scope", "narrative_function_suggestions", "placement_suggestions", "target_chapter_candidates", "required_caveats", "do_not_say", "evidence_limitations", "citation_requirements", "provenance_paths"]:
        values = as_list(pkg.get(field), field)
        if field in {"evidence_bound_factual_atoms", "narrative_function_suggestions", "placement_suggestions"}:
            for item in values:
                if isinstance(item, str) and len(item.split()) > 28:
                    raise ValueError(f"{field} items must be short atomic notes, not prose")
    if pkg.get("singleton_input") is not True:
        raise ValueError("singleton_input must be true")
    if pkg.get("advisory_only") is not True:
        raise ValueError("advisory_only must be true")
    for flag in FALSE_FLAGS:
        if pkg.get(flag) is not False:
            raise ValueError(f"{flag} must be false")
    if REQUIRED_CAVEAT not in joined(pkg.get("required_caveats")):
        raise ValueError("rebuilt input missing required caveat")
    dns = joined(normalized_do_not_say(pkg.get("do_not_say")))
    for item in REQUIRED_DO_NOT_SAY:
        if item not in dns:
            raise ValueError(f"rebuilt input do_not_say missing: {item}")
    validate_no_prose_or_approval(pkg, "rebuilt input")
    if pkg.get("rebuilt_input_decision") == "rebuilt_draft_input_candidate":
        if pkg.get("author_allowed") is not False or pkg.get("eligible_for_authoring") is not False or pkg.get("chapter_update_allowed") is not False:
            raise ValueError("rebuilt_draft_input_candidate still requires author_allowed=false, eligible_for_authoring=false, chapter_update_allowed=false")


def make_validator(selected: list[dict[str, Any]]):
    selected_by_input = {str(s["draft_input_id"]): s for s in selected}

    def validator(obj: dict[str, Any]) -> None:
        packages = obj.get("rebuilt_author_draft_inputs")
        if not isinstance(packages, list):
            raise ValueError("LLM JSON must contain rebuilt_author_draft_inputs list")
        if len(packages) != len(selected_by_input):
            raise ValueError(f"expected {len(selected_by_input)} rebuilt input(s), got {len(packages)}")
        seen = set()
        for pkg in packages:
            validate_rebuilt_package(pkg, selected_by_input)
            pid = pkg["prior_draft_input_id"]
            if pid in seen:
                raise ValueError(f"duplicate prior_draft_input_id: {pid}")
            seen.add(pid)
    return validator


def build_prompt(selected: list[dict[str, Any]], excluded: list[dict[str, Any]], run_id: str) -> str:
    schema = {
        "rebuilt_author_draft_inputs": [
            {
                "rebuilt_input_id": "string deterministic-looking id",
                "prior_draft_input_id": "string",
                "prior_draft_canary_id": "string",
                "source_packet_id": "string",
                "source_cluster_id": "string",
                "source_note_ids": ["strings"],
                "source_review_ids": ["strings"],
                "source_ids": ["strings"],
                "manifest_item_ids": ["strings"],
                "candidate_source_ids": ["strings where available"],
                "rebuilt_input_type": "choose exactly one string: enriched_caveat_only_author_draft_input | safe_reports_only_author_input | needs_more_sources_author_input | excluded_author_input",
                "rebuilt_input_decision": "choose exactly one string: rebuilt_draft_input_candidate | safe_reports_only | needs_more_sources | source_context_unclear | exclude_from_authoring | contradiction_review_required",
                "rebuilt_input_use": "choose exactly one string: caveat_only | context_only | safe_reports_only | not_for_authoring | not_for_publication",
                "title": "short planning title",
                "authoring_purpose": "planning-only purpose, not a paragraph for book text",
                "evidence_bound_factual_atoms": ["short atomic notes, each under 28 words; not prose"],
                "allowed_author_scope": ["planning constraints only"],
                "forbidden_author_scope": ["planning constraints only"],
                "narrative_function_suggestions": ["functional descriptions only, not finished sentences"],
                "placement_suggestions": ["suggestions only; no chapter assignment"],
                "target_chapter_candidates": ["suggested conceptual locations only"],
                "target_chapter_status": "not_assigned or suggested_only",
                "required_caveats": [REQUIRED_CAVEAT],
                "do_not_say": REQUIRED_DO_NOT_SAY,
                "evidence_summary": "planning summary only",
                "evidence_limitations": ["strings"],
                "residual_risk": "string",
                "confidence": "limited_caveat_only or lower",
                "citation_requirements": ["strings"],
                "later_canary_instruction_seed": "instructions only; no final prose; no book-ready wording",
                "usefulness_improvement_notes": "string explaining improvement over Run 24 caveat restatement",
                "why_prior_canary_was_not_useful": "string",
                "provenance_paths": ["strings"],
                "singleton_input": True,
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
        "task": "Run 26 report-only enriched caveat-only author-draft input rebuild",
        "selected_canary_redteams": selected,
        "excluded_canary_redteams": excluded,
        "required_caveat": REQUIRED_CAVEAT,
        "required_do_not_say": REQUIRED_DO_NOT_SAY,
        "allowed_rebuilt_input_type_values": sorted(ALLOWED_TYPES),
        "allowed_rebuilt_input_decision_values": sorted(ALLOWED_DECISIONS),
        "allowed_rebuilt_input_use_values": sorted(ALLOWED_USES),
        "required_schema": schema,
        "instructions": [
            "Return JSON only. No markdown or prose outside JSON.",
            "Rebuild richer author-draft input metadata; do not generate draft prose or publishable wording.",
            "Address the Run 25 finding: safe_but_not_useful / not_useful_restates_caveat_only / needs_better_authoring_input.",
            "Add structured planning context: evidence-bound factual atoms, allowed/forbidden boundaries, narrative function suggestions, placement suggestions only, citation/provenance requirements, and a useful later-canary instruction seed.",
            "The safe narrative function is ecosystem/tooling adjacency, not architectural dependency.",
            "Do not say Hermes is a runtime dependency of OpenClaw, a general operating environment for OpenClaw, or required for web/phone access.",
            "Do not assign a chapter. Do not write docs/book prose. Do not write final paragraphs. Do not include fields named chapter_prose, publishable_paragraph, draft_paragraph, final_prose, book_text, chapter_ready_prose, or citation_resolved_chapter_text.",
            "Do not use the phrase chapter-ready or approved for publication/authoring inside any rebuilt package field.",
            "Choose exactly ONE string enum value for rebuilt_input_type, rebuilt_input_decision, rebuilt_input_use, and target_chapter_status; do NOT return arrays/objects for these fields.",
            "Set all authoring, publication, claim-insertion, and chapter-update flags false even when the package is a rebuilt_draft_input_candidate.",
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
        "docs_book_modified": False,
        "schema_modified": False,
        "daily_worker_modified": False,
        "gpt55_advisory_is_human_or_editor_approval": False,
        "rebuilt_input_is_authoring": False,
        "rebuilt_input_is_publishable_material": False,
    }


def build_payload(args: argparse.Namespace) -> dict[str, Any]:
    redteam_path = resolve(args.redteam_report)
    canary_path = resolve(args.canary_report)
    preflight_path = resolve(args.preflight_report)
    draft_input_path = resolve(args.draft_input_report)
    run25 = load_json(redteam_path, "Run 25 redteam report")
    run24 = load_json(canary_path, "Run 24 canary report")
    run23 = load_json(preflight_path, "Run 23 preflight report")
    run22b = load_json(draft_input_path, "Run 22B draft-input report")
    validate_input_reports(run25, run24, run23, run22b)
    try:
        profile = load_model_profile(args.reasoning_profile)
    except ModelProfileError as exc:
        raise RebuildInputError(f"model_profile_error:{exc}") from exc
    selected, excluded = select_redteams(run25, run24, run22b)
    db = db_path()
    with connect_readonly(db) as con:
        before_counts = {"source_notes": table_count(con, "source_notes"), "claims": table_count(con, "claims"), "editorial_reviews": table_count(con, "editorial_reviews")}
        before_status = status_snapshots(con)
        prompt = build_prompt(selected, excluded, args.run_id)
        try:
            llm = call_high_reasoning_json(
                prompt,
                schema_name="run26_rebuild_author_draft_input",
                validator=make_validator(selected),
                provider=args.provider,
                model=args.model,
                timeout_seconds=args.timeout_seconds,
                reasoning_profile=args.reasoning_profile,
            )
        except HighReasoningError as exc:
            raise RebuildInputError(str(exc.result.get("error") or exc)) from exc
        after_counts = {"source_notes": table_count(con, "source_notes"), "claims": table_count(con, "claims"), "editorial_reviews": table_count(con, "editorial_reviews")}
        after_status = status_snapshots(con)
    packages = llm["parsed_json"]["rebuilt_author_draft_inputs"]
    payload = {
        "run_id": args.run_id,
        "generated_at": utc_now(),
        "mode": MODE,
        "input_paths": {
            "redteam_report": rel(redteam_path),
            "canary_report": rel(canary_path),
            "preflight_report": rel(preflight_path),
            "draft_input_report": rel(draft_input_path),
            "sqlite_db": rel(db),
        },
        "report_only": True,
        "llm_used": bool(llm.get("llm_used")),
        "reasoning_status": llm.get("reasoning_status"),
        "provider": llm.get("provider") or profile["provider"],
        "model": llm.get("model") or profile["model"],
        "bridge": llm.get("bridge") or profile["bridge"],
        "model_profile": llm.get("model_profile") or profile["profile_name"],
        "strict_json_required": bool(llm.get("strict_json_required", profile["strict_json_required"])),
        "weak_local_fallback_refused": bool(llm.get("weak_local_fallback_refused", True)),
        "selected_canary_redteam_count": len(selected),
        "rebuilt_input_count": len(packages),
        "excluded_canary_redteam_count": len(excluded),
        "rebuilt_input_type_counts": dict(Counter(p["rebuilt_input_type"] for p in packages)),
        "rebuilt_input_decision_counts": dict(Counter(p["rebuilt_input_decision"] for p in packages)),
        "rebuilt_input_use_counts": dict(Counter(p["rebuilt_input_use"] for p in packages)),
        "target_chapter_status_counts": dict(Counter(p["target_chapter_status"] for p in packages)),
        "selected_canary_redteams": selected,
        "excluded_canary_redteams": excluded,
        "rebuilt_author_draft_inputs": packages,
        "failed_rebuild_checks": [],
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
        raise RebuildInputError("high reasoning was not used")
    if payload["provider"] != "copilot" or payload["model"] != "gpt-5.5" or payload["bridge"] != "hermes_cli" or payload["model_profile"] != args.reasoning_profile:
        raise RebuildInputError("unexpected high-reasoning provider/model/bridge/profile")
    if payload["changed_source_notes"] or payload["claims_inserted"] or payload["editorial_reviews_inserted"] or payload["source_status_changed"] or payload["claim_status_changed"] or payload["editorial_status_changed"]:
        raise RebuildInputError("forbidden DB/status delta detected during report-only rebuild")
    return payload


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        f"# Run 26 author-draft input rebuild — {payload['run_id']}", "",
        "## Summary", "",
        f"- Report-only: `{payload['report_only']}`",
        f"- GPT-5.5 used: `{payload['llm_used']}`",
        f"- Provider/model/bridge/profile: `{payload['provider']}` / `{payload['model']}` / `{payload['bridge']}` / `{payload['model_profile']}`",
        f"- Selected Run 25 red-team results: `{payload['selected_canary_redteam_count']}`",
        f"- Rebuilt input packages: `{payload['rebuilt_input_count']}`",
        f"- Excluded Run 25 red-team results: `{payload['excluded_canary_redteam_count']}`",
        "", "## Selected Run 25 result", "",
    ]
    for r in payload["selected_canary_redteams"]:
        lines += [
            f"- draft_canary_id: `{r['draft_canary_id']}`",
            f"  - redteam_decision: `{r['redteam_decision']}`",
            f"  - canary_usefulness: `{r['canary_usefulness']}`",
            f"  - disposition: `{r['closed_loop_disposition']}`",
            f"  - next stage: `{r['recommended_next_stage']}`",
        ]
    lines += ["", "## Rebuilt input packages", ""]
    for p in payload["rebuilt_author_draft_inputs"]:
        lines += [
            f"- rebuilt_input_id: `{p['rebuilt_input_id']}`",
            f"  - type: `{p['rebuilt_input_type']}`",
            f"  - decision: `{p['rebuilt_input_decision']}`",
            f"  - use: `{p['rebuilt_input_use']}`",
            f"  - target_chapter_status: `{p['target_chapter_status']}`",
            f"  - improvement: {p['usefulness_improvement_notes']}",
            f"  - why prior canary was not useful: {p['why_prior_canary_was_not_useful']}",
            "", "### Caveat-only constraints", "",
            "- Required caveat is preserved.",
            "- Author/publication/claim/chapter flags remain false.",
            "- Package is planning metadata only, not prose.",
            "", "### Allowed future author scope", "",
            *[f"- {x}" for x in p.get("allowed_author_scope", [])],
            "", "### Forbidden future author scope", "",
            *[f"- {x}" for x in p.get("forbidden_author_scope", [])],
            "", "### Do-not-say guidance", "",
            *[f"- {x}" for x in p.get("do_not_say", [])],
            "", "### Evidence limitations and residual risk", "",
            *[f"- {x}" for x in p.get("evidence_limitations", [])],
            f"- Residual risk: {p['residual_risk']}", "",
        ]
    lines += [
        "## Why this is not authoring/publication/chapter update", "",
        "This run rebuilds structured author-input metadata only. It does not create draft prose, chapter prose, claim insertion requests, editorial reviews, source notes, source/status changes, or docs/book mutations. GPT-5.5 output is advisory and is not human/editor approval.",
        "", "## Recommendation for Run 27", "",
        "Run a report-only preflight/red-team gate over the enriched Run 26 input before any later controlled canary. Do not write docs/book or approve authoring/publication.",
    ]
    return "\n".join(lines) + "\n"


def write_reports(payload: dict[str, Any], output_dir: Path, suffix: str) -> dict[str, str]:
    out_dir = output_dir if output_dir.is_absolute() else ROOT / output_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{payload['run_id']}-author-draft-input-rebuild-{suffix}" if suffix else f"{payload['run_id']}-author-draft-input-rebuild"
    json_path = out_dir / f"{stem}.json"
    md_path = out_dir / f"{stem}.md"
    payload["output_paths"] = {"json": rel(json_path), "markdown": rel(md_path)}
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(payload), encoding="utf-8")
    return payload["output_paths"]


def parse_args(argv: list[str]) -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", default=RUN_ID_DEFAULT)
    ap.add_argument("--redteam-report", default=DEFAULT_RUN25)
    ap.add_argument("--canary-report", default=DEFAULT_RUN24)
    ap.add_argument("--preflight-report", default=DEFAULT_RUN23)
    ap.add_argument("--draft-input-report", default=DEFAULT_RUN22B)
    ap.add_argument("--output-dir", default="reports/editorial")
    ap.add_argument("--report-suffix", default="run26")
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
            "selected_canary_redteam_count": payload["selected_canary_redteam_count"],
            "rebuilt_input_count": payload["rebuilt_input_count"],
            "excluded_canary_redteam_count": payload["excluded_canary_redteam_count"],
            "rebuilt_input_type_counts": payload["rebuilt_input_type_counts"],
            "rebuilt_input_decision_counts": payload["rebuilt_input_decision_counts"],
            "rebuilt_input_use_counts": payload["rebuilt_input_use_counts"],
            "target_chapter_status_counts": payload["target_chapter_status_counts"],
        }, sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
