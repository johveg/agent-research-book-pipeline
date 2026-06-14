#!/usr/bin/env python3
"""Run 17 report-only audit of persisted source-support rereview notes.

Reads Run 16 persistence output plus source_notes rows and emits a downstream
eligibility manifest for a future clustering run. This script performs no DB
writes and never promotes advisory notes to claims, editorial approval, authoring,
or publication.
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

from model_profiles import load_model_profile  # noqa: E402
from research_common import DB_PATH as DEFAULT_DB_PATH, sha256_text  # noqa: E402

RUN_ID_DEFAULT = "citation-pipeline-test-20260612"
NOTE_TYPE = "source_support_rereview_draft"
MODE = "audit_persisted_rereview_notes"
DEFAULT_RUN16 = f"reports/editorial/{RUN_ID_DEFAULT}-persisted-source-support-rereview-notes-run16.json"
DEFAULT_RUN15 = f"reports/editorial/{RUN_ID_DEFAULT}-source-support-rereview-run15.json"
ELIGIBLE_SUPPORT = {"supported", "partially_supported"}
ELIGIBLE_CORROBORATION = {"corroborated", "partially_corroborated"}
ELIGIBLE_EVIDENCE_USE = {
    "eligible_as_caveat_only_after_corroboration",
    "eligible_for_filing_later_after_corroboration",
}
ALLOWED_MANIFEST_DECISIONS = {
    "eligible_for_clustering",
    "caveat_only_cluster_candidate",
    "needs_more_sources",
    "source_context_unclear",
    "exclude_from_clustering",
    "contradiction_review_required",
    "safe_reports_only",
}
REQUIRED_NOTE_FLAGS = {
    "advisory_only": True,
    "author_allowed": False,
    "publication_approved": False,
    "claim_inserted": False,
    "editorial_review_inserted": False,
    "source_registry_promoted": False,
}
REQUIRED_PROVENANCE_KEYS = {
    "source_review_id",
    "item_id",
    "original_source_id",
    "candidate_source_ids",
    "support_decision",
    "corroboration_decision",
    "evidence_use_decision",
    "closed_loop_disposition",
}


class AuditRereviewNotesError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def db_path() -> Path:
    override = os.environ.get("TEREFO_BOOK_DB_PATH", "").strip()
    return Path(override) if override else DEFAULT_DB_PATH


def resolve(path: str | Path) -> Path:
    p = Path(path)
    return p if p.is_absolute() else ROOT / p


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def load_json(path: Path, label: str) -> dict[str, Any]:
    if not path.exists():
        raise AuditRereviewNotesError(f"missing input {label}: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AuditRereviewNotesError(f"invalid JSON in {label}: {exc}") from exc
    if not isinstance(data, dict):
        raise AuditRereviewNotesError(f"{label} must be a JSON object")
    return data


def compact_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


def note_id_for(note: dict[str, Any]) -> str:
    seed = f"{NOTE_TYPE}:{note['source_review_id']}:{note.get('output_hash') or note.get('source_review_hash', '')}"
    return "note_" + sha256_text(seed)[:24]


def manifest_item_id_for(note_id: str, source_review_id: str) -> str:
    return "manifest_" + sha256_text(f"run17:{note_id}:{source_review_id}")[:24]


def connect_readonly(path: Path) -> sqlite3.Connection:
    if not path.exists():
        raise AuditRereviewNotesError(f"missing SQLite DB: {path}")
    uri = f"file:{path}?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA query_only = ON")
    return con


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
    return {name: sha256_text(compact_json([tuple(r) for r in con.execute(sql).fetchall()])) for name, sql in specs.items()}


def validate_run16(run16: dict[str, Any]) -> list[dict[str, Any]]:
    if run16.get("mode") != "persist_source_support_rereview_notes":
        raise AuditRereviewNotesError("Run 16 report mode mismatch")
    safety = run16.get("safety_flags")
    if not isinstance(safety, dict):
        raise AuditRereviewNotesError("Run 16 report missing safety_flags")
    for key, expected in REQUIRED_NOTE_FLAGS.items():
        if safety.get(key) is not expected:
            raise AuditRereviewNotesError(f"Run 16 safety flag invalid: {key}")
    persisted = run16.get("persisted_items") or run16.get("eligible_items")
    if not isinstance(persisted, list) or not persisted:
        raise AuditRereviewNotesError("Run 16 report has no persisted/eligible note items")
    return persisted


def validate_run15(run15: dict[str, Any]) -> None:
    if run15.get("mode") != "source_support_rereview":
        raise AuditRereviewNotesError("Run 15 report mode mismatch")
    safety = run15.get("safety_flags")
    if not isinstance(safety, dict) or safety.get("advisory_only") is not True or safety.get("author_allowed") is not False or safety.get("publication_approved") is not False:
        raise AuditRereviewNotesError("Run 15 safety flags invalid")


def parse_note_json(note_text: str, note_id: str) -> dict[str, Any]:
    try:
        note = json.loads(note_text)
    except json.JSONDecodeError as exc:
        raise AuditRereviewNotesError(f"malformed persisted note JSON for {note_id}: {exc}") from exc
    if not isinstance(note, dict):
        raise AuditRereviewNotesError(f"persisted note {note_id} is not a JSON object")
    return note


def validate_note(note_id: str, row: sqlite3.Row, note: dict[str, Any], run16_item: dict[str, Any], run15_report_path: Path, run16_report_path: Path) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    if row["note_type"] != NOTE_TYPE:
        raise AuditRereviewNotesError(f"persisted note {note_id} has wrong note_type")
    if note.get("note_kind") != NOTE_TYPE:
        raise AuditRereviewNotesError(f"persisted note {note_id} has wrong note_kind")
    for key, expected in REQUIRED_NOTE_FLAGS.items():
        if note.get(key) is not expected:
            raise AuditRereviewNotesError(f"persisted note {note_id} safety flag invalid: {key}")
    missing = [key for key in REQUIRED_PROVENANCE_KEYS if key not in note or note.get(key) in (None, "", [])]
    if missing:
        raise AuditRereviewNotesError(f"persisted note {note_id} missing provenance fields: {missing}")
    if note.get("closed_loop_disposition") != "eligible_for_review_note_persistence":
        raise AuditRereviewNotesError(f"persisted note {note_id} is not eligible disposition")
    provenance = note.get("provenance")
    if not isinstance(provenance, dict) or not provenance.get("source_support_rereview_report"):
        raise AuditRereviewNotesError(f"persisted note {note_id} missing Run 15 provenance path")
    if provenance.get("source_support_rereview_report") != rel(run15_report_path):
        raise AuditRereviewNotesError(f"persisted note {note_id} Run 15 provenance path mismatch")
    if not note.get("caveat_text") and not note.get("limitations"):
        raise AuditRereviewNotesError(f"persisted note {note_id} missing caveat/limitations")
    if note.get("source_review_id") != run16_item.get("source_review_id"):
        raise AuditRereviewNotesError(f"persisted note {note_id} source_review_id mismatch with Run 16")
    if run16_item.get("note_id") != note_id:
        raise AuditRereviewNotesError(f"Run 16 note id mismatch for {note_id}")
    expected_id = note_id_for(note)
    if expected_id != note_id:
        raise AuditRereviewNotesError(f"deterministic note id mismatch for {note_id}; expected {expected_id}")
    findings.append({"check": "persisted_note_matches_run16", "status": "pass", "note_id": note_id})
    findings.append({"check": "deterministic_note_id", "status": "pass", "note_id": note_id})
    findings.append({"check": "provenance_paths", "status": "pass", "note_id": note_id, "run15_report": rel(run15_report_path), "run16_report": rel(run16_report_path)})
    return findings


def has_raw_capture_dependency(note: dict[str, Any]) -> bool:
    if note.get("raw_content_stored") is True:
        return True
    for c in note.get("candidate_source_summary", []) or []:
        if isinstance(c, dict) and c.get("raw_content_stored") is True:
            return True
    return False


def decision_for_note(note: dict[str, Any]) -> str:
    if note.get("contradiction_flag") is True or note.get("support_decision") == "contradicted":
        return "contradiction_review_required"
    if note.get("do_not_use") is True or note.get("evidence_use_decision") == "do_not_use":
        return "exclude_from_clustering"
    if has_raw_capture_dependency(note):
        return "exclude_from_clustering"
    if note.get("closed_loop_disposition") != "eligible_for_review_note_persistence":
        return str(note.get("closed_loop_disposition") or "safe_reports_only") if str(note.get("closed_loop_disposition") or "") in ALLOWED_MANIFEST_DECISIONS else "safe_reports_only"
    if note.get("support_decision") not in ELIGIBLE_SUPPORT:
        return "needs_more_sources"
    if note.get("corroboration_decision") not in ELIGIBLE_CORROBORATION:
        return "needs_more_sources"
    if note.get("evidence_use_decision") not in ELIGIBLE_EVIDENCE_USE:
        return "exclude_from_clustering"
    if not note.get("candidate_source_ids") or not note.get("provenance"):
        return "source_context_unclear"
    if note.get("caveat_required") is True or note.get("evidence_use_decision") == "eligible_as_caveat_only_after_corroboration":
        return "caveat_only_cluster_candidate"
    return "eligible_for_clustering"


def manifest_item(row: sqlite3.Row, note: dict[str, Any], decision: str, run15_report_path: Path, run16_report_path: Path) -> dict[str, Any]:
    return {
        "manifest_item_id": manifest_item_id_for(row["id"], note["source_review_id"]),
        "note_id": row["id"],
        "note_type": row["note_type"],
        "source_id": row["source_id"],
        "source_review_id": note["source_review_id"],
        "item_id": note["item_id"],
        "support_decision": note["support_decision"],
        "corroboration_decision": note["corroboration_decision"],
        "evidence_use_decision": note["evidence_use_decision"],
        "closed_loop_disposition": note["closed_loop_disposition"],
        "downstream_manifest_decision": decision,
        "caveat_required": bool(note.get("caveat_required")),
        "caveat_text": note.get("caveat_text", ""),
        "limitations": note.get("limitations", ""),
        "residual_risk": note.get("residual_risk", ""),
        "accepted_candidate_source_ids": note.get("accepted_candidate_source_ids") or note.get("candidate_source_ids") or [],
        "provenance_paths": {
            "run15_report": rel(run15_report_path),
            "run16_report": rel(run16_report_path),
            "persisted_note_provenance": note.get("provenance", {}).get("source_support_rereview_report", ""),
        },
        "advisory_only": True,
        "author_allowed": False,
        "publication_approved": False,
        "eligible_for_claim_insertion": False,
        "eligible_for_authoring": False,
        "eligible_for_publication": False,
    }


def excluded_from_run16(run16: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in run16.get("skipped_items", []) or []:
        if not isinstance(item, dict):
            continue
        disp = item.get("closed_loop_disposition") or "safe_reports_only"
        decision = disp if disp in ALLOWED_MANIFEST_DECISIONS else "safe_reports_only"
        out.append({
            "source_review_id": item.get("source_review_id", ""),
            "item_id": item.get("item_id", ""),
            "skip_reason": item.get("skip_reason", "not_persisted"),
            "closed_loop_disposition": disp,
            "downstream_manifest_decision": decision,
            "advisory_only": True,
            "author_allowed": False,
            "publication_approved": False,
        })
    return out


def build_payload(args: argparse.Namespace) -> dict[str, Any]:
    run16_path = resolve(args.run16_report)
    run15_path = resolve(args.run15_report)
    run16 = load_json(run16_path, "Run 16 report")
    run15 = load_json(run15_path, "Run 15 report")
    persisted_items = validate_run16(run16)
    validate_run15(run15)
    profile = load_model_profile("closed_loop_editorial")
    path = db_path()
    manifest_items: list[dict[str, Any]] = []
    excluded_items: list[dict[str, Any]] = []
    audit_findings: list[dict[str, Any]] = []
    failed_checks: list[dict[str, Any]] = []
    with connect_readonly(path) as con:
        before_counts = {
            "source_notes": table_count(con, "source_notes"),
            "source_support_rereview_draft": table_count(con, "source_notes", "note_type = ?", (NOTE_TYPE,)),
            "claims": table_count(con, "claims"),
            "editorial_reviews": table_count(con, "editorial_reviews"),
        }
        before_status = status_snapshots(con)
        for item in persisted_items:
            note_id = item.get("note_id")
            if not note_id:
                raise AuditRereviewNotesError("Run 16 persisted item missing note_id")
            row = con.execute("SELECT id, source_id, note_type, note, created_at FROM source_notes WHERE id = ?", (note_id,)).fetchone()
            if not row:
                raise AuditRereviewNotesError(f"missing persisted source_notes row: {note_id}")
            note = parse_note_json(row["note"], note_id)
            audit_findings.extend(validate_note(note_id, row, note, item, run15_path, run16_path))
            decision = decision_for_note(note)
            if decision not in ALLOWED_MANIFEST_DECISIONS:
                raise AuditRereviewNotesError(f"invalid downstream manifest decision: {decision}")
            m = manifest_item(row, note, decision, run15_path, run16_path)
            if decision in {"eligible_for_clustering", "caveat_only_cluster_candidate"}:
                manifest_items.append(m)
            else:
                excluded_items.append(m)
        excluded_items.extend(excluded_from_run16(run16))
        after_counts = {
            "source_notes": table_count(con, "source_notes"),
            "source_support_rereview_draft": table_count(con, "source_notes", "note_type = ?", (NOTE_TYPE,)),
            "claims": table_count(con, "claims"),
            "editorial_reviews": table_count(con, "editorial_reviews"),
        }
        after_status = status_snapshots(con)
    changed_source_notes = before_counts["source_notes"] != after_counts["source_notes"] or before_counts["source_support_rereview_draft"] != after_counts["source_support_rereview_draft"]
    decision_counts = Counter([i["downstream_manifest_decision"] for i in manifest_items + excluded_items])
    disposition_counts = Counter([i.get("closed_loop_disposition", "") for i in manifest_items + excluded_items])
    payload = {
        "run_id": args.run_id,
        "generated_at": utc_now(),
        "mode": MODE,
        "input_paths": {
            "run16_report": rel(run16_path),
            "run15_report": rel(run15_path),
            "sqlite_db": rel(path),
        },
        "model_profile": {
            "profile_name": profile["profile_name"],
            "provider": profile["provider"],
            "model": profile["model"],
            "bridge": profile["bridge"],
            "strict_json_required": profile["strict_json_required"],
            "weak_local_fallback_refused": profile["weak_local_fallback_refused"],
            "llm_used": False,
            "reasoning_status": "deterministic_closed_loop_audit_no_llm_needed",
        },
        "report_only": True,
        "reviewed_persisted_notes_count": len(persisted_items),
        "eligible_for_clustering_count": decision_counts.get("eligible_for_clustering", 0),
        "caveat_only_cluster_candidate_count": decision_counts.get("caveat_only_cluster_candidate", 0),
        "excluded_items_count": len(excluded_items),
        "skipped_items_count": 0,
        "manifest_items": manifest_items,
        "excluded_items": excluded_items,
        "audit_findings": audit_findings,
        "failed_audit_checks": failed_checks,
        "downstream_manifest_decision_counts": dict(decision_counts),
        "closed_loop_disposition_counts": dict(disposition_counts),
        "changed_db": False,
        "changed_source_notes": changed_source_notes,
        "changed_source_registry": False,
        "changed_raw_captures": False,
        "changed_docs_book": False,
        "changed_schema": False,
        "changed_daily_worker": False,
        "claims_inserted": max(0, after_counts["claims"] - before_counts["claims"]),
        "editorial_reviews_inserted": max(0, after_counts["editorial_reviews"] - before_counts["editorial_reviews"]),
        "source_status_changed": before_status["sources_status_hash"] != after_status["sources_status_hash"],
        "claim_status_changed": before_status["claims_status_hash"] != after_status["claims_status_hash"],
        "editorial_status_changed": before_status["editorial_reviews_hash"] != after_status["editorial_reviews_hash"],
        "source_notes_count_before": before_counts["source_notes"],
        "source_notes_count_after": after_counts["source_notes"],
        "source_support_rereview_draft_count_before": before_counts["source_support_rereview_draft"],
        "source_support_rereview_draft_count_after": after_counts["source_support_rereview_draft"],
        "claims_count_before": before_counts["claims"],
        "claims_count_after": after_counts["claims"],
        "editorial_reviews_count_before": before_counts["editorial_reviews"],
        "editorial_reviews_count_after": after_counts["editorial_reviews"],
        "safety_flags": {
            "advisory_only": True,
            "author_allowed": False,
            "publication_approved": False,
            "eligible_for_claim_insertion": False,
            "eligible_for_authoring": False,
            "eligible_for_publication": False,
            "source_notes_written": False,
            "claims_inserted": False,
            "editorial_reviews_inserted": False,
            "source_registry_promoted": False,
            "raw_content_stored": False,
            "chapter_prose_generated": False,
            "narrative_packets_created": False,
        },
    }
    if payload["changed_source_notes"] or payload["claims_inserted"] or payload["editorial_reviews_inserted"] or payload["source_status_changed"] or payload["claim_status_changed"] or payload["editorial_status_changed"]:
        raise AuditRereviewNotesError("forbidden DB/status delta detected during report-only audit")
    return payload


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        f"# Run 17 downstream eligibility manifest — {payload['run_id']}", "",
        "## Summary", "",
        f"- Report-only: `{payload['report_only']}`",
        f"- Persisted notes audited: `{payload['reviewed_persisted_notes_count']}`",
        f"- Eligible for clustering: `{payload['eligible_for_clustering_count']}`",
        f"- Caveat-only cluster candidates: `{payload['caveat_only_cluster_candidate_count']}`",
        f"- Excluded items: `{payload['excluded_items_count']}`",
        f"- Source notes changed: `{payload['changed_source_notes']}`",
        "", "## Manifest items", "",
    ]
    for item in payload["manifest_items"]:
        lines += [
            f"- `{item['manifest_item_id']}` / note `{item['note_id']}`",
            f"  - source_review_id: `{item['source_review_id']}`",
            f"  - decision: `{item['downstream_manifest_decision']}`",
            f"  - caveat_required: `{item['caveat_required']}`",
            f"  - support/corroboration/evidence: `{item['support_decision']}` / `{item['corroboration_decision']}` / `{item['evidence_use_decision']}`",
            "",
        ]
    lines += ["## Excluded items", ""]
    for item in payload["excluded_items"]:
        lines += [
            f"- source_review_id: `{item.get('source_review_id', '')}`",
            f"  - decision: `{item['downstream_manifest_decision']}`",
            f"  - disposition: `{item.get('closed_loop_disposition', '')}`",
            "",
        ]
    lines += [
        "## Safety", "",
        "This manifest does not insert claims or editorial reviews, does not update source/claim/editorial statuses, does not change source_registry/raw captures/docs/book/schema/daily worker, and does not approve authoring or publication.",
        "", "## Recommendation for Run 18", "",
        "Run 18 may perform clustering over only the Run 17 manifest items marked `eligible_for_clustering` or `caveat_only_cluster_candidate`. It should remain report-first, not create claims or narrative packets by default, and should preserve author/publication approval flags as false.",
    ]
    return "\n".join(lines) + "\n"


def write_reports(payload: dict[str, Any], output_dir: Path, suffix: str) -> dict[str, str]:
    out_dir = output_dir if output_dir.is_absolute() else ROOT / output_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{payload['run_id']}-downstream-eligibility-manifest-{suffix}" if suffix else f"{payload['run_id']}-downstream-eligibility-manifest"
    json_path = out_dir / f"{stem}.json"
    md_path = out_dir / f"{stem}.md"
    payload["output_paths"] = {"json": rel(json_path), "markdown": rel(md_path)}
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(payload), encoding="utf-8")
    return payload["output_paths"]


def parse_args(argv: list[str]) -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", default=RUN_ID_DEFAULT)
    ap.add_argument("--run16-report", default=DEFAULT_RUN16)
    ap.add_argument("--run15-report", default=DEFAULT_RUN15)
    ap.add_argument("--output-dir", default="reports/editorial")
    ap.add_argument("--report-suffix", default="run17")
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        payload = build_payload(args)
        write_reports(payload, resolve(args.output_dir), args.report_suffix)
        print(json.dumps({
            "ok": True,
            "output_paths": payload["output_paths"],
            "reviewed_persisted_notes_count": payload["reviewed_persisted_notes_count"],
            "eligible_for_clustering_count": payload["eligible_for_clustering_count"],
            "caveat_only_cluster_candidate_count": payload["caveat_only_cluster_candidate_count"],
            "excluded_items_count": payload["excluded_items_count"],
        }, sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
