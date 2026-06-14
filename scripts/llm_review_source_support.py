#!/usr/bin/env python3
"""Run 10 report-only source-support and corroboration review.

Reads Run 9 filing/novelty evaluations plus Run 8 packet provenance and reviews
whether each filing item is supported enough by its source chain to proceed
later. This script is advisory/report-only: no DB writes, no claim insertion, no
status changes, no chapter edits, no narrative packets, no publication/author
approval.
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

MODE = "source_support_review"
ALLOWED_SUPPORT = {"supported", "partially_supported", "unsupported", "unclear"}
ALLOWED_CORROBORATION = {"corroboration_not_required", "corroboration_recommended", "corroboration_required", "cannot_corrobate_from_available_material"}
ALLOWED_EVIDENCE_USE = {"eligible_for_filing_later", "eligible_as_caveat_only", "needs_corroboration_before_filing", "needs_source_review", "too_weak", "do_not_use"}
ALLOWED_NEXT = {"eligible_for_filing_persistence", "run_corroboration_research", "needs_human_editor_review", "needs_prompt_revision", "needs_source_review", "ignore", "do_not_use"}


class SourceSupportError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def repo_relative(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def resolve(path: str) -> Path:
    p = Path(path)
    return p if p.is_absolute() else REPO_ROOT / p


def clean_text(value: Any, max_len: int = 360) -> str:
    text = re.sub(r"https?://\S+", "[url]", str(value or ""))
    text = re.sub(r"\b(?:claim|src|note|card|obj|review|filing_eval|editor_packet)_[0-9a-f]{8,}\b", "[internal-id]", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[: max_len - 1].rstrip() + "…" if len(text) > max_len else text


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
        raise SourceSupportError(f"missing input report: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SourceSupportError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise SourceSupportError(f"input report must be object: {path}")
    return data


def connect_readonly() -> sqlite3.Connection:
    con = sqlite3.connect(f"file:{DB_PATH.resolve()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA query_only = ON")
    return con


def db_context(source_ids: list[str]) -> dict[str, Any]:
    out = {"sources": [], "source_notes": [], "claims_sample_count": 0}
    if not DB_PATH.exists():
        return out
    with connect_readonly() as con:
        try:
            out["claims_sample_count"] = con.execute("SELECT COUNT(*) FROM claims").fetchone()[0]
        except sqlite3.Error:
            pass
        if source_ids:
            q = ",".join("?" for _ in source_ids)
            try:
                cols = {r[1] for r in con.execute("PRAGMA table_info(sources)")}
                select = [c for c in ["id", "title", "source_type", "publisher", "quality_score", "privacy_publication_status", "url"] if c in cols]
                if select:
                    for r in con.execute(f"SELECT {', '.join(select)} FROM sources WHERE id IN ({q})", source_ids):
                        d = dict(r)
                        for k in ["title", "publisher", "url"]:
                            if k in d:
                                d[k] = clean_text(d[k], 180)
                        out["sources"].append(d)
            except sqlite3.Error:
                pass
            try:
                cols = {r[1] for r in con.execute("PRAGMA table_info(source_notes)")}
                select = [c for c in ["id", "source_id", "note_type", "note", "created_at"] if c in cols]
                if select:
                    for r in con.execute(f"SELECT {', '.join(select)} FROM source_notes WHERE source_id IN ({q}) ORDER BY created_at DESC, id DESC LIMIT 80", source_ids):
                        d = dict(r)
                        if "note" in d:
                            d["note"] = clean_text(d["note"], 240)
                        out["source_notes"].append(d)
            except sqlite3.Error:
                pass
    return out


def validate_inputs(filing: dict[str, Any], packet: dict[str, Any] | None) -> None:
    if filing.get("mode") != "filing_novelty_evaluation":
        raise SourceSupportError("filing/novelty report mode mismatch")
    if filing.get("author_allowed") is not False or filing.get("publication_approved") is not False or filing.get("advisory_only") is not True:
        raise SourceSupportError("filing report approval/advisory flags invalid")
    if filing.get("db_modified") not in (False, None):
        raise SourceSupportError("filing report indicates DB modification")
    if packet is not None:
        if packet.get("mode") != "editor_review_packet":
            raise SourceSupportError("editor packet mode mismatch")
        if packet.get("author_allowed") is not False or packet.get("publication_approved") is not False or packet.get("advisory_only") is not True:
            raise SourceSupportError("editor packet approval/advisory flags invalid")


def packet_index(packet: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not packet:
        return {}
    return {str(i.get("packet_item_id")): i for i in packet.get("packet_items", []) if i.get("packet_item_id")}


def select_evaluations(filing: dict[str, Any], args: argparse.Namespace) -> list[dict[str, Any]]:
    items = list(filing.get("filing_evaluations", []))
    if args.only_needs_source_review or not args.include_warn:
        items = [i for i in items if i.get("next_stage_recommendation") in {"needs_source_review", "run_corroboration_research"} or i.get("filing_decision") in {"needs_corroboration", "new_caveat_candidate", "new_claim_candidate"} or bool(i.get("corroboration_needed"))]
    if args.limit is not None:
        items = items[: args.limit]
    for item in items:
        for key in ["filing_evaluation_id", "packet_item_id", "source_id", "source_card_id", "semantic_object_id", "quality_review_id", "semantic_object_text"]:
            if not item.get(key):
                raise SourceSupportError(f"filing evaluation missing {key}: {item.get('filing_evaluation_id')}")
        if item.get("author_allowed") is not False or item.get("publication_approved") is not False or item.get("advisory_only") is not True:
            raise SourceSupportError(f"filing evaluation approval/advisory flags invalid: {item.get('filing_evaluation_id')}")
    return items


def structural_review(ev: dict[str, Any], pkt: dict[str, Any] | None, *, llm_used: bool, provider: str, model: str, bridge: str, reasoning_status: str) -> dict[str, Any]:
    quality = str((pkt or {}).get("quality_score") or "").upper()
    filing = str(ev.get("filing_decision") or "")
    is_caveat = filing == "new_caveat_candidate" or "caveat" in str(ev.get("semantic_object_type", "")).lower()
    needs_corr = bool(ev.get("corroboration_needed")) or filing in {"needs_corroboration", "new_claim_candidate"}
    support = "partially_supported" if pkt else "unclear"
    corr_decision = "corroboration_required" if needs_corr else "corroboration_recommended"
    if not pkt:
        corr_decision = "cannot_corrobate_from_available_material"
        evidence_use = "needs_source_review"
        next_stage = "needs_source_review"
    elif is_caveat and not needs_corr and quality in {"A", "B"}:
        evidence_use = "eligible_as_caveat_only"
        next_stage = "needs_human_editor_review"
    elif is_caveat:
        evidence_use = "eligible_as_caveat_only"
        next_stage = "needs_human_editor_review" if not needs_corr else "run_corroboration_research"
    elif needs_corr:
        evidence_use = "needs_corroboration_before_filing"
        next_stage = "run_corroboration_research"
    else:
        evidence_use = "needs_source_review"
        next_stage = "needs_human_editor_review"
    seed = json.dumps({"eval": ev["filing_evaluation_id"], "support": support, "corr": corr_decision, "use": evidence_use}, sort_keys=True)
    item = {
        "source_review_id": "source_review_" + sha256_text(seed)[:20],
        "run_id": ev.get("run_id"),
        "filing_evaluation_id": ev["filing_evaluation_id"],
        "packet_item_id": ev["packet_item_id"],
        "source_id": ev["source_id"],
        "source_card_id": ev["source_card_id"],
        "semantic_object_id": ev["semantic_object_id"],
        "quality_review_id": ev["quality_review_id"],
        "source_title": clean_text((pkt or {}).get("source_title"), 180),
        "source_type": clean_text((pkt or {}).get("source_type"), 80),
        "publisher": clean_text((pkt or {}).get("publisher"), 120),
        "quality_score": clean_text((pkt or {}).get("quality_score"), 20),
        "privacy_publication_status": clean_text((pkt or {}).get("privacy_publication_status"), 80),
        "canonical_url_available": bool((pkt or {}).get("canonical_url_available")),
        "semantic_object_type": clean_text(ev.get("semantic_object_type"), 80),
        "semantic_object_text": clean_text(ev.get("semantic_object_text"), 320),
        "filing_decision": clean_text(ev.get("filing_decision"), 80),
        "novelty_decision": clean_text(ev.get("novelty_decision"), 80),
        "source_support_decision": support,
        "corroboration_decision": corr_decision,
        "evidence_use_decision": evidence_use,
        "next_stage_recommendation": next_stage,
        "support_rationale": "Packet/source-card provenance is present and gives enough advisory context for source review, but Run 10 does not treat a single source as final truth.",
        "corroboration_rationale": "Independent corroboration is required or recommended before later filing/persistence unless a human editor accepts caveat-only use.",
        "corroboration_questions": listify(ev.get("corroboration_questions")) or ["Can a second public source independently support this semantic object?"],
        "suggested_corroboration_sources": ["official/project documentation", "independent public analysis", "primary source release notes or repository docs"],
        "blockers": listify(ev.get("blockers")),
        "risk_flags": sorted(set(listify(ev.get("risk_flags")) + (["single_source_chain"] if needs_corr else []))),
        "required_editor_decisions": listify(ev.get("required_editor_decisions")) or ["Confirm source support before later filing/persistence."],
        "confidence": "low" if not llm_used else "medium",
        "author_allowed": False,
        "publication_approved": False,
        "advisory_only": True,
        "input_hash": sha256_text(json.dumps({"filing": ev, "packet": pkt or {}}, sort_keys=True, ensure_ascii=False)),
        "output_hash": "",
        "llm_used": llm_used,
        "provider": provider if llm_used else "none",
        "model": model if llm_used else "none",
        "bridge": bridge if llm_used else "none",
        "reasoning_status": reasoning_status,
    }
    item["output_hash"] = sha256_text(json.dumps({k: v for k, v in item.items() if k != "output_hash"}, sort_keys=True, ensure_ascii=False))
    return item


def validate_llm_response(obj: dict[str, Any]) -> None:
    reviews = obj.get("source_reviews")
    if not isinstance(reviews, list):
        raise ValueError("source_reviews must be a list")
    for r in reviews:
        if not isinstance(r, dict):
            raise ValueError("source review must be object")
        if not r.get("filing_evaluation_id"):
            raise ValueError("filing_evaluation_id required")
        if r.get("source_support_decision") not in ALLOWED_SUPPORT:
            raise ValueError("invalid source_support_decision")
        if r.get("corroboration_decision") not in ALLOWED_CORROBORATION:
            raise ValueError("invalid corroboration_decision")
        if r.get("evidence_use_decision") not in ALLOWED_EVIDENCE_USE:
            raise ValueError("invalid evidence_use_decision")
        if r.get("next_stage_recommendation") not in ALLOWED_NEXT:
            raise ValueError("invalid next_stage_recommendation")


def build_prompt(reviews: list[dict[str, Any]], ctx: dict[str, Any]) -> str:
    compact = []
    for r in reviews:
        compact.append({
            "filing_evaluation_id": r["filing_evaluation_id"],
            "packet_item_id": r["packet_item_id"],
            "source_id": r["source_id"],
            "source_card_id": r["source_card_id"],
            "semantic_object_id": r["semantic_object_id"],
            "quality_review_id": r["quality_review_id"],
            "source_title": r["source_title"],
            "source_type": r["source_type"],
            "quality_score": r["quality_score"],
            "privacy_publication_status": r["privacy_publication_status"],
            "semantic_object_type": r["semantic_object_type"],
            "semantic_object_text": r["semantic_object_text"],
            "filing_decision": r["filing_decision"],
            "novelty_decision": r["novelty_decision"],
            "risk_flags": r["risk_flags"],
        })
    schema = {
        "source_reviews": [{
            "filing_evaluation_id": "...",
            "source_support_decision": sorted(ALLOWED_SUPPORT),
            "corroboration_decision": sorted(ALLOWED_CORROBORATION),
            "evidence_use_decision": sorted(ALLOWED_EVIDENCE_USE),
            "next_stage_recommendation": sorted(ALLOWED_NEXT),
            "support_rationale": "short rationale",
            "corroboration_rationale": "short rationale",
            "corroboration_questions": [],
            "suggested_corroboration_sources": [],
            "blockers": [],
            "risk_flags": [],
            "required_editor_decisions": [],
            "confidence": "low|medium|high",
        }]
    }
    return "\n".join([
        "You are doing report-only source-support review for advisory filing items.",
        "No publication approval, no author approval, no claim insertion. Do not browse the web. Use only provided source-chain metadata and DB context.",
        "Return strict JSON only. supported does not mean true; eligible_for_filing_persistence does not write to DB.",
        "Schema:", json.dumps(schema, ensure_ascii=False),
        "Items:", json.dumps(compact, ensure_ascii=False),
        "Read-only DB context:", json.dumps(ctx, ensure_ascii=False),
    ])


def merge_llm(base_reviews: list[dict[str, Any]], parsed: dict[str, Any], provider: str, model: str) -> list[dict[str, Any]]:
    by_id = {str(r.get("filing_evaluation_id")): r for r in parsed.get("source_reviews", []) if isinstance(r, dict)}
    out = []
    for base in base_reviews:
        src = by_id.get(base["filing_evaluation_id"], {})
        r = dict(base)
        for key in ["source_support_decision", "corroboration_decision", "evidence_use_decision", "next_stage_recommendation", "support_rationale", "corroboration_rationale", "confidence"]:
            if key in src:
                r[key] = src[key]
        for key in ["corroboration_questions", "suggested_corroboration_sources", "blockers", "risk_flags", "required_editor_decisions"]:
            if key in src:
                r[key] = listify(src[key])
        if r["source_support_decision"] not in ALLOWED_SUPPORT or r["corroboration_decision"] not in ALLOWED_CORROBORATION or r["evidence_use_decision"] not in ALLOWED_EVIDENCE_USE or r["next_stage_recommendation"] not in ALLOWED_NEXT:
            raise SourceSupportError(f"invalid LLM decision for {r['filing_evaluation_id']}")
        r.update({"llm_used": True, "provider": provider, "model": model, "bridge": "hermes_cli", "reasoning_status": "high_reasoning_used", "author_allowed": False, "publication_approved": False, "advisory_only": True})
        r["output_hash"] = sha256_text(json.dumps({k: v for k, v in r.items() if k != "output_hash"}, sort_keys=True, ensure_ascii=False))
        out.append(r)
    return out


def build_payload(args: argparse.Namespace, filing: dict[str, Any], packet: dict[str, Any] | None) -> dict[str, Any]:
    pkt_by_id = packet_index(packet)
    evals = select_evaluations(filing, args)
    ctx = db_context([str(e["source_id"]) for e in evals])
    llm_used = not args.no_llm
    provider = args.provider if llm_used else "none"
    model = args.model if llm_used else "none"
    bridge = "hermes_cli" if llm_used else "none"
    reasoning_status = "high_reasoning_used" if llm_used else "no_llm_structural_only"
    reviews = [structural_review(e, pkt_by_id.get(e["packet_item_id"]), llm_used=llm_used, provider=args.provider, model=args.model, bridge="hermes_cli", reasoning_status=reasoning_status) for e in evals]
    bridge_result: dict[str, Any] = {}
    if llm_used:
        bridge_result = call_high_reasoning_json(build_prompt(reviews, ctx), "source_support_review_v1", validate_llm_response, provider=args.provider, model=args.model)
        reviews = merge_llm(reviews, bridge_result["parsed_json"], args.provider, args.model)
    support_counts = dict(Counter(r["source_support_decision"] for r in reviews))
    corr_counts = dict(Counter(r["corroboration_decision"] for r in reviews))
    use_counts = dict(Counter(r["evidence_use_decision"] for r in reviews))
    next_counts = dict(Counter(r["next_stage_recommendation"] for r in reviews))
    payload = {
        "run_id": args.run_id if args.run_id != "latest" else filing.get("run_id", "latest"),
        "generated_at": utc_now(),
        "mode": MODE,
        "llm_used": llm_used,
        "provider": provider,
        "model": model,
        "bridge": bridge,
        "reasoning_status": reasoning_status,
        "confidence_level": "medium" if llm_used else "low",
        "filing_novelty_report": repo_relative(resolve(args.filing_novelty_report)),
        "editor_packet_report": repo_relative(resolve(args.editor_packet_report)) if args.editor_packet_report else "",
        "filing_evaluations_available": len(filing.get("filing_evaluations", [])),
        "items_reviewed": len(reviews),
        "source_support_decision_counts": support_counts,
        "corroboration_decision_counts": corr_counts,
        "evidence_use_decision_counts": use_counts,
        "next_stage_recommendation_counts": next_counts,
        "eligible_for_filing_persistence_count": next_counts.get("eligible_for_filing_persistence", 0),
        "eligible_as_caveat_only_count": use_counts.get("eligible_as_caveat_only", 0),
        "needs_corroboration_count": corr_counts.get("corroboration_required", 0) + use_counts.get("needs_corroboration_before_filing", 0),
        "do_not_use_count": use_counts.get("do_not_use", 0) + next_counts.get("do_not_use", 0),
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
        "live_web_corroboration_used": bool(args.allow_live_web_corroboration and False),
        "author_allowed": False,
        "publication_approved": False,
        "advisory_only": True,
        "source_reviews": reviews,
        "summary": {
            "items_sufficiently_supported": [r["source_review_id"] for r in reviews if r["source_support_decision"] == "supported"],
            "items_eligible_as_caveat_only": [r["source_review_id"] for r in reviews if r["evidence_use_decision"] == "eligible_as_caveat_only"],
            "items_requiring_corroboration": [r["source_review_id"] for r in reviews if r["corroboration_decision"] == "corroboration_required" or r["evidence_use_decision"] == "needs_corroboration_before_filing"],
            "items_too_weak_or_unsupported": [r["source_review_id"] for r in reviews if r["source_support_decision"] == "unsupported" or r["evidence_use_decision"] in {"too_weak", "do_not_use"}],
            "before_filing_persistence_or_narrative_packets": "Resolve source-review/corroboration blockers and obtain human/editor review; no author/publication approval is granted.",
        },
        "risks": ["Report-only advisory review.", "No external web search was run by default.", "Single-source chains may still overclaim.", "No item is author-approved or publication-approved."],
        "next_run_recommendation": {},
        "high_reasoning_bridge": bridge_result,
        "verification": {},
    }
    if payload["eligible_for_filing_persistence_count"] >= 2:
        rec = "persist_source_review_filing_notes_to_source_notes_disabled_by_default"
    elif next_counts.get("run_corroboration_research", 0) >= 2 or payload["needs_corroboration_count"] >= 2:
        rec = "run_live_corroboration_research_for_items_requiring_corroboration"
    elif payload["eligible_as_caveat_only_count"] >= 2:
        rec = "build_caveat_focused_narrative_packet_candidates_report_only"
    else:
        rec = "rerun_source_selection_with_larger_sample"
    payload["next_run_recommendation"] = {"recommendation": rec, "conditions": ["remain report-only unless persistence is explicitly authorized", "do not insert claims or approve publication", "avoid narrative packets until source support/corroboration blockers are resolved"]}
    return payload


def md_cell(v: Any) -> str:
    return clean_text(v, 90).replace("|", "\\|")


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [f"# Source-support review: {payload['run_id']}", "", "## Executive summary", ""]
    for k in ["filing_novelty_report", "items_reviewed", "provider", "model", "bridge", "reasoning_status"]:
        lines.append(f"- {k}: `{payload.get(k)}`")
    lines += [f"- Source-support decision counts: `{payload['source_support_decision_counts']}`", f"- Corroboration decision counts: `{payload['corroboration_decision_counts']}`", f"- Evidence-use decision counts: `{payload['evidence_use_decision_counts']}`", f"- Next-stage recommendation counts: `{payload['next_stage_recommendation_counts']}`", "- Safety: report-only; no DB/status/chapter/schema/worker/allowlist changes; not author-approved; not publication-approved.", "", "## Source-support table", "", "| filing evaluation id | packet item id | source id | semantic object id | filing decision | source support | corroboration | evidence use | next stage | confidence | blockers |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in payload["source_reviews"]:
        lines.append("| " + " | ".join([md_cell(r["filing_evaluation_id"]), md_cell(r["packet_item_id"]), md_cell(r["source_id"]), md_cell(r["semantic_object_id"]), md_cell(r["filing_decision"]), md_cell(r["source_support_decision"]), md_cell(r["corroboration_decision"]), md_cell(r["evidence_use_decision"]), md_cell(r["next_stage_recommendation"]), md_cell(r["confidence"]), md_cell("; ".join(r["blockers"]))]) + " |")
    lines += ["", "## Per-item source review"]
    for r in payload["source_reviews"]:
        lines += ["", f"### {r['source_review_id']}", "", f"- Provenance: filing `{r['filing_evaluation_id']}`, packet `{r['packet_item_id']}`, source `{r['source_id']}`, card `{r['source_card_id']}`, object `{r['semantic_object_id']}`, quality review `{r['quality_review_id']}`", f"- Source metadata: {r['source_title']} / {r['source_type']} / quality `{r['quality_score']}` / privacy `{r['privacy_publication_status']}`", f"- Semantic object: {r['semantic_object_text']}", f"- Source support rationale: {r['support_rationale']}", f"- Corroboration rationale: {r['corroboration_rationale']}", f"- Corroboration questions: {', '.join(r['corroboration_questions']) or 'none'}", f"- Suggested corroboration sources: {', '.join(r['suggested_corroboration_sources']) or 'none'}", f"- Evidence-use decision: `{r['evidence_use_decision']}`", f"- Required editor decisions: {', '.join(r['required_editor_decisions']) or 'none'}", f"- Risk flags: {', '.join(r['risk_flags']) or 'none'}", "- Explicit safety: not author-approved, not publication-approved, advisory-only."]
    s = payload["summary"]
    lines += ["", "## Cross-item synthesis", "", f"- Items sufficiently supported: `{s['items_sufficiently_supported']}`", f"- Items eligible as caveat-only: `{s['items_eligible_as_caveat_only']}`", f"- Items requiring corroboration: `{s['items_requiring_corroboration']}`", f"- Items too weak or unsupported: `{s['items_too_weak_or_unsupported']}`", f"- Before filing/persistence/narrative packets: {s['before_filing_persistence_or_narrative_packets']}", "", "## Safety assessment", ""]
    for k in ["db_modified", "db_write_scope", "chapters_modified", "statuses_modified", "schema_modified", "daily_worker_modified", "commit_allowlist_modified", "raw_private_material_written", "long_source_excerpt_written", "live_web_corroboration_used", "claims_inserted", "editorial_reviews_inserted", "author_allowed", "publication_approved", "advisory_only"]:
        lines.append(f"- {k}: `{payload[k]}`")
    lines += ["", "## Recommendation for Run 11", "", f"- Recommendation: `{payload['next_run_recommendation']['recommendation']}`"]
    for c in payload["next_run_recommendation"]["conditions"]:
        lines.append(f"- Condition: {c}")
    return "\n".join(lines) + "\n"


def write_reports(payload: dict[str, Any], output_dir: Path, json_only: bool, markdown_only: bool, suffix: str) -> dict[str, str]:
    output_dir = output_dir if output_dir.is_absolute() else REPO_ROOT / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    name = f"source-support-review-{suffix}" if suffix else "source-support-review"
    jp = output_dir / f"{payload['run_id']}-{name}.json"
    mp = output_dir / f"{payload['run_id']}-{name}.md"
    outputs = {"json": repo_relative(jp), "markdown": repo_relative(mp)}
    payload["output_paths"] = outputs
    if not markdown_only:
        write_json(jp, payload)
    if not json_only:
        mp.write_text(render_markdown(payload), encoding="utf-8")
    return outputs


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Report-only source-support/corroboration review.")
    p.add_argument("--run-id", default="latest")
    p.add_argument("--output-dir", default="reports/editorial")
    p.add_argument("--filing-novelty-report", required=True)
    p.add_argument("--editor-packet-report", default="")
    p.add_argument("--source-card-report", default="")
    p.add_argument("--semantic-object-report", default="")
    p.add_argument("--quality-gate-report", default="")
    p.add_argument("--candidate-selection-report", default="")
    p.add_argument("--only-needs-source-review", action="store_true")
    p.add_argument("--include-warn", action="store_true")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--provider", default=DEFAULT_PROVIDER)
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--no-llm", action="store_true")
    p.add_argument("--require-high-reasoning", action="store_true")
    p.add_argument("--json-only", action="store_true")
    p.add_argument("--markdown-only", action="store_true")
    p.add_argument("--report-suffix", default="run10")
    p.add_argument("--allow-live-web-corroboration", action="store_true")
    args = p.parse_args(argv)
    if args.json_only and args.markdown_only:
        raise SourceSupportError("--json-only and --markdown-only are mutually exclusive")
    if args.no_llm and args.require_high_reasoning:
        raise SourceSupportError("--no-llm and --require-high-reasoning are mutually exclusive")
    if args.limit is not None and args.limit < 0:
        raise SourceSupportError("--limit must be non-negative")
    if args.allow_live_web_corroboration:
        raise SourceSupportError("live web corroboration is not implemented in Run 10; disabled by default")
    return args


def main(argv: list[str] | None = None) -> int:
    try:
        args = parse_args(argv or sys.argv[1:])
        if not args.no_llm and not args.require_high_reasoning:
            args.require_high_reasoning = True
        filing = load_json(resolve(args.filing_novelty_report))
        packet = load_json(resolve(args.editor_packet_report)) if args.editor_packet_report else None
        validate_inputs(filing, packet)
        payload = build_payload(args, filing, packet)
        outputs = write_reports(payload, Path(args.output_dir), args.json_only, args.markdown_only, args.report_suffix)
        print(json.dumps({"status": "ok", "run_id": payload["run_id"], "outputs": outputs, "items_reviewed": payload["items_reviewed"], "source_support_decision_counts": payload["source_support_decision_counts"], "corroboration_decision_counts": payload["corroboration_decision_counts"], "evidence_use_decision_counts": payload["evidence_use_decision_counts"], "next_stage_recommendation_counts": payload["next_stage_recommendation_counts"], "llm_used": payload["llm_used"], "provider": payload["provider"], "model": payload["model"], "bridge": payload["bridge"], "db_modified": False, "claims_inserted": 0}, indent=2, sort_keys=True))
        return 0
    except HighReasoningError as exc:
        print("ERROR: high-reasoning source-support call failed; weak/local fallback refused; no DB writes attempted", file=sys.stderr)
        print(json.dumps(exc.result, sort_keys=True), file=sys.stderr)
        return 2
    except SourceSupportError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
