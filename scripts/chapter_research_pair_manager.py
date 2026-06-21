#!/usr/bin/env python3
"""Create recurring research pairs for human-approved chapter subjects."""
from __future__ import annotations

import argparse
import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DISCOVERY_CONFIG = ROOT / "config" / "chapter_discovery_topics.json"
DEFAULT_SEARCH_CONFIG = ROOT / "data" / "search_config.json"
DEFAULT_QUEUE = ROOT / "config" / "book_manuscript_queue.json"
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


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: str | Path, default: Any = None) -> Any:
    p = Path(path)
    if not p.exists():
        return default
    return json.loads(p.read_text(encoding="utf-8"))


def write_json(path: str | Path, obj: Any) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def _append_unique(items: list[str], value: str | None) -> bool:
    if not value:
        return False
    if value in items:
        return False
    items.append(value)
    return True


def approved_subjects(config: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for item in config.get("approved_subjects", []) if isinstance(config.get("approved_subjects"), list) else []:
        if isinstance(item, dict) and item.get("status") == "approved":
            out.append(item)
    return out


def target_path_for(subject: dict[str, Any]) -> str:
    chapter_id = str(subject.get("chapter_id") or "new_chapter")
    slug = chapter_id.replace("_", "-")
    return str(subject.get("target_path") or f"docs/book/{slug}.md")


def queue_has_chapter(queue: dict[str, Any], chapter_id: str) -> bool:
    for item in queue.get("queue", []) if isinstance(queue.get("queue"), list) else []:
        if item.get("chapter_id") == chapter_id:
            return True
    return False


def apply_approved_subjects(discovery_config: dict[str, Any], search_config: dict[str, Any], queue: dict[str, Any]) -> dict[str, Any]:
    search = deepcopy(search_config)
    q = deepcopy(queue)
    search.setdefault("web_queries", [])
    search.setdefault("linkedin_queries", [])
    q.setdefault("queue", [])
    created = []
    for subject in approved_subjects(discovery_config):
        chapter_id = str(subject.get("chapter_id") or "").strip()
        if not chapter_id:
            continue
        web_added = _append_unique(search["web_queries"], subject.get("web_query"))
        li_added = _append_unique(search["linkedin_queries"], subject.get("linkedin_query"))
        if not queue_has_chapter(q, chapter_id):
            q["queue"].append({
                "chapter_id": chapter_id,
                "title": subject.get("title") or chapter_id.replace("_", " ").title(),
                "mode": "human_approved_research_pair",
                "status": "approved_research_lane",
                "target_path": target_path_for(subject),
                "required_gates": list(REQUIRED_GATES),
                "research_pair": {
                    "linkedin_query": subject.get("linkedin_query"),
                    "web_query": subject.get("web_query"),
                },
                "human_approved_at_utc": subject.get("approved_at_utc"),
            })
        if web_added or li_added:
            created.append(chapter_id)
    return {
        "ok": True,
        "generated_at_utc": utc_now(),
        "human_approval_required": True,
        "research_pairs_created": len(created),
        "created_chapter_ids": created,
        "search_config": search,
        "queue": q,
        "docs_book_changed": False,
        "publication_approved": False,
        "chapter_update_allowed": False,
    }


def render_md(report: dict[str, Any]) -> str:
    lines = [
        "# Chapter research pair manager",
        "",
        f"- Generated: `{report.get('generated_at_utc')}`",
        f"- Research pairs created: `{report.get('research_pairs_created')}`",
        f"- Docs/book changed: `{report.get('docs_book_changed')}`",
        "",
        "## Created chapter IDs",
        "",
    ]
    for chapter_id in report.get("created_chapter_ids", []):
        lines.append(f"- `{chapter_id}`")
    if not report.get("created_chapter_ids"):
        lines.append("No approved subjects required new research pairs.")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--discovery-config", default=str(DEFAULT_DISCOVERY_CONFIG))
    ap.add_argument("--search-config", default=str(DEFAULT_SEARCH_CONFIG))
    ap.add_argument("--queue-json", default=str(DEFAULT_QUEUE))
    ap.add_argument("--write", action="store_true", help="Persist approved research-pair additions")
    ap.add_argument("--output-json")
    ap.add_argument("--output-md")
    args = ap.parse_args()

    discovery_config = load_json(args.discovery_config, {}) or {}
    search_config = load_json(args.search_config, {"web_queries": [], "linkedin_queries": []}) or {"web_queries": [], "linkedin_queries": []}
    queue = load_json(args.queue_json, {"queue": []}) or {"queue": []}
    report = apply_approved_subjects(discovery_config, search_config, queue)
    if args.write:
        write_json(args.search_config, report["search_config"])
        write_json(args.queue_json, report["queue"])
    if args.output_json:
        write_json(args.output_json, {k: v for k, v in report.items() if k not in {"search_config", "queue"}} | {
            "search_config_path": str(args.search_config),
            "queue_json_path": str(args.queue_json),
        })
    if args.output_md:
        p = Path(args.output_md)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(render_md(report), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k not in {"search_config", "queue"}}, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
