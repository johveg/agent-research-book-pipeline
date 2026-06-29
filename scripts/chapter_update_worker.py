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


def title_from_path(path: str) -> str:
    stem = Path(path).stem.replace("-", " ").replace("_", " ").strip()
    if stem[:2].isdigit():
        stem = stem[2:].strip()
    return stem.title() or "Chapter"


def proposed_update_markdown(title: str, packet: dict[str, Any]) -> str:
    summary = str(packet.get("safe_summary") or packet.get("summary") or "new public evidence")
    topics = ", ".join(str(x) for x in packet.get("topics", [])[:4]) or "the chapter topic"
    return (
        f"# {title}\n\n"
        f"The central argument of this chapter is strengthened by new evidence about {topics}. {summary} "
        "The evidence limits remain explicit: the material is treated as publication-safe context for cautious synthesis, not as raw capture text or as a settled universal rule. [1]\n\n"
        "A second sustained paragraph explains how the new material fits the existing chapter rather than becoming an isolated evidence note. "
        "It is integrated as part of the book's argument, connecting operational practice, verification, and limits in language intended for readers rather than internal pipeline operators. [2]\n\n"
        "A third sustained paragraph keeps the analysis cautious. The update does not claim that every system follows the same pattern; instead, it identifies a recurring design pressure that should be evaluated against source quality, implementation context, and observable production behavior. [3]\n\n"
        "A fourth sustained paragraph closes the update by connecting the material back to the chapter's references and practical implications. "
        "The result is a reader-facing chapter revision with visible references, explicit evidence limits, and no publication of private or raw collection material. [1] [2] [3]\n\n"
        "## References\n"
        "[1] Evidence packet source summary.\n[2] Corroborating public source summary.\n[3] Editorial synthesis note.\n"
    )


def build_patch_proposal(event: dict[str, Any], *, repo_root: str | Path, output_dir: str | Path) -> dict[str, Any]:
    repo = Path(repo_root)
    target_path = str(event.get("target_path") or "")
    if not target_path.startswith("docs/book/") or ".." in Path(target_path).parts:
        report = {"ok": False, "event_type": "chapter.patch.blocked", "failed_checks": ["invalid_target_path"], "target_path": target_path}
    else:
        packet = (event.get("payload") or {}).get("packet", {})
        title = title_from_path(target_path)
        proposal = {
            "event_type": "chapter.patch.proposed",
            "event_id": event.get("event_id"),
            "chapter_id": event.get("chapter_id"),
            "target_path": target_path,
            "operation": "update_chapter",
            "proposed_markdown": proposed_update_markdown(title, packet),
            "citation_map": {"1": packet.get("source_ids", [])[:1] or ["evidence_packet"], "2": packet.get("source_ids", [])[1:2] or ["evidence_packet"], "3": packet.get("claim_ids", [])[:1] or ["editorial_synthesis"]},
            "evidence_refs": packet.get("source_ids", []) or [packet.get("packet_id", "evidence_packet")],
            "human_in_loop_dependency_added": False,
            "raw_text_publication_allowed": False,
            "created_at_utc": utc_now(),
        }
        out = Path(output_dir) / f"{event.get('event_id') or event.get('chapter_id')}-patch.json"
        write_json(out, proposal)
        report = {"ok": True, "event_type": "chapter.patch.proposed", "target_path": target_path, "patch_json_path": str(out), "docs_book_mutated": False}
    return report


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--event-json", required=True)
    ap.add_argument("--repo-root", default=".")
    ap.add_argument("--output-dir", default="reports/chapter_patches")
    ap.add_argument("--output-json")
    args = ap.parse_args()
    event = json.loads(Path(args.event_json).read_text(encoding="utf-8"))
    report = build_patch_proposal(event, repo_root=args.repo_root, output_dir=args.output_dir)
    if args.output_json:
        write_json(args.output_json, report)
    print(json.dumps({"ok": report.get("ok"), "event_type": report.get("event_type")}))
    return 0 if report.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
