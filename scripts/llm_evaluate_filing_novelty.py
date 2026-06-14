#!/usr/bin/env python3
"""Run 9 report-only filing and novelty evaluation.

Reads the Run 8 editor packet and existing repo/SQLite material read-only, then
classifies downstream-eligible packet chains for later filing/novelty work. This
script never inserts claims, writes editorial reviews, changes statuses, edits
chapters, creates narrative packets, or approves author/publication use.
"""
from __future__ import annotations

import argparse
import json
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

from hermes_high_reasoning_json import DEFAULT_MODEL, DEFAULT_PROVIDER, HighReasoningError, call_high_reasoning_json  # noqa: E402
from research_common import DB_PATH, ROOT as REPO_ROOT, sha256_text, write_json  # noqa: E402

MODE = "filing_novelty_evaluation"
ALLOWED_FILING = {
    "new_claim_candidate", "new_example_candidate", "new_chapter_idea_candidate", "new_trend_signal_candidate",
    "new_caveat_candidate", "strengthens_existing_claim", "weakens_existing_claim", "contradicts_existing_claim",
    "duplicate_existing_material", "needs_corroboration", "too_weak", "do_not_use",
}
ALLOWED_NOVELTY = {"novel", "partially_novel", "duplicate", "unclear", "not_useful"}
ALLOWED_NEXT = {"eligible_for_filing_later", "needs_human_editor_review", "needs_corroboration", "needs_prompt_revision", "needs_source_review", "ignore", "do_not_use"}
RAW_ID_RE = re.compile(r"\b(?:claim|src|note)_[0-9a-f]{8,}\b")


class FilingNoveltyError(RuntimeError):
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


