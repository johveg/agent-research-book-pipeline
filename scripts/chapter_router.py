#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return slug or "untitled_chapter"


def path_slug(text: str) -> str:
    return slugify(text).replace("_", "-")


def event_id_for(event_type: str, packet_id: str, chapter_id: str = "") -> str:
    digest = hashlib.sha256(f"{event_type}:{packet_id}:{chapter_id}".encode()).hexdigest()[:16]
    return f"bookevt-{digest}"


def load_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_chapters(contract_path: str | Path) -> dict[str, dict[str, Any]]:
    doc = load_json(contract_path)
    chapters = doc.get("chapters", {}) if isinstance(doc, dict) else {}
    out: dict[str, dict[str, Any]] = {}
    for cid, spec in chapters.items():
        if isinstance(spec, dict):
            topics = set(str(x).lower() for x in spec.get("topics", []))
            topics.add(str(spec.get("title", cid)).lower())
            topics.add(str(cid).replace("_", " ").lower())
            out[cid] = {**spec, "chapter_id": cid, "topics": sorted(topics)}
    return out


def packet_text(packet: dict[str, Any]) -> str:
    parts = [packet.get("title", ""), packet.get("summary", ""), packet.get("safe_summary", "")]
    parts += packet.get("topics", []) if isinstance(packet.get("topics"), list) else []
    return " ".join(str(x).lower() for x in parts if x)


def fit_score(packet: dict[str, Any], chapter: dict[str, Any]) -> float:
    text = packet_text(packet)
    topics = [str(x).lower() for x in chapter.get("topics", []) if str(x).strip()]
    if not topics:
        return 0.0
    hits = 0
    for topic in topics:
        topic_norm = topic.replace("_", " ").replace("-", " ").strip()
        if topic_norm and topic_norm in text:
            hits += 1
    return min(1.0, hits / max(1, min(3, len(topics))))


def is_weak(packet: dict[str, Any]) -> bool:
    strength = str(packet.get("evidence_strength", "")).lower()
    sources = [str(x).lower() for x in packet.get("source_ids", [])]
    return strength in {"weak", "social_only", "caveat_only"} or (sources and all("linkedin" in s or "social" in s for s in sources))


def make_event(event_type: str, packet: dict[str, Any], **fields: Any) -> dict[str, Any]:
    packet_id = str(packet.get("packet_id") or packet.get("id") or uuid.uuid4())
    chapter_id = str(fields.get("chapter_id") or "")
    payload = fields.pop("payload", {})
    payload.setdefault("packet_id", packet_id)
    payload.setdefault("packet", packet)
    return {
        "event_id": event_id_for(event_type, packet_id, chapter_id),
        "event_type": event_type,
        "created_at_utc": utc_now(),
        "packet_id": packet_id,
        "human_in_loop_dependency_added": False,
        "idempotency_key": event_id_for(event_type, packet_id, chapter_id),
        "payload": payload,
        **fields,
    }


def chapter_id_from_target_path(target_path: str) -> str:
    stem = Path(target_path).stem
    stem = re.sub(r"^\d+-", "", stem)
    return stem.replace("-", "_") or "untitled_chapter"


def route_packet(
    packet: dict[str, Any],
    chapters: dict[str, dict[str, Any]],
    threshold: float = 0.34,
    existing_targets: set[str] | None = None,
) -> dict[str, Any]:
    existing_targets = existing_targets or set()
    source_ids = packet.get("source_ids", []) if isinstance(packet.get("source_ids"), list) else []
    source_count = len(source_ids)

    if is_weak(packet):
        trace = {
            "reason_code": "weak_or_social_only_evidence",
            "fit_threshold": float(threshold),
            "source_count": source_count,
            "required_source_count": 3,
            "evidence_strength": str(packet.get("evidence_strength", "")),
        }
        return {
            "ok": True,
            "packet_id": packet.get("packet_id"),
            "events": [
                make_event("evidence.packet.deferred", packet, payload={"packet": packet, "reason": "weak_or_social_only_evidence", "no_book_mutation": True, "trace": trace}),
                make_event("research_gap.detected", packet, payload={"packet": packet, "reason": "need_stronger_public_corroboration", "suggested_queries": packet.get("topics", []), "trace": trace}),
            ],
        }

    scored = sorted(((fit_score(packet, spec), cid, spec) for cid, spec in chapters.items()), reverse=True)
    top_match_scores = [{"chapter_id": cid, "score": round(score, 3)} for score, cid, _ in scored[:3]]
    events: list[dict[str, Any]] = []
    for score, cid, spec in scored[:3]:
        if score >= threshold:
            events.append(make_event(
                "chapter.update.requested",
                packet,
                chapter_id=cid,
                target_path=spec.get("target_path"),
                confidence=round(score, 3),
                update_type="integrate_evidence_packet",
                payload={"packet": packet, "reason": "evidence_packet_matches_existing_chapter", "packet_id": packet.get("packet_id")},
            ))
    if not events:
        title = str(packet.get("title") or (packet.get("topics") or ["New Chapter"])[0])
        hinted_target = str(packet.get("target_path_hint") or "")
        proposed_target = hinted_target if hinted_target.startswith("docs/book/") else f"docs/book/{path_slug(title)}.md"
        if proposed_target in existing_targets:
            cid = chapter_id_from_target_path(proposed_target)
            events.append(make_event(
                "chapter.update.requested",
                packet,
                chapter_id=cid,
                target_path=proposed_target,
                confidence=0.0,
                update_type="integrate_evidence_packet",
                payload={"packet": packet, "reason": "target_path_already_exists", "packet_id": packet.get("packet_id")},
            ))
        else:
            cid = slugify(title)
            events.append(make_event(
                "chapter.creation.requested",
                packet,
                chapter_id=cid,
                target_path=proposed_target,
                confidence=0.0,
                payload={"packet": packet, "title": title, "reason_new_chapter_needed": "no_existing_chapter_fit_above_threshold"},
            ))
    if source_count < 3:
        events.append(make_event(
            "research_gap.detected",
            packet,
            payload={
                "packet": packet,
                "reason": "additional_independent_sources_would_strengthen_publication",
                "suggested_queries": packet.get("topics", []),
                "trace": {
                    "reason_code": "source_count_below_minimum",
                    "fit_threshold": float(threshold),
                    "source_count": source_count,
                    "required_source_count": 3,
                    "top_match_scores": top_match_scores,
                },
            },
        ))
    return {"ok": True, "packet_id": packet.get("packet_id"), "events": events}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--packet-json", required=True)
    ap.add_argument("--contract-json", default="config/book_manuscript_production_contract.json")
    ap.add_argument("--output-json", required=True)
    args = ap.parse_args()
    packet = load_json(args.packet_json)
    result = route_packet(packet, load_chapters(args.contract_json))
    out = Path(args.output_json)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"ok": result["ok"], "event_count": len(result["events"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
