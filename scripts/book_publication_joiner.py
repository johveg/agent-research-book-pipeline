#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from public_chapter_proof import evaluate_public_chapter_text, chapter_title_from_target  # noqa: E402


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: str | Path, obj: Any) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def safe_target(repo: Path, target_path: str) -> Path | None:
    if not target_path.startswith("docs/book/") or ".." in Path(target_path).parts:
        return None
    target = repo / target_path
    try:
        target.resolve().relative_to((repo / "docs" / "book").resolve())
    except Exception:
        return None
    return target


def ensure_nav_entry(mkdocs_path: Path, nav_entry: dict[str, str], *, public_nav_allowed: bool = False) -> bool:
    if not public_nav_allowed or not mkdocs_path.exists() or not nav_entry:
        return False
    text = mkdocs_path.read_text(encoding="utf-8")
    line = f"      - {nav_entry['title']}: {nav_entry['path']}"
    if line in text:
        return False
    marker = "      - Open Questions: book/open-questions.md"
    if marker in text:
        text = text.replace(marker, line + "\n" + marker, 1)
    else:
        text = text.rstrip() + "\n" + line + "\n"
    mkdocs_path.write_text(text, encoding="utf-8")
    return True


def chapter_id_from_path(path: str) -> str:
    stem = Path(path).stem
    stem = re.sub(r"^\d+-", "", stem)
    return stem.replace("-", "_")


def proof_for_file(path: Path, target_path: str, chapter_id: str | None = None) -> dict[str, Any]:
    title = chapter_title_from_target(target_path, None)
    return evaluate_public_chapter_text(path.read_text(encoding="utf-8"), title, chapter_id=chapter_id or chapter_id_from_path(target_path))


def full_manuscript_report(repo: Path) -> dict[str, Any]:
    docs = repo / "docs" / "book"
    results: dict[str, dict[str, Any]] = {}
    failed: list[str] = []
    for path in sorted(docs.glob("*.md")):
        cid = chapter_id_from_path(path.name)
        target = "docs/book/" + path.name
        result = proof_for_file(path, target, cid)
        result.update({"source": str(path), "target_path": target})
        results[cid] = result
        if not result.get("ok"):
            failed.append(cid)
    return {
        "ok": not failed,
        "source_kind": "all_local_book_chapters_report_only",
        "total_chapters": len(results),
        "failed_chapters": failed,
        "passed_chapters": [c for c in sorted(results) if c not in failed],
        "chapter_results": results,
    }


def apply_patch_proposals(proposal_paths: list[str | Path], *, repo_root: str | Path, apply: bool, run_id: str, output_dir: str | Path) -> dict[str, Any]:
    repo = Path(repo_root)
    proposals = [load_json(p) for p in proposal_paths]
    changed: list[str] = []
    failed: list[str] = []
    rejected: list[dict[str, Any]] = []
    seen_targets: set[str] = set()
    applied_proposals: list[dict[str, Any]] = []
    for proposal in proposals:
        target_path = str(proposal.get("target_path") or "")
        if target_path in seen_targets:
            rejected.append({"event_id": proposal.get("event_id"), "reason": "target_conflict", "target_path": target_path})
            continue
        seen_targets.add(target_path)
        target = safe_target(repo, target_path)
        if target is None:
            rejected.append({"event_id": proposal.get("event_id"), "reason": "invalid_target_path", "target_path": target_path})
            continue
        markdown = str(proposal.get("proposed_markdown") or "")
        if not markdown.strip():
            rejected.append({"event_id": proposal.get("event_id"), "reason": "empty_markdown", "target_path": target_path})
            continue
        tmp_result = evaluate_public_chapter_text(markdown, chapter_title_from_target(target_path), chapter_id=proposal.get("chapter_id") or chapter_id_from_path(target_path))
        if not tmp_result.get("ok"):
            rejected.append({"event_id": proposal.get("event_id"), "reason": "changed_chapter_public_proof_failed", "failed_checks": tmp_result.get("failed_checks"), "target_path": target_path})
            continue
        if apply:
            before = target.read_bytes() if target.exists() else b""
            target.parent.mkdir(parents=True, exist_ok=True)
            desired = markdown.rstrip() + "\n"
            if before == desired.encode("utf-8"):
                rejected.append({"event_id": proposal.get("event_id"), "reason": "proposal_identical_to_existing", "target_path": target_path})
                continue
            target.write_text(desired, encoding="utf-8")
            if proposal.get("operation") == "create_chapter":
                public_nav_allowed = proposal.get("publication_stage") == "chapter_matured" or bool(proposal.get("public_nav_allowed"))
                ensure_nav_entry(repo / "mkdocs.yml", proposal.get("nav_entry") or {}, public_nav_allowed=public_nav_allowed)
            after = target.read_bytes()
            if before != after:
                changed.append(target_path)
        applied_proposals.append(proposal)
    changed_proofs: dict[str, Any] = {}
    for target_path in changed:
        target = repo / target_path
        result = proof_for_file(target, target_path)
        changed_proofs[target_path] = result
        if not result.get("ok"):
            failed.append(f"changed_chapter_public_proof_failed:{target_path}")
    full = full_manuscript_report(repo) if (repo / "docs" / "book").exists() else {"ok": True, "failed_chapters": []}
    report = {
        "mode": "event_driven_book_publication_joiner",
        "run_id": run_id,
        "generated_at": utc_now(),
        "ok": not failed and not any(r.get("reason") == "invalid_target_path" for r in rejected),
        "publication_applied": bool(changed),
        "publication_decision": "event_driven_publication_applied" if changed else "event_driven_no_content_delta",
        "no_content_delta": not bool(changed),
        "changed_files": changed,
        "applied_patch_count": len(applied_proposals),
        "rejected_patches": rejected,
        "failed_checks": failed,
        "changed_chapter_public_proof": changed_proofs,
        "full_manuscript_proof": full,
        "all_chapters_public_proof_blocking": False,
        "human_in_loop_dependency_added": False,
        "raw_text_publication_allowed": False,
    }
    outdir = Path(output_dir)
    write_json(outdir / f"{run_id}-event-driven-publication.json", report)
    return report


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--proposal", action="append", default=[])
    ap.add_argument("--proposals-glob")
    ap.add_argument("--repo-root", default=".")
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--output-dir", default="reports/editorial")
    ap.add_argument("--output-json")
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    proposals = [Path(p) for p in args.proposal]
    if args.proposals_glob:
        proposals.extend(sorted(Path(args.repo_root).glob(args.proposals_glob)))
    report = apply_patch_proposals(proposals, repo_root=args.repo_root, apply=args.apply, run_id=args.run_id, output_dir=args.output_dir)
    if args.output_json:
        write_json(args.output_json, report)
    print(json.dumps({"ok": report["ok"], "changed_files": report["changed_files"], "all_chapters_public_proof_blocking": False}, sort_keys=True))
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
