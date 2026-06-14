#!/usr/bin/env python3
"""Run 16 disabled-by-default persistence of Run 15 source-support rereview notes.

Writes only eligible advisory Run 15 re-review outcomes into source_notes when
explicitly invoked with --write-source-notes. Default mode is report-only.
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

from research_common import DB_PATH as DEFAULT_DB_PATH, sha256_text  # noqa: E402

RUN_ID_DEFAULT = "citation-pipeline-test-20260612"
DEFAULT_RUN15 = f"reports/editorial/{RUN_ID_DEFAULT}-source-support-rereview-run15.json"
NOTE_TYPE = "source_support_rereview_draft"
MODE = "persist_source_support_rereview_notes"
REQUIRED_SOURCE_NOTE_COLUMNS = {"id", "source_id", "note", "note_type", "created_at"}
ELIGIBLE_SUPPORT = {"supported", "partially_supported"}
ELIGIBLE_CORROBORATION = {"corroborated", "partially_corroborated"}
ELIGIBLE_EVIDENCE_USE = {"eligible_as_caveat_only_after_corroboration", "eligible_for_filing_later_after_corroboration"}
ALLOWED_DISPOSITIONS = {
    "eligible_for_review_note_persistence",
    "caveat_only",
    "needs_more_sources",
    "source_context_unclear",
    "safe_reports_only",
    "exclude_from_pipeline",
    "contradiction_review_required",
}


class PersistRereviewNotesError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def db_path() -> Path:
    override = os.environ.get("TEREFO_BOOK_DB_PATH", "").strip()
    return Path(override) if override else DEFAULT_DB_PATH


def resolve(path: str) -> Path:
    p = Path(path)
    return p if p.is_absolute() else ROOT / p


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise PersistRereviewNotesError(f"missing input report: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PersistRereviewNotesError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise PersistRereviewNotesError("input report must be a JSON object")
    return data


def clean_text(value: Any, max_len: int = 700) -> str:
    text = " ".join(str(value or "").split())
    if len(text) > max_len:
        return text[: max_len - 1].rstrip() + "…"
    return text


def compact_json(obj: dict[str, Any]) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def validate_report(report: dict[str, Any]) -> None:
    if report.get("mode") != "source_support_rereview":
        raise PersistRereviewNotesError("input report mode must be source_support_rereview")
    safety = report.get("safety_flags")
    if not isinstance(safety, dict):
        raise PersistRereviewNotesError("input report missing safety_flags")
    required = {
        "advisory_only": True,
        "author_allowed": False,
        "publication_approved": False,
        "no_claim_insertion": True,
        "no_editorial_review_insertion": True,
        "no_status_changes": True,
    }
    for key, expected in required.items():
        if safety.get(key) is not expected:
            raise PersistRereviewNotesError(f"input report safety flag invalid: {key}")
    if not isinstance(report.get("rereviews"), list):
        raise PersistRereviewNotesError("input report rereviews must be a list")


def validate_item_hard_flags(item: dict[str, Any]) -> None:
    for key, expected in {"advisory_only": True, "author_allowed": False, "publication_approved": False}.items():
        if key not in item or item.get(key) is not expected:
            raise PersistRereviewNotesError(f"missing or invalid hard safety flag {key} for {item.get('source_review_id', 'unknown')}")


def selected_index(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for item in report.get("selected_items", []):
        if isinstance(item, dict) and item.get("source_review_id"):
            out[str(item["source_review_id"])] = item
    return out


def source_summary(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summaries = []
    for c in candidates:
        summaries.append({
            "candidate_source_id": c.get("candidate_source_id", ""),
            "title": clean_text(c.get("title"), 160),
            "url": clean_text(c.get("url"), 240),
            "publisher": clean_text(c.get("publisher"), 120),
            "source_type": clean_text(c.get("source_type"), 80),
            "evidence_strength": clean_text(c.get("evidence_strength"), 80),
            "support_direction": clean_text(c.get("support_direction"), 80),
            "safe_summary": clean_text(c.get("safe_summary"), 400),
            "limitations": clean_text(c.get("limitations"), 300),
            "raw_content_stored": bool(c.get("raw_content_stored")),
            "access_type": clean_text(c.get("access_type"), 80),
        })
    return summaries


def disposition_for(item: dict[str, Any], reason: str | None = None) -> str:
    if item.get("recommended_next_stage") == "eligible_for_review_note_persistence":
        return "eligible_for_review_note_persistence"
    if item.get("recommended_next_stage") == "needs_editor_review":
        return "source_context_unclear"
    if item.get("evidence_use_decision") == "do_not_use" or item.get("recommended_next_stage") == "exclude_from_pipeline":
        return "exclude_from_pipeline"
    if item.get("support_decision") == "contradicted" or item.get("recommended_next_stage") == "contradiction_review_required":
        return "contradiction_review_required"
    if item.get("support_decision") in {"unsupported", "weakly_supported"} or item.get("evidence_use_decision") == "needs_more_sources":
        return "needs_more_sources"
    if item.get("evidence_use_decision") == "eligible_as_caveat_only_after_corroboration":
        return "caveat_only"
    return "safe_reports_only"


def eligibility_reason(item: dict[str, Any]) -> str | None:
    validate_item_hard_flags(item)
    if item.get("recommended_next_stage") != "eligible_for_review_note_persistence":
        return str(item.get("recommended_next_stage") or "not_eligible_next_stage")
    if item.get("support_decision") not in ELIGIBLE_SUPPORT:
        return "support_decision_not_eligible"
    if item.get("corroboration_decision") not in ELIGIBLE_CORROBORATION:
        return "corroboration_decision_not_eligible"
    if item.get("evidence_use_decision") not in ELIGIBLE_EVIDENCE_USE:
        return "evidence_use_decision_not_eligible"
    return None


def build_note(item: dict[str, Any], selected: dict[str, Any], run_id: str, input_path: Path) -> dict[str, Any]:
    candidates = selected.get("accepted_candidate_sources") or []
    candidate_ids = item.get("accepted_candidate_source_ids") or [c.get("candidate_source_id") for c in candidates if c.get("candidate_source_id")]
    note = {
        "note_kind": NOTE_TYPE,
        "run_id": run_id,
        "source_review_id": item["source_review_id"],
        "item_id": item["item_id"],
        "original_source_id": selected.get("original_source_id", ""),
        "source_ids": sorted({str(c.get("source_id")) for c in candidates if c.get("source_id")} | ({str(selected.get("original_source_id"))} if selected.get("original_source_id") else set())),
        "candidate_source_ids": candidate_ids,
        "support_decision": item["support_decision"],
        "corroboration_decision": item["corroboration_decision"],
        "evidence_use_decision": item["evidence_use_decision"],
        "recommended_next_stage": item["recommended_next_stage"],
        "caveat_required": bool(item.get("caveat_required")),
        "caveat_text": clean_text(item.get("caveat_text"), 700),
        "limitations": clean_text(item.get("limitations"), 700),
        "residual_risk": clean_text(item.get("residual_risk"), 700),
        "accepted_candidate_source_ids": candidate_ids,
        "candidate_source_summary": source_summary(candidates),
        "original_statement": clean_text(item.get("original_statement") or selected.get("original_statement"), 700),
        "combined_evidence_assessment": clean_text(item.get("combined_evidence_assessment"), 900),
        "closed_loop_disposition": "eligible_for_review_note_persistence",
        "advisory_only": True,
        "author_allowed": False,
        "publication_approved": False,
        "claim_inserted": False,
        "editorial_review_inserted": False,
        "source_registry_promoted": False,
        "created_by_run": "run16",
        "provenance": {
            "source_support_rereview_report": rel(input_path),
            "run15_input_paths": {},
        },
        "input_hash": item.get("input_hash", ""),
        "output_hash": item.get("output_hash", ""),
        "source_review_hash": sha256_text(compact_json({"item": item, "selected": selected}))[:32],
        "llm_used": item.get("llm_used") is True,
        "provider": item.get("provider", ""),
        "model": item.get("model", ""),
        "bridge": item.get("bridge", ""),
    }
    return note


def note_id_for(note: dict[str, Any]) -> str:
    seed = f"{NOTE_TYPE}:{note['source_review_id']}:{note.get('output_hash') or note['source_review_hash']}"
    return "note_" + sha256_text(seed)[:24]


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
        raise PersistRereviewNotesError(f"source_notes schema incompatible; found columns {sorted(cols)}")
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
        rows = [tuple(r) for r in con.execute(sql).fetchall()]
        out[name] = sha256_text(json.dumps(rows, sort_keys=True, ensure_ascii=False, default=str))
    return out


def select_items(report: dict[str, Any], run_id: str, input_path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    idx = selected_index(report)
    eligible: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for item in report["rereviews"]:
        if not isinstance(item, dict):
            skipped.append({"source_review_id": "unknown", "skip_reason": "not_object", "closed_loop_disposition": "safe_reports_only"})
            continue
        rid = str(item.get("source_review_id") or "")
        if rid not in idx:
            skipped.append({"source_review_id": rid or "unknown", "item_id": item.get("item_id", ""), "skip_reason": "missing_selected_item_provenance", "closed_loop_disposition": "safe_reports_only"})
            continue
        reason = eligibility_reason(item)
        disp = disposition_for(item, reason)
        if disp not in ALLOWED_DISPOSITIONS:
            raise PersistRereviewNotesError(f"invalid closed-loop disposition {disp}")
        if reason is None:
            note = build_note(item, idx[rid], run_id, input_path)
            note_text = compact_json(note)
            note_id = note_id_for(note)
            eligible.append({
                "source_review_id": rid,
                "item_id": item.get("item_id", ""),
                "original_source_id": note["original_source_id"],
                "support_decision": item.get("support_decision"),
                "corroboration_decision": item.get("corroboration_decision"),
                "evidence_use_decision": item.get("evidence_use_decision"),
                "recommended_next_stage": item.get("recommended_next_stage"),
                "closed_loop_disposition": note["closed_loop_disposition"],
                "note_id": note_id,
                "note_type": NOTE_TYPE,
                "note_json": note,
                "note_text": note_text,
                "note_hash": sha256_text(note_text),
                "persistence_result": "pending",
                "author_allowed": False,
                "publication_approved": False,
                "advisory_only": True,
            })
        else:
            skipped.append({
                "source_review_id": rid,
                "item_id": item.get("item_id", ""),
                "support_decision": item.get("support_decision", ""),
                "corroboration_decision": item.get("corroboration_decision", ""),
                "evidence_use_decision": item.get("evidence_use_decision", ""),
                "recommended_next_stage": item.get("recommended_next_stage", ""),
                "skip_reason": reason,
                "closed_loop_disposition": disp,
                "advisory_only": True,
                "author_allowed": False,
                "publication_approved": False,
            })
    return eligible, skipped


def persist_items(con: sqlite3.Connection, eligible: list[dict[str, Any]], *, write: bool) -> tuple[list[dict[str, Any]], dict[str, int]]:
    counts = {"inserted": 0, "existing": 0, "conflicted": 0, "failed": 0}
    persisted: list[dict[str, Any]] = []
    now = utc_now()
    for e in eligible:
        result = "would_insert"
        existing = con.execute("SELECT note FROM source_notes WHERE id = ?", (e["note_id"],)).fetchone()
        if existing:
            if existing["note"] == e["note_text"]:
                counts["existing"] += 1
                result = "existing_identical"
            else:
                counts["conflicted"] += 1
                raise PersistRereviewNotesError(f"conflicting existing note id {e['note_id']} for {e['source_review_id']}")
        elif write:
            con.execute(
                "INSERT INTO source_notes (id, source_id, note, note_type, created_at) VALUES (?, ?, ?, ?, ?)",
                (e["note_id"], e["original_source_id"], e["note_text"], NOTE_TYPE, now),
            )
            counts["inserted"] += 1
            result = "inserted"
        out = {k: v for k, v in e.items() if k not in {"note_text", "note_json"}}
        out["persistence_result"] = result
        persisted.append(out)
    return persisted, counts


def build_payload(args: argparse.Namespace, report: dict[str, Any], input_path: Path) -> dict[str, Any]:
    validate_report(report)
    selected, skipped = select_items(report, args.run_id, input_path)
    path = db_path()
    with connect_db(path) as con:
        schema = inspect_schema(con)
        before_notes = table_count(con, "source_notes")
        before_drafts = table_count(con, "source_notes", "note_type = ?", (NOTE_TYPE,))
        before_claims = table_count(con, "claims")
        before_editorial = table_count(con, "editorial_reviews")
        before_status = status_snapshots(con)
        counts = {"inserted": 0, "existing": 0, "conflicted": 0, "failed": 0}
        try:
            if args.write_source_notes:
                con.execute("BEGIN")
                persisted, counts = persist_items(con, selected, write=True)
                con.commit()
            else:
                persisted, counts = persist_items(con, selected, write=False)
        except Exception:
            con.rollback()
            raise
        after_notes = table_count(con, "source_notes")
        after_drafts = table_count(con, "source_notes", "note_type = ?", (NOTE_TYPE,))
        after_claims = table_count(con, "claims")
        after_editorial = table_count(con, "editorial_reviews")
        after_status = status_snapshots(con)
    disp_counts = Counter([i["closed_loop_disposition"] for i in selected] + [i["closed_loop_disposition"] for i in skipped])
    reason_counts = Counter(i.get("skip_reason", "unknown") for i in skipped)
    changed_source_notes = after_notes != before_notes or after_drafts != before_drafts
    payload = {
        "run_id": args.run_id,
        "generated_at": utc_now(),
        "mode": MODE,
        "input_paths": {"source_support_rereview_report": rel(input_path)},
        "report_only": not bool(args.write_source_notes),
        "write_source_notes": bool(args.write_source_notes),
        "reviewed_items_count": len(report.get("rereviews", [])),
        "eligible_items_count": len(selected),
        "skipped_items_count": len(skipped),
        "inserted_notes_count": counts["inserted"],
        "existing_notes_count": counts["existing"],
        "conflicted_notes_count": counts["conflicted"],
        "failed_notes_count": counts["failed"],
        "note_type": NOTE_TYPE,
        "changed_db": changed_source_notes,
        "changed_source_notes": changed_source_notes,
        "changed_source_registry": False,
        "changed_raw_captures": False,
        "changed_docs_book": False,
        "changed_schema": False,
        "changed_daily_worker": False,
        "claims_inserted": max(0, after_claims - before_claims),
        "editorial_reviews_inserted": max(0, after_editorial - before_editorial),
        "source_status_changed": before_status["sources_status_hash"] != after_status["sources_status_hash"],
        "claim_status_changed": before_status["claims_status_hash"] != after_status["claims_status_hash"],
        "editorial_status_changed": before_status["editorial_reviews_hash"] != after_status["editorial_reviews_hash"],
        "source_notes_count_before": before_notes,
        "source_notes_count_after": after_notes,
        "source_support_rereview_draft_count_before": before_drafts,
        "source_support_rereview_draft_count_after": after_drafts,
        "eligible_items": [{**{k: v for k, v in e.items() if k not in {"note_text", "note_json"}}, "persistence_result": next((p["persistence_result"] for p in persisted if p["note_id"] == e["note_id"]), e.get("persistence_result", "pending"))} for e in selected],
        "skipped_items": skipped,
        "skipped_reason_counts": dict(reason_counts),
        "closed_loop_disposition_counts": dict(disp_counts),
        "persisted_items": persisted,
        "source_notes_schema_found": [{"name": r["name"], "type": r["type"], "notnull": r["notnull"], "pk": r["pk"]} for r in schema],
        "safety_flags": {
            "advisory_only": True,
            "author_allowed": False,
            "publication_approved": False,
            "claim_inserted": False,
            "editorial_review_inserted": False,
            "source_registry_promoted": False,
            "source_notes_only": True,
            "raw_content_stored": False,
            "chapter_prose_generated": False,
            "narrative_packets_created": False,
        },
    }
    if payload["claims_inserted"] or payload["editorial_reviews_inserted"] or payload["source_status_changed"] or payload["claim_status_changed"] or payload["editorial_status_changed"]:
        raise PersistRereviewNotesError("forbidden DB/status delta detected")
    return payload


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        f"# Run 16 persisted source-support rereview notes — {payload['run_id']}", "",
        "## Summary", "",
        f"- Report-only mode: `{payload['report_only']}`",
        f"- `--write-source-notes`: `{payload['write_source_notes']}`",
        f"- Reviewed items: `{payload['reviewed_items_count']}`",
        f"- Eligible items: `{payload['eligible_items_count']}`",
        f"- Skipped items: `{payload['skipped_items_count']}`",
        f"- Inserted notes: `{payload['inserted_notes_count']}`",
        f"- Existing identical notes: `{payload['existing_notes_count']}`",
        f"- Conflicted notes: `{payload['conflicted_notes_count']}`",
        f"- Note type: `{payload['note_type']}`",
        "", "## Eligible / persisted items", "",
    ]
    for item in payload["persisted_items"] or payload["eligible_items"]:
        lines += [
            f"- Source review: `{item['source_review_id']}`",
            f"  - note_id: `{item['note_id']}`",
            f"  - persistence_result: `{item['persistence_result']}`",
            f"  - closed_loop_disposition: `{item['closed_loop_disposition']}`",
            f"  - support: `{item['support_decision']}`; corroboration: `{item['corroboration_decision']}`; evidence use: `{item['evidence_use_decision']}`",
            "",
        ]
    lines += ["## Skipped items", ""]
    for item in payload["skipped_items"]:
        lines += [
            f"- Source review: `{item['source_review_id']}`",
            f"  - skip_reason: `{item['skip_reason']}`",
            f"  - automated closed-loop disposition: `{item['closed_loop_disposition']}`",
            "",
        ]
    lines += [
        "## DB/source_notes delta", "",
        f"- source_notes before/after: `{payload['source_notes_count_before']}` → `{payload['source_notes_count_after']}`",
        f"- source_support_rereview_draft before/after: `{payload['source_support_rereview_draft_count_before']}` → `{payload['source_support_rereview_draft_count_after']}`",
        f"- changed_db: `{payload['changed_db']}`",
        f"- changed_source_notes: `{payload['changed_source_notes']}`",
        "", "## Safety confirmations", "",
        "No claims, editorial_reviews, source/claim/editorial statuses, source_registry, raw captures, docs/book, schema, daily worker, narrative packets, chapter prose, author approval, or publication approval were changed or created. This is advisory source_notes persistence only.",
        "", "## Recommended Run 17", "",
        "Run 17 should audit the persisted draft note and decide whether any additional source-context review is needed before downstream extraction. It must remain report-first and must not create claims, narrative packets, chapter prose, author approval, or publication approval.",
    ]
    return "\n".join(lines) + "\n"


def write_reports(payload: dict[str, Any], output_dir: Path, suffix: str) -> dict[str, str]:
    out_dir = output_dir if output_dir.is_absolute() else ROOT / output_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{payload['run_id']}-persisted-source-support-rereview-notes-{suffix}" if suffix else f"{payload['run_id']}-persisted-source-support-rereview-notes"
    json_path = out_dir / f"{stem}.json"
    md_path = out_dir / f"{stem}.md"
    payload["output_paths"] = {"json": rel(json_path), "markdown": rel(md_path)}
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(payload), encoding="utf-8")
    return payload["output_paths"]


def parse_args(argv: list[str]) -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", default=RUN_ID_DEFAULT)
    ap.add_argument("--source-support-rereview-report", default=DEFAULT_RUN15)
    ap.add_argument("--output-dir", default="reports/editorial")
    ap.add_argument("--report-suffix", default="run16")
    ap.add_argument("--write-source-notes", action="store_true")
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        input_path = resolve(args.source_support_rereview_report)
        report = load_json(input_path)
        payload = build_payload(args, report, input_path)
        write_reports(payload, resolve(args.output_dir), args.report_suffix)
        print(json.dumps({"ok": True, "output_paths": payload["output_paths"], "inserted_notes_count": payload["inserted_notes_count"], "existing_notes_count": payload["existing_notes_count"]}, sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
