#!/usr/bin/env python3
from __future__ import annotations
import argparse, json
from datetime import datetime, timezone
from pathlib import Path

FALSE_FLAGS = {
    "author_allowed": False,
    "publication_approved": False,
    "eligible_for_claim_insertion": False,
    "eligible_for_authoring": False,
    "eligible_for_publication": False,
    "chapter_update_allowed": False,
}

AUTONOMOUS_CHAPTER_REVISION_POLICY = {
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

REQUIRED_GATES = [
    "chapter_revision_decision",
    "input_packet_valid",
    "draft_created",
    "manuscript_quality_passed",
    "evidence_safety_passed",
    "publisher_scope_valid",
    "mkdocs_strict_passed",
    "mutation_guard_passed",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_contract() -> dict:
    chapters = {
        "introduction": {
            "title": "Introduction",
            "target_path": "docs/book/introduction.md",
            "role": "front_matter_chapter",
            "required_sections": ["opening thesis", "scope", "contribution", "methodology preview", "limitations", "chapter roadmap"],
            "publication_mode": "guarded_publish_canary",
        },
        "methodology": {
            "title": "Methodology",
            "target_path": "docs/book/methodology.md",
            "role": "foundation_chapter",
            "required_sections": ["evidence sources", "inclusion boundaries", "claim status model", "automation limits", "reproducibility limits"],
            "publication_mode": "future_guarded_publish",
        },
        "agent_loop": {"title": "The Agent Loop", "target_path": "docs/book/01-the-agent-loop.md", "role": "core_concept_chapter", "publication_mode": "published_canary_existing"},
        "hermes": {"title": "Hermes", "target_path": "docs/book/02-hermes.md", "role": "tool_case_chapter", "publication_mode": "future_guarded_publish"},
        "openclaw": {"title": "OpenClaw", "target_path": "docs/book/03-openclaw.md", "role": "tool_case_chapter", "publication_mode": "future_guarded_publish"},
        "loop_engineering": {"title": "Loop Engineering", "target_path": "docs/book/04-loop-engineering.md", "role": "core_concept_chapter", "publication_mode": "future_guarded_publish"},
        "context_memory": {"title": "Context and Memory Architecture", "target_path": "docs/book/05-context-memory-architecture.md", "role": "tool_case_chapter", "publication_mode": "future_guarded_publish"},
        "operating_loops": {"title": "Operating Loops in Production", "target_path": "docs/book/06-operating-loops.md", "role": "production_operations_chapter", "publication_mode": "future_guarded_publish"},
    }
    return {
        "contract_name": "book_manuscript_production_contract",
        "version": 1,
        "run_introduced": "run58",
        "created_at_utc": utc_now(),
        "global_publication_mode": "guarded_one_chapter_at_a_time",
        "hard_safety_flags": dict(FALSE_FLAGS),
        "reader_facing_rules": {
            "prefer_sustained_paragraphs": True,
            "forbid_evidence_ledger_language": True,
            "forbid_internal_claim_source_ids": True,
            "require_limitations": True,
            "require_integrated_citations": True,
        },
        "forbidden_reader_facing_phrases": [
            "Current evidence status", "Source/claim mapping", "Bullet 1 maps to", "Editor notes", "Changelog", "Editorial policy", "status supported", "status weakly_supported", "quality A", "quality B", "claim record", "source tokens"
        ],
        "autonomous_chapter_revision_policy": AUTONOMOUS_CHAPTER_REVISION_POLICY,
        "chapters": chapters,
    }


def build_queue(contract: dict) -> dict:
    queue = []
    for cid in ["introduction", "methodology", "hermes", "openclaw", "loop_engineering", "context_memory", "operating_loops"]:
        chapter = contract["chapters"][cid]
        queue.append({
            "chapter_id": cid,
            "target_path": chapter["target_path"],
            "mode": "guarded_publish_canary" if cid == "introduction" else "future_guarded_publish",
            "required_gates": list(REQUIRED_GATES),
            "status": "ready_for_run58" if cid == "introduction" else "queued_after_introduction",
        })
    return {"queue_name": "book_manuscript_production_queue", "created_at_utc": utc_now(), "queue": queue}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output-contract", default="config/book_manuscript_production_contract.json")
    ap.add_argument("--output-queue", default="config/book_manuscript_queue.json")
    args = ap.parse_args(argv)
    contract = build_contract()
    queue = build_queue(contract)
    Path(args.output_contract).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output_contract).write_text(json.dumps(contract, indent=2, sort_keys=True) + "\n")
    Path(args.output_queue).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output_queue).write_text(json.dumps(queue, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"ok": True, "contract": args.output_contract, "queue": args.output_queue, "next_chapter": queue["queue"][0]["chapter_id"]}, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
