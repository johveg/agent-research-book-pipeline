#!/usr/bin/env python3
"""Run 44 publication orchestrator.

Consumes Run 43 report-only packets, broadens existing local evidence, forces the
GPT-5.5 closed-loop editorial profile for publication packet generation, then
applies either one guarded docs/book canary or a truthful rolling daily status
fallback. No external collection and no weak fallback are allowed.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from closed_loop_author_editor import normalize_packets  # noqa: E402
from closed_loop_book_publisher import apply_daily_status, publish_packets, select_publishable_packets, write_json, write_markdown  # noqa: E402
from closed_loop_publish_packet_validator import validate_publish_packet  # noqa: E402
from hermes_high_reasoning_json import HighReasoningError, call_high_reasoning_json  # noqa: E402

ALLOWED_DISPOSITIONS = {
    "publish_packet_machine_approved",
    "caveat_only_publish_packet",
    "publish_daily_no_safe_promotions",
    "publish_packet_blocked",
    "needs_more_sources",
    "contradiction_review_required",
    "quarantine",
    "safe_reports_only",
}
FORBIDDEN_DEPENDENCY_TERMS = [
    "human_" + "review_required",
    "requires_" + "human_review",
    "manual_" + "approval_required",
    "editor_" + "must_review",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def resolve(path: str | Path) -> Path:
    p = Path(path)
    return p if p.is_absolute() else ROOT / p


def rel(path: str | Path) -> str:
    p = Path(path)
    try:
        return str(p.resolve().relative_to(ROOT))
    except Exception:
        return str(p)


def load_json(path: str | Path) -> Any:
    return json.loads(resolve(path).read_text(encoding="utf-8"))


def extract_packets(doc: Any) -> list[dict[str, Any]]:
    if isinstance(doc, list):
        return [x for x in doc if isinstance(x, dict)]
    if isinstance(doc, dict):
        return [x for x in (doc.get("publish_packets") or doc.get("packets") or []) if isinstance(x, dict)]
    return []


def load_run43_packets(path: str | Path) -> list[dict[str, Any]]:
    return extract_packets(load_json(path))


def model_profile_errors(profile: str, provider: str, model: str, strict_json: bool, no_weak_local_fallback: bool) -> list[str]:
    errors = []
    if profile != "closed_loop_editorial":
        errors.append("model_profile must be closed_loop_editorial")
    if provider != "copilot":
        errors.append("provider must be copilot")
    if model != "gpt-5.5":
        errors.append("model must be gpt-5.5")
    if strict_json is not True:
        errors.append("strict_json must be true")
    if no_weak_local_fallback is not True:
        errors.append("weak/local fallback refused: --no-weak-local-fallback required")
    return errors


def ready_packets(packets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return select_publishable_packets(packets, max_packets=1)["selected"]


def db_counts() -> dict[str, int]:
    path = ROOT / ".var" / "book.sqlite"
    con = sqlite3.connect(path)
    try:
        return {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ["source_notes", "claims", "editorial_reviews"]}
    finally:
        con.close()


def db_candidates(limit: int) -> list[dict[str, Any]]:
    path = ROOT / ".var" / "book.sqlite"
    if not path.exists():
        return []
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    candidates: list[dict[str, Any]] = []
    try:
        rows = con.execute(
            """
            SELECT c.id claim_id, c.claim_text, c.confidence, c.status, c.evidence_strength,
                   c.source_count, c.source_quality, c.contradiction_status, c.publication_decision,
                   group_concat(cs.source_id) source_ids,
                   group_concat(s.title) source_titles,
                   group_concat(coalesce(s.reliability_tier,'')) reliability_tiers,
                   group_concat(coalesce(s.privacy_publication_status,'')) privacy_statuses
            FROM claims c
            LEFT JOIN claim_sources cs ON cs.claim_id = c.id
            LEFT JOIN sources s ON s.id = cs.source_id
            GROUP BY c.id
            ORDER BY c.source_count DESC, c.evidence_strength DESC, c.id
            LIMIT ?
            """,
            (max(limit * 3, 10),),
        ).fetchall()
        for row in rows:
            source_ids = [x for x in str(row["source_ids"] or "").split(",") if x]
            privacy = str(row["privacy_statuses"] or "").lower()
            quality = str(row["source_quality"] or row["reliability_tiers"] or "unknown").lower()
            claim = str(row["claim_text"] or "").strip()
            if not claim or len(claim) > 400:
                continue
            if "private" in privacy or "cookie" in claim.lower() or "token" in claim.lower():
                continue
            score = len(set(source_ids)) * 3
            if "strong" in str(row["evidence_strength"] or "").lower():
                score += 3
            if "public" in privacy:
                score += 1
            if "social" not in quality:
                score += 1
            candidates.append({
                "candidate_id": "claim:" + str(row["claim_id"]),
                "claim_text": claim,
                "source_ids": sorted(set(source_ids))[:5],
                "source_titles": [x for x in str(row["source_titles"] or "").split(",") if x][:5],
                "source_count": int(row["source_count"] or len(set(source_ids))),
                "source_quality": str(row["source_quality"] or "unknown"),
                "evidence_strength": str(row["evidence_strength"] or "unknown"),
                "contradiction_status": str(row["contradiction_status"] or "unknown"),
                "publication_decision": str(row["publication_decision"] or "unknown"),
                "privacy_publication_status": str(row["privacy_statuses"] or "unknown")[:200],
                "selection_score": score,
                "evidence_refs": ["claim:" + str(row["claim_id"])] + ["source:" + s for s in sorted(set(source_ids))[:3]],
            })
    finally:
        con.close()
    return sorted(candidates, key=lambda x: (-int(x.get("selection_score", 0)), x["candidate_id"]))[:limit]


def context_candidates(path: str | Path, limit: int) -> list[dict[str, Any]]:
    data = load_json(path)
    raw = data.get("constrained_authoring_context_candidates") or data.get("selected_contexts") or data.get("contexts") or [] if isinstance(data, dict) else []
    out = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        cid = str(item.get("context_id") or item.get("metadata_id") or "context")
        atoms = item.get("evidence_bound_atoms") or item.get("context_summary") or []
        out.append({
            "candidate_id": cid,
            "claim_text": "; ".join(str(x) for x in atoms[:2]) if isinstance(atoms, list) else str(atoms)[:400],
            "source_ids": [],
            "source_titles": [],
            "source_count": len(item.get("provenance_paths") or []),
            "source_quality": "internal_report_context",
            "evidence_strength": "caveat_only",
            "contradiction_status": "unknown",
            "publication_decision": "candidate_context_only",
            "required_caveats": item.get("required_caveats") or [],
            "provenance_paths": item.get("provenance_paths") or [],
            "selection_score": 1,
            "evidence_refs": [cid],
        })
    return out[:limit]


def expand_evidence(run42_context: str | Path, limit: int = 10) -> dict[str, Any]:
    candidates = db_candidates(limit)
    if len(candidates) < limit:
        seen = {c["candidate_id"] for c in candidates}
        for c in context_candidates(run42_context, limit - len(candidates)):
            if c["candidate_id"] not in seen:
                candidates.append(c)
    return {
        "mode": "closed_loop_evidence_expansion_run44",
        "generated_at": utc_now(),
        "evidence_expansion_status": "expanded_existing_evidence" if candidates else "no_existing_evidence_candidates",
        "no_external_collection": True,
        "candidates_considered": len(candidates),
        "selection_policy": "existing DB claims/source mappings plus Run42 constrained context; prefer multiple sources, public metadata, low contradiction risk; avoid social-only/private/raw leakage.",
        "candidates": candidates[:limit],
        "db_counts": db_counts(),
    }


def validate_llm_payload(obj: dict[str, Any]) -> None:
    if not isinstance(obj.get("publish_packets"), list):
        raise ValueError("publish_packets must be list")
    for pkt in obj["publish_packets"]:
        if not isinstance(pkt, dict):
            raise ValueError("publish_packets entries must be objects")
        disp = pkt.get("disposition")
        if disp not in ALLOWED_DISPOSITIONS:
            raise ValueError(f"unsupported disposition {disp}")
        blob = json.dumps(pkt, sort_keys=True, default=str).lower()
        if any(term in blob for term in FORBIDDEN_DEPENDENCY_TERMS):
            raise ValueError("human-review dependency term refused")


def build_prompt(run_id: str, evidence: dict[str, Any], prior_packets: list[dict[str, Any]]) -> str:
    payload = {
        "run_id": run_id,
        "task": "Run 44 guarded book publication canary packet generation",
        "model_rule": {"provider": "copilot", "model": "gpt-5.5", "strict_json": True, "weak_local_fallback": False},
        "constraints": [
            "Use only supplied existing evidence candidates; do not invent or use web collection.",
            "Return strict JSON only with key publish_packets.",
            "Every proposed claim must map to evidence_refs and citation_map.",
            "No raw text copying; no unsupported broad claims; no human-review dependency fields or terms.",
            "Choose at most one substantive candidate if safe; otherwise produce publish_daily_no_safe_promotions or safe_reports_only.",
            "Allowed dispositions: publish_packet_machine_approved, caveat_only_publish_packet, publish_daily_no_safe_promotions, publish_packet_blocked, needs_more_sources, contradiction_review_required, quarantine, safe_reports_only.",
            "Target file for substantive canary should normally be docs/book/03-openclaw.md or docs/book/06-operating-loops.md. Daily fallback target is docs/book/daily-pipeline-status.md.",
        ],
        "required_packet_fields": [
            "publish_packet_id", "source_packet_ids", "input_context_ids", "target_book_area", "target_file_suggestion", "update_type", "title", "summary", "proposed_markdown_delta", "claim_map", "citation_map", "evidence_refs", "source_quality_summary", "required_caveats", "forbidden_claims_checked", "redteam_findings", "machine_editor_findings", "disposition", "publication_readiness", "idempotency_key", "human_in_loop_dependency_added", "raw_text_publication_allowed", "docs_book_update_applied", "publication_deployed"
        ],
        "prior_run43_packets": prior_packets[:2],
        "evidence_expansion": evidence,
    }
    return "Return JSON only, no markdown.\n" + json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False)


def markdown_summary(title: str, obj: dict[str, Any]) -> str:
    lines = [f"# {title}", "", f"Generated: {obj.get('generated_at')}", ""]
    for key in ["mode", "publication_status", "evidence_expansion_status", "candidates_considered", "publish_packet_count", "publication_decision", "target_file", "docs_book_applied", "daily_status_fallback_applied"]:
        if key in obj:
            lines.append(f"- {key}: `{obj.get(key)}`")
    if obj.get("disposition_counts"):
        lines.append("- disposition_counts:")
        for k, v in sorted(obj["disposition_counts"].items()):
            lines.append(f"  - {k}: {v}")
    if obj.get("reports"):
        lines.append("- reports:")
        for k, v in obj["reports"].items():
            lines.append(f"  - {k}: `{v}`")
    return "\n".join(lines) + "\n"


def write_md(path: str | Path, title: str, obj: dict[str, Any]) -> None:
    out = resolve(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(markdown_summary(title, obj), encoding="utf-8")


def run(args: argparse.Namespace) -> int:
    errors = model_profile_errors(args.model_profile, args.provider, args.model, args.strict_json, args.no_weak_local_fallback)
    before_counts = db_counts()
    run43_doc = load_json(args.run43_publish_packets)
    run43_packets = extract_packets(run43_doc)
    initial_ready = ready_packets(run43_packets)
    evidence = expand_evidence(args.run42_context, args.limit)
    write_json(args.evidence_expansion_json, evidence)
    write_md(args.evidence_expansion_md, "Run 44 evidence expansion", evidence)

    packets: list[dict[str, Any]] = []
    llm_result: dict[str, Any] = {"llm_used": False, "error": "", "reasoning_status": "not_started"}
    publication_status = ""
    validation_errors: list[str] = []

    if errors:
        publication_status = "failed_closed_model_unavailable"
        llm_result = {"llm_used": False, "error": "; ".join(errors), "reasoning_status": publication_status, "weak_local_fallback_refused": True}
    else:
        try:
            prompt = build_prompt(args.run_id, evidence, run43_packets)
            llm_result = call_high_reasoning_json(prompt, "run44_publication_packets", validator=validate_llm_payload, provider=args.provider, model=args.model, timeout_seconds=args.timeout_seconds, reasoning_profile=args.model_profile)
            packets = normalize_packets((llm_result.get("parsed_json") or {}).get("publish_packets") or [])
            for packet in packets:
                update_type = str(packet.get("update_type") or "")
                if update_type.startswith("substantive_canary"):
                    packet["update_type"] = "guarded_substantive_canary"
            publication_status = "live_gpt55_completed"
        except HighReasoningError as exc:
            llm_result = exc.result
            publication_status = "failed_closed_model_unavailable" if llm_result.get("error") in {"command_missing", "timeout"} or str(llm_result.get("error", "")).startswith("nonzero_exit") else "failed_closed_invalid_gpt55_json"
        except Exception as exc:
            llm_result = {"llm_used": False, "error": str(exc), "reasoning_status": "failed_closed_exception", "weak_local_fallback_refused": True}
            publication_status = "failed_closed_invalid_gpt55_json"

    for idx, packet in enumerate(packets):
        for err in validate_publish_packet(packet):
            validation_errors.append(f"publish_packets[{idx}]: {err}")
    if validation_errors:
        publication_status = "failed_closed_invalid_gpt55_json"

    counts = Counter(str(p.get("disposition") or "") for p in packets)
    selection = select_publishable_packets(packets, args.max_packets, docs_root=args.docs_root)
    substantive_selected = selection["selected"][: args.max_packets]
    patch_preview = {
        "mode": "run44_book_patch_preview",
        "run_id": args.run_id,
        "generated_at": utc_now(),
        "patch_preview_generated": bool(substantive_selected),
        "preview_count": len(substantive_selected),
        "patch_previews": [
            {"publish_packet_id": p.get("publish_packet_id"), "target_file_suggestion": p.get("target_file_suggestion"), "proposed_markdown_delta": p.get("proposed_markdown_delta"), "citation_map": p.get("citation_map")}
            for p in substantive_selected
        ],
        "validation_result": "ready_for_guarded_publication" if substantive_selected else "publish_daily_no_safe_promotions",
    }
    write_json(args.publish_packets_json, {"mode": "run44_publish_packets", "run_id": args.run_id, "generated_at": utc_now(), "publish_packets": packets, "publish_packet_count": len(packets), "disposition_counts": dict(counts)})
    write_md(args.publish_packets_md, "Run 44 publish packets", {"generated_at": utc_now(), "mode": "run44_publish_packets", "publish_packet_count": len(packets), "disposition_counts": dict(counts)})
    write_json(args.patch_preview_json, patch_preview)
    write_md(args.patch_preview_md, "Run 44 book patch preview", patch_preview)

    publication_report: dict[str, Any]
    docs_applied = False
    if publication_status.startswith("failed_closed"):
        publication_report = publish_packets([], args.docs_root, apply=False, max_packets=args.max_packets, run_id=args.run_id)
    elif substantive_selected and args.apply_if_machine_approved:
        publication_report = publish_packets(substantive_selected, args.docs_root, apply=True, max_packets=args.max_packets, run_id=args.run_id)
    elif not substantive_selected and args.allow_daily_status_fallback:
        reason = "No substantive publish packet passed machine gates after Run 44 evidence expansion."
        publication_report = apply_daily_status(args.docs_root, args.run_id, len(packets), reason, apply=True)
    else:
        publication_report = publish_packets(substantive_selected, args.docs_root, apply=False, max_packets=args.max_packets, run_id=args.run_id)
    docs_applied = bool(publication_report.get("docs_book_update_applied"))
    write_json(args.publication_report_json, publication_report)
    write_markdown(args.publication_report_md, "Run 44 guarded book publication", publication_report)

    after_counts = db_counts()
    report = {
        "mode": "closed_loop_publication_orchestrator_run44",
        "run_id": args.run_id,
        "generated_at": utc_now(),
        "publication_status": publication_status,
        "provider": args.provider,
        "model": args.model,
        "model_profile": args.model_profile,
        "reasoning_profile": args.model_profile,
        "bridge": llm_result.get("bridge", "hermes_cli"),
        "strict_json_required": True,
        "weak_local_fallback_refused": True,
        "llm_used": bool(llm_result.get("llm_used")),
        "llm_error": llm_result.get("error", ""),
        "run43_packets_consumed": len(run43_packets),
        "run43_ready_packets": len(initial_ready),
        "evidence_expansion_status": evidence["evidence_expansion_status"],
        "candidates_considered": evidence["candidates_considered"],
        "publish_packet_count": len(packets),
        "disposition_counts": dict(counts),
        "substantive_packet_approved_count": len(substantive_selected),
        "machine_approved_count": counts.get("publish_packet_machine_approved", 0),
        "caveat_only_packet_count": counts.get("caveat_only_publish_packet", 0),
        "no_safe_promotion_count": counts.get("publish_daily_no_safe_promotions", 0) + counts.get("safe_reports_only", 0),
        "publication_decision": publication_report.get("publication_decision"),
        "target_file": publication_report.get("target_file", ""),
        "docs_book_applied": docs_applied,
        "daily_status_fallback_applied": bool(publication_report.get("daily_status_fallback_applied")),
        "validation_errors": validation_errors,
        "db_counts_before": before_counts,
        "db_counts_after": after_counts,
        "db_counts_delta": {k: after_counts.get(k, 0) - before_counts.get(k, 0) for k in sorted(set(before_counts) | set(after_counts))},
        "reports": {
            "orchestrator_json": rel(args.output_json),
            "orchestrator_md": rel(args.output_md),
            "evidence_expansion_json": rel(args.evidence_expansion_json),
            "evidence_expansion_md": rel(args.evidence_expansion_md),
            "publish_packets_json": rel(args.publish_packets_json),
            "publish_packets_md": rel(args.publish_packets_md),
            "patch_preview_json": rel(args.patch_preview_json),
            "patch_preview_md": rel(args.patch_preview_md),
            "publication_report_json": rel(args.publication_report_json),
            "publication_report_md": rel(args.publication_report_md),
        },
    }
    write_json(args.output_json, report)
    write_md(args.output_md, "Run 44 publication orchestrator", report)
    if publication_status.startswith("failed_closed"):
        print("failed_closed: " + str(llm_result.get("error", publication_status)), file=sys.stderr)
        return 2
    print(json.dumps({"ok": True, "publication_decision": report["publication_decision"], "docs_book_applied": docs_applied, "publish_packet_count": len(packets)}, sort_keys=True))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Run 44 publication orchestrator")
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--run43-publish-packets", required=True)
    ap.add_argument("--run42-context", required=True)
    ap.add_argument("--author-editor-script", required=True)
    ap.add_argument("--publisher-script", required=True)
    ap.add_argument("--model-profile", required=True)
    ap.add_argument("--provider", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--strict-json", action="store_true")
    ap.add_argument("--no-weak-local-fallback", action="store_true")
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--max-packets", type=int, default=1)
    ap.add_argument("--allow-daily-status-fallback", action="store_true")
    ap.add_argument("--apply-if-machine-approved", action="store_true")
    ap.add_argument("--docs-root", default=str(ROOT / "docs" / "book"))
    ap.add_argument("--output-json", required=True)
    ap.add_argument("--output-md", required=True)
    ap.add_argument("--evidence-expansion-json", required=True)
    ap.add_argument("--evidence-expansion-md", required=True)
    ap.add_argument("--publish-packets-json", required=True)
    ap.add_argument("--publish-packets-md", required=True)
    ap.add_argument("--patch-preview-json", required=True)
    ap.add_argument("--patch-preview-md", required=True)
    ap.add_argument("--publication-report-json", required=True)
    ap.add_argument("--publication-report-md", required=True)
    ap.add_argument("--timeout-seconds", type=int, default=240)
    try:
        return run(ap.parse_args(argv))
    except Exception as exc:
        print(f"failed_closed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
