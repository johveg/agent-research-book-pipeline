#!/usr/bin/env python3
"""Plan post-processing chapter revisions and guarded new chapter creation.

This script is deliberately a planning gate. It decides whether newly processed
information should be integrated into an existing manuscript chapter or routed
into an automatic guarded new-chapter queue item. It does not mutate docs/book.
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

FALSE_FLAGS = {
    "author_allowed": False,
    "publication_approved": False,
    "eligible_for_claim_insertion": False,
    "eligible_for_authoring": False,
    "eligible_for_publication": False,
    "chapter_update_allowed": False,
}

REQUIRED_GATES = [
    "chapter_revision_decision",
    "input_packet_valid",
    "draft_created",
    "manuscript_quality_passed",
    "evidence_safety_passed",
    "publisher_scope_valid",
    "mkdocs_strict_passed",
    "mutation_guard_passed",
    "all_chapter_public_proof_gate",
]

DEFAULT_POLICY = {
    "trigger": "after_automatic_collection_and_processing",
    "existing_chapter_revision": {
        "required": True,
        "decision_question": "Is there new information to add to an existing chapter?",
        "action_when_yes": "add_and_refactor_rewrite_existing_chapter",
        "integration_style": "fluent_refactor_rewrite",
        "append_only_allowed": False,
    },
    "new_chapter_creation": {
        "required": True,
        "decision_question": "Is there new information that should render a new chapter?",
        "action_when_yes": "create_new_chapter_automatically",
        "chapter_creation_mode": "automatic_guarded_queue_item",
        "write_docs_book_immediately": False,
    },
    "safety": {
        "planning_gate_only": True,
        "docs_book_write_requires_guarded_publisher": True,
        "preserve_hard_false_flags_until_publication_gate": True,
        "require_academic_professional_prose": True,
        "forbid_evidence_led_reader_pages": True,
    },
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _tokens(value: Any) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, (list, tuple, set)):
        text = " ".join(str(v) for v in value)
    else:
        text = str(value)
    return {t for t in re.findall(r"[a-z0-9]+", text.lower()) if len(t) >= 3}


def _chapter_topics(chapter_id: str, chapter: dict[str, Any]) -> set[str]:
    topics = set()
    for key in ("topics", "title", "role", "target_path"):
        topics |= _tokens(chapter.get(key))
    topics |= _tokens(chapter_id.replace("_", " "))
    return topics


def _item_topics(item: dict[str, Any]) -> set[str]:
    topics = set()
    for key in ("topics", "title", "summary", "entities", "keywords"):
        topics |= _tokens(item.get(key))
    return topics


def _supported(item: dict[str, Any]) -> bool:
    status = str(item.get("evidence_status") or item.get("status") or "supported").lower()
    return status in {"supported", "weakly_supported", "promoted_to_chapter", "caveat_only"}


def _slug(text: str) -> str:
    words = re.findall(r"[a-z0-9]+", text.lower())
    return "-".join(words[:6]) or "new-chapter"


def _chapter_id_from_slug(slug: str) -> str:
    return slug.replace("-", "_")


def _best_existing_chapter(item: dict[str, Any], chapters: dict[str, Any]) -> tuple[str | None, dict[str, Any] | None, int]:
    item_topics = _item_topics(item)
    best_id = None
    best_chapter = None
    best_score = 0
    for chapter_id, chapter in chapters.items():
        if not isinstance(chapter, dict):
            continue
        score = len(item_topics & _chapter_topics(chapter_id, chapter))
        if score > best_score:
            best_id = chapter_id
            best_chapter = chapter
            best_score = score
    return best_id, best_chapter, best_score


def build_revision_plan(contract: dict[str, Any], processed: dict[str, Any], run_id: str = "manual") -> dict[str, Any]:
    policy = contract.get("autonomous_chapter_revision_policy") or DEFAULT_POLICY
    chapters = contract.get("chapters") if isinstance(contract.get("chapters"), dict) else {}
    items = processed.get("processed_information") or processed.get("items") or processed.get("new_information") or []
    if not isinstance(items, list):
        items = []

    existing: list[dict[str, Any]] = []
    new_chapters: list[dict[str, Any]] = []
    ignored: list[dict[str, Any]] = []

    for idx, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            ignored.append({"index": idx, "reason": "not_an_object"})
            continue
        if not _supported(item):
            ignored.append({"index": idx, "title": item.get("title"), "reason": "unsupported_or_blocked_evidence"})
            continue
        chapter_id, chapter, score = _best_existing_chapter(item, chapters)
        if chapter_id and chapter and score > 0:
            existing.append({
                "chapter_id": chapter_id,
                "target_path": chapter.get("target_path"),
                "title": chapter.get("title", chapter_id.replace("_", " ").title()),
                "matched_topic_count": score,
                "new_information_title": item.get("title"),
                "new_information_summary": item.get("summary"),
                "revision_instruction": "refactor_rewrite_for_fluent_integration",
                "required_action": "add_new_information_and_rewrite_chapter_fluently",
                "append_only_allowed": False,
                "write_docs_book_now": False,
                "required_gates": list(REQUIRED_GATES),
            })
        else:
            slug = _slug(str(item.get("title") or item.get("summary") or "new chapter"))
            new_chapters.append({
                "chapter_id": _chapter_id_from_slug(slug),
                "title": str(item.get("title") or slug.replace("-", " ").title()),
                "target_path": f"docs/book/{slug}.md",
                "source_information_title": item.get("title"),
                "source_information_summary": item.get("summary"),
                "queue_mode": "automatic_guarded_new_chapter",
                "required_action": "create_new_chapter_automatically_after_gates",
                "write_docs_book_now": False,
                "required_gates": list(REQUIRED_GATES),
            })

    return {
        "ok": True,
        "run_id": run_id,
        "generated_at_utc": utc_now(),
        "trigger": policy.get("trigger", DEFAULT_POLICY["trigger"]),
        "revision_required": bool(existing),
        "new_chapter_required": bool(new_chapters),
        "existing_chapter_revisions": existing,
        "new_chapter_candidates": new_chapters,
        "ignored_information": ignored,
        "decision_summary": {
            "processed_information_count": len(items),
            "existing_chapter_revision_count": len(existing),
            "new_chapter_candidate_count": len(new_chapters),
            "ignored_count": len(ignored),
        },
        "publication_safety_flags": dict(FALSE_FLAGS),
        "safety_flags": dict(FALSE_FLAGS),
        "docs_book_changed": False,
        "chapter_update_allowed": False,
        "publication_approved": False,
        "disposition": "chapter_revision_plan_created_report_only",
    }


def write_reports(plan: dict[str, Any], output_json: Path, output_md: Path) -> None:
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(plan, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    lines = [
        "# Chapter revision policy plan",
        "",
        f"- ok: `{plan.get('ok')}`",
        f"- trigger: `{plan.get('trigger')}`",
        f"- existing chapter revisions: `{len(plan.get('existing_chapter_revisions', []))}`",
        f"- new chapter candidates: `{len(plan.get('new_chapter_candidates', []))}`",
        f"- docs/book changed: `{plan.get('docs_book_changed')}`",
        "",
        "## Existing chapter revisions",
        "",
    ]
    for item in plan.get("existing_chapter_revisions", []):
        lines.append(f"- `{item.get('chapter_id')}` -> `{item.get('target_path')}`: add the new information and refactor/rewrite the chapter for fluent integration; append-only is `{item.get('append_only_allowed')}`.")
    if not plan.get("existing_chapter_revisions"):
        lines.append("- none")
    lines += ["", "## New chapter candidates", ""]
    for item in plan.get("new_chapter_candidates", []):
        lines.append(f"- `{item.get('chapter_id')}` -> `{item.get('target_path')}`: automatic guarded new chapter queue item; docs/book write now is `{item.get('write_docs_book_now')}`.")
    if not plan.get("new_chapter_candidates"):
        lines.append("- none")
    output_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--contract", default="config/book_manuscript_production_contract.json")
    ap.add_argument("--processed-json", required=True)
    ap.add_argument("--run-id", default="manual")
    ap.add_argument("--output-json", required=True)
    ap.add_argument("--output-md", required=True)
    args = ap.parse_args(argv)
    try:
        contract = json.loads(Path(args.contract).read_text(encoding="utf-8"))
        processed = json.loads(Path(args.processed_json).read_text(encoding="utf-8"))
        plan = build_revision_plan(contract, processed, run_id=args.run_id)
    except Exception as exc:
        plan = {
            "ok": False,
            "run_id": args.run_id,
            "generated_at_utc": utc_now(),
            "failed_checks": [type(exc).__name__],
            "error": str(exc),
            "publication_safety_flags": dict(FALSE_FLAGS),
            "safety_flags": dict(FALSE_FLAGS),
            "docs_book_changed": False,
            "disposition": "chapter_revision_plan_failed_closed",
        }
    write_reports(plan, Path(args.output_json), Path(args.output_md))
    print(json.dumps({"ok": plan.get("ok"), "revision_required": plan.get("revision_required"), "new_chapter_required": plan.get("new_chapter_required"), "output_json": args.output_json}, sort_keys=True))
    return 0 if plan.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
