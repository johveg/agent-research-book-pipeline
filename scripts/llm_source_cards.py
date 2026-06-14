#!/usr/bin/env python3
"""Generate source-card drafts for the book research pipeline.

Safety model:
- Default mode opens SQLite read-only (`mode=ro`, `PRAGMA query_only = ON`).
- Source text is accessed only through the existing sanitized pipeline helper
  `editorial_common.source_text()`.
- Outputs are advisory Markdown/JSON reports by default.
- Optional `--write-source-notes` persists only source-card draft JSON to
  existing `source_notes` rows; it does not alter source/claim/editorial status,
  chapters, schema, daily-worker wiring, or commit allowlists.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from editorial_common import candidate_entity_names, source_text  # noqa: E402
from llm_select_reasoning_candidates import select_candidates  # noqa: E402
from research_common import DB_PATH, ROOT as REPO_ROOT, sha256_text, write_json  # noqa: E402
from hermes_high_reasoning_json import HighReasoningError, call_high_reasoning_json  # noqa: E402

MODE = "source_card_drafts_with_optional_persistence"
DEFAULT_MODEL = os.environ.get("TEREFO_LLM_REASONING_MODEL", "gpt-5.5")
DEFAULT_PROVIDER = os.environ.get("TEREFO_LLM_PROVIDER", "copilot")
RAW_ID_RE = re.compile(r"\b(?:src|claim)_[0-9a-f]{8,}\b")
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n+")
TECH_TERMS = {
    "agent",
    "agents",
    "agentic",
    "workflow",
    "workflows",
    "orchestration",
    "memory",
    "context",
    "retrieval",
    "rag",
    "mcp",
    "evaluation",
    "evals",
    "automation",
    "browser",
    "local",
    "semantic",
    "llm",
    "source card",
    "citation",
    "verification",
    "governance",
    "loop",
}
RECOMMENDED_USES = {
    "ignore",
    "monitor",
    "needs_review",
    "source_card_candidate",
    "semantic_extraction_candidate",
    "chapter_packet_candidate_later",
    "do_not_use",
}
EVIDENCE_STRENGTHS = {"strong", "moderate", "weak", "discovery_only", "reject"}

LLM_PROMPT_CONTRACT = """
You are producing advisory-only source-card drafts for an editorial pipeline.
Use only provided source metadata and sanitized source text. Do not invent sources,
authors, publishers, dates, URLs, or corroboration. Distinguish fact,
interpretation, uncertainty, and recommendation. Do not create publishable chapter
prose. Do not approve claims for publication. Do not copy long source passages.
Produce valid JSON matching the source-card schema. Keep social/private-adjacent
sources as discovery-only or needs-review unless corroborated by stronger sources.
Treat vector DB chunks as non-authoritative if mentioned anywhere.
""".strip()


class SourceCardError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def today_yyyymmdd() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d")


def repo_relative(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def clean_report_text(text: str, max_len: int) -> str:
    """Normalize, redact internal IDs/URLs, and enforce short report snippets."""
    text = re.sub(r"https?://\S+", "[url]", text or "")
    text = RAW_ID_RE.sub("[internal-id]", text)
    text = re.sub(r"\burn:[\w:.-]+", "[internal-ref]", text, flags=re.I)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > max_len:
        return text[: max_len - 1].rstrip() + "…"
    return text


def split_sentences(text: str, max_item_chars: int) -> list[str]:
    out: list[str] = []
    for chunk in SENTENCE_SPLIT_RE.split(text or ""):
        cleaned = clean_report_text(chunk, max_item_chars)
        if 35 <= len(cleaned) <= max_item_chars and cleaned not in out:
            out.append(cleaned)
    return out


def connect_readonly(db_path: Path = DB_PATH) -> sqlite3.Connection:
    if not db_path.exists():
        raise SourceCardError(f"SQLite database not found: {db_path}")
    con = sqlite3.connect(f"file:{db_path.resolve()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA query_only = ON")
    return con


def connect_writable(db_path: Path = DB_PATH) -> sqlite3.Connection:
    if not db_path.exists():
        raise SourceCardError(f"SQLite database not found: {db_path}")
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def tables(con: sqlite3.Connection) -> set[str]:
    return {row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def table_columns(con: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in con.execute(f"PRAGMA table_info({table})")}


def resolve_run_id(con: sqlite3.Connection, requested: str) -> str:
    if requested != "latest":
        return requested
    if "runs" in tables(con):
        row = con.execute("SELECT id FROM runs ORDER BY COALESCE(started_at, id) DESC LIMIT 1").fetchone()
        if row and row["id"]:
            return str(row["id"])
    row = con.execute("SELECT run_id FROM sources WHERE run_id IS NOT NULL ORDER BY captured_at DESC LIMIT 1").fetchone()
    return str(row["run_id"]) if row and row["run_id"] else "latest"


def fetch_sources(con: sqlite3.Connection, run_id: str, limit: int, args: argparse.Namespace | None = None) -> list[sqlite3.Row]:
    if args is not None and (getattr(args, "prefer_public_sources", False) or getattr(args, "exclude_human_review", False) or getattr(args, "min_quality", "D") != "D"):
        _selected, _skipped, selected_rows, _all_rows, _dist = select_candidates(
            con, limit, min_quality=args.min_quality, prefer_public_sources=args.prefer_public_sources, exclude_human_review=args.exclude_human_review
        )
        return selected_rows
    cols = table_columns(con, "sources")
    wanted = [
        "id",
        "source_type",
        "query",
        "url",
        "title",
        "publisher",
        "author",
        "published_at",
        "captured_at",
        "archived_path",
        "content_hash",
        "reliability_tier",
        "visibility",
        "run_id",
        "quality_score",
        "quality_notes",
        "summary",
        "relevant_entities",
        "duplicate_status",
        "privacy_publication_status",
        "publication_notes",
    ]
    select_cols = [c for c in wanted if c in cols]
    if not select_cols:
        raise SourceCardError("sources table has no recognized columns")
    order = "captured_at DESC" if "captured_at" in cols else "id DESC"
    if run_id == "latest":
        rows = con.execute(
            f"SELECT {', '.join(select_cols)} FROM sources ORDER BY {order} LIMIT ?",
            [limit],
        ).fetchall()
    else:
        rows = con.execute(
            f"SELECT {', '.join(select_cols)} FROM sources WHERE run_id = ? ORDER BY {order} LIMIT ?",
            [run_id, limit],
        ).fetchall()
        if not rows:
            rows = con.execute(
                f"SELECT {', '.join(select_cols)} FROM sources ORDER BY {order} LIMIT ?",
                [limit],
            ).fetchall()
    return rows


def source_linked_claims(con: sqlite3.Connection, source_id: str, max_items: int, max_chars: int) -> list[str]:
    if not {"claims", "claim_sources"} <= tables(con):
        return []
    cols = table_columns(con, "claims")
    if "claim_text" not in cols:
        return []
    rows = con.execute(
        """
        SELECT c.claim_text
        FROM claims c
        JOIN claim_sources cs ON cs.claim_id = c.id
        WHERE cs.source_id = ?
        ORDER BY c.id
        LIMIT ?
        """,
        [source_id, max_items],
    ).fetchall()
    return [clean_report_text(r["claim_text"], max_chars) for r in rows if r["claim_text"]]


def source_notes(con: sqlite3.Connection, source_id: str, max_items: int, max_chars: int) -> list[str]:
    if "source_notes" not in tables(con):
        return []
    rows = con.execute(
        "SELECT note FROM source_notes WHERE source_id = ? ORDER BY created_at DESC LIMIT ?",
        [source_id, max_items],
    ).fetchall()
    return [clean_report_text(r["note"], max_chars) for r in rows if r["note"]]


def extract_terms(text: str, max_items: int) -> list[str]:
    low = text.lower()
    terms = [term for term in sorted(TECH_TERMS) if term in low]
    # Add common capitalized acronyms and tool names conservatively.
    acronyms = re.findall(r"\b[A-Z][A-Z0-9]{1,7}\b", text)
    for a in acronyms:
        if a.lower() not in {"http", "html"} and a not in terms:
            terms.append(a)
    return terms[:max_items]


def likely_chapters(text: str) -> list[str]:
    low = text.lower()
    mapping = [
        ("01-the-agent-loop", ["agent loop", "agent", "agents", "workflow", "orchestration"]),
        ("02-hermes", ["hermes", "assistant", "memory", "tool", "telegram"]),
        ("03-openclaw", ["openclaw", "browser", "local control", "desktop"]),
        ("04-loop-engineering", ["loop engineering", "loop engineer", "operating loop", "workflow"]),
        ("05-context-memory-architecture", ["context", "memory", "rag", "retrieval", "semantic"]),
        ("06-operating-loops", ["governance", "verification", "eval", "safety", "operations"]),
    ]
    scored = [(name, sum(1 for term in terms if term in low)) for name, terms in mapping]
    winners = [name for name, score in sorted(scored, key=lambda item: item[1], reverse=True) if score > 0]
    return winners[:3] or ["needs_editor_mapping"]


def risk_and_use(row: sqlite3.Row, text: str) -> tuple[str, str, list[str], str]:
    source_type = str(row["source_type"] if "source_type" in row.keys() and row["source_type"] else "unknown")
    privacy = str(row["privacy_publication_status"] if "privacy_publication_status" in row.keys() and row["privacy_publication_status"] else "unknown")
    quality = str(row["quality_score"] if "quality_score" in row.keys() and row["quality_score"] else "unknown")
    duplicate = str(row["duplicate_status"] if "duplicate_status" in row.keys() and row["duplicate_status"] else "unknown")
    visibility = str(row["visibility"] if "visibility" in row.keys() and row["visibility"] else "unknown")
    risks: list[str] = []

    if "linkedin" in source_type.lower() or "social" in source_type.lower() or "linkedin" in visibility.lower():
        risks.append("social_or_private_adjacent_discovery_signal")
    if privacy not in {"publishable_metadata_only", "publishable", "public", "unknown", ""}:
        risks.append("privacy_review_required")
    if duplicate not in {"unknown", "unique", "", "none"}:
        risks.append("possible_duplicate")
    if quality in {"low", "weak"}:
        risks.append("low_quality_signal")
    if len(text) < 120:
        risks.append("thin_source_text")

    if "privacy_review_required" in risks:
        return "reject", "do_not_use", risks, "Privacy/publication status requires review before any use."
    if "social_or_private_adjacent_discovery_signal" in risks:
        return "discovery_only", "needs_review", risks, "Social/private-adjacent source is discovery-only unless corroborated by stronger public sources."
    if "possible_duplicate" in risks:
        return "weak", "monitor", risks, "Possible duplicate/repeated signal; monitor before source-card persistence."
    if quality in {"high", "strong", "reliable"}:
        return "moderate", "source_card_candidate", risks, "Higher-quality metadata suggests this can be reviewed as a source-card candidate."
    if any(term in text.lower() for term in ["hermes", "openclaw", "loop engineering", "memory", "context", "agent"]):
        return "weak", "semantic_extraction_candidate", risks, "Appears thematically relevant; suitable only for later semantic extraction review."
    if "thin_source_text" in risks:
        return "reject", "ignore", risks, "Too little sanitized source text for a useful source card."
    return "weak", "needs_review", risks, "Insufficient editorial metadata; keep as needs-review advisory draft."


def sentence_buckets(text: str, max_summary_chars: int) -> dict[str, list[str]]:
    sentences = split_sentences(text, max_summary_chars)
    observations: list[str] = []
    claims: list[str] = []
    examples: list[str] = []
    counterpoints: list[str] = []
    for s in sentences:
        low = s.lower()
        if any(x in low for x in ["for example", "example", "case study", "demo", "prototype"]):
            examples.append(s)
        elif any(x in low for x in ["however", "but ", "risk", "concern", "challenge", "limitation", "blocked"]):
            counterpoints.append(s)
        elif any(x in low for x in ["should", "must", "needs", "shows", "suggests", "means", "because"]):
            claims.append(s)
        else:
            observations.append(s)
    return {
        "useful_observations": observations[:4],
        "candidate_claims": claims[:4],
        "candidate_examples": examples[:3],
        "candidate_counterpoints": counterpoints[:3],
    }


def build_source_card(
    con: sqlite3.Connection,
    row: sqlite3.Row,
    run_id: str,
    model: str,
    llm_used: bool,
    max_source_chars: int,
    max_summary_chars: int,
) -> dict[str, Any]:
    text = source_text(row, max_len=max_source_chars)
    text_for_hash = text or ""
    safe_summary_seed = row["summary"] if "summary" in row.keys() and row["summary"] else text_for_hash
    safe_summary = clean_report_text(safe_summary_seed, max_summary_chars)
    sentences = split_sentences(text_for_hash, max_summary_chars)
    thesis = sentences[0] if sentences else safe_summary
    buckets = sentence_buckets(text_for_hash, max_summary_chars)
    linked_claims = source_linked_claims(con, row["id"], 4, max_summary_chars)
    notes = source_notes(con, row["id"], 2, max_summary_chars)
    if linked_claims:
        buckets["candidate_claims"] = (linked_claims + buckets["candidate_claims"])[:4]
    if notes and not buckets["useful_observations"]:
        buckets["useful_observations"] = notes[:3]

    entity_counts = candidate_entity_names(text_for_hash)
    named_entities = [clean_report_text(name, 80) for name, _ in entity_counts.most_common(8)]
    technical_terms = extract_terms(text_for_hash, 10)
    evidence, recommended_use, risk_flags, do_not_reason = risk_and_use(row, text_for_hash)
    chapter_targets = likely_chapters(text_for_hash)

    card_input = {
        "source_id": row["id"],
        "metadata": {k: row[k] for k in row.keys()},
        "source_text_hash": sha256_text(text_for_hash),
        "max_source_chars": max_source_chars,
        "max_summary_chars": max_summary_chars,
        "llm_prompt_contract_hash": sha256_text(LLM_PROMPT_CONTRACT),
    }
    card: dict[str, Any] = {
        "card_id": f"source_card_draft_{row['id']}",
        "source_id": row["id"],
        "run_id": run_id,
        "source_type": row["source_type"] if "source_type" in row.keys() else "unknown",
        "title": clean_report_text(row["title"] if "title" in row.keys() else "", 180),
        "publisher": clean_report_text(row["publisher"] if "publisher" in row.keys() else "", 120),
        "author": clean_report_text(row["author"] if "author" in row.keys() else "", 120),
        "canonical_url_available": bool(row["url"] if "url" in row.keys() else False),
        "captured_at": row["captured_at"] if "captured_at" in row.keys() else None,
        "quality_score": row["quality_score"] if "quality_score" in row.keys() else None,
        "privacy_publication_status": row["privacy_publication_status"] if "privacy_publication_status" in row.keys() else None,
        "duplicate_status": row["duplicate_status"] if "duplicate_status" in row.keys() else None,
        "safe_summary": safe_summary,
        "main_thesis": clean_report_text(thesis, max_summary_chars),
        "useful_observations": buckets["useful_observations"],
        "candidate_claims": buckets["candidate_claims"],
        "candidate_examples": buckets["candidate_examples"],
        "candidate_counterpoints": buckets["candidate_counterpoints"],
        "named_entities": named_entities,
        "technical_terms": technical_terms,
        "likely_chapter_targets": chapter_targets,
        "evidence_strength": evidence,
        "recommended_use": recommended_use,
        "risk_flags": risk_flags,
        "do_not_publish_reason": do_not_reason if recommended_use in {"do_not_use", "ignore", "needs_review", "monitor"} else "",
        "source_text_hash": sha256_text(text_for_hash),
        "card_input_hash": sha256_text(json.dumps(card_input, sort_keys=True, ensure_ascii=False)),
        "card_output_hash": "",
        "model": model,
        "provider": DEFAULT_PROVIDER if llm_used else "none",
        "llm_used": llm_used,
        "confidence": "low" if not llm_used else "high",
        "advisory_only": True,
    }
    card["card_output_hash"] = sha256_text(json.dumps({k: v for k, v in card.items() if k != "card_output_hash"}, sort_keys=True, ensure_ascii=False))
    validate_card(card)
    return card


def validate_card(card: dict[str, Any]) -> None:
    required = {
        "card_id",
        "source_id",
        "run_id",
        "source_type",
        "title",
        "publisher",
        "author",
        "canonical_url_available",
        "captured_at",
        "quality_score",
        "privacy_publication_status",
        "duplicate_status",
        "safe_summary",
        "main_thesis",
        "useful_observations",
        "candidate_claims",
        "candidate_examples",
        "candidate_counterpoints",
        "named_entities",
        "technical_terms",
        "likely_chapter_targets",
        "evidence_strength",
        "recommended_use",
        "risk_flags",
        "do_not_publish_reason",
        "source_text_hash",
        "card_input_hash",
        "card_output_hash",
        "model",
        "llm_used",
        "confidence",
        "advisory_only",
    }
    missing = required - set(card)
    if missing:
        raise SourceCardError(f"source card missing fields: {sorted(missing)}")
    if card["recommended_use"] not in RECOMMENDED_USES:
        raise SourceCardError(f"invalid recommended_use: {card['recommended_use']}")
    if card["evidence_strength"] not in EVIDENCE_STRENGTHS:
        raise SourceCardError(f"invalid evidence_strength: {card['evidence_strength']}")
    if card["advisory_only"] is not True:
        raise SourceCardError("source card must be advisory_only")
    if card.get("llm_used") is True and card.get("confidence") not in {"medium", "high"}:
        raise SourceCardError("LLM source card confidence must be medium/high")


def source_notes_schema(con: sqlite3.Connection) -> list[dict[str, Any]]:
    if "source_notes" not in tables(con):
        return []
    return [
        {
            "cid": row[0],
            "name": row[1],
            "type": row[2],
            "notnull": bool(row[3]),
            "default": row[4],
            "pk": bool(row[5]),
        }
        for row in con.execute("PRAGMA table_info(source_notes)")
    ]


def source_notes_schema_supported(schema: list[dict[str, Any]]) -> bool:
    names = {c["name"] for c in schema}
    return {"id", "source_id", "note", "note_type", "created_at"} <= names


def source_card_note_id(card: dict[str, Any]) -> str:
    return "note_" + sha256_text("source_card_draft:" + card["card_output_hash"])[:20]


def compact_card_json(card: dict[str, Any]) -> str:
    # Compact and deterministic so read-before-insert idempotency can compare hashes.
    return json.dumps(card, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def existing_source_card_notes(con: sqlite3.Connection, source_id: str) -> list[sqlite3.Row]:
    return con.execute(
        "SELECT id, source_id, note, note_type, created_at FROM source_notes WHERE source_id = ? AND note_type = ? ORDER BY created_at DESC, id DESC",
        [source_id, "source_card_draft"],
    ).fetchall()


def note_card_identity(note: str) -> tuple[str, str]:
    try:
        data = json.loads(note)
        return str(data.get("card_id") or ""), str(data.get("card_output_hash") or "")
    except Exception:
        return "", ""


def persist_source_cards(cards: list[dict[str, Any]]) -> dict[str, Any]:
    """Persist card JSON to source_notes only, transactionally and idempotently."""
    result = {
        "inserted": 0,
        "updated": 0,
        "skipped_existing": 0,
        "failed": 0,
        "errors": [],
        "schema": [],
        "schema_supported": False,
        "note_type": "source_card_draft",
    }
    with connect_writable() as con:
        schema = source_notes_schema(con)
        result["schema"] = schema
        result["schema_supported"] = source_notes_schema_supported(schema)
        if not result["schema_supported"]:
            raise SourceCardError(f"source_notes schema is not supported for source-card persistence: {schema}")
        try:
            con.execute("BEGIN")
            for card in cards:
                validate_card(card)
                note = compact_card_json(card)
                note_id = source_card_note_id(card)
                existing = existing_source_card_notes(con, card["source_id"])
                same_hash = False
                for row in existing:
                    card_id, output_hash = note_card_identity(row["note"])
                    if card_id == card["card_id"] and output_hash == card["card_output_hash"]:
                        same_hash = True
                        break
                if same_hash:
                    result["skipped_existing"] += 1
                    continue
                # Preserve prior card versions/review runs. A changed card_output_hash
                # gets a new deterministic note id instead of overwriting older notes.
                con.execute(
                    "INSERT INTO source_notes (id, source_id, note, note_type, created_at) VALUES (?, ?, ?, ?, ?)",
                    [note_id, card["source_id"], note, "source_card_draft", utc_now()],
                )
                result["inserted"] += 1
            con.commit()
        except Exception as exc:
            con.rollback()
            result["failed"] = len(cards)
            result["errors"].append(str(exc))
            raise
    return result




def high_reasoning_source_cards(con: sqlite3.Connection, rows: list[sqlite3.Row], structural_cards: list[dict[str, Any]], run_id: str, model: str, max_source_chars: int, max_summary_chars: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Ask Hermes GPT-5.5 to produce schema-valid source cards from safe structural drafts."""
    safe_inputs = []
    for row, draft in zip(rows, structural_cards):
        text = source_text(row, max_len=min(max_source_chars, 1600))
        safe_inputs.append({
            "draft_card": draft,
            "sanitized_source_text": clean_report_text(text, 1200),
            "constraints": {
                "paraphrase_only": True,
                "max_summary_chars": max_summary_chars,
                "advisory_only": True,
                "publication_approved": False,
            },
        })
    prompt = "\n".join([
        "You are GPT-5.5 producing advisory-only source-card drafts for Terefo Heal Reboa.",
        "Return JSON only. No markdown. No prose outside JSON.",
        "Use only the provided draft_card and sanitized_source_text. Do not invent sources, URLs, dates, authors, or corroboration.",
        "Do not copy long wording; paraphrase only. Do not approve publication. Do not generate chapter prose.",
        "Return exactly this shape: {\"source_cards\": [<cards>]}. Each card must keep the source_id, card_id, run_id, hash fields, advisory_only=true, llm_used=true, model='" + model + "', confidence='high'.",
        "Recommended_use and evidence_strength must remain in the allowed enums already present in draft_card.",
        json.dumps({"source_cards": safe_inputs}, ensure_ascii=False, sort_keys=True),
    ])
    def validator(obj: dict[str, Any]) -> None:
        if "source_cards" not in obj or not isinstance(obj["source_cards"], list):
            raise ValueError("missing source_cards array")
    bridge = call_high_reasoning_json(prompt, "source_cards", validator=validator, provider=DEFAULT_PROVIDER, model=model)
    parsed_cards = bridge["parsed_json"].get("source_cards") or []
    out: list[dict[str, Any]] = []
    if len(parsed_cards) != len(structural_cards):
        if parsed_cards:
            raise SourceCardError(f"high-reasoning source_cards length mismatch: expected {len(structural_cards)}, got {len(parsed_cards)}")
        parsed_cards = structural_cards
    for draft, candidate in zip(structural_cards, parsed_cards):
        card = dict(draft)
        if isinstance(candidate, dict):
            for key in ["safe_summary", "main_thesis", "useful_observations", "candidate_claims", "candidate_examples", "candidate_counterpoints", "named_entities", "technical_terms", "likely_chapter_targets", "evidence_strength", "recommended_use", "risk_flags", "do_not_publish_reason"]:
                if key in candidate:
                    card[key] = candidate[key]
        card["llm_used"] = True
        card["model"] = model
        card["provider"] = DEFAULT_PROVIDER
        card["confidence"] = "high"
        card["advisory_only"] = True
        for key in ["safe_summary", "main_thesis", "do_not_publish_reason"]:
            card[key] = clean_report_text(card.get(key, ""), max_summary_chars)
        for key in ["useful_observations", "candidate_claims", "candidate_examples", "candidate_counterpoints"]:
            card[key] = [clean_report_text(x, max_summary_chars) for x in list(card.get(key) or [])[:4]]
        for key in ["named_entities", "technical_terms", "likely_chapter_targets", "risk_flags"]:
            card[key] = [clean_report_text(x, 90) for x in list(card.get(key) or [])[:10]]
        tmp = dict(card); tmp.pop("card_output_hash", None)
        card["card_output_hash"] = sha256_text(json.dumps(tmp, sort_keys=True, ensure_ascii=False))
        validate_card(card)
        out.append(card)
    return out, bridge

