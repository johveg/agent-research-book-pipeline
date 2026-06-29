#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import chapter_creation_worker  # noqa: E402
import chapter_router  # noqa: E402
import chapter_update_worker  # noqa: E402


def load_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: str | Path, obj: Any) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def load_packets(path: str | Path | None) -> list[dict[str, Any]]:
    if not path:
        return []
    data = load_json(path)
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        for key in ["evidence_packets", "packets", "candidates"]:
            if isinstance(data.get(key), list):
                return [x for x in data[key] if isinstance(x, dict)]
    return []


def dispatch_packets(*, packets: list[dict[str, Any]], contract_json: str | Path, repo_root: str | Path, run_id: str, output_dir: str | Path, max_events: int = 8) -> dict[str, Any]:
    outdir = Path(output_dir)
    event_dir = outdir / f"{run_id}-book-events"
    patch_dir = outdir / f"{run_id}-chapter-patches"
    chapters = chapter_router.load_chapters(contract_json)
    events: list[dict[str, Any]] = []
    patch_reports: list[dict[str, Any]] = []
    proposal_paths: list[str] = []
    for packet in packets:
        routed = chapter_router.route_packet(packet, chapters)
        for event in routed.get("events", []):
            if len(events) >= max_events:
                break
            events.append(event)
            write_json(event_dir / f"{event['event_id']}.json", event)
            if event["event_type"] == "chapter.update.requested":
                report = chapter_update_worker.build_patch_proposal(event, repo_root=repo_root, output_dir=patch_dir)
            elif event["event_type"] in {"chapter.creation.requested", "chapter.seed.requested"}:
                report = chapter_creation_worker.build_creation_patch(event, repo_root=repo_root, output_dir=patch_dir)
            else:
                continue
            patch_reports.append(report)
            if report.get("patch_json_path"):
                proposal_paths.append(report["patch_json_path"])
    result = {
        "ok": True,
        "mode": "event_driven_book_dispatcher",
        "run_id": run_id,
        "packet_count": len(packets),
        "event_count": len(events),
        "patch_proposal_count": len(proposal_paths),
        "events_dir": str(event_dir),
        "patch_dir": str(patch_dir),
        "proposal_paths": proposal_paths,
        "events": events,
        "patch_reports": patch_reports,
        "human_in_loop_dependency_added": False,
    }
    write_json(outdir / f"{run_id}-event-driven-dispatch.json", result)
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--packets-json")
    ap.add_argument("--contract-json", default="config/book_manuscript_production_contract.json")
    ap.add_argument("--repo-root", default=".")
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--output-dir", default="reports/editorial")
    ap.add_argument("--output-json")
    ap.add_argument("--max-events", type=int, default=8)
    args = ap.parse_args()
    packets = load_packets(args.packets_json)
    result = dispatch_packets(packets=packets, contract_json=args.contract_json, repo_root=args.repo_root, run_id=args.run_id, output_dir=args.output_dir, max_events=args.max_events)
    if args.output_json:
        write_json(args.output_json, result)
    print(json.dumps({"ok": result["ok"], "event_count": result["event_count"], "patch_proposal_count": result["patch_proposal_count"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
