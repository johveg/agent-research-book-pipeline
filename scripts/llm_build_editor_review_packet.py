#!/usr/bin/env python3
"""Build a report-only human/editor review packet for passed high-reasoning chains.

Run 8 safety model:
- Reads prior JSON reports only.
- Does not call an LLM.
- Does not write SQLite, docs/book, raw captures, schema, daily worker wiring, commit allowlists, claims, statuses, narrative packets, or chapter prose.
- Packet items are advisory only and never author/publication approvals.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from research_common import ROOT as REPO_ROOT, sha256_text, write_json  # noqa: E402

MODE = "editor_review_packet"
RAW_ID_RE = re.compile(r"\b(?:claim)_[0-9a-f]{8,}\b")


class EditorPacketError(RuntimeError):
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


def clean_text(text: Any, max_len: int = 260) -> str:
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
        raise EditorPacketError(f"missing input report: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise EditorPacketError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise EditorPacketError(f"input report must be JSON object: {path}")
    return data


def require_high_reasoning(report: dict[str, Any], label: str) -> None:
    if report.get("llm_used") is not True:
        raise EditorPacketError(f"{label} report is not live high-reasoning output")
    if report.get("reasoning_status") != "high_reasoning_used":
        raise EditorPacketError(f"{label} report does not have reasoning_status=high_reasoning_used")
    if report.get("provider") != "copilot" or report.get("model") != "gpt-5.5" or report.get("bridge") != "hermes_cli":
        raise EditorPacketError(f"{label} report has unexpected provider/model/bridge")
    if report.get("db_modified") not in (False, None):
        raise EditorPacketError(f"{label} report indicates DB modification")


def assert_no_approval(obj: dict[str, Any], label: str) -> None:
    # Older upstream draft reports may omit explicit approval booleans, but they must never
    # contain affirmative approval. The Run 8 packet itself normalizes all output flags to
    # author_allowed=false, publication_approved=false, advisory_only=true.
    if obj.get("author_allowed") is True:
        raise EditorPacketError(f"{label} violates approval safety: author_allowed must not be true")
    if obj.get("publication_approved") is True:
        raise EditorPacketError(f"{label} violates approval safety: publication_approved must not be true")
    if "advisory_only" in obj and obj.get("advisory_only") is not True:
        raise EditorPacketError(f"{label} violates advisory safety: advisory_only must be true when present")


def ensure_inputs(candidate: dict[str, Any], source_cards: dict[str, Any], semantic: dict[str, Any], quality: dict[str, Any]) -> None:
    if candidate.get("db_modified") not in (False, None):
        raise EditorPacketError("candidate-selection report indicates DB modification")
    require_high_reasoning(source_cards, "source-card")
    require_high_reasoning(semantic, "semantic-object")
    require_high_reasoning(quality, "quality-gate")
    for card in source_cards.get("source_cards", []):
        assert_no_approval(card, f"source card {card.get('card_id')}")
    for obj in semantic.get("semantic_objects", []):
        assert_no_approval(obj, f"semantic object {obj.get('semantic_object_id')}")
    for review in quality.get("source_card_reviews", []) + quality.get("semantic_object_reviews", []):
        assert_no_approval(review, f"quality review {review.get('review_id') or review.get('target_id')}")


def key_by(items: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for item in items:
        value = item.get(key)
        if value:
            out[str(value)] = item
    return out


def build_packet_item(run_id: str, card: dict[str, Any], obj: dict[str, Any], review: dict[str, Any], card_review: dict[str, Any] | None) -> dict[str, Any]:
    decision = str(review.get("decision") or "warn")
    if decision not in {"pass", "warn", "fail"}:
        decision = {"ready_for_editor_review": "pass", "needs_revision": "warn", "blocked": "fail"}.get(decision, "warn")
    downstream = decision == "pass" and str(review.get("downstream_eligibility") or "").lower() in {
        "ready_for_editor_review",
        "eligible_for_human_editor_review",
        "eligible_for_editor_review",
        "eligible",
    }
    if decision == "fail":
        downstream = False
    seed = "|".join([run_id, str(card.get("card_id")), str(obj.get("semantic_object_id")), str(review.get("review_id") or review.get("target_id"))])
    source_hash = str(obj.get("source_text_hash") or card.get("source_text_hash") or "")
    card_hash = str(obj.get("source_card_hash") or card.get("card_output_hash") or card.get("card_input_hash") or "")
    obj_hash = str(obj.get("object_output_hash") or sha256_text(json.dumps(obj, sort_keys=True, ensure_ascii=False)))
    review_hash = str(review.get("review_output_hash") or review.get("output_hash") or sha256_text(json.dumps(review, sort_keys=True, ensure_ascii=False)))
    caveats = []
    caveats.extend(listify(review.get("weaknesses")))
    caveats.extend(listify(card.get("risk_flags")))
    caveats.extend(listify(obj.get("risk_flags")))
    if card_review and card_review.get("decision") != "pass":
        caveats.append(f"source-card review decision is {card_review.get('decision')}")
    caveats.append("Not author-approved and not publication-approved; editor packet only.")
    return {
        "packet_item_id": "editor_packet_" + sha256_text(seed)[:20],
        "run_id": run_id,
        "source_id": str(obj.get("source_id") or card.get("source_id") or review.get("source_id") or ""),
        "source_card_id": str(card.get("card_id") or obj.get("source_card_id") or review.get("source_card_id") or ""),
        "semantic_object_id": str(obj.get("semantic_object_id") or review.get("target_id") or ""),
        "quality_review_id": str(review.get("review_id") or review.get("target_id") or ""),
        "source_title": clean_text(card.get("title"), 180),
        "source_type": clean_text(card.get("source_type"), 80),
        "publisher": clean_text(card.get("publisher"), 120),
        "canonical_url_available": bool(card.get("canonical_url_available")),
        "quality_score": clean_text(card.get("quality_score"), 20),
        "privacy_publication_status": clean_text(card.get("privacy_publication_status"), 80),
        "candidate_chapter_targets": listify(obj.get("candidate_chapter_targets") or card.get("likely_chapter_targets")),
        "semantic_object_type": clean_text(obj.get("object_type"), 80),
        "semantic_object_text": clean_text(obj.get("text"), 300),
        "source_card_summary": clean_text(card.get("safe_summary") or card.get("main_thesis"), 300),
        "quality_decision": decision,
        "downstream_eligible": downstream,
        "recommended_next_stage": clean_text(review.get("recommended_next_stage") or ("filing_novelty_evaluation_candidate" if downstream else "editor_revision_needed"), 120),
        "strengths": listify(review.get("strengths")),
        "weaknesses": listify(review.get("weaknesses")),
        "required_fixes": listify(review.get("required_fixes")),
        "risk_flags": sorted(set(listify(review.get("risk_flags")) + listify(card.get("risk_flags")) + listify(obj.get("risk_flags")))),
        "caveats": sorted(set(caveats)),
        "source_text_hash": source_hash,
        "source_card_hash": card_hash,
        "semantic_object_hash": obj_hash,
        "quality_review_hash": review_hash,
        "author_allowed": False,
        "publication_approved": False,
        "advisory_only": True,
    }


def build_packet(args: argparse.Namespace, reports: dict[str, dict[str, Any]]) -> dict[str, Any]:
    candidate = reports["candidate"]
    source_report = reports["source"]
    semantic_report = reports["semantic"]
    quality_report = reports["quality"]
    ensure_inputs(candidate, source_report, semantic_report, quality_report)
    run_id = args.run_id if args.run_id != "latest" else str(source_report.get("run_id") or quality_report.get("run_id") or "latest")
    cards = key_by(source_report.get("source_cards", []), "card_id")
    objects = key_by(semantic_report.get("semantic_objects", []), "semantic_object_id")
    card_reviews = key_by(quality_report.get("source_card_reviews", []), "target_id")
    packet_items: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for review in quality_report.get("semantic_object_reviews", []):
        obj_id = str(review.get("target_id") or "")
        obj = objects.get(obj_id)
        card_id = str(review.get("source_card_id") or (obj or {}).get("source_card_id") or "")
        card = cards.get(card_id)
        if not obj or not card or not card_id:
            excluded.append({"target_id": obj_id, "reason": "missing complete source-card/semantic-object linkage"})
            continue
        if card.get("source_id") != obj.get("source_id") or review.get("source_id") != obj.get("source_id"):
            excluded.append({"target_id": obj_id, "reason": "source linkage mismatch"})
            continue
        decision = review.get("decision")
        if decision == "fail" or review.get("downstream_eligibility") == "blocked":
            excluded.append({"target_id": obj_id, "reason": "failed/blocked item excluded from ready packet"})
            continue
        item = build_packet_item(run_id, card, obj, review, card_reviews.get(card_id))
        if item["quality_decision"] == "fail":
            item["downstream_eligible"] = False
        packet_items.append(item)
    counts = Counter(item["quality_decision"] for item in packet_items)
    chapters = Counter(ch for item in packet_items for ch in item["candidate_chapter_targets"])
    risks = Counter(flag for item in packet_items for flag in item["risk_flags"])
    caveats = Counter(c for item in packet_items for c in item["caveats"])
    payload = {
        "run_id": run_id,
        "generated_at": utc_now(),
        "mode": MODE,
        "input_reports": {
            "candidate_selection_report": repo_relative(Path(args.candidate_selection_report).resolve()),
            "source_card_report": repo_relative(Path(args.source_card_report).resolve()),
            "semantic_object_report": repo_relative(Path(args.semantic_object_report).resolve()),
            "quality_gate_report": repo_relative(Path(args.quality_gate_report).resolve()),
        },
        "source_cards_available": len(source_report.get("source_cards", [])),
        "semantic_objects_available": len(semantic_report.get("semantic_objects", [])),
        "quality_reviews_available": len(quality_report.get("source_card_reviews", [])) + len(quality_report.get("semantic_object_reviews", [])),
        "quality_source_cards_reviewed": quality_report.get("source_cards_reviewed"),
        "quality_semantic_objects_reviewed": quality_report.get("semantic_objects_reviewed"),
        "packet_items_total": len(packet_items),
        "packet_items_pass": counts.get("pass", 0),
        "packet_items_warn": counts.get("warn", 0),
        "packet_items_fail": counts.get("fail", 0),
        "complete_chains_total": len(packet_items),
        "downstream_eligible_count": sum(1 for item in packet_items if item["downstream_eligible"]),
        "author_allowed": False,
        "publication_approved": False,
        "advisory_only": True,
        "db_modified": False,
        "db_write_scope": "none",
        "chapters_modified": False,
        "statuses_modified": False,
        "schema_modified": False,
        "daily_worker_modified": False,
        "commit_allowlist_modified": False,
        "raw_private_material_written": False,
        "long_source_excerpt_written": False,
        "claims_inserted": 0,
        "narrative_packets_created": False,
        "chapter_prose_generated": False,
        "packet_items": packet_items,
        "excluded_items": excluded,
        "editor_summary": {
            "strongest_candidate_themes": [k for k, _ in chapters.most_common(8)],
            "weakest_areas": [k for k, _ in risks.most_common(8)] or ["human/editor corroboration still required"],
            "recurring_caveats": [k for k, _ in caveats.most_common(8)],
            "missing_corroboration": "No external corroboration/fetching was performed in Run 8; packet is based on Run 7 reports and existing metadata only.",
            "suggested_next_editorial_decisions": [
                "Review passed chains for filing/novelty evaluation eligibility.",
                "Decide whether any warn items need source-card or semantic-object revision before downstream work.",
                "Keep author/publication approval disabled until human review and corroboration are complete.",
            ],
        },
        "risks": [
            "Packet is advisory and report-only; not an approval workflow.",
            "Source text is excerpt-limited/summarized and may require editor source verification.",
            "Quality-gate decisions are GPT-5.5 reviewer judgments and should be checked by a human editor.",
            "No vector DB chunks were used as source authority.",
        ],
        "next_run_recommendation": {
            "recommendation": "proceed_to_filing_novelty_evaluation_for_packet_items",
            "conditions": [
                "Keep report-only defaults.",
                "Use only packet items with downstream_eligible=true.",
                "Do not insert claims or approve publication without explicit human/editor decision.",
            ],
        },
        "verification": {},
    }
    return payload


def md_cell(text: Any) -> str:
    return clean_text(text, 90).replace("|", "\\|")


def render_markdown(payload: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append(f"# Editor review packet: {payload['run_id']}")
    lines.append("")
    lines.append("## Executive summary")
    lines.append("")
    lines.append(f"- Run ID: `{payload['run_id']}`")
    lines.append(f"- Input reports used: `{payload['input_reports']}`")
    lines.append(f"- Source cards available: {payload['source_cards_available']}")
    lines.append(f"- Semantic objects available: {payload['semantic_objects_available']}")
    lines.append(f"- Quality reviews available: {payload['quality_reviews_available']}")
    lines.append(f"- Complete chains: {payload['complete_chains_total']}")
    lines.append(f"- Packet pass/warn/fail: {payload['packet_items_pass']} / {payload['packet_items_warn']} / {payload['packet_items_fail']}")
    lines.append(f"- Downstream eligible count: {payload['downstream_eligible_count']}")
    lines.append("- Safety status: advisory editor review only; not author-approved, not publication-approved, no DB/status/chapter changes.")
    lines.append("")
    lines.append("## Editor review packet table")
    lines.append("")
    lines.append("| source id | source title | source type | semantic object type | chapter target | quality decision | downstream eligible | risk flags | required fixes |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for item in payload["packet_items"]:
        lines.append("| " + " | ".join([
            md_cell(item["source_id"]), md_cell(item["source_title"]), md_cell(item["source_type"]), md_cell(item["semantic_object_type"]), md_cell(", ".join(item["candidate_chapter_targets"])), md_cell(item["quality_decision"]), md_cell(str(item["downstream_eligible"])), md_cell("; ".join(item["risk_flags"])), md_cell("; ".join(item["required_fixes"])),
        ]) + " |")
    lines.append("")
    lines.append("## Per-item review sections")
    for item in payload["packet_items"]:
        lines.append("")
        lines.append(f"### {item['packet_item_id']}")
        lines.append("")
        lines.append(f"- Source: `{item['source_id']}` — {item['source_title']}")
        lines.append(f"- Source metadata: type `{item['source_type']}`, publisher `{item['publisher']}`, canonical URL available `{item['canonical_url_available']}`, quality `{item['quality_score']}`, privacy `{item['privacy_publication_status']}`")
        lines.append(f"- Source-card: `{item['source_card_id']}` — {item['source_card_summary']}")
        lines.append(f"- Semantic object: `{item['semantic_object_id']}` (`{item['semantic_object_type']}`) — {item['semantic_object_text']}")
        lines.append(f"- Quality-gate decision: `{item['quality_decision']}`; downstream eligible `{item['downstream_eligible']}`; next stage `{item['recommended_next_stage']}`")
        lines.append(f"- Strengths: {', '.join(item['strengths']) or 'none recorded'}")
        lines.append(f"- Caveats: {', '.join(item['caveats']) or 'none recorded'}")
        lines.append(f"- Required fixes: {', '.join(item['required_fixes']) or 'none'}")
        lines.append("- Provenance/hashes:")
        lines.append(f"  - source_text_hash: `{item['source_text_hash']}`")
        lines.append(f"  - source_card_hash: `{item['source_card_hash']}`")
        lines.append(f"  - semantic_object_hash: `{item['semantic_object_hash']}`")
        lines.append(f"  - quality_review_hash: `{item['quality_review_hash']}`")
        lines.append("- Explicit safety: not author-approved, not publication-approved, advisory-only.")
    lines.append("")
    lines.append("## Cross-packet synthesis")
    lines.append("")
    es = payload["editor_summary"]
    lines.append(f"- Strongest candidate themes: {', '.join(es['strongest_candidate_themes']) or 'none'}")
    lines.append(f"- Weakest areas: {', '.join(es['weakest_areas']) or 'none'}")
    lines.append(f"- Recurring caveats: {', '.join(es['recurring_caveats']) or 'none'}")
    lines.append(f"- Missing corroboration: {es['missing_corroboration']}")
    lines.append("- Suggested next editorial decisions:")
    for decision in es["suggested_next_editorial_decisions"]:
        lines.append(f"  - {decision}")
    lines.append("")
    lines.append("## Safety assessment")
    lines.append("")
    for key in ["db_modified", "db_write_scope", "chapters_modified", "statuses_modified", "schema_modified", "daily_worker_modified", "commit_allowlist_modified", "raw_private_material_written", "long_source_excerpt_written", "claims_inserted", "narrative_packets_created", "chapter_prose_generated", "author_allowed", "publication_approved", "advisory_only"]:
        lines.append(f"- {key}: `{payload[key]}`")
    lines.append("")
    lines.append("## Recommendation for Run 9")
    lines.append("")
    lines.append(f"- Recommendation: `{payload['next_run_recommendation']['recommendation']}`")
    for cond in payload["next_run_recommendation"]["conditions"]:
        lines.append(f"- Condition: {cond}")
    lines.append("")
    return "\n".join(lines)


def write_reports(payload: dict[str, Any], output_dir: Path, json_only: bool, markdown_only: bool, report_suffix: str) -> dict[str, str]:
    output_dir = output_dir if output_dir.is_absolute() else REPO_ROOT / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    suffix = f"editor-review-packet-{report_suffix}" if report_suffix else "editor-review-packet"
    json_path = output_dir / f"{payload['run_id']}-{suffix}.json"
    md_path = output_dir / f"{payload['run_id']}-{suffix}.md"
    outputs = {"json": repo_relative(json_path), "markdown": repo_relative(md_path)}
    payload["output_paths"] = outputs
    if not markdown_only:
        write_json(json_path, payload)
    if not json_only:
        md_path.write_text(render_markdown(payload), encoding="utf-8")
    return outputs


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build a report-only human/editor review packet for high-reasoning chains.")
    p.add_argument("--run-id", required=True)
    p.add_argument("--output-dir", default="reports/editorial")
    p.add_argument("--candidate-selection-report", required=True)
    p.add_argument("--source-card-report", required=True)
    p.add_argument("--semantic-object-report", required=True)
    p.add_argument("--quality-gate-report", required=True)
    p.add_argument("--report-suffix", default="run8")
    p.add_argument("--json-only", action="store_true")
    p.add_argument("--markdown-only", action="store_true")
    args = p.parse_args(argv)
    if args.json_only and args.markdown_only:
        raise EditorPacketError("--json-only and --markdown-only are mutually exclusive")
    return args


def resolve(path: str) -> Path:
    p = Path(path)
    return p if p.is_absolute() else REPO_ROOT / p


def main(argv: list[str] | None = None) -> int:
    try:
        args = parse_args(argv or sys.argv[1:])
        reports = {
            "candidate": load_json(resolve(args.candidate_selection_report)),
            "source": load_json(resolve(args.source_card_report)),
            "semantic": load_json(resolve(args.semantic_object_report)),
            "quality": load_json(resolve(args.quality_gate_report)),
        }
        payload = build_packet(args, reports)
        outputs = write_reports(payload, Path(args.output_dir), args.json_only, args.markdown_only, args.report_suffix)
        print(json.dumps({
            "status": "ok",
            "run_id": payload["run_id"],
            "outputs": outputs,
            "packet_items_total": payload["packet_items_total"],
            "packet_items_pass": payload["packet_items_pass"],
            "packet_items_warn": payload["packet_items_warn"],
            "packet_items_fail": payload["packet_items_fail"],
            "complete_chains_total": payload["complete_chains_total"],
            "downstream_eligible_count": payload["downstream_eligible_count"],
            "db_modified": False,
            "author_allowed": False,
            "publication_approved": False,
        }, indent=2, sort_keys=True))
        return 0
    except EditorPacketError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