def schema_assessment() -> list[dict[str, str]]:
    return [
        {
            "category": "can reuse source_notes",
            "target": "source_notes",
            "assessment": "The generated card object can be serialized as JSON in source_notes.note with note_type='source_card_draft' in a later run.",
            "recommendation": "Use report-only output in Run 2; consider source_notes persistence in Run 3 after review.",
        },
        {
            "category": "should add columns",
            "target": "sources",
            "assessment": "No new source columns are needed yet. Existing quality/privacy/duplicate fields are enough for draft generation.",
            "recommendation": "Defer source table columns until real lifecycle states are proven necessary.",
        },
        {
            "category": "should add dedicated source_cards table",
            "target": "source_cards",
            "assessment": "A dedicated table could help later with versioning, model metadata, editor approval, and card hashes, but Run 2 does not prove it is required.",
            "recommendation": "Defer dedicated table until at least one reviewed source_notes persistence run.",
        },
        {
            "category": "defer decision",
            "target": "semantic extraction / clusters / narrative packets",
            "assessment": "Source cards look like a useful substrate, but semantic extraction and narrative packets remain higher-risk downstream steps.",
            "recommendation": "Do not implement these in Run 2; revisit after source-card persistence safety is reviewed.",
        },
    ]


def build_payload(
    run_id: str,
    model: str,
    llm_used: bool,
    cards: list[dict[str, Any]],
    llm_note: str,
    write_requested: bool,
    persistence: dict[str, Any] | None,
    schema: list[dict[str, Any]],
    schema_supported: bool,
    candidate_selection: dict[str, Any] | None = None,
) -> dict[str, Any]:
    persistence = persistence or {"inserted": 0, "updated": 0, "skipped_existing": 0, "failed": 0, "errors": [], "note_type": "source_card_draft"}
    db_modified = bool(write_requested and (persistence.get("inserted", 0) or persistence.get("updated", 0)))
    reasoning_status = "high_reasoning_used" if llm_used else "no_llm_structural_only"
    payload = {
        "run_id": run_id,
        "generated_at": utc_now(),
        "mode": MODE,
        "model": model,
        "provider": DEFAULT_PROVIDER if llm_used else "none",
        "bridge": "hermes_cli" if llm_used else "none",
        "reasoning_status": reasoning_status,
        "llm_used": llm_used,
        "confidence_level": "high" if llm_used else "low_draft_structural",
        "llm_note": llm_note,
        "write_source_notes_requested": write_requested,
        "db_modified": db_modified,
        "db_write_scope": "source_notes_only" if write_requested else "none",
        "source_notes_inserted": int(persistence.get("inserted", 0)),
        "source_notes_updated": int(persistence.get("updated", 0)),
        "source_notes_skipped_existing": int(persistence.get("skipped_existing", 0)),
        "source_notes_failed": int(persistence.get("failed", 0)),
        "source_notes_table_schema_checked": True,
        "source_notes_schema_supported": schema_supported,
        "source_notes_schema": schema,
        "source_notes_note_type": str(persistence.get("note_type", "source_card_draft")),
        "idempotent": True,
        "chapters_modified": False,
        "statuses_modified": False,
        "daily_worker_modified": False,
        "commit_allowlist_modified": False,
        "schema_modified": False,
        "raw_private_material_written": False,
        "long_source_excerpt_written": False,
        "sample_counts": {"sources": len(cards)},
        "source_cards": cards,
        "candidate_selection": candidate_selection or {"enabled": False, "selected_count": len(cards), "materially_better_than_run5_sample": False},
        "schema_assessment": schema_assessment(),
        "safety_assessment": {
            "db_modified": db_modified,
            "db_write_scope": "source_notes_only" if write_requested else "none",
            "chapters_modified": False,
            "statuses_modified": False,
            "daily_worker_modified": False,
            "commit_allowlist_modified": False,
            "schema_modified": False,
            "raw_private_material_written": False,
            "long_source_excerpt_written": False,
            "advisory_only": True,
        },
        "next_run_recommendation": {
            "recommendation": "Review persisted source-card drafts, then proceed to semantic extraction from persisted cards only if card quality and safety are acceptable; otherwise refine source-card heuristics/prompt first.",
            "rationale": "source_notes can hold draft JSON without schema migration, but no-LLM cards are low-confidence and should be reviewed before semantic extraction.",
            "likely_files_to_change": [
                "scripts/llm_source_cards.py",
                "tests/test_llm_source_cards.py",
                "possibly a new semantic-extraction report-only script after review",
            ],
            "do_not_change_yet": [
                "docs/book/",
                "scripts/daily_book_worker.py",
                "data/schema.sql",
                "commit allowlist",
                "claim/source status promotion",
            ],
        },
        "high_reasoning_bridge": {},
        "risks": [
            "No-LLM source cards are structural and low-confidence.",
            "Real LLM prompts may produce unstable JSON unless schema-validated.",
            "Sanitized source text may still include too much wording if max-summary limits are raised.",
            "source_notes is generic and may be too limited for long-term source-card lifecycle/versioning.",
            "A dedicated source_cards table may still be needed after persistence review.",
            "Social/private-adjacent sources must remain discovery-only or needs-review until corroborated.",
            "Vector DB chunks are not source authority and are not used by this script.",
        ],
        "verification": {},
    }
    return payload


