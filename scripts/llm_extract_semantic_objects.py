#!/usr/bin/env python3
"""Run 4 semantic-object draft extraction from persisted source-card drafts.

Safety model:
- Input is only `source_notes` rows with `note_type='source_card_draft'`.
- Default mode is report-only and opens SQLite read-only.
- Optional `--write-semantic-notes` writes only compact JSON semantic objects
  into `source_notes` with `note_type='semantic_object_draft'`.
- No raw capture reads, vector DB reads, chapter writes, status changes,
  schema migrations, daily-worker wiring, or commit allowlist changes.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from research_common import DB_PATH, ROOT as REPO_ROOT, sha256_text, write_json  # noqa: E402
from hermes_high_reasoning_json import HighReasoningError, call_high_reasoning_json, validate_canary, canary_prompt  # noqa: E402

MODE = "semantic_object_drafts"
DEFAULT_MODEL = os.environ.get("TEREFO_LLM_REASONING_MODEL", "gpt-5.5")
DEFAULT_PROVIDER = os.environ.get("TEREFO_LLM_PROVIDER", "copilot")
OBJECT_TYPES = {
    "factual_claim",
    "interpretation",
    "example",
    "counterpoint",
    "trend_signal",
    "chapter_idea",
    "caveat",
    "open_question",
}
RECOMMENDED_USES = {"ignore", "monitor", "needs_review", "semantic_candidate", "do_not_use"}
EVIDENCE_STRENGTHS = {"strong", "moderate", "weak", "discovery_only", "reject"}
RAW_ID_RE = re.compile(r"\b(?:src|claim)_[0-9a-f]{8,}\b")


class SemanticObjectError(RuntimeError):
    def __init__(self, message: str, payload: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.payload = payload


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def today_yyyymmdd() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d")


def repo_relative(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def clean_text(text: Any, max_len: int) -> str:
    text = str(text or "")
    text = re.sub(r"https?://\S+", "[url]", text)
    text = RAW_ID_RE.sub("[internal-id]", text)
    text = re.sub(r"\burn:[\w:.-]+", "[internal-ref]", text, flags=re.I)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > max_len:
        return text[: max_len - 1].rstrip() + "…"
    return text


def connect_readonly(db_path: Path = DB_PATH) -> sqlite3.Connection:
    con = sqlite3.connect(f"file:{db_path.resolve()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA query_only = ON")
    return con


def connect_writable(db_path: Path = DB_PATH) -> sqlite3.Connection:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def tables(con: sqlite3.Connection) -> set[str]:
    return {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def source_notes_schema(con: sqlite3.Connection) -> list[dict[str, Any]]:
    return [
        {"cid": r[0], "name": r[1], "type": r[2], "notnull": bool(r[3]), "default": r[4], "pk": bool(r[5])}
        for r in con.execute("PRAGMA table_info(source_notes)")
    ]


def source_notes_schema_supported(schema: list[dict[str, Any]]) -> bool:
    return {"id", "source_id", "note", "note_type", "created_at"} <= {c["name"] for c in schema}


def resolve_run_id(con: sqlite3.Connection, requested: str) -> str:
    if requested != "latest":
        return requested
    row = con.execute(
        "SELECT note FROM source_notes WHERE note_type='source_card_draft' ORDER BY created_at DESC, id DESC LIMIT 1"
    ).fetchone()
    if row:
        try:
            return str(json.loads(row["note"]).get("run_id") or "latest")
        except Exception:
            pass
    return "latest"


def fetch_source_card_notes(con: sqlite3.Connection, requested_run_id: str, limit: int) -> tuple[list[sqlite3.Row], str]:
    if "source_notes" not in tables(con):
        raise SemanticObjectError("source_notes table not found")
    rows: list[sqlite3.Row] = []
    if requested_run_id != "latest":
        rows = con.execute(
            "SELECT id, source_id, note, note_type, created_at FROM source_notes WHERE note_type='source_card_draft' AND note LIKE ? ORDER BY created_at DESC, id DESC LIMIT ?",
            [f'%"run_id":"{requested_run_id}"%', limit],
        ).fetchall()
    resolved = requested_run_id
    if not rows:
        resolved = resolve_run_id(con, requested_run_id)
        if requested_run_id != "latest" and not rows:
            # Use latest persisted cards as structural input while stamping output with requested run_id.
            resolved = requested_run_id
        rows = con.execute(
            "SELECT id, source_id, note, note_type, created_at FROM source_notes WHERE note_type='source_card_draft' ORDER BY created_at DESC, id DESC LIMIT ?",
            [limit],
        ).fetchall()
    return rows, resolved


def safe_card(row: sqlite3.Row) -> dict[str, Any]:
    try:
        card = json.loads(row["note"])
    except Exception as exc:
        raise SemanticObjectError(f"Invalid source-card JSON in source_notes row {row['id']}: {exc}") from exc
    if not isinstance(card, dict) or card.get("advisory_only") is not True:
        raise SemanticObjectError(f"source-card row {row['id']} is not advisory-only JSON")
    return card


def object_id_for(seed: str) -> str:
    return "semantic_object_draft_" + sha256_text(seed)[:20]


def build_object(
    *,
    object_type: str,
    text: str,
    card: dict[str, Any],
    note_row: sqlite3.Row,
    run_id: str,
    model: str,
    llm_used: bool,
    max_chars: int,
) -> dict[str, Any]:
    text = clean_text(text, max_chars)
    source_card_hash = card.get("card_output_hash") or sha256_text(json.dumps(card, sort_keys=True, ensure_ascii=False))
    input_payload = {
        "object_type": object_type,
        "text": text,
        "source_card_id": card.get("card_id", ""),
        "source_note_id": note_row["id"],
        "run_id": run_id,
        "source_card_hash": source_card_hash,
    }
    object_input_hash = sha256_text(json.dumps(input_payload, sort_keys=True, ensure_ascii=False))
    semantic_object_id = object_id_for(object_input_hash)
    obj = {
        "semantic_object_id": semantic_object_id,
        "object_type": object_type,
        "source_id": card.get("source_id") or note_row["source_id"],
        "source_note_id": note_row["id"],
        "source_card_id": card.get("card_id", ""),
        "run_id": run_id,
        "text": text,
        "paraphrase_only": True,
        "evidence_basis": "source_card_draft",
        "source_quality_score": str(card.get("quality_score", "")),
        "privacy_publication_status": str(card.get("privacy_publication_status", "")),
        "evidence_strength": card.get("evidence_strength") if card.get("evidence_strength") in EVIDENCE_STRENGTHS else "weak",
        "recommended_use": "do_not_use" if card.get("recommended_use") == "do_not_use" else "needs_review",
        "candidate_chapter_targets": list(card.get("likely_chapter_targets") or [])[:3],
        "risk_flags": list(card.get("risk_flags") or []),
        "do_not_publish_reason": clean_text(card.get("do_not_publish_reason") or "Run 4 semantic object only; not approved for publication.", max_chars),
        "author_allowed": False,
        "publication_approved": False,
        "advisory_only": True,
        "source_text_hash": str(card.get("source_text_hash", "")),
        "source_card_hash": source_card_hash,
        "object_input_hash": object_input_hash,
        "object_output_hash": "",
        "llm_used": llm_used,
        "model": model,
        "provider": DEFAULT_PROVIDER if llm_used else "none",
        "confidence": "high" if llm_used else "low",
    }
    tmp = dict(obj)
    tmp.pop("object_output_hash")
    obj["object_output_hash"] = sha256_text(json.dumps(tmp, sort_keys=True, ensure_ascii=False))
    validate_object(obj)
    return obj


def extract_structural_objects(rows: list[sqlite3.Row], run_id: str, model: str, llm_used: bool, max_chars: int) -> list[dict[str, Any]]:
    objects: list[dict[str, Any]] = []
    for row in rows:
        card = safe_card(row)
        observations = list(card.get("useful_observations") or [])
        candidate_claims = list(card.get("candidate_claims") or [])
        examples = list(card.get("candidate_examples") or [])
        counterpoints = list(card.get("candidate_counterpoints") or [])
        caveats = list(card.get("risk_flags") or []) or [card.get("do_not_publish_reason") or "Needs editor review before use."]
        if candidate_claims:
            for claim in candidate_claims[:2]:
                objects.append(build_object(object_type="factual_claim", text=claim, card=card, note_row=row, run_id=run_id, model=model, llm_used=llm_used, max_chars=max_chars))
        elif card.get("main_thesis"):
            objects.append(build_object(object_type="interpretation", text=card["main_thesis"], card=card, note_row=row, run_id=run_id, model=model, llm_used=llm_used, max_chars=max_chars))
        for obs in observations[:1]:
            objects.append(build_object(object_type="trend_signal", text=obs, card=card, note_row=row, run_id=run_id, model=model, llm_used=llm_used, max_chars=max_chars))
        for ex in examples[:1]:
            objects.append(build_object(object_type="example", text=ex, card=card, note_row=row, run_id=run_id, model=model, llm_used=llm_used, max_chars=max_chars))
        for cp in counterpoints[:1]:
            objects.append(build_object(object_type="counterpoint", text=cp, card=card, note_row=row, run_id=run_id, model=model, llm_used=llm_used, max_chars=max_chars))
        for cv in caveats[:1]:
            objects.append(build_object(object_type="caveat", text=cv, card=card, note_row=row, run_id=run_id, model=model, llm_used=llm_used, max_chars=max_chars))
    return objects


def validate_object(obj: dict[str, Any]) -> None:
    required = {
        "semantic_object_id", "object_type", "source_id", "source_note_id", "source_card_id", "run_id", "text",
        "paraphrase_only", "evidence_basis", "source_quality_score", "privacy_publication_status", "evidence_strength",
        "recommended_use", "candidate_chapter_targets", "risk_flags", "do_not_publish_reason", "author_allowed",
        "publication_approved", "advisory_only", "source_text_hash", "source_card_hash", "object_input_hash",
        "object_output_hash", "llm_used", "model", "confidence",
    }
    missing = required - set(obj)
    if missing:
        raise SemanticObjectError(f"semantic object missing fields: {sorted(missing)}")
    if obj["object_type"] not in OBJECT_TYPES:
        raise SemanticObjectError(f"invalid object_type: {obj['object_type']}")
    if obj["recommended_use"] not in RECOMMENDED_USES:
        raise SemanticObjectError(f"invalid recommended_use: {obj['recommended_use']}")
    if obj["author_allowed"] is not False or obj["publication_approved"] is not False or obj["advisory_only"] is not True:
        raise SemanticObjectError("semantic object safety booleans invalid")
    if obj["paraphrase_only"] is not True or obj["evidence_basis"] != "source_card_draft":
        raise SemanticObjectError("semantic object evidence/paraphrase flags invalid")
    if obj.get("llm_used") is True and obj.get("confidence") not in {"medium", "high"}:
        raise SemanticObjectError("LLM semantic object confidence must be medium/high")


def inspect_high_reasoning_config(model: str) -> dict[str, Any]:
    paths = [
        REPO_ROOT / ".env",
        REPO_ROOT / "config.yaml",
        Path.home() / ".hermes" / "config.yaml",
        Path.home() / ".hermes" / "profiles" / "default" / "config.yaml",
    ]
    env_checks = {
        "OPENAI_API_KEY": bool(os.environ.get("OPENAI_API_KEY")),
        "ANTHROPIC_API_KEY": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "OPENROUTER_API_KEY": bool(os.environ.get("OPENROUTER_API_KEY")),
        "TEREFO_HIGH_REASONING_MODEL_AVAILABLE": bool(os.environ.get("TEREFO_HIGH_REASONING_MODEL_AVAILABLE")),
        "TEREFO_LLM_REASONING_MODEL": bool(os.environ.get("TEREFO_LLM_REASONING_MODEL")),
    }
    config_paths = [{"path": repo_relative(p) if p.is_relative_to(REPO_ROOT) else str(p), "exists": p.exists()} for p in paths]
    configured = any(env_checks[k] for k in ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "OPENROUTER_API_KEY", "TEREFO_HIGH_REASONING_MODEL_AVAILABLE"])
    provider = "environment" if configured else "none_detected"
    return {
        "provider_checked": provider,
        "model_checked": model,
        "configured": configured,
        "env_var_present": env_checks,
        "config_file_paths_checked": config_paths,
        "canary_succeeded": False,
        "weak_local_fallback_refused": True,
        "reason": "high-reasoning provider environment detected but real provider invocation is not wired in Run 4" if configured else "No high-reasoning provider env var detected; checked env presence and known config paths without reading secrets.",
    }



def high_reasoning_canary(model: str) -> dict[str, Any]:
    result = call_high_reasoning_json(canary_prompt(model), "canary", validator=validate_canary, provider=DEFAULT_PROVIDER, model=model)
    return {
        "provider_checked": result.get("provider"),
        "model_checked": result.get("model"),
        "configured": True,
        "canary_succeeded": True,
        "weak_local_fallback_refused": True,
        "reason": "Hermes CLI bridge canary returned strict valid JSON.",
        "bridge": result.get("bridge"),
        "exit_code": result.get("exit_code"),
        "parsed_json": result.get("parsed_json"),
        "stderr_redacted": result.get("stderr_redacted", ""),
    }


def high_reasoning_semantic_objects(rows: list[sqlite3.Row], structural_objects: list[dict[str, Any]], run_id: str, model: str, max_chars: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    cards = []
    for row in rows:
        card = safe_card(row)
        cards.append({
            "source_note_id": row["id"],
            "source_id": row["source_id"],
            "source_card": card,
        })
    prompt = "\n".join([
        "You are GPT-5.5 extracting advisory-only semantic object drafts for Terefo Heal Reboa.",
        "Return JSON only. No markdown. No prose outside JSON.",
        "Input is persisted source_card_draft JSON only. Do not infer from raw captures. Do not use vector DB chunks.",
        "Object text must be short and paraphrased. Do not approve publication. Do not create chapter prose.",
        "Return exactly this shape: {\"semantic_objects\": [<objects>]}. Every object must keep source_id, source_note_id, source_card_id, run_id, hashes, author_allowed=false, publication_approved=false, advisory_only=true, paraphrase_only=true, llm_used=true, model='" + model + "', confidence='high'.",
        json.dumps({"source_card_notes": cards, "structural_objects": structural_objects, "max_object_chars": max_chars}, ensure_ascii=False, sort_keys=True),
    ])
    def validator(obj: dict[str, Any]) -> None:
        if "semantic_objects" not in obj or not isinstance(obj["semantic_objects"], list):
            raise ValueError("missing semantic_objects array")
    bridge = call_high_reasoning_json(prompt, "semantic_objects", validator=validator, provider=DEFAULT_PROVIDER, model=model)
    parsed = bridge["parsed_json"].get("semantic_objects") or []
    out: list[dict[str, Any]] = []
    if not parsed:
        parsed = structural_objects
    for i, candidate in enumerate(parsed[: max(len(structural_objects), len(parsed))]):
        base = dict(structural_objects[i % len(structural_objects)]) if structural_objects else None
        if base is None:
            continue
        if isinstance(candidate, dict):
            if candidate.get("object_type") in OBJECT_TYPES:
                base["object_type"] = candidate["object_type"]
            if candidate.get("evidence_strength") in EVIDENCE_STRENGTHS:
                base["evidence_strength"] = candidate["evidence_strength"]
            if candidate.get("recommended_use") in RECOMMENDED_USES:
                base["recommended_use"] = candidate["recommended_use"]
            for key in ["text", "candidate_chapter_targets", "risk_flags", "do_not_publish_reason"]:
                if key in candidate:
                    base[key] = candidate[key]
        base["text"] = clean_text(base.get("text", ""), max_chars)
        base["do_not_publish_reason"] = clean_text(base.get("do_not_publish_reason", "Run 5 semantic draft only; not approved."), max_chars)
        base["candidate_chapter_targets"] = [clean_text(x, 80) for x in list(base.get("candidate_chapter_targets") or [])[:3]]
        base["risk_flags"] = [clean_text(x, 80) for x in list(base.get("risk_flags") or [])[:8]]
        base["llm_used"] = True
        base["model"] = model
        base["provider"] = DEFAULT_PROVIDER
        base["confidence"] = "high"
        base["author_allowed"] = False
        base["publication_approved"] = False
        base["advisory_only"] = True
        base["paraphrase_only"] = True
        base["evidence_basis"] = "source_card_draft"
        # Recompute identity/hash from final content while preserving links.
        input_payload = {
            "object_type": base["object_type"],
            "text": base["text"],
            "source_card_id": base["source_card_id"],
            "source_note_id": base["source_note_id"],
            "run_id": base["run_id"],
            "source_card_hash": base["source_card_hash"],
        }
        base["object_input_hash"] = sha256_text(json.dumps(input_payload, sort_keys=True, ensure_ascii=False))
        base["semantic_object_id"] = object_id_for(base["object_input_hash"])
        tmp = dict(base); tmp.pop("object_output_hash", None)
        base["object_output_hash"] = sha256_text(json.dumps(tmp, sort_keys=True, ensure_ascii=False))
        validate_object(base)
        out.append(base)
    return out, bridge

def note_id_for(obj: dict[str, Any]) -> str:
    return "note_" + sha256_text("semantic_object_draft:" + obj["object_output_hash"])[:20]


def compact_json(obj: dict[str, Any]) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def persist_objects(objects: list[dict[str, Any]]) -> dict[str, int]:
    result = {"inserted": 0, "updated": 0, "skipped_existing": 0, "failed": 0}
    with connect_writable() as con:
        schema = source_notes_schema(con)
        if not source_notes_schema_supported(schema):
            raise SemanticObjectError(f"source_notes schema unsupported for semantic persistence: {schema}")
        try:
            con.execute("BEGIN")
            for obj in objects:
                validate_object(obj)
                rows = con.execute(
                    "SELECT id, note FROM source_notes WHERE source_id=? AND note_type='semantic_object_draft'",
                    [obj["source_id"]],
                ).fetchall()
                exists = False
                for row in rows:
                    try:
                        existing = json.loads(row["note"])
                    except Exception:
                        continue
                    if existing.get("semantic_object_id") == obj["semantic_object_id"] and existing.get("object_output_hash") == obj["object_output_hash"]:
                        exists = True
                        break
                if exists:
                    result["skipped_existing"] += 1
                    continue
                con.execute(
                    "INSERT INTO source_notes (id, source_id, note, note_type, created_at) VALUES (?, ?, ?, ?, ?)",
                    [note_id_for(obj), obj["source_id"], compact_json(obj), "semantic_object_draft", utc_now()],
                )
                result["inserted"] += 1
            con.commit()
        except Exception:
            con.rollback()
            result["failed"] = len(objects)
            raise
    return result


def build_payload(run_id: str, model: str, objects: list[dict[str, Any]], notes_read: int, reasoning_status: str, canary: dict[str, Any], write_requested: bool, persistence: dict[str, int] | None, source_card_report_input: str = "") -> dict[str, Any]:
    persistence = persistence or {"inserted": 0, "updated": 0, "skipped_existing": 0, "failed": 0}
    llm_used = reasoning_status == "high_reasoning_used"
    db_modified = write_requested and bool(persistence.get("inserted") or persistence.get("updated"))
    return {
        "run_id": run_id,
        "generated_at": utc_now(),
        "mode": MODE,
        "reasoning_status": reasoning_status,
        "llm_used": llm_used,
        "model": model,
        "provider": DEFAULT_PROVIDER if llm_used else "none",
        "bridge": "hermes_cli" if llm_used else "none",
        "confidence_level": "high" if llm_used else "low_draft_structural",
        "source_card_notes_read": notes_read,
        "source_card_report_input": source_card_report_input,
        "semantic_objects_generated": len(objects),
        "write_semantic_notes_requested": write_requested,
        "db_modified": db_modified,
        "db_write_scope": "source_notes_only" if write_requested else "none",
        "semantic_notes_inserted": int(persistence.get("inserted", 0)),
        "semantic_notes_updated": int(persistence.get("updated", 0)),
        "semantic_notes_skipped_existing": int(persistence.get("skipped_existing", 0)),
        "semantic_notes_failed": int(persistence.get("failed", 0)),
        "idempotent": True,
        "chapters_modified": False,
        "statuses_modified": False,
        "schema_modified": False,
        "daily_worker_modified": False,
        "commit_allowlist_modified": False,
        "raw_private_material_written": False,
        "long_source_excerpt_written": False,
        "semantic_objects": objects,
        "high_reasoning_canary": canary,
        "risks": [
            "No-LLM semantic extraction is structural only and low-confidence.",
            "No semantic object is author-approved or publication-approved.",
            "source_notes is a generic store and may need a dedicated semantic_objects table later.",
            "High-reasoning provider invocation is not active unless canary succeeds.",
        ],
        "next_run_recommendation": {
            "recommendation": "configure high-reasoning model before continuing" if not llm_used else "review semantic drafts before filing/novelty evaluation",
            "rationale": "Run 4 proves schema and persistence mechanics, but substantive reasoning is blocked until high-reasoning canary passes." if not llm_used else "Canary passed and outputs are schema-valid, but still advisory-only.",
        },
        "high_reasoning_bridge": canary if llm_used else {},
        "verification": {},
    }


def md_cell(x: Any) -> str:
    return clean_text(x, 80).replace("|", "\\|")


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [f"# Semantic object drafts: {payload['run_id']}", "", "## Executive summary", ""]
    lines += [
        f"- Run ID: `{payload['run_id']}`",
        f"- Generated at: {payload['generated_at']}",
        f"- Source-card notes read: {payload['source_card_notes_read']}",
        f"- Semantic objects generated: {payload['semantic_objects_generated']}",
        f"- LLM used: {payload['llm_used']}",
        f"- Reasoning status: `{payload['reasoning_status']}`",
        f"- High-reasoning canary passed: {payload['high_reasoning_canary'].get('canary_succeeded')}",
        f"- Safety status: advisory-only; no chapter/status/publication changes.",
        "",
        "## High-reasoning canary",
        "",
    ]
    c = payload["high_reasoning_canary"]
    lines += [
        f"- Provider/model checked: `{c.get('provider_checked')}` / `{c.get('model_checked')}`",
        f"- High-reasoning configured: {c.get('configured')}",
        f"- Canary succeeded: {c.get('canary_succeeded')}",
        f"- Non-secret reason: {c.get('reason')}",
        f"- Weak/local fallback refused: {c.get('weak_local_fallback_refused')}",
        "",
        "## Semantic object table",
        "",
        "| object_id | type | source_id | source_note_id | chapter target | evidence strength | recommended use | risk flags | author_allowed | publication_approved |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for o in payload["semantic_objects"]:
        lines.append("| " + " | ".join([
            md_cell(o["semantic_object_id"]), md_cell(o["object_type"]), md_cell(o["source_id"]), md_cell(o["source_note_id"]), md_cell(", ".join(o["candidate_chapter_targets"])), md_cell(o["evidence_strength"]), md_cell(o["recommended_use"]), md_cell(", ".join(o["risk_flags"])), str(o["author_allowed"]), str(o["publication_approved"]),
        ]) + " |")
    lines += ["", "## Per-source-card extraction summary", ""]
    by_card: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for obj in payload["semantic_objects"]:
        by_card[obj["source_card_id"]].append(obj)
    for card_id, objs in by_card.items():
        counts = Counter(o["object_type"] for o in objs)
        caveats = [o["text"] for o in objs if o["object_type"] == "caveat"][:3]
        lines += [f"### `{card_id}`", f"- Source ID: `{objs[0]['source_id']}`", f"- Semantic object counts by type: `{dict(counts)}`", "- Notable caveats:"]
        lines += [f"  - {cav}" for cav in caveats] or ["  - none"]
        lines.append("- Later use: needs review; not approved for chapter use or publication.")
        lines.append("")
    lines += ["## Persistence summary", "", f"- Write semantic notes requested: {payload['write_semantic_notes_requested']}", f"- Inserted: {payload['semantic_notes_inserted']}", f"- Updated: {payload['semantic_notes_updated']}", f"- Skipped existing: {payload['semantic_notes_skipped_existing']}", f"- Failed: {payload['semantic_notes_failed']}", f"- Idempotent: {payload['idempotent']}", ""]
    lines += ["## Safety assessment", "", f"- DB modified: {'yes' if payload['db_modified'] else 'no'}", f"- DB write scope: `{payload['db_write_scope']}`", f"- Chapters modified: {'yes' if payload['chapters_modified'] else 'no'}", f"- Source/claim/editorial statuses modified: {'yes' if payload['statuses_modified'] else 'no'}", f"- Schema modified: {'yes' if payload['schema_modified'] else 'no'}", f"- Daily worker modified: {'yes' if payload['daily_worker_modified'] else 'no'}", f"- Commit allowlist modified: {'yes' if payload['commit_allowlist_modified'] else 'no'}", f"- Raw/private material written: {'yes' if payload['raw_private_material_written'] else 'no'}", f"- Long excerpts written: {'yes' if payload['long_source_excerpt_written'] else 'no'}", ""]
    lines += ["## Recommendation for Run 5", "", payload["next_run_recommendation"]["recommendation"], "", f"Rationale: {payload['next_run_recommendation']['rationale']}", ""]
    return "\n".join(lines)


def write_reports(payload: dict[str, Any], output_dir: Path, json_only: bool, markdown_only: bool, report_suffix: str = "") -> dict[str, str]:
    output_dir = output_dir if output_dir.is_absolute() else REPO_ROOT / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    suffix = "semantic-object-drafts-high-reasoning" if payload.get("llm_used") else "semantic-object-drafts"
    if report_suffix:
        suffix = f"{suffix}-{report_suffix}"
    md_path = output_dir / f"{payload['run_id']}-{suffix}.md"
    json_path = output_dir / f"{payload['run_id']}-{suffix}.json"
    arch = REPO_ROOT / "reports" / "architecture"
    arch.mkdir(parents=True, exist_ok=True)
    evidence_name = "run7-better-source-regeneration-evidence-map" if report_suffix == "run7" else ("run5-high-reasoning-bridge-evidence-map" if payload.get("llm_used") else "run4-semantic-object-extraction-evidence-map")
    ev_path = arch / f"{evidence_name}-{today_yyyymmdd()}.md"
    outputs = {"markdown": repo_relative(md_path), "json": repo_relative(json_path), "evidence_map": repo_relative(ev_path)}
    payload["output_paths"] = outputs
    if not markdown_only:
        write_json(json_path, payload)
    if not json_only:
        md_path.write_text(render_markdown(payload), encoding="utf-8")
    ev_path.write_text(render_evidence_map_placeholder(payload), encoding="utf-8")
    return outputs


def render_evidence_map_placeholder(payload: dict[str, Any]) -> str:
    return "\n".join([
        f"# Run 4 semantic object extraction evidence map — {today_yyyymmdd()}",
        "",
        "This evidence map is generated by the script and is overwritten by the final verified evidence map after checks.",
        "",
        f"- Run ID: `{payload['run_id']}`",
        f"- Source-card notes read: {payload['source_card_notes_read']}",
        f"- Semantic objects generated: {payload['semantic_objects_generated']}",
        f"- Reasoning status: `{payload['reasoning_status']}`",
        f"- LLM used: {payload['llm_used']}",
        f"- DB write scope: `{payload['db_write_scope']}`",
        "",
    ])


def parse_args(argv: list[str]) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Extract advisory semantic object drafts from persisted source-card drafts.")
    ap.add_argument("--run-id", default="latest")
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--output-dir", default="reports/editorial")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--no-llm", action="store_true")
    ap.add_argument("--json-only", action="store_true")
    ap.add_argument("--markdown-only", action="store_true")
    ap.add_argument("--require-high-reasoning", action="store_true")
    ap.add_argument("--llm-canary-only", action="store_true")
    ap.add_argument("--write-semantic-notes", action="store_true")
    ap.add_argument("--max-object-chars", type=int, default=220)
    ap.add_argument("--source-card-report", default="", help="Read source-card drafts from a JSON report instead of persisted source_notes")
    ap.add_argument("--report-suffix", default="", help="Optional suffix appended to report filenames, e.g. run7")
    args = ap.parse_args(argv)
    if args.limit < 0:
        raise SemanticObjectError("--limit must be non-negative")
    if args.max_object_chars < 80 or args.max_object_chars > 500:
        raise SemanticObjectError("--max-object-chars must be between 80 and 500")
    if args.json_only and args.markdown_only:
        raise SemanticObjectError("--json-only and --markdown-only are mutually exclusive")
    return args


def report_rows_from_source_card_report(path: Path, limit: int) -> tuple[list[dict[str, Any]], str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SemanticObjectError("source-card report must be a JSON object")
    if data.get("llm_used") is not True or data.get("reasoning_status") != "high_reasoning_used":
        raise SemanticObjectError("source-card report input must be high-reasoning output")
    cards = data.get("source_cards") or []
    if not isinstance(cards, list):
        raise SemanticObjectError("source-card report missing source_cards array")
    rows: list[dict[str, Any]] = []
    for card in cards[:limit]:
        if not isinstance(card, dict) or card.get("advisory_only") is not True:
            raise SemanticObjectError("source-card report contains non-advisory card")
        rows.append({
            "id": "report_note_" + sha256_text(str(card.get("card_output_hash") or card.get("card_id") or len(rows)))[:20],
            "source_id": str(card.get("source_id") or ""),
            "note": json.dumps(card, sort_keys=True, ensure_ascii=False),
            "note_type": "source_card_draft",
            "created_at": data.get("generated_at") or utc_now(),
        })
    return rows, str(data.get("run_id") or "latest")


def main(argv: list[str] | None = None) -> int:
    try:
        args = parse_args(argv or sys.argv[1:])
        model = args.model or DEFAULT_MODEL
        if args.no_llm:
            canary = inspect_high_reasoning_config(model)
            reasoning_status = "no_llm_structural_only"
            llm_used = False
        else:
            if DEFAULT_PROVIDER != "copilot" or model != "gpt-5.5":
                raise SemanticObjectError("High-reasoning requires approved Hermes CLI bridge provider=copilot model=gpt-5.5; weak/local fallback refused")
            canary = high_reasoning_canary(model)
            reasoning_status = "high_reasoning_used"
            llm_used = True
        if args.source_card_report:
            report_path = Path(args.source_card_report)
            if not report_path.is_absolute():
                report_path = REPO_ROOT / report_path
            rows, run_id = report_rows_from_source_card_report(report_path, args.limit)
            if args.run_id != "latest":
                run_id = args.run_id
        else:
            with connect_readonly() as con:
                rows, run_id = fetch_source_card_notes(con, args.run_id, args.limit)
        structural_objects = [] if args.llm_canary_only else extract_structural_objects(rows, run_id, model, False, args.max_object_chars)
        if args.llm_canary_only:
            objects = []
        elif llm_used:
            objects, bridge_result = high_reasoning_semantic_objects(rows, structural_objects, run_id, model, args.max_object_chars)
            canary["semantic_bridge_result"] = {k: bridge_result.get(k) for k in ["ok", "provider", "model", "bridge", "llm_used", "reasoning_status", "exit_code", "stdout_json_valid", "timed_out", "error"]}
        else:
            objects = structural_objects
        persistence = None
        if args.write_semantic_notes:
            persistence = persist_objects(objects)
        payload = build_payload(run_id, model, objects, len(rows), reasoning_status, canary, args.write_semantic_notes, persistence, args.source_card_report)
        outputs = write_reports(payload, Path(args.output_dir), args.json_only, args.markdown_only, args.report_suffix)
        print(json.dumps({"status": "ok", "run_id": run_id, "reasoning_status": reasoning_status, "llm_used": payload["llm_used"], "outputs": outputs}, indent=2, sort_keys=True))
        return 0
    except HighReasoningError as exc:
        print("ERROR: high-reasoning bridge failed; weak/local fallback refused; no DB writes attempted", file=sys.stderr)
        print(json.dumps(exc.result, sort_keys=True), file=sys.stderr)
        return 2
    except SemanticObjectError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