def clean_text(text: Any, max_len: int = 360) -> str:
    text = re.sub(r"https?://\S+", "[url]", str(text or ""))
    text = RAW_ID_RE.sub("[internal-id]", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > max_len:
        return text[: max_len - 1].rstrip() + "…"
    return text


def listify(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [clean_text(v, 180) for v in value if clean_text(v, 180)]
    if isinstance(value, str):
        return [clean_text(value, 180)] if value.strip() else []
    return [clean_text(value, 180)]


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FilingNoveltyError(f"missing input report: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise FilingNoveltyError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise FilingNoveltyError(f"input report must be JSON object: {path}")
    return data


def connect_readonly() -> sqlite3.Connection:
    con = sqlite3.connect(f"file:{DB_PATH.resolve()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA query_only = ON")
    return con


def table_columns(con: sqlite3.Connection, table: str) -> set[str]:
    try:
        return {r[1] for r in con.execute(f"PRAGMA table_info({table})")}
    except sqlite3.Error:
        return set()


def existing_context(limit_claims: int = 200, limit_notes: int = 200) -> dict[str, Any]:
    ctx: dict[str, Any] = {"claims": [], "source_notes": [], "sources": []}
    with connect_readonly() as con:
        if "claim_text" in table_columns(con, "claims"):
            cols = table_columns(con, "claims")
            select = [c for c in ["id", "claim_text", "status", "publication_decision", "contradiction_status"] if c in cols]
            for r in con.execute(f"SELECT {', '.join(select)} FROM claims ORDER BY id LIMIT ?", [limit_claims]):
                d = dict(r); d["claim_text"] = clean_text(d.get("claim_text"), 240); ctx["claims"].append(d)
        if "source_notes" in {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}:
            cols = table_columns(con, "source_notes")
            select = [c for c in ["id", "source_id", "note_type", "note", "created_at"] if c in cols]
            if select:
                for r in con.execute(f"SELECT {', '.join(select)} FROM source_notes ORDER BY created_at DESC, id DESC LIMIT ?", [limit_notes]):
                    d = dict(r); d["note"] = clean_text(d.get("note"), 220); ctx["source_notes"].append(d)
        if "sources" in {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}:
            cols = table_columns(con, "sources")
            select = [c for c in ["id", "title", "source_type", "quality_score", "privacy_publication_status"] if c in cols]
            if select:
                for r in con.execute(f"SELECT {', '.join(select)} FROM sources ORDER BY id LIMIT 200"):
                    d = dict(r); d["title"] = clean_text(d.get("title"), 160); ctx["sources"].append(d)
    return ctx


def validate_packet(packet: dict[str, Any]) -> None:
    if packet.get("mode") != "editor_review_packet":
        raise FilingNoveltyError("editor packet report mode mismatch")
    if packet.get("author_allowed") is not False or packet.get("publication_approved") is not False or packet.get("advisory_only") is not True:
        raise FilingNoveltyError("editor packet top-level approval/advisory flags invalid")
    if packet.get("db_modified") not in (False, None):
        raise FilingNoveltyError("editor packet indicates DB modification")
    for item in packet.get("packet_items", []):
        if item.get("author_allowed") is not False or item.get("publication_approved") is not False or item.get("advisory_only") is not True:
            raise FilingNoveltyError(f"packet item {item.get('packet_item_id')} approval/advisory flags invalid")


def selected_items(packet: dict[str, Any], args: argparse.Namespace) -> list[dict[str, Any]]:
    items = list(packet.get("packet_items", []))
    if args.include_warn:
        items = [i for i in items if i.get("quality_decision") in {"pass", "warn"}]
    elif args.only_downstream_eligible or not args.include_warn:
        items = [i for i in items if i.get("downstream_eligible") is True]
    if args.limit is not None:
        items = items[: args.limit]
    for i in items:
        for key in ["packet_item_id", "source_id", "source_card_id", "semantic_object_id", "quality_review_id", "semantic_object_text"]:
            if not i.get(key):
                raise FilingNoveltyError(f"packet item missing required provenance field {key}: {i.get('packet_item_id')}")
    return items


def token_set(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{3,}", text.lower()) if t not in {"with", "from", "that", "this", "have", "will", "into", "source", "object"}}


def find_similar(item: dict[str, Any], ctx: dict[str, Any], max_items: int = 3) -> tuple[list[str], list[str], str]:
    terms = token_set(str(item.get("semantic_object_text", "")))
    claim_scores = []
    for c in ctx.get("claims", []):
        cterms = token_set(str(c.get("claim_text", "")))
        score = len(terms & cterms)
        if score:
            claim_scores.append((score, str(c.get("id")), clean_text(c.get("claim_text"), 120)))
    claim_scores.sort(reverse=True)
    source_ids = []
    item_source = item.get("source_id")
    if item_source:
        source_ids.append(str(item_source))
    matches = [cid for score, cid, _ in claim_scores[:max_items] if score >= 2]
    rationale = "No close existing claim match found in read-only claims/source-notes context."
    if matches:
        rationale = "Potential overlap with existing claim text based on shared terms: " + "; ".join(f"{cid}" for _, cid, _ in claim_scores[:max_items])
    return matches, source_ids[:max_items], rationale


def structural_eval(item: dict[str, Any], ctx: dict[str, Any], *, llm_used: bool, provider: str, model: str, bridge: str, reasoning_status: str) -> dict[str, Any]:
    matched_claims, matched_sources, rationale = find_similar(item, ctx)
    text = str(item.get("semantic_object_text", ""))
    typ = str(item.get("semantic_object_type", ""))
    risk_flags = listify(item.get("risk_flags"))
    blockers = []
    corroboration_needed = True
    if matched_claims:
        filing = "strengthens_existing_claim"
        novelty = "partially_novel"
        next_stage = "needs_human_editor_review"
    elif "example" in typ.lower():
        filing = "new_example_candidate"
        novelty = "partially_novel"
        next_stage = "needs_corroboration"
    elif any(w in text.lower() for w in ["caveat", "risk", "counter", "however"]):
        filing = "new_caveat_candidate"
        novelty = "partially_novel"
        next_stage = "needs_corroboration"
    else:
        filing = "new_claim_candidate"
        novelty = "partially_novel" if item.get("quality_decision") == "pass" else "unclear"
        next_stage = "needs_corroboration"
    if item.get("quality_decision") == "warn":
        filing = "needs_corroboration"
        next_stage = "needs_human_editor_review"
        blockers.extend(listify(item.get("required_fixes")) or ["warn item requires editor review before filing"])
    seed = json.dumps({"item": item.get("packet_item_id"), "filing": filing, "novelty": novelty, "next": next_stage}, sort_keys=True)
    ev = {
        "filing_evaluation_id": "filing_eval_" + sha256_text(seed)[:20],
        "run_id": item.get("run_id"),
        "packet_item_id": item["packet_item_id"],
        "source_id": item["source_id"],
        "source_card_id": item["source_card_id"],
        "semantic_object_id": item["semantic_object_id"],
        "quality_review_id": item["quality_review_id"],
        "semantic_object_type": clean_text(item.get("semantic_object_type"), 80),
        "semantic_object_text": clean_text(item.get("semantic_object_text"), 320),
        "candidate_chapter_targets": listify(item.get("candidate_chapter_targets")),
        "filing_decision": filing,
        "novelty_decision": novelty,
        "next_stage_recommendation": next_stage,
        "matched_existing_claim_ids": matched_claims,
        "matched_existing_source_ids": matched_sources,
        "similarity_rationale": rationale,
        "filing_summary": clean_text(f"Advisory filing evaluation for {item.get('semantic_object_type')}: {text}", 260),
        "why_it_matters": "May support later editorial filing around the packet's candidate chapter/topic, pending corroboration and human review.",
        "corroboration_needed": corroboration_needed,
        "corroboration_questions": ["Can an independent, public, higher-quality source corroborate this chain?", "Does a human editor agree this is distinct from existing claims?"],
        "blockers": blockers,
        "risk_flags": sorted(set(risk_flags + (["requires_corroboration"] if corroboration_needed else []))),
        "required_editor_decisions": ["Confirm filing category.", "Confirm novelty relative to existing claims.", "Decide whether corroboration is sufficient before downstream use."],
        "confidence": "low" if not llm_used else "medium",
        "author_allowed": False,
        "publication_approved": False,
        "advisory_only": True,
        "input_hash": sha256_text(json.dumps(item, sort_keys=True, ensure_ascii=False)),
        "output_hash": "",
        "llm_used": llm_used,
        "provider": provider if llm_used else "none",
        "model": model if llm_used else "none",
        "bridge": bridge if llm_used else "none",
        "reasoning_status": reasoning_status,
    }
    ev["output_hash"] = sha256_text(json.dumps({k: v for k, v in ev.items() if k != "output_hash"}, sort_keys=True, ensure_ascii=False))
    return ev


def validate_llm_response(obj: dict[str, Any]) -> None:
    vals = obj.get("filing_evaluations")
    if not isinstance(vals, list):
        raise ValueError("filing_evaluations must be a list")
    for ev in vals:
        if not isinstance(ev, dict):
            raise ValueError("each filing evaluation must be an object")
        if ev.get("filing_decision") not in ALLOWED_FILING:
            raise ValueError(f"invalid filing_decision {ev.get('filing_decision')}")
        if ev.get("novelty_decision") not in ALLOWED_NOVELTY:
            raise ValueError(f"invalid novelty_decision {ev.get('novelty_decision')}")
        if ev.get("next_stage_recommendation") not in ALLOWED_NEXT:
            raise ValueError(f"invalid next_stage_recommendation {ev.get('next_stage_recommendation')}")
        if not ev.get("packet_item_id"):
            raise ValueError("packet_item_id required")


def build_prompt(items: list[dict[str, Any]], ctx: dict[str, Any]) -> str:
    compact_items = []
    for i in items:
        compact_items.append({
            "packet_item_id": i["packet_item_id"], "source_id": i["source_id"], "source_card_id": i["source_card_id"],
            "semantic_object_id": i["semantic_object_id"], "quality_review_id": i["quality_review_id"],
            "semantic_object_type": i.get("semantic_object_type"), "semantic_object_text": clean_text(i.get("semantic_object_text"), 260),
            "candidate_chapter_targets": i.get("candidate_chapter_targets", []), "quality_decision": i.get("quality_decision"),
            "risk_flags": i.get("risk_flags", []), "required_fixes": i.get("required_fixes", []),
        })
    compact_ctx = {
        "claims": ctx.get("claims", [])[:60],
        "source_notes": ctx.get("source_notes", [])[:40],
        "instruction": "Evaluate novelty only against existing repo/database material. Do not browse web. Return strict JSON only.",
    }
    schema = {
        "filing_evaluations": [{
            "packet_item_id": "...",
            "filing_decision": sorted(ALLOWED_FILING),
            "novelty_decision": sorted(ALLOWED_NOVELTY),
            "next_stage_recommendation": sorted(ALLOWED_NEXT),
            "matched_existing_claim_ids": [],
            "matched_existing_source_ids": [],
            "similarity_rationale": "short rationale",
            "filing_summary": "short summary",
            "why_it_matters": "short reason",
            "corroboration_needed": True,
            "corroboration_questions": [],
            "blockers": [],
            "risk_flags": [],
            "required_editor_decisions": [],
            "confidence": "low|medium|high",
        }]
    }
    return "\n".join([
        "You are reviewing advisory editor-packet chains for report-only filing/novelty evaluation.",
        "No claim insertion, no publication approval, no author approval. Anything weak needs corroboration.",
        "Allowed decisions are exactly those in the schema. Return strict JSON only, no markdown.",
        "Schema:", json.dumps(schema, ensure_ascii=False),
        "Packet items:", json.dumps(compact_items, ensure_ascii=False),
        "Existing repo/database context:", json.dumps(compact_ctx, ensure_ascii=False),
    ])


def merge_llm_evals(items: list[dict[str, Any]], base_evals: list[dict[str, Any]], llm_parsed: dict[str, Any], provider: str, model: str) -> list[dict[str, Any]]:
    llm_by_id = {str(ev.get("packet_item_id")): ev for ev in llm_parsed.get("filing_evaluations", []) if isinstance(ev, dict)}
    item_by_id = {i["packet_item_id"]: i for i in items}
    out = []
    for base in base_evals:
        pid = base["packet_item_id"]
        src = llm_by_id.get(pid, {})
        ev = dict(base)
        for key in ["filing_decision", "novelty_decision", "next_stage_recommendation", "similarity_rationale", "filing_summary", "why_it_matters", "corroboration_needed", "confidence"]:
            if key in src:
                ev[key] = src[key]
        for key in ["matched_existing_claim_ids", "matched_existing_source_ids", "corroboration_questions", "blockers", "risk_flags", "required_editor_decisions"]:
            if key in src:
                ev[key] = listify(src[key])
        if ev["filing_decision"] not in ALLOWED_FILING: raise FilingNoveltyError(f"invalid LLM filing decision for {pid}")
        if ev["novelty_decision"] not in ALLOWED_NOVELTY: raise FilingNoveltyError(f"invalid LLM novelty decision for {pid}")
        if ev["next_stage_recommendation"] not in ALLOWED_NEXT: raise FilingNoveltyError(f"invalid LLM next-stage decision for {pid}")
        ev.update({"llm_used": True, "provider": provider, "model": model, "bridge": "hermes_cli", "reasoning_status": "high_reasoning_used", "author_allowed": False, "publication_approved": False, "advisory_only": True})
        ev["input_hash"] = sha256_text(json.dumps(item_by_id[pid], sort_keys=True, ensure_ascii=False))
        ev["output_hash"] = sha256_text(json.dumps({k: v for k, v in ev.items() if k != "output_hash"}, sort_keys=True, ensure_ascii=False))
        out.append(ev)
    return out


def build_payload(args: argparse.Namespace, packet: dict[str, Any], items: list[dict[str, Any]], ctx: dict[str, Any]) -> dict[str, Any]:
    llm_used = not args.no_llm
    if args.no_llm:
        reasoning_status = "no_llm_structural_only"; provider = model = bridge = "none"; confidence = "low"
    else:
        reasoning_status = "high_reasoning_used"; provider = args.provider; model = args.model; bridge = "hermes_cli"; confidence = "medium"
    base = [structural_eval(i, ctx, llm_used=llm_used, provider=args.provider, model=args.model, bridge="hermes_cli", reasoning_status=reasoning_status) for i in items]
    bridge_result: dict[str, Any] = {}
    if llm_used:
        prompt = build_prompt(items, ctx)
        bridge_result = call_high_reasoning_json(prompt, "filing_novelty_evaluation_v1", validate_llm_response, provider=args.provider, model=args.model)
        base = merge_llm_evals(items, base, bridge_result["parsed_json"], args.provider, args.model)
    filing_counts = dict(Counter(ev["filing_decision"] for ev in base))
    novelty_counts = dict(Counter(ev["novelty_decision"] for ev in base))
    next_counts = dict(Counter(ev["next_stage_recommendation"] for ev in base))
    packet_items = packet.get("packet_items", [])
    payload = {
        "run_id": args.run_id if args.run_id != "latest" else packet.get("run_id", "latest"),
        "generated_at": utc_now(),
        "mode": MODE,
        "llm_used": llm_used,
        "provider": provider,
        "model": model,
        "bridge": bridge,
        "reasoning_status": reasoning_status,
        "confidence_level": confidence,
        "editor_packet_report": repo_relative(resolve(args.editor_packet_report)),
        "editor_packet_items_available": len(packet_items),
        "downstream_eligible_items_available": sum(1 for i in packet_items if i.get("downstream_eligible") is True),
        "items_evaluated": len(base),
        "filing_decision_counts": filing_counts,
        "novelty_decision_counts": novelty_counts,
        "next_stage_recommendation_counts": next_counts,
        "eligible_for_filing_later_count": next_counts.get("eligible_for_filing_later", 0),
        "needs_corroboration_count": filing_counts.get("needs_corroboration", 0) + next_counts.get("needs_corroboration", 0),
        "duplicate_count": filing_counts.get("duplicate_existing_material", 0) + novelty_counts.get("duplicate", 0),
        "do_not_use_count": filing_counts.get("do_not_use", 0) + next_counts.get("do_not_use", 0),
        "claims_inserted": 0,
        "editorial_reviews_inserted": 0,
        "db_modified": False,
        "db_write_scope": "none",
        "chapters_modified": False,
        "statuses_modified": False,
        "schema_modified": False,
        "daily_worker_modified": False,
        "commit_allowlist_modified": False,
        "raw_private_material_written": False,
        "long_source_excerpt_written": False,
        "author_allowed": False,
        "publication_approved": False,
        "advisory_only": True,
        "external_web_search_used": False,
        "vector_db_authority_used": False,
        "filing_evaluations": base,
        "summary": {
            "strongest_new_candidates": [ev["filing_evaluation_id"] for ev in base if ev["next_stage_recommendation"] == "eligible_for_filing_later"][:10],
            "likely_duplicates": [ev["filing_evaluation_id"] for ev in base if ev["novelty_decision"] == "duplicate"],
            "items_needing_corroboration": [ev["filing_evaluation_id"] for ev in base if ev["corroboration_needed"] or ev["next_stage_recommendation"] == "needs_corroboration"],
            "chapter_distribution": dict(Counter(ch for ev in base for ch in ev.get("candidate_chapter_targets", []))),
            "recurring_blockers": dict(Counter(b for ev in base for b in ev.get("blockers", []))),
            "before_narrative_packets": "Human/editor review plus corroboration or explicit acceptance of filing notes is required before narrative packet candidates.",
        },
        "risks": [
            "Report-only novelty evaluation; no claims inserted or promoted.",
            "Novelty compared only against existing repo/database material, not the external web.",
            "GPT-5.5 decisions are advisory and require human/editor review.",
            "No packet item is author-approved or publication-approved.",
        ],
        "next_run_recommendation": {},
        "high_reasoning_bridge": bridge_result,
        "verification": {},
    }
    if payload["eligible_for_filing_later_count"] >= 2:
        rec = "build_narrative_packet_candidates_for_eligible_filed_items"
    elif payload["needs_corroboration_count"] >= max(1, len(base) // 2):
        rec = "run_corroboration_research_for_items_needing_corroboration"
    elif payload["duplicate_count"] or payload["do_not_use_count"]:
        rec = "rerun_source_selection_with_larger_sample"
    else:
        rec = "persist_filing_evaluation_notes_to_source_notes"
    payload["next_run_recommendation"] = {"recommendation": rec, "conditions": ["keep report-only unless explicitly asked to persist", "do not insert claims or approve publication", "use human/editor review before narrative packets"]}
    return payload


def md_cell(x: Any) -> str:
    return clean_text(x, 90).replace("|", "\\|")


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [f"# Filing and novelty evaluation: {payload['run_id']}", "", "## Executive summary", ""]
    for key in ["editor_packet_report", "editor_packet_items_available", "downstream_eligible_items_available", "items_evaluated", "provider", "model", "bridge", "reasoning_status"]:
        lines.append(f"- {key}: `{payload.get(key)}`")
    lines += [f"- Filing decision counts: `{payload['filing_decision_counts']}`", f"- Novelty decision counts: `{payload['novelty_decision_counts']}`", f"- Next-stage recommendation counts: `{payload['next_stage_recommendation_counts']}`", "- Safety: report-only; no DB/status/chapter/schema/worker/allowlist changes; not author-approved; not publication-approved.", "", "## Filing/novelty table", "", "| packet item id | source id | semantic object id | semantic object type | chapter target | filing decision | novelty decision | next stage | matched existing claim/source ids | confidence | blockers |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for ev in payload["filing_evaluations"]:
        lines.append("| " + " | ".join([md_cell(ev["packet_item_id"]), md_cell(ev["source_id"]), md_cell(ev["semantic_object_id"]), md_cell(ev["semantic_object_type"]), md_cell(", ".join(ev["candidate_chapter_targets"])), md_cell(ev["filing_decision"]), md_cell(ev["novelty_decision"]), md_cell(ev["next_stage_recommendation"]), md_cell(", ".join(ev["matched_existing_claim_ids"] + ev["matched_existing_source_ids"])), md_cell(ev["confidence"]), md_cell("; ".join(ev["blockers"]))]) + " |")
    lines += ["", "## Per-item filing evaluation"]
    for ev in payload["filing_evaluations"]:
        lines += ["", f"### {ev['filing_evaluation_id']}", "", f"- Provenance: packet `{ev['packet_item_id']}`, source `{ev['source_id']}`, card `{ev['source_card_id']}`, object `{ev['semantic_object_id']}`, quality review `{ev['quality_review_id']}`", f"- Semantic object: {ev['semantic_object_text']}", f"- Filing decision: `{ev['filing_decision']}`", f"- Novelty decision: `{ev['novelty_decision']}`", f"- Next stage: `{ev['next_stage_recommendation']}`", f"- Similarity rationale: {ev['similarity_rationale']}", f"- Corroboration needed: `{ev['corroboration_needed']}`", f"- Corroboration questions: {', '.join(ev['corroboration_questions']) or 'none'}", f"- Required editor decisions: {', '.join(ev['required_editor_decisions']) or 'none'}", f"- Risk flags: {', '.join(ev['risk_flags']) or 'none'}", "- Explicit safety: not author-approved, not publication-approved, advisory-only."]
    s = payload["summary"]
    lines += ["", "## Cross-item synthesis", "", f"- Strongest new candidates: `{s['strongest_new_candidates']}`", f"- Likely duplicates: `{s['likely_duplicates']}`", f"- Items needing corroboration: `{s['items_needing_corroboration']}`", f"- Chapter/topic distribution: `{s['chapter_distribution']}`", f"- Recurring blockers: `{s['recurring_blockers']}`", f"- Before narrative packets: {s['before_narrative_packets']}", "", "## Safety assessment", ""]
    for key in ["db_modified", "db_write_scope", "chapters_modified", "statuses_modified", "schema_modified", "daily_worker_modified", "commit_allowlist_modified", "raw_private_material_written", "long_source_excerpt_written", "claims_inserted", "editorial_reviews_inserted", "author_allowed", "publication_approved", "advisory_only", "external_web_search_used", "vector_db_authority_used"]:
        lines.append(f"- {key}: `{payload[key]}`")
    lines += ["", "## Recommendation for Run 10", "", f"- Recommendation: `{payload['next_run_recommendation']['recommendation']}`"]
    for c in payload["next_run_recommendation"]["conditions"]:
        lines.append(f"- Condition: {c}")
    return "\n".join(lines) + "\n"


def write_reports(payload: dict[str, Any], output_dir: Path, json_only: bool, markdown_only: bool, report_suffix: str) -> dict[str, str]:
    output_dir = output_dir if output_dir.is_absolute() else REPO_ROOT / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    suffix = f"filing-novelty-evaluation-{report_suffix}" if report_suffix else "filing-novelty-evaluation"
    jp = output_dir / f"{payload['run_id']}-{suffix}.json"
    mp = output_dir / f"{payload['run_id']}-{suffix}.md"
    outputs = {"json": repo_relative(jp), "markdown": repo_relative(mp)}
    payload["output_paths"] = outputs
    if not markdown_only: write_json(jp, payload)
    if not json_only: mp.write_text(render_markdown(payload), encoding="utf-8")
    return outputs


def resolve(path: str) -> Path:
    p = Path(path); return p if p.is_absolute() else REPO_ROOT / p


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Report-only filing/novelty evaluation for editor packet chains.")
    p.add_argument("--run-id", default="latest")
    p.add_argument("--output-dir", default="reports/editorial")
    p.add_argument("--editor-packet-report", required=True)
    p.add_argument("--quality-gate-report", default="")
    p.add_argument("--source-card-report", default="")
    p.add_argument("--semantic-object-report", default="")
    p.add_argument("--candidate-selection-report", default="")
    p.add_argument("--only-downstream-eligible", action="store_true")
    p.add_argument("--include-warn", action="store_true")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--provider", default=DEFAULT_PROVIDER)
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--no-llm", action="store_true")
    p.add_argument("--require-high-reasoning", action="store_true")
    p.add_argument("--json-only", action="store_true")
    p.add_argument("--markdown-only", action="store_true")
    p.add_argument("--report-suffix", default="run9")
    args = p.parse_args(argv)
    if args.json_only and args.markdown_only: raise FilingNoveltyError("--json-only and --markdown-only are mutually exclusive")
    if args.no_llm and args.require_high_reasoning: raise FilingNoveltyError("--no-llm and --require-high-reasoning are mutually exclusive")
    if args.include_warn and args.only_downstream_eligible: raise FilingNoveltyError("--include-warn and --only-downstream-eligible are mutually exclusive")
    if args.limit is not None and args.limit < 0: raise FilingNoveltyError("--limit must be non-negative")
    return args


def main(argv: list[str] | None = None) -> int:
    try:
        args = parse_args(argv or sys.argv[1:])
        if not args.no_llm and not args.require_high_reasoning:
            args.require_high_reasoning = True
        packet = load_json(resolve(args.editor_packet_report)); validate_packet(packet)
        items = selected_items(packet, args)
        ctx = existing_context()
        payload = build_payload(args, packet, items, ctx)
        outputs = write_reports(payload, Path(args.output_dir), args.json_only, args.markdown_only, args.report_suffix)
        print(json.dumps({"status": "ok", "run_id": payload["run_id"], "outputs": outputs, "items_evaluated": payload["items_evaluated"], "filing_decision_counts": payload["filing_decision_counts"], "novelty_decision_counts": payload["novelty_decision_counts"], "next_stage_recommendation_counts": payload["next_stage_recommendation_counts"], "llm_used": payload["llm_used"], "provider": payload["provider"], "model": payload["model"], "bridge": payload["bridge"], "db_modified": False, "claims_inserted": 0}, indent=2, sort_keys=True))
        return 0
    except HighReasoningError as exc:
        print("ERROR: high-reasoning filing/novelty call failed; weak/local fallback refused; no DB writes attempted", file=sys.stderr)
        print(json.dumps(exc.result, sort_keys=True), file=sys.stderr)
        return 2
    except FilingNoveltyError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
