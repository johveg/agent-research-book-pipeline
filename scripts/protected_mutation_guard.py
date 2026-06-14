#!/usr/bin/env python3
"""Protected mutation guard and reduced verification profiles.

Run 35 control-plane safety utility. It snapshots protected workspace state,
compares before/after snapshots, and fail-closes on unexpected writes. Snapshot
and compare are report-only operations: no SQLite writes, no source registry/raw
capture/docs/book/schema/daily-worker mutation, and no production human-review
dependency.
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = ".var/book.sqlite"
DEFAULT_PROTECTED_PATHS = [
    "data/source_registry.json",
    "raw",
    "docs/book",
    "docs/entities",
    "docs/research/claims.md",
    "data/schema.sql",
    "scripts/daily_book_worker.py",
    ".var/book.sqlite",
]

DB_TABLES = ["source_notes", "claims", "editorial_reviews"]
STATUS_HASH_QUERIES = {
    "source_status_hash": "SELECT id, quality_score, privacy_publication_status, duplicate_status FROM sources ORDER BY id",
    "claim_status_hash": "SELECT id, status, publication_decision, contradiction_status FROM claims ORDER BY id",
    "editorial_review_hash": "SELECT id, run_id, review_type, status, summary, report_path, created_at FROM editorial_reviews ORDER BY id",
    "source_notes_hash": "SELECT id, source_id, note_type, created_at FROM source_notes ORDER BY id",
}
HARD_FLAGS = [
    "author_allowed",
    "publication_approved",
    "eligible_for_claim_insertion",
    "eligible_for_authoring",
    "eligible_for_publication",
    "chapter_update_allowed",
]
FORBIDDEN_HUMAN_TERMS = ["human_review_required", "requires_human_review"]

PROFILES: dict[str, dict[str, Any]] = {
    "report_only": {
        "allowed": ["reports/**"],
        "allow_db": {},
        "future_disabled": False,
    },
    "config_only": {
        "allowed": ["config/closed_loop_state_machine.json", "config/reasoning_models.json", "reports/**"],
        "allow_db": {},
        "future_disabled": False,
    },
    "control_plane_code_only": {
        "allowed": [
            "scripts/closed_loop_*.py",
            "scripts/protected_mutation_guard.py",
            "scripts/closed_loop_verification_profiles.py",
            "scripts/analyze_*closed_loop*.py",
            "tests/test_closed_loop_*.py",
            "tests/test_protected_mutation_guard.py",
            "tests/test_closed_loop_verification_profiles.py",
            "tests/test_analyze_*closed_loop*.py",
            "reports/**",
        ],
        "allow_db": {},
        "future_disabled": False,
    },
    "db_write_source_notes_only": {
        "allowed": ["reports/**"],
        "allow_db": {"counts": ["source_notes"], "hashes": ["source_notes_hash"]},
        "future_disabled": False,
    },
    "db_write_claims_only": {
        "allowed": ["reports/**"],
        "allow_db": {"counts": ["claims"], "hashes": []},
        "future_disabled": False,
    },
    "docs_book_write": {
        "allowed": ["reports/**", "docs/book/**"],
        "allow_db": {},
        "future_disabled": True,
        "required_gates": ["chapter_update_allowed", "publication_approved"],
    },
    "schema_change": {
        "allowed": ["reports/**", "data/schema.sql"],
        "allow_db": {},
        "future_disabled": True,
    },
    "daily_worker_change": {
        "allowed": ["reports/**", "scripts/daily_book_worker.py"],
        "allow_db": {},
        "future_disabled": True,
    },
    "full_publication_gate": {
        "allowed": ["reports/**", "docs/book/**"],
        "allow_db": {},
        "future_disabled": True,
        "required_gates": ["publication_approved", "chapter_update_allowed"],
    },
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def resolve(root: str | Path, path: str | Path) -> Path:
    p = Path(path)
    return p if p.is_absolute() else Path(root) / p


def sha256_file(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def snapshot_path_hashes(root: str | Path = ROOT, paths: list[str] | None = None) -> dict[str, Any]:
    root = Path(root)
    result: dict[str, Any] = {}
    for rel in paths or DEFAULT_PROTECTED_PATHS:
        path = resolve(root, rel)
        entry: dict[str, Any] = {"exists": path.exists(), "files": {}, "tree_hash": None}
        if path.exists():
            if path.is_file():
                entry["files"] = {".": sha256_file(path)}
            else:
                files = {}
                for file in sorted(p for p in path.rglob("*") if p.is_file()):
                    files[str(file.relative_to(path))] = sha256_file(file)
                entry["files"] = files
            entry["tree_hash"] = hashlib.sha256(json.dumps(entry["files"], sort_keys=True).encode()).hexdigest()
        result[rel] = entry
    return result


def snapshot_git_diff_names(root: str | Path = ROOT) -> dict[str, list[str]]:
    root = Path(root)
    def run(args: list[str]) -> list[str]:
        try:
            out = subprocess.check_output(args, cwd=root, text=True, stderr=subprocess.DEVNULL)
            return [line for line in out.splitlines() if line.strip()]
        except Exception:
            return []
    return {
        "git_diff_names": run(["git", "diff", "--name-only"]),
        "git_status_short": run(["git", "status", "--short"]),
    }


def snapshot_db_state(db_path: str | Path = DEFAULT_DB_PATH, root: str | Path = ROOT) -> dict[str, Any]:
    path = resolve(root, db_path)
    state = {"path": str(path), "exists": path.exists(), "counts": {}, "hashes": {}}
    if not path.exists():
        return state
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        con.execute("PRAGMA query_only = ON")
        for table in DB_TABLES:
            state["counts"][table] = int(con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
        for name, sql in STATUS_HASH_QUERIES.items():
            rows = [tuple(r) for r in con.execute(sql).fetchall()]
            state["hashes"][name] = hashlib.sha256(json.dumps(rows, sort_keys=True, default=str).encode()).hexdigest()
    finally:
        con.close()
    return state


def snapshot_workspace_state(
    root: str | Path = ROOT,
    db_path: str | Path = DEFAULT_DB_PATH,
    protected_paths: list[str] | None = None,
) -> dict[str, Any]:
    git = snapshot_git_diff_names(root)
    return {
        "generated_at": utc_now(),
        "root": str(Path(root).resolve()),
        "git_diff_names": git["git_diff_names"],
        "git_status_short": git["git_status_short"],
        "db": snapshot_db_state(db_path, root),
        "path_hashes": snapshot_path_hashes(root, protected_paths),
        "report_safety_scan": {},
    }


def _status_path(line: str) -> str:
    # porcelain short: XY path or XY old -> new
    path = line[3:] if len(line) > 3 else line.strip()
    if " -> " in path:
        path = path.split(" -> ", 1)[1]
    return path.strip()


def _changed_paths(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    before_status = set(before.get("git_status_short", []))
    after_status = set(after.get("git_status_short", []))
    new_status_paths = {_status_path(line) for line in after_status - before_status}
    before_diff = set(before.get("git_diff_names", []))
    after_diff = set(after.get("git_diff_names", []))
    new_diff_paths = after_diff - before_diff
    return sorted(p for p in (new_status_paths | new_diff_paths) if p)


def _matches(path: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(path, pat) or (pat.endswith("/**") and path.startswith(pat[:-3] + "/")) for pat in patterns)


def classify_changed_paths(changed_paths: list[str], profile: str) -> dict[str, list[str]]:
    spec = PROFILES.get(profile)
    if not spec or spec.get("future_disabled"):
        return {"allowed_changed_paths": [], "unexpected_changed_paths": sorted(changed_paths)}
    allowed = [p for p in changed_paths if _matches(p, spec["allowed"])]
    unexpected = [p for p in changed_paths if p not in allowed]
    return {"allowed_changed_paths": sorted(allowed), "unexpected_changed_paths": sorted(unexpected)}


def _delta_dict(before: dict[str, Any], after: dict[str, Any]) -> dict[str, int]:
    keys = set(before) | set(after)
    return {k: int(after.get(k, 0)) - int(before.get(k, 0)) for k in sorted(keys) if int(after.get(k, 0)) - int(before.get(k, 0)) != 0}


def _hash_delta(before: dict[str, Any], after: dict[str, Any]) -> dict[str, bool]:
    keys = set(before) | set(after)
    return {k: before.get(k) != after.get(k) for k in sorted(keys) if before.get(k) != after.get(k)}


def _protected_delta(before: dict[str, Any], after: dict[str, Any]) -> dict[str, bool]:
    b = before.get("path_hashes", {})
    a = after.get("path_hashes", {})
    keys = set(b) | set(a)
    return {k: b.get(k, {}).get("tree_hash") != a.get(k, {}).get("tree_hash") for k in sorted(keys)}


def _scan_report_flags(snapshot: dict[str, Any]) -> tuple[bool, dict[str, bool]]:
    scan = snapshot.get("report_safety_scan") if isinstance(snapshot.get("report_safety_scan"), dict) else {}
    human = bool(scan.get("human_in_loop_dependency_added"))
    hard = {flag: False for flag in HARD_FLAGS}
    hard.update({k: bool(v) for k, v in (scan.get("hard_flags_changed") or {}).items() if k in HARD_FLAGS})
    return human, hard


def _scan_changed_report_files(root: Path, changed_paths: list[str]) -> tuple[bool, dict[str, bool]]:
    human = False
    flags = {flag: False for flag in HARD_FLAGS}
    for rel in changed_paths:
        if not rel.startswith("reports/") or not rel.endswith(".json"):
            continue
        path = root / rel
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        blob = json.dumps(data, sort_keys=True, default=str).lower()
        if any(term in blob for term in FORBIDDEN_HUMAN_TERMS):
            human = True
        for flag in HARD_FLAGS:
            if _contains_true_flag(data, flag):
                flags[flag] = True
        if data.get("human_in_loop_dependency_added") is True:
            human = True
    return human, flags


def _contains_true_flag(obj: Any, flag: str) -> bool:
    if isinstance(obj, dict):
        if obj.get(flag) is True:
            return True
        return any(_contains_true_flag(v, flag) for v in obj.values())
    if isinstance(obj, list):
        return any(_contains_true_flag(v, flag) for v in obj)
    return False


def validate_allowed_write_scope(report: dict[str, Any]) -> dict[str, Any]:
    failed = []
    if report.get("unexpected_changed_paths"):
        failed.append("unexpected_changed_paths")
    if any(report.get("protected_path_delta", {}).values()):
        failed.append("protected_path_delta")
    if report.get("human_in_loop_dependency_added"):
        failed.append("human_in_loop_dependency_added")
    if any(report.get("hard_flags_changed", {}).values()):
        failed.append("hard_flags_changed")
    return {"ok": not failed, "failed_checks": failed}


def compare_snapshots(before: dict[str, Any], after: dict[str, Any], profile: str, root: str | Path = ROOT) -> dict[str, Any]:
    changed_paths = _changed_paths(before, after)
    classified = classify_changed_paths(changed_paths, profile)
    db_delta = _delta_dict(before.get("db", {}).get("counts", {}), after.get("db", {}).get("counts", {}))
    status_hash_delta = _hash_delta(before.get("db", {}).get("hashes", {}), after.get("db", {}).get("hashes", {}))
    protected_path_delta = _protected_delta(before, after)
    spec = PROFILES.get(profile)
    failed: list[str] = []
    if spec is None:
        failed.append("unknown_profile")
        spec = {"allow_db": {}, "future_disabled": False}
    if spec.get("future_disabled"):
        failed.append("future_profile_disabled")

    allowed_counts = set(spec.get("allow_db", {}).get("counts", []))
    allowed_hashes = set(spec.get("allow_db", {}).get("hashes", []))
    for table in db_delta:
        if table not in allowed_counts:
            failed.append(f"unexpected_db_count_delta:{table}")
    for name in status_hash_delta:
        if name not in allowed_hashes:
            failed.append(f"unexpected_status_hash_delta:{name}")

    root_path = Path(root)
    scan_human, scan_flags = _scan_report_flags(after)
    file_human, file_flags = _scan_changed_report_files(root_path, changed_paths)
    human = scan_human or file_human
    hard_flags = {flag: bool(scan_flags.get(flag) or file_flags.get(flag)) for flag in HARD_FLAGS}
    if human:
        failed.append("human_in_loop_dependency_added")
    for flag, value in hard_flags.items():
        if value:
            failed.append(f"hard_flag_true:{flag}")

    if classified["unexpected_changed_paths"]:
        failed.append("unexpected_changed_paths")

    # Protected hashes changing is fail-closed unless the profile is the explicit
    # future disabled profile; those profiles are still not usable in Run 35.
    protected_changed = {k: v for k, v in protected_path_delta.items() if v}
    for rel in protected_changed:
        failed.append(f"protected_path_changed:{rel}")

    report = {
        "ok": not failed,
        "profile": profile,
        "changed_paths": changed_paths,
        "allowed_changed_paths": classified["allowed_changed_paths"],
        "unexpected_changed_paths": classified["unexpected_changed_paths"],
        "db_delta": db_delta,
        "status_hash_delta": status_hash_delta,
        "protected_path_delta": protected_path_delta,
        "source_registry_changed": protected_path_delta.get("data/source_registry.json", False),
        "raw_changed": protected_path_delta.get("raw", False),
        "docs_book_changed": protected_path_delta.get("docs/book", False),
        "docs_entities_changed": protected_path_delta.get("docs/entities", False),
        "docs_claims_changed": protected_path_delta.get("docs/research/claims.md", False),
        "schema_changed": protected_path_delta.get("data/schema.sql", False),
        "daily_worker_changed": protected_path_delta.get("scripts/daily_book_worker.py", False),
        "human_in_loop_dependency_added": human,
        "hard_flags_changed": hard_flags,
        "failed_checks": sorted(set(failed)),
        "recommendation": "proceed_with_profile_scope" if not failed else "stop_and_investigate_unexpected_mutation",
        "generated_at": utc_now(),
    }
    scope = validate_allowed_write_scope(report)
    report["scope_validation"] = scope
    if not scope["ok"] and report["ok"]:
        report["ok"] = False
        report["failed_checks"] = sorted(set(report["failed_checks"] + scope["failed_checks"]))
    return report


def build_mutation_guard_report(before: dict[str, Any], after: dict[str, Any], profile: str, root: str | Path = ROOT) -> dict[str, Any]:
    return compare_snapshots(before, after, profile, root)


def write_mutation_guard_report(report: dict[str, Any], output: str | Path) -> dict[str, str]:
    out = Path(output)
    if not out.is_absolute():
        out = ROOT / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    md = out.with_suffix(".md")
    lines = [
        "# Protected mutation guard report",
        "",
        f"Generated: {report.get('generated_at')}",
        "",
        f"- ok: `{report.get('ok')}`",
        f"- profile: `{report.get('profile')}`",
        f"- recommendation: `{report.get('recommendation')}`",
        f"- human_in_loop_dependency_added: `{report.get('human_in_loop_dependency_added')}`",
        "",
        "## Changed paths",
        "",
        "Allowed:",
        *[f"- `{p}`" for p in report.get("allowed_changed_paths", [])],
        "",
        "Unexpected:",
        *[f"- `{p}`" for p in report.get("unexpected_changed_paths", [])],
        "",
        "## DB delta",
        "",
        "```json",
        json.dumps(report.get("db_delta", {}), indent=2, sort_keys=True),
        "```",
        "",
        "## Failed checks",
        "",
        *[f"- `{x}`" for x in report.get("failed_checks", [])],
    ]
    md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"json": str(out), "markdown": str(md)}


def load_snapshot(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Protected mutation guard")
    sub = parser.add_subparsers(dest="command", required=True)
    snap = sub.add_parser("snapshot")
    snap.add_argument("--output", required=True)
    snap.add_argument("--root", default=str(ROOT))
    snap.add_argument("--db-path", default=DEFAULT_DB_PATH)
    comp = sub.add_parser("compare")
    comp.add_argument("--before", required=True)
    comp.add_argument("--after", required=True)
    comp.add_argument("--profile", required=True)
    comp.add_argument("--output", required=True)
    comp.add_argument("--root", default=str(ROOT))
    args = parser.parse_args(argv)
    if args.command == "snapshot":
        data = snapshot_workspace_state(args.root, args.db_path)
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
        print(json.dumps({"ok": True, "output": str(out)}, sort_keys=True))
        return 0
    if args.command == "compare":
        before = load_snapshot(args.before)
        after = load_snapshot(args.after)
        report = build_mutation_guard_report(before, after, args.profile, args.root)
        paths = write_mutation_guard_report(report, args.output)
        print(json.dumps({"ok": report["ok"], "profile": args.profile, "output_json": paths["json"]}, sort_keys=True))
        return 0 if report["ok"] else 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
