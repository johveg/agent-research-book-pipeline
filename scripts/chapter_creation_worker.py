#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def write_json(path: str | Path, obj: Any) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def titleize(text: str) -> str:
    return re.sub(r"[_-]+", " ", text).strip().title() or "New Chapter"


def seed_markdown(title: str, packet: dict[str, Any]) -> str:
    topics = ", ".join(str(x) for x in packet.get("topics", [])[:4]) or title.lower()
    return (
        f"# {title}\n\n"
        f"The central argument of this seed chapter is that {topics} has become distinct enough to deserve a dedicated research lane in the book. "
        "The chapter is intentionally cautious: it frames the subject, states evidence limits, and avoids turning early signals into broad claims. [1]\n\n"
        "A second sustained paragraph explains why the topic should not be hidden only inside adjacent chapters. It may overlap with existing material, but its operational questions, vocabulary, and risks create a separate reader-facing path for future synthesis. [2]\n\n"
        "A third sustained paragraph describes how this seed will mature. Future updates should add corroborated sources, refine definitions, and integrate concrete examples only after citation and privacy gates confirm that the material is safe for publication. [3]\n\n"
        "A fourth sustained paragraph marks the evidence limits clearly. This chapter is not a claim ledger or a status report; it is a book-facing research lane that can later become a mature chapter when the evidence base is strong enough. [1] [2] [3]\n\n"
        "## References\n"
        "[1] [Approved research lane](open-questions.md).\n\n"
        "[2] [Evidence packet summary](source-registry.md).\n\n"
        "[3] [Editorial synthesis note](methodology.md).\n"
    )


def build_creation_patch(event: dict[str, Any], *, repo_root: str | Path, output_dir: str | Path) -> dict[str, Any]:
    target_path = str(event.get("target_path") or "")
    if not target_path.startswith("docs/book/") or ".." in Path(target_path).parts:
        return {"ok": False, "event_type": "chapter.creation.blocked", "failed_checks": ["invalid_target_path"], "target_path": target_path}
    payload = event.get("payload") or {}
    packet = payload.get("packet", {})
    title = str(payload.get("title") or titleize(str(event.get("chapter_id") or Path(target_path).stem)))
    proposal = {
        "event_type": "chapter.patch.proposed",
        "event_id": event.get("event_id"),
        "chapter_id": event.get("chapter_id"),
        "target_path": target_path,
        "operation": "create_chapter",
        "proposed_markdown": seed_markdown(title, packet),
        "nav_entry": {"title": title, "path": "book/" + Path(target_path).name},
        "citation_map": {"1": ["approved_research_lane"], "2": packet.get("source_ids", []) or ["evidence_packet"], "3": ["editorial_synthesis"]},
        "evidence_refs": packet.get("source_ids", []) or [packet.get("packet_id", "evidence_packet")],
        "human_in_loop_dependency_added": False,
        "raw_text_publication_allowed": False,
        "publication_stage": "research_lane_seed",
        "public_nav_allowed": False,
        "created_at_utc": utc_now(),
    }
    out = Path(output_dir) / f"{event.get('event_id') or event.get('chapter_id')}-patch.json"
    write_json(out, proposal)
    return {"ok": True, "event_type": "chapter.patch.proposed", "target_path": target_path, "patch_json_path": str(out), "docs_book_mutated": False}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--event-json", required=True)
    ap.add_argument("--repo-root", default=".")
    ap.add_argument("--output-dir", default="reports/chapter_patches")
    ap.add_argument("--output-json")
    args = ap.parse_args()
    event = json.loads(Path(args.event_json).read_text(encoding="utf-8"))
    report = build_creation_patch(event, repo_root=args.repo_root, output_dir=args.output_dir)
    if args.output_json:
        write_json(args.output_json, report)
    print(json.dumps({"ok": report.get("ok"), "event_type": report.get("event_type")}))
    return 0 if report.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
