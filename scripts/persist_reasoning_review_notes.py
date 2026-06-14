#!/usr/bin/env python3
"""Run 11 disabled-by-default persistence of reasoning review filing notes.

Persists only eligible Run 10 source-support review items into source_notes when
explicitly invoked with --write-source-notes. Default mode is report-only.

Safety boundaries:
- no claims inserts
- no editorial_reviews inserts
- no source/claim/editorial status changes
- no docs/book changes
- no schema migration
- source_notes only, compact deterministic JSON
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from research_common import DB_PATH as DEFAULT_DB_PATH, ROOT as REPO_ROOT, sha256_text, write_json  # noqa: E402

NOTE_TYPE = "reasoning_review_filing_draft"
NOTE_SCHEMA = "reasoning_review_filing_draft.v1"
MODE = "persist_reasoning_review_notes"
REQUIRED_SOURCE_NOTE_COLUMNS = {"id", "source_id", "note", "note_type", "created_at"}
REQUIRED_PROVENANCE = [
    "source_review_id",
    "filing_evaluation_id",
    "packet_item_id",
    "source_id",
    "source_card_id",
    "semantic_object_id",
    "quality_review_id",
]


class PersistNotesError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def db_path() -> Path:
    override = os.environ.get("TEREFO_BOOK_DB_PATH", "").strip()
    if override:
        return Path(override)
    return DEFAULT_DB_PATH


def resolve(path: str) -> Path:
    p = Path(path)
    return p if p.is_absolute() else REPO_ROOT / p


def repo_relative(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def clean_text(value: Any, max_len: int = 420) -> str:
    text = " ".join(str(value or "").split())
    if len(text) > max_len:
        return text[: max_len - 1].rstrip() + "…"
    return text


def listify(value: Any, max_len: int = 180) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [clean_text(v, max_len) for v in value if clean_text(v, max_len)]
    if isinstance(value, str):
        return [clean_text(value, max_len)] if value.strip() else []
    return [clean_text(value, max_len)]


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise PersistNotesError(f"missing source-support review report: {path}")
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PersistNotesError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(obj, dict):
        raise PersistNotesError("source-support review report must be a JSON object")
    return obj


def validate_report(report: dict[str, Any]) -> None:
    if report.get("mode") != "source_support_review":
        raise PersistNotesError("input report mode must be source_support_review")
    if report.get("author_allowed") is not False or report.get("publication_approved") is not False or report.get("advisory_only") is not True:
        raise PersistNotesError("input report safety flags invalid")
    if report.get("db_modified") not in (False, None):
        raise PersistNotesError("input report indicates DB modification; refusing persistence")
    if not isinstance(report.get("source_reviews"), list):
        raise PersistNotesError("input report source_reviews must be a list")


def connect_db(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def inspect_schema(con: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = [dict(r) for r in con.execute("PRAGMA table_info(source_notes)")]
    cols = {r["name"] for r in rows}
    if not REQUIRED_SOURCE_NOTE_COLUMNS.issubset(cols):
        raise PersistNotesError(f"source_notes schema incompatible; found columns {sorted(cols)}")
    return rows


def table_count(con: sqlite3.Connection, table: str, where: str = "", params: tuple[Any, ...] = ()) -> int:
    sql = f"SELECT COUNT(*) FROM {table}"
    if where:
        sql += f" WHERE {where}"
    return int(con.execute(sql, params).fetchone()[0])


def status_snapshots(con: sqlite3.Connection) -> dict[str, str]:
    specs = {
        "sources_status_hash": "SELECT id, quality_score, privacy_publication_status, duplicate_status FROM sources ORDER BY id",
        "claims_status_hash": "SELECT id, status, publication_decision, contradiction_status FROM claims ORDER BY id",
        "editorial_reviews_hash": "SELECT id, run_id, review_type, status, summary, report_path, created_at FROM editorial_reviews ORDER BY id",
    }
    out: dict[str, str] = {}
    for name, sql in specs.items():
        try:
            rows = [dict(r) for r in con.execute(sql)]
        except sqlite3.Error:
            rows = []
        out[name] = sha256_text(json.dumps(rows, sort_keys=True, ensure_ascii=False))
    return out


def validate_item_safety(item: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    missing = [k for k in REQUIRED_PROVENANCE if not item.get(k)]
    if missing:
        reasons.append("missing_provenance")
    if item.get("author_allowed") is not False or item.get("publication_approved") is not False or item.get("advisory_only") is not True:
        reasons.append("missing_safety_flags")
    return reasons


def skip_reason(item: dict[str, Any], *, include_corroboration_required: bool, include_unsupported: bool) -> str | None:
    safety = validate_item_safety(item)
    if safety:
        return safety[0]
    support = item.get("source_support_decision")
    evidence = item.get("evidence_use_decision")
    next_stage = item.get("next_stage_recommendation")
    corr = item.get("corroboration_decision")
    if support == "unsupported" and not include_unsupported:
        return "unsupported"
    if support == "unclear":
        return "unclear"
    if evidence == "needs_corroboration_before_filing" or next_stage == "run_corroboration_research" or corr == "corroboration_required":
        if not include_corroboration_required:
            return "needs_corroboration"
    if next_stage == "needs_source_review" or evidence == "needs_source_review":
        return "needs_source_review"
    eligible = (
        next_stage == "eligible_for_filing_persistence"
        and evidence in {"eligible_as_caveat_only", "eligible_for_filing_later"}
        and support in {"supported", "partially_supported"}
        and item.get("publication_approved") is False
        and item.get("author_allowed") is False
        and item.get("advisory_only") is True
    )
    if not eligible:
        return "not_eligible"
    return None


def build_note_json(item: dict[str, Any], run_id: str) -> dict[str, Any]:
    note = {
        "note_schema": NOTE_SCHEMA,
        "run_id": run_id,
        "source_review_id": item["source_review_id"],
        "filing_evaluation_id": item["filing_evaluation_id"],
        "packet_item_id": item["packet_item_id"],
        "source_id": item["source_id"],
        "source_card_id": item["source_card_id"],
        "semantic_object_id": item["semantic_object_id"],
        "quality_review_id": item["quality_review_id"],
        "source_title": clean_text(item.get("source_title"), 160),
        "source_type": clean_text(item.get("source_type"), 80),
        "publisher": clean_text(item.get("publisher"), 120),
        "quality_score": clean_text(item.get("quality_score"), 40),
        "privacy_publication_status": clean_text(item.get("privacy_publication_status"), 80),
        "canonical_url_available": bool(item.get("canonical_url_available")),
        "semantic_object_type": clean_text(item.get("semantic_object_type"), 80),
        "semantic_object_text": clean_text(item.get("semantic_object_text"), 420),
        "filing_decision": clean_text(item.get("filing_decision"), 80),
        "novelty_decision": clean_text(item.get("novelty_decision"), 80),
        "source_support_decision": item.get("source_support_decision"),
        "corroboration_decision": item.get("corroboration_decision"),
        "evidence_use_decision": item.get("evidence_use_decision"),
        "next_stage_recommendation": item.get("next_stage_recommendation"),
        "support_rationale": clean_text(item.get("support_rationale"), 500),
        "corroboration_rationale": clean_text(item.get("corroboration_rationale"), 500),
        "corroboration_questions": listify(item.get("corroboration_questions")),
        "blockers": listify(item.get("blockers")),
        "risk_flags": listify(item.get("risk_flags")),
        "required_editor_decisions": listify(item.get("required_editor_decisions")),
        "eligible_for_filing_persistence": True,
        "eligible_as_caveat_only": item.get("evidence_use_decision") == "eligible_as_caveat_only",
        "author_allowed": False,
        "publication_approved": False,
        "advisory_only": True,
        "input_hash": item.get("input_hash"),
        "output_hash": item.get("output_hash"),
        "llm_used": item.get("llm_used") is True,
        "provider": item.get("provider"),
        "model": item.get("model"),
        "bridge": item.get("bridge"),
        "reasoning_status": item.get("reasoning_status"),
        "persisted_by": "persist_reasoning_review_notes.py",
        "persisted_note_type": NOTE_TYPE,
    }
    return note


def note_id_for(note: dict[str, Any]) -> str:
    seed = f"{NOTE_TYPE}:{note['source_review_id']}:{note['output_hash']}"
    return "note_" + sha256_text(seed)[:24]


def select_items(report: dict[str, Any], args: argparse.Namespace) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    selected: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for item in report["source_reviews"]:
        if not isinstance(item, dict):
            skipped.append({"source_review_id": "unknown", "skip_reason": "not_object"})
            continue
        reason = skip_reason(
            item,
            include_corroboration_required=args.include_corroboration_required,
            include_unsupported=args.include_unsupported,
        )
        if reason is None:
            selected.append(item)
        else:
            skipped.append({
                "source_review_id": item.get("source_review_id", ""),
                "filing_evaluation_id": item.get("filing_evaluation_id", ""),
                "source_id": item.get("source_id", ""),
                "semantic_object_id": item.get("semantic_object_id", ""),
                "source_support_decision": item.get("source_support_decision", ""),
                "evidence_use_decision": item.get("evidence_use_decision", ""),
                "next_stage_recommendation": item.get("next_stage_recommendation", ""),
                "skip_reason": reason,
            })
    return selected, skipped


def persist_notes(con: sqlite3.Connection, selected_rows: list[dict[str, Any]], run_id: str, *, write: bool) -> tuple[list[dict[str, Any]], dict[str, int]]:
    counts = {"inserted": 0, "skipped_existing": 0, "failed": 0, "conflicted": 0}
    output: list[dict[str, Any]] = []
    now = utc_now()
    for item in selected_rows:
        note = build_note_json(item, run_id)
        note_text = json.dumps(note, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        note_id = note_id_for(note)
        result = "would_insert"
        existing = con.execute("SELECT note FROM source_notes WHERE id = ?", (note_id,)).fetchone()
        if existing:
            if existing["note"] == note_text:
                counts["skipped_existing"] += 1
                result = "skipped_existing"
            else:
                counts["conflicted"] += 1
                result = "conflict"
                raise PersistNotesError(f"conflicting existing note id {note_id} for {note['source_review_id']}")
        elif write:
            con.execute(
                "INSERT INTO source_notes (id, source_id, note, note_type, created_at) VALUES (?, ?, ?, ?, ?)",
                (note_id, note["source_id"], note_text, NOTE_TYPE, now),
            )
            counts["inserted"] += 1
            result = "inserted"
        output.append({
            "note_id": note_id,
            "source_review_id": note["source_review_id"],
            "filing_evaluation_id": note["filing_evaluation_id"],
            "source_id": note["source_id"],
            "semantic_object_id": note["semantic_object_id"],
            "source_support_decision": note["source_support_decision"],
            "evidence_use_decision": note["evidence_use_decision"],
            "next_stage_recommendation": note["next_stage_recommendation"],
            "note_type": NOTE_TYPE,
            "persistence_result": result,
            "author_allowed": False,
            "publication_approved": False,
            "advisory_only": True,
        })
    return output, counts


def recommendation(payload: dict[str, Any]) -> dict[str, Any]:
    if payload["notes_inserted"] == 2 and any(i.get("skip_reason") == "needs_corroboration" for i in payload["skipped_items"]):
        rec = "controlled_corroboration_research_for_two_items_requiring_corroboration"
    elif payload["notes_inserted"] + payload["notes_skipped_existing"] >= 2:
        rec = "controlled_corroboration_research_for_two_items_requiring_corroboration"
    elif payload["items_selected_for_persistence"] > 0:
        rec = "rerun_idempotent_persistence_with_explicit_write_source_notes"
    else:
        rec = "run_larger_source_selection_regeneration"
    return {
        "recommendation": rec,
        "conditions": [
            "do not build narrative packets until corroboration-required items are resolved or explicitly excluded",
            "do not insert claims or approve publication",
            "keep any live corroboration run controlled and report-only by default",
        ],
    }


def md_cell(v: Any) -> str:
    return clean_text(v, 90).replace("|", "\\|")


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [f"# Persisted review notes: {payload['run_id']}", "", "## Executive summary", ""]
    for k in ["input_report", "source_reviews_available", "eligible_items_available", "items_selected_for_persistence", "write_source_notes_requested", "db_modified", "notes_inserted", "notes_skipped_existing", "notes_failed", "notes_conflicted"]:
        lines.append(f"- {k}: `{payload[k]}`")
    lines += ["- Safety: source_notes-only opt-in persistence; no claims/editorial_reviews/status/chapter/schema/worker/allowlist changes; not author-approved; not publication-approved.", "", "## Selected items", "", "| source review id | filing evaluation id | source id | semantic object id | source support | evidence use | next stage | note type | persistence result |", "|---|---|---|---|---|---|---|---|---|"]
    for item in payload["selected_items"]:
        lines.append("| " + " | ".join([md_cell(item.get("source_review_id")), md_cell(item.get("filing_evaluation_id")), md_cell(item.get("source_id")), md_cell(item.get("semantic_object_id")), md_cell(item.get("source_support_decision")), md_cell(item.get("evidence_use_decision")), md_cell(item.get("next_stage_recommendation")), md_cell(item.get("note_type")), md_cell(item.get("persistence_result"))]) + " |")
    lines += ["", "## Skipped items", "", "| source review id | filing evaluation id | source id | semantic object id | source support | evidence use | next stage | reason |", "|---|---|---|---|---|---|---|---|"]
    for item in payload["skipped_items"]:
        lines.append("| " + " | ".join([md_cell(item.get("source_review_id")), md_cell(item.get("filing_evaluation_id")), md_cell(item.get("source_id")), md_cell(item.get("semantic_object_id")), md_cell(item.get("source_support_decision")), md_cell(item.get("evidence_use_decision")), md_cell(item.get("next_stage_recommendation")), md_cell(item.get("skip_reason"))]) + " |")
    lines += ["", "## Persistence details", "", f"- source_notes schema used: `{payload['source_notes_schema_found']}`", "- Deterministic ID strategy: `note_<sha256(note_type + source_review_id + output_hash)[:24]>`", f"- Idempotency result: inserted `{payload['notes_inserted']}`, skipped existing `{payload['notes_skipped_existing']}`, conflicted `{payload['notes_conflicted']}`", "- Transaction behavior: one transaction; rollback on validation failure, duplicate conflict, or any write error.", "", "## Safety assessment", ""]
    for k in ["db_modified", "db_write_scope", "source_notes_count_before", "source_notes_count_after", "claims_inserted", "editorial_reviews_inserted", "chapters_modified", "statuses_modified", "schema_modified", "daily_worker_modified", "commit_allowlist_modified", "raw_private_material_written", "long_source_excerpt_written", "author_allowed", "publication_approved", "advisory_only"]:
        lines.append(f"- {k}: `{payload[k]}`")
    lines += ["", "## Recommendation for Run 12", "", f"- Recommendation: `{payload['next_run_recommendation']['recommendation']}`"]
    for condition in payload["next_run_recommendation"]["conditions"]:
        lines.append(f"- Condition: {condition}")
    return "\n".join(lines) + "\n"


def write_reports(payload: dict[str, Any], output_dir: Path, suffix: str, *, json_only: bool, markdown_only: bool) -> dict[str, str]:
    output_dir = output_dir if output_dir.is_absolute() else REPO_ROOT / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{payload['run_id']}-persisted-review-notes-{suffix}" if suffix else f"{payload['run_id']}-persisted-review-notes"
    json_path = output_dir / f"{stem}.json"
    md_path = output_dir / f"{stem}.md"
    outputs = {"json": repo_relative(json_path), "markdown": repo_relative(md_path)}
    payload["output_paths"] = outputs
    if not markdown_only:
        write_json(json_path, payload)
    if not json_only:
        md_path.write_text(render_markdown(payload), encoding="utf-8")
    return outputs


def build_payload(args: argparse.Namespace, report: dict[str, Any]) -> dict[str, Any]:
    path = db_path()
    selected_source_reviews, skipped_items = select_items(report, args)
    with connect_db(path) as con:
        schema = inspect_schema(con)
        source_notes_before = table_count(con, "source_notes")
        claims_before = table_count(con, "claims")
        editorial_before = table_count(con, "editorial_reviews")
        status_before = status_snapshots(con)
        selected_items: list[dict[str, Any]] = []
        counts = {"inserted": 0, "skipped_existing": 0, "failed": 0, "conflicted": 0}
        write = bool(args.write_source_notes and not args.dry_run)
        if write:
            try:
                con.execute("BEGIN")
                selected_items, counts = persist_notes(con, selected_source_reviews, args.run_id, write=True)
                con.commit()
            except Exception:
                con.rollback()
                raise
        else:
            selected_items, counts = persist_notes(con, selected_source_reviews, args.run_id, write=False)
        source_notes_after = table_count(con, "source_notes")
        claims_after = table_count(con, "claims")
        editorial_after = table_count(con, "editorial_reviews")
        status_after = status_snapshots(con)
    db_modified = source_notes_after != source_notes_before
    db_write_scope = "source_notes" if db_modified else "none"
    reason_counts = dict(Counter(i.get("skip_reason", "unknown") for i in skipped_items))
    payload: dict[str, Any] = {
        "run_id": args.run_id if args.run_id != "latest" else report.get("run_id", "latest"),
        "generated_at": utc_now(),
        "mode": MODE,
        "input_report": repo_relative(resolve(args.source_support_review_report)),
        "filing_novelty_report": repo_relative(resolve(args.filing_novelty_report)) if args.filing_novelty_report else "",
        "editor_packet_report": repo_relative(resolve(args.editor_packet_report)) if args.editor_packet_report else "",
        "source_reviews_available": len(report.get("source_reviews", [])),
        "eligible_items_available": len(selected_source_reviews),
        "items_selected_for_persistence": len(selected_source_reviews),
        "write_source_notes_requested": bool(args.write_source_notes),
        "dry_run": bool(args.dry_run),
        "db_modified": db_modified,
        "db_write_scope": db_write_scope,
        "source_notes_schema_found": [{"name": r["name"], "type": r["type"], "notnull": r["notnull"], "pk": r["pk"]} for r in schema],
        "source_notes_count_before": source_notes_before,
        "source_notes_count_after": source_notes_after,
        "notes_inserted": counts["inserted"],
        "notes_skipped_existing": counts["skipped_existing"],
        "notes_failed": counts["failed"],
        "notes_conflicted": counts["conflicted"],
        "idempotent": counts["conflicted"] == 0 and counts["failed"] == 0,
        "note_type": NOTE_TYPE,
        "claims_count_before": claims_before,
        "claims_count_after": claims_after,
        "editorial_reviews_count_before": editorial_before,
        "editorial_reviews_count_after": editorial_after,
        "claims_inserted": 0,
        "editorial_reviews_inserted": 0,
        "chapters_modified": False,
        "statuses_modified": status_before != status_after,
        "schema_modified": False,
        "daily_worker_modified": False,
        "commit_allowlist_modified": False,
        "raw_private_material_written": False,
        "long_source_excerpt_written": False,
        "author_allowed": False,
        "publication_approved": False,
        "advisory_only": True,
        "selected_items": selected_items,
        "skipped_items": skipped_items,
        "skipped_reason_counts": reason_counts,
        "status_hashes_before": status_before,
        "status_hashes_after": status_after,
        "risks": [
            "Persistence stores advisory filing/review notes only, not claims.",
            "Persisted caveat-only notes are not author approval or publication approval.",
            "Unsupported, unclear, source-review, and corroboration-required items are skipped by default.",
        ],
        "next_run_recommendation": {},
        "verification": {},
    }
    if payload["claims_count_after"] != payload["claims_count_before"]:
        raise PersistNotesError("claims count changed; refusing to report success")
    if payload["editorial_reviews_count_after"] != payload["editorial_reviews_count_before"]:
        raise PersistNotesError("editorial_reviews count changed; refusing to report success")
    if payload["statuses_modified"]:
        raise PersistNotesError("status hashes changed; refusing to report success")
    payload["next_run_recommendation"] = recommendation(payload)
    return payload


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Persist eligible reasoning review notes into source_notes only when explicitly requested.")
    p.add_argument("--run-id", default="latest")
    p.add_argument("--output-dir", default="reports/editorial")
    p.add_argument("--source-support-review-report", required=True)
    p.add_argument("--filing-novelty-report", default="")
    p.add_argument("--editor-packet-report", default="")
    p.add_argument("--only-eligible", action="store_true", default=True)
    p.add_argument("--include-corroboration-required", action="store_true")
    p.add_argument("--include-unsupported", action="store_true")
    p.add_argument("--write-source-notes", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--json-only", action="store_true")
    p.add_argument("--markdown-only", action="store_true")
    p.add_argument("--report-suffix", default="run11")
    args = p.parse_args(argv)
    if args.json_only and args.markdown_only:
        raise PersistNotesError("--json-only and --markdown-only are mutually exclusive")
    if args.dry_run and args.write_source_notes:
        # Dry-run wins: explicit no write.
        args.write_source_notes = False
    if args.include_corroboration_required or args.include_unsupported:
        raise PersistNotesError("Run 11 persists only eligible items by default; unsupported/corroboration-required inclusion is not implemented")
    return args


def main(argv: list[str] | None = None) -> int:
    try:
        args = parse_args(argv or sys.argv[1:])
        report = load_json(resolve(args.source_support_review_report))
        validate_report(report)
        payload = build_payload(args, report)
        outputs = write_reports(payload, Path(args.output_dir), args.report_suffix, json_only=args.json_only, markdown_only=args.markdown_only)
        print(json.dumps({
            "status": "ok",
            "run_id": payload["run_id"],
            "outputs": outputs,
            "source_reviews_available": payload["source_reviews_available"],
            "eligible_items_available": payload["eligible_items_available"],
            "items_selected_for_persistence": payload["items_selected_for_persistence"],
            "write_source_notes_requested": payload["write_source_notes_requested"],
            "db_modified": payload["db_modified"],
            "db_write_scope": payload["db_write_scope"],
            "notes_inserted": payload["notes_inserted"],
            "notes_skipped_existing": payload["notes_skipped_existing"],
            "notes_failed": payload["notes_failed"],
            "notes_conflicted": payload["notes_conflicted"],
            "idempotent": payload["idempotent"],
            "skipped_reason_counts": payload["skipped_reason_counts"],
        }, indent=2, sort_keys=True))
        return 0
    except PersistNotesError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except sqlite3.Error as exc:
        print(f"ERROR: SQLite/source_notes persistence failed safely: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