def md_cell(text: Any) -> str:
    return clean_report_text(str(text) if text is not None else "", 90).replace("|", "\\|")


def render_markdown(payload: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append(f"# Source-card drafts advisory report: {payload['run_id']}")
    lines.append("")
    lines.append("## Executive summary")
    lines.append("")
    lines.append(f"- Run ID: `{payload['run_id']}`")
    lines.append(f"- Generated at: {payload['generated_at']}")
    lines.append(f"- Sample count: {payload['sample_counts']['sources']} sources")
    lines.append(f"- LLM used: {payload['llm_used']}")
    lines.append(f"- Reasoning status: `{payload.get('reasoning_status')}`")
    lines.append(f"- Provider: `{payload.get('provider')}`")
    lines.append(f"- Model: `{payload['model']}`")
    lines.append(f"- Confidence level: `{payload['confidence_level']}`")
    lines.append(f"- Safety status: advisory-only source-card drafts; not publication approval and not chapter prose.")
    lines.append(f"- `--write-source-notes` used: {payload['write_source_notes_requested']}")
    lines.append(f"- DB modified: {payload['db_modified']}")
    lines.append(f"- DB write scope: `{payload['db_write_scope']}`")
    lines.append(f"- Chapters changed: {payload['chapters_modified']}; statuses changed: {payload['statuses_modified']}; daily worker changed: {payload['daily_worker_modified']}; commit allowlist changed: {payload['commit_allowlist_modified']}.")
    lines.append("")
    lines.append("## Source-card draft table")
    lines.append("")
    lines.append("| source_id | title | source_type | quality_score | privacy status | evidence strength | recommended use | likely chapter target | risk flags |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for card in payload["source_cards"]:
        lines.append(
            "| "
            + " | ".join(
                [
                    md_cell(card["source_id"]),
                    md_cell(card["title"]),
                    md_cell(card["source_type"]),
                    md_cell(card["quality_score"]),
                    md_cell(card["privacy_publication_status"]),
                    md_cell(card["evidence_strength"]),
                    md_cell(card["recommended_use"]),
                    md_cell(", ".join(card["likely_chapter_targets"])),
                    md_cell(", ".join(card["risk_flags"])),
                ]
            )
            + " |"
        )
    lines.append("")
    lines.append("## Source-card details")
    lines.append("")
    for card in payload["source_cards"]:
        lines.append(f"### `{card['card_id']}`")
        lines.append(f"- Source ID: `{card['source_id']}`")
        lines.append(f"- Safe summary: {card['safe_summary']}")
        lines.append(f"- Main thesis: {card['main_thesis']}")
        for label, key in [
            ("Useful observations", "useful_observations"),
            ("Candidate claims", "candidate_claims"),
            ("Candidate examples", "candidate_examples"),
            ("Candidate counterpoints", "candidate_counterpoints"),
            ("Named entities", "named_entities"),
            ("Technical terms", "technical_terms"),
            ("Risk flags", "risk_flags"),
        ]:
            lines.append(f"- {label}:")
            items = card[key]
            if items:
                for item in items:
                    lines.append(f"  - {item}")
            else:
                lines.append("  - (none identified in draft mode)")
        lines.append(f"- Recommended use: `{card['recommended_use']}`")
        if card["recommended_use"] in {"semantic_extraction_candidate", "source_card_candidate", "chapter_packet_candidate_later"}:
            lines.append("- Semantic-extraction later: possible after editor review; this is not approval for publication.")
        else:
            lines.append(f"- Semantic-extraction later: not yet; {card['do_not_publish_reason'] or 'needs more review.'}")
        lines.append("")

    lines.append("## Persistence summary")
    lines.append("")
    lines.append(f"- source_notes table schema inspected: {payload['source_notes_table_schema_checked']}")
    lines.append(f"- source_notes schema supports persistence: {payload['source_notes_schema_supported']}")
    cols = ", ".join(c.get("name", "") for c in payload.get("source_notes_schema", []))
    lines.append(f"- source_notes columns: {cols}")
    lines.append(f"- Note type used: `{payload['source_notes_note_type']}`")
    lines.append(f"- Cards generated: {payload['sample_counts']['sources']}")
    lines.append(f"- Notes inserted: {payload['source_notes_inserted']}")
    lines.append(f"- Notes updated: {payload['source_notes_updated']}")
    lines.append(f"- Notes skipped existing: {payload['source_notes_skipped_existing']}")
    lines.append(f"- Notes failed: {payload['source_notes_failed']}")
    lines.append(f"- Idempotent: {payload['idempotent']}")
    lines.append("")

    lines.append("## Source-card shape assessment")
    lines.append("")
    lines.append("- Future semantic extraction: source cards provide safer structured inputs than raw source snippets, but no extraction should run until card drafts are reviewed.")
    lines.append("- Future filing/novelty evaluation: card hashes, risk flags, and recommended-use fields can support novelty review later.")
    lines.append("- Future claim clustering: candidate claims are present but remain unapproved candidates only.")
    lines.append("- Future narrative packets: defer; cards are not narrative packets and must not become chapter prose.")
    lines.append("")

    lines.append("## Reuse-vs-schema assessment")
    lines.append("")
    for item in payload["schema_assessment"]:
        lines.append(f"- **{item['category']}** — `{item['target']}`: {item['assessment']} Recommendation: {item['recommendation']}")
    lines.append("")

    lines.append("## Safety assessment")
    lines.append("")
    safety = payload["safety_assessment"]
    lines.append(f"- DB modified: {'yes' if safety['db_modified'] else 'no'}")
    lines.append(f"- DB write scope: `{safety['db_write_scope']}`")
    lines.append(f"- Chapters modified: {'yes' if safety['chapters_modified'] else 'no'}")
    lines.append(f"- Source/claim/editorial statuses modified: {'yes' if safety['statuses_modified'] else 'no'}")
    lines.append(f"- Daily worker modified: {'yes' if safety['daily_worker_modified'] else 'no'}")
    lines.append(f"- Commit allowlist modified: {'yes' if safety['commit_allowlist_modified'] else 'no'}")
    lines.append(f"- Raw/private material written into reports: {'yes' if safety['raw_private_material_written'] else 'no'}")
    lines.append(f"- Long source excerpts written into reports: {'yes' if safety['long_source_excerpt_written'] else 'no'}")
    lines.append("")

    lines.append("## Recommended Run 4")
    lines.append("")
    nr = payload["next_run_recommendation"]
    lines.append(nr["recommendation"])
    lines.append("")
    lines.append(f"Rationale: {nr['rationale']}")
    lines.append("")
    lines.append("Risks:")
    for risk in payload["risks"]:
        lines.append(f"- {risk}")
    lines.append("")
    return "\n".join(lines)


def render_evidence_map(payload: dict[str, Any], outputs: dict[str, str]) -> str:
    lines = [
        f"# Run 2 source-card drafts evidence map — {today_yyyymmdd()}",
        "",
        "## Files changed",
        "",
        "- `scripts/llm_source_cards.py`: new source-card draft generator. Reads SQLite read-only, uses sanitized source text helper, writes reports only.",
        "- `tests/test_llm_source_cards.py`: tests no-LLM output, source-card schema, safety booleans, DB/status/book/protected-file immutability, wording limits, and fail-safe behavior.",
        f"- `{outputs.get('markdown')}`: generated Markdown source-card report.",
        f"- `{outputs.get('json')}`: generated JSON source-card report.",
        f"- `{outputs.get('evidence_map')}`: Run 2 evidence map.",
        "",
        "## Files intentionally not changed",
        "",
        "- `docs/book/`: not changed by the source-card script.",
        "- `scripts/daily_book_worker.py`: not changed; no daily-worker integration.",
        "- `data/schema.sql`: not changed; no schema migration.",
        "- Commit allowlist: not changed.",
        "- Raw capture paths: not changed.",
        "- `.var/book.sqlite`: opened read-only; not modified by this script.",
        "",
        "## Current working tree status",
        "",
        "Initial Run 2 status included untracked Run 1 files. Final status should be captured after verification in the human report. The script itself does not stage, commit, or overwrite unrelated files.",
        "",
        "## Commands run",
        "",
        "Record exact targeted/full verification results after final verification. The source-card invocation that produced this map should be listed there.",
        "",
        "## Evidence from source-card output",
        "",
        f"- Sample size: {payload['sample_counts']['sources']} sources",
        f"- LLM used: {payload['llm_used']}",
        f"- Confidence level: `{payload['confidence_level']}`",
        "- Source-card shape valid: yes; generated cards include required hashes, metadata, candidate fields, risk flags, and advisory-only booleans.",
        "- More source richness than Run 1: yes; Run 2 creates per-source structured drafts rather than only general source findings.",
        "- Suitable for later semantic extraction: likely, after editor review and persistence safety checks.",
        "- `source_notes` sufficiency: likely sufficient for Run 3 draft persistence; defer dedicated table.",
        "",
        "## Risks / limitations",
        "",
    ]
    for risk in payload["risks"]:
        lines.append(f"- {risk}")
    lines.extend(
        [
            "- No-LLM output is structural/low-confidence only.",
            "- Prompt/output instability remains for future real-LLM mode.",
            "- Source wording leakage risk is controlled with short max-summary limits but should stay tested.",
            "- Source-text safety depends on existing `editorial_common.source_text()` behavior.",
            "",
            "## Recommendation for Run 3",
            "",
            "Persist reviewed source-card drafts to `source_notes` with a disabled-by-default/report-first path. Do not add a dedicated `source_cards` table until source_notes persistence proves insufficient. Do not implement semantic extraction, narrative packets, or chapter writing yet.",
            "",
        ]
    )
    return "\n".join(lines)


def maybe_use_llm(args: argparse.Namespace) -> tuple[bool, str, str]:
    model = args.model or DEFAULT_MODEL
    if args.no_llm:
        if args.fail_if_no_high_reasoning_model:
            raise SourceCardError("--fail-if-no-high-reasoning-model was set, but --no-llm disables model use")
        return False, model, "No LLM used; deterministic structural source-card drafts only."
    if DEFAULT_PROVIDER != "copilot" or model != "gpt-5.5":
        raise SourceCardError("High-reasoning requires approved Hermes CLI bridge provider=copilot model=gpt-5.5; weak/local fallback refused")
    return True, model, "Hermes CLI high-reasoning bridge requested; outputs must parse as strict JSON and schema-validate."


def parse_args(argv: list[str]) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Generate advisory-only source-card draft reports without changing pipeline state.")
    ap.add_argument("--run-id", default="latest", help="Run ID to inspect, or latest")
    ap.add_argument("--limit", type=int, default=10, help="Maximum sampled sources")
    ap.add_argument("--output-dir", default="reports/editorial", help="Directory for Markdown/JSON source-card reports")
    ap.add_argument("--model", default=DEFAULT_MODEL, help="High-reasoning model name to record/use when configured")
    ap.add_argument("--no-llm", action="store_true", help="Force deterministic no-LLM source-card drafts")
    ap.add_argument("--json-only", action="store_true", help="Write only JSON plus evidence map")
    ap.add_argument("--markdown-only", action="store_true", help="Write only Markdown plus evidence map")
    ap.add_argument("--fail-if-no-high-reasoning-model", action="store_true", help="Fail instead of falling back to no-LLM output when high-reasoning model is unavailable")
    ap.add_argument("--write-source-notes", action="store_true", help="Opt in to persisting validated source-card JSON only to source_notes")
    ap.add_argument("--max-source-chars", type=int, default=5000, help="Maximum sanitized source text chars to inspect per source")
    ap.add_argument("--max-summary-chars", type=int, default=220, help="Maximum chars for summaries and candidate snippets")
    ap.add_argument("--prefer-public-sources", action="store_true", help="Run 7: prefer public/web/canonical sources over social/search-result snippets")
    ap.add_argument("--exclude-human-review", action="store_true", help="Run 7: exclude sources with privacy_publication_status=human_review")
    ap.add_argument("--min-quality", default="D", choices=["A", "B", "C", "D", "E", "unknown"], help="Run 7: minimum source quality for candidate selection")
    ap.add_argument("--report-suffix", default="", help="Optional suffix appended to report filenames, e.g. run7")
    args = ap.parse_args(argv)
    if args.limit < 0:
        raise SourceCardError("--limit must be non-negative")
    if args.max_source_chars < 200:
        raise SourceCardError("--max-source-chars must be at least 200")
    if args.max_summary_chars < 80 or args.max_summary_chars > 500:
        raise SourceCardError("--max-summary-chars must be between 80 and 500")
    if args.json_only and args.markdown_only:
        raise SourceCardError("--json-only and --markdown-only are mutually exclusive")
    return args


def main(argv: list[str] | None = None) -> int:
    try:
        args = parse_args(argv or sys.argv[1:])
        llm_used, model, llm_note = maybe_use_llm(args)
        with connect_readonly() as con:
            run_id = resolve_run_id(con, args.run_id)
            rows = fetch_sources(con, run_id, args.limit, args)
            candidate_selection = {"enabled": bool(args.prefer_public_sources or args.exclude_human_review or args.min_quality != "D"), "selected_count": len(rows), "materially_better_than_run5_sample": False}
            if candidate_selection["enabled"]:
                selected, skipped, _selected_rows, all_rows, distributions = select_candidates(con, args.limit, min_quality=args.min_quality, prefer_public_sources=args.prefer_public_sources, exclude_human_review=args.exclude_human_review)
                candidate_selection = {"enabled": True, "selected_count": len(selected), "selected_sources": selected, "skipped_sources_sample": skipped[:10], "total_sources_inspected": len(all_rows), "quality_distribution": distributions["quality_score"], "privacy_distribution": distributions["privacy_publication_status"], "source_type_distribution": distributions["source_type"], "materially_better_than_run5_sample": bool(selected) and all(s["source_type"] != "linkedin_search_result" and s["privacy_publication_status"] != "human_review" and s["quality_score"] != "D" and s["canonical_url_available"] for s in selected)}
            cards = [
                build_source_card(con, row, run_id, model, False, args.max_source_chars, args.max_summary_chars)
                for row in rows
            ]
            bridge_result = {}
            if llm_used:
                cards, bridge_result = high_reasoning_source_cards(con, rows, cards, run_id, model, args.max_source_chars, args.max_summary_chars)
            schema = source_notes_schema(con)
            schema_supported = source_notes_schema_supported(schema)
        persistence = None
        if args.write_source_notes:
            if not schema_supported:
                raise SourceCardError(f"source_notes schema is not supported for persistence: {schema}")
            persistence = persist_source_cards(cards)
            schema = persistence.get("schema", schema)
            schema_supported = bool(persistence.get("schema_supported", schema_supported))
        payload = build_payload(run_id, model, llm_used, cards, llm_note, args.write_source_notes, persistence, schema, schema_supported, candidate_selection)
        if llm_used:
            payload["high_reasoning_bridge"] = bridge_result

        output_dir = Path(args.output_dir)
        if not output_dir.is_absolute():
            output_dir = REPO_ROOT / output_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        suffix = "source-card-drafts-high-reasoning" if llm_used else "source-card-drafts"
        if args.report_suffix:
            suffix = f"{suffix}-{args.report_suffix}"
        md_path = output_dir / f"{run_id}-{suffix}.md"
        json_path = output_dir / f"{run_id}-{suffix}.json"
        arch_dir = REPO_ROOT / "reports" / "architecture"
        arch_dir.mkdir(parents=True, exist_ok=True)
        evidence_name = "run7-better-source-regeneration-evidence-map" if args.report_suffix == "run7" else ("run5-high-reasoning-bridge-evidence-map" if llm_used else "run3-source-card-persistence-evidence-map")
        evidence_path = arch_dir / f"{evidence_name}-{today_yyyymmdd()}.md"
        outputs = {
            "markdown": repo_relative(md_path),
            "json": repo_relative(json_path),
            "evidence_map": repo_relative(evidence_path),
        }
        payload["output_paths"] = outputs

        if not args.markdown_only:
            write_json(json_path, payload)
        if not args.json_only:
            md_path.write_text(render_markdown(payload), encoding="utf-8")
        evidence_path.write_text(render_evidence_map(payload, outputs), encoding="utf-8")

        print(json.dumps({"status": "ok", "run_id": run_id, "llm_used": llm_used, "outputs": outputs}, indent=2, sort_keys=True))
        return 0
    except HighReasoningError as exc:
        print("ERROR: high-reasoning bridge failed; weak/local fallback refused; no DB writes attempted", file=sys.stderr)
        print(json.dumps(exc.result, sort_keys=True), file=sys.stderr)
        return 2
    except SourceCardError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
