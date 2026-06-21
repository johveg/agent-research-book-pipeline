#!/usr/bin/env python3
"""Run 43 autonomous author/editor/red-team publish-packet lane.

Consumes constrained authoring context and asks the configured GPT-5.5 closed-loop
editorial profile to produce machine dispositions and publish-packet candidates.
Run 43 is dry-run/report-only: it does not write docs/book, docs/entities, raw,
source registry, schema, or the SQLite DB.
"""
from __future__ import annotations

import argparse
import hashlib
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

from closed_loop_publish_packet_validator import validate_publish_packet  # noqa: E402
from hermes_high_reasoning_json import HighReasoningError, call_high_reasoning_json  # noqa: E402
from model_profiles import load_model_profile  # noqa: E402
from research_common import DB_PATH as DEFAULT_DB_PATH, sha256_text  # noqa: E402

MODE = "closed_loop_author_editor"
ALLOWED_DISPOSITIONS = {
    "publish_packet_candidate",
    "publish_packet_machine_approved",
    "caveat_only_publish_packet",
    "publish_packet_blocked",
    "needs_more_sources",
    "contradiction_review_required",
    "quarantine",
    "safe_reports_only",
    "publish_daily_no_safe_promotions",
}
FALSE_FLAGS = {
    "docs_book_update_allowed": False,
    "production_publish_enabled": False,
    "docs_book_update_applied": False,
    "publication_deployed": False,
}


class AuthorEditorError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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
        raise AuthorEditorError(f"missing {label}: {path}")
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AuthorEditorError(f"invalid JSON in {label}: {exc}") from exc
    if not isinstance(obj, dict):
        raise AuthorEditorError(f"{label} must be object")
    return obj


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def db_path() -> Path:
    override = os.environ.get("TEREFO_BOOK_DB_PATH", "").strip()
    return Path(override) if override else DEFAULT_DB_PATH


def db_counts(path: Path) -> dict[str, int]:
    if not path.exists():
        return {}
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        con.execute("PRAGMA query_only = ON")
        return {t: int(con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]) for t in ["source_notes", "claims", "editorial_reviews"]}
    finally:
        con.close()


def db_status_hash(path: Path) -> str:
    if not path.exists():
        return ""
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA query_only = ON")
        payload = {
            "source_notes": [tuple(r) for r in con.execute("SELECT id, source_id, note_type, created_at FROM source_notes ORDER BY id")],
            "claims": [tuple(r) for r in con.execute("SELECT id, status, publication_decision, contradiction_status FROM claims ORDER BY id")],
            "editorial_reviews": [tuple(r) for r in con.execute("SELECT id, run_id, review_type, status, summary, report_path, created_at FROM editorial_reviews ORDER BY id")],
        }
        return sha256_text(json.dumps(payload, sort_keys=True, default=str))
    finally:
        con.close()


def model_profile_valid(profile_name: str, provider: str, model: str, strict_json: bool, no_weak_local_fallback: bool) -> list[str]:
    errors: list[str] = []
    if profile_name != "closed_loop_editorial":
        errors.append("model_profile must be closed_loop_editorial")
    if provider != "copilot":
        errors.append("provider must be copilot")
    if model != "gpt-5.5":
        errors.append("model must be gpt-5.5")
    if strict_json is not True:
        errors.append("strict JSON is required")
    if no_weak_local_fallback is not True:
        errors.append("weak/local fallback refused; pass --no-weak-local-fallback")
    try:
        profile = load_model_profile(profile_name)
        if profile.get("provider") != provider or profile.get("model") != model or profile.get("bridge") != "hermes_cli":
            errors.append("configured profile does not resolve to copilot/gpt-5.5/hermes_cli")
        if profile.get("allow_weak_fallback") is not False or profile.get("allow_local_fallback") is not False:
            errors.append("configured profile must disable weak/local fallback")
        if profile.get("strict_json_required") is not True:
            errors.append("configured profile must require strict JSON")
    except Exception as exc:
        errors.append(f"model profile unavailable: {exc}")
    return errors


def extract_contexts(context_report: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    contexts = context_report.get("constrained_authoring_context_candidates")
    if not isinstance(contexts, list) or not contexts:
        raise AuthorEditorError("input context report has no constrained_authoring_context_candidates")
    out = []
    for item in contexts[:limit]:
        if not isinstance(item, dict):
            continue
        out.append(item)
    if not out:
        raise AuthorEditorError("no valid context candidates")
    return out


def evidence_ref_for(context: dict[str, Any], idx: int) -> str:
    basis = context.get("context_id") or context.get("metadata_id") or f"context_{idx}"
    return "evidence_" + hashlib.sha256(str(basis).encode()).hexdigest()[:12]


def fixture_packets(contexts: list[dict[str, Any]], input_context_path: str) -> list[dict[str, Any]]:
    packets: list[dict[str, Any]] = []
    for idx, context in enumerate(contexts, 1):
        ref = evidence_ref_for(context, idx)
        caveats = context.get("required_caveats") if isinstance(context.get("required_caveats"), list) else []
        do_not = context.get("do_not_say") if isinstance(context.get("do_not_say"), list) else []
        packets.append({
            "publish_packet_id": f"publish_packet_run43_{idx}_{hashlib.sha256(json.dumps(context, sort_keys=True, default=str).encode()).hexdigest()[:12]}",
            "source_packet_ids": [str(context.get("metadata_id") or context.get("contract_candidate_id") or context.get("context_id"))],
            "input_context_ids": [str(context.get("context_id") or f"context_{idx}")],
            "target_book_area": "OpenClaw/Hermes tooling caveat note",
            "target_file_suggestion": "docs/book/03-openclaw.md",
            "update_type": "caveated_note",
            "title": "OpenClaw Hermes tooling caveat",
            "summary": "Caveat-only dry-run packet based on narrow OpenClaw documentation references to Hermes tooling contexts.",
            "proposed_markdown_delta": "OpenClaw documentation references Hermes in migration/setup tooling contexts; this does not establish Hermes as a runtime dependency or general operating environment.",
            "claim_map": [{"claim": "OpenClaw documentation references Hermes in migration/setup tooling contexts.", "evidence_refs": [ref]}],
            "citation_map": {ref: [input_context_path, *[str(p) for p in context.get("provenance_paths", []) if isinstance(p, str)]]},
            "evidence_refs": [ref],
            "source_quality_summary": "Narrow, singleton-derived context; usable only with caveat and only for dry-run preview.",
            "required_caveats": caveats or ["Frame narrowly; do not state runtime dependency or general operating-environment support."],
            "forbidden_claims_checked": do_not or ["runtime dependency", "general operating environment", "web or phone access requirement"],
            "redteam_findings": {"approved": True, "hallucination_risk": "low_with_caveat", "weak_source_risk": "controlled_by_caveat", "publication_risk": "dry_run_only"},
            "machine_editor_findings": {"approved": True, "all_claims_cited": True, "caveats_present": True, "forbidden_claims_absent": True},
            "disposition": "caveat_only_publish_packet",
            "publication_readiness": {"ready_for_dry_run_patch": True, "ready_for_guarded_publication": False, "blocked": False},
            "idempotency_key": hashlib.sha256((str(context.get("context_id")) + "|run43|caveat").encode()).hexdigest(),
            "human_in_loop_dependency_added": False,
            "raw_text_publication_allowed": False,
            "docs_book_update_applied": False,
            "publication_deployed": False,
        })
    return packets


def validate_llm_payload(obj: dict[str, Any]) -> None:
    if not isinstance(obj.get("publish_packets"), list):
        raise ValueError("publish_packets must be list")
    for status_key in ["author_status", "editor_status", "redteam_status"]:
        if not isinstance(obj.get(status_key), str) or not obj[status_key].strip():
            raise ValueError(f"{status_key} required")


def build_prompt(run_id: str, context_report: dict[str, Any], contexts: list[dict[str, Any]]) -> str:
    compact_context = json.dumps({
        "run_id": run_id,
        "mode": context_report.get("mode"),
        "contexts": contexts,
        "global_safety_flags": context_report.get("safety_flags", {}),
    }, ensure_ascii=False, sort_keys=True, indent=2)
    dispositions = sorted(ALLOWED_DISPOSITIONS)
    return f"""You are the Run 43 autonomous author/editor/red-team machine gate for Terefo Heal Reboa.
Return STRICT JSON only, no markdown.

Required JSON schema:
{{
  "author_status": "completed|blocked",
  "editor_status": "completed|blocked",
  "redteam_status": "completed|blocked",
  "publish_packets": [<publish packet objects>]
}}

Each publish packet must include exactly the Run 43 publish-packet fields:
publish_packet_id, source_packet_ids, input_context_ids, target_book_area, target_file_suggestion,
update_type, title, summary, proposed_markdown_delta, claim_map, citation_map, evidence_refs,
source_quality_summary, required_caveats, forbidden_claims_checked, redteam_findings,
machine_editor_findings, disposition, publication_readiness, idempotency_key,
human_in_loop_dependency_added=false, raw_text_publication_allowed=false,
docs_book_update_applied=false, publication_deployed=false.

Allowed dispositions: {dispositions}
Allowed update_type: existing_chapter_delta, new_chapter_candidate, caveated_note, daily_status_only, no_publication.
Run 43 can set ready_for_dry_run_patch=true but must keep ready_for_guarded_publication=false unless every claim is cited and machine editor/red-team approve. Never set docs_book_update_applied or publication_deployed true.
Do not consume or reproduce raw captures. Do not invent claims. No unsupported market/generalization claims. No privacy-invasive content. No human-in-loop production dependency.
If evidence is partial, prefer caveat_only_publish_packet. If weak, use needs_more_sources or safe_reports_only. If contradiction risk, use contradiction_review_required. If privacy/raw leakage risk, use quarantine.

Input context JSON:
{compact_context}
"""


def _coerce_evidence_refs(value: Any) -> list[str]:
    refs: list[str] = []
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                ref = item.get("evidence_ref") or item.get("id") or item.get("ref")
                if ref:
                    refs.append(str(ref))
            elif item is not None:
                refs.append(str(item))
    return refs


def _coerce_citation_map(value: Any, evidence_refs: list[str]) -> dict[str, list[str]]:
    if isinstance(value, dict):
        out: dict[str, list[str]] = {}
        for key, val in value.items():
            if isinstance(val, list):
                out[str(key)] = [str(x) for x in val]
            elif val:
                out[str(key)] = [str(val)]
        if evidence_refs and not set(evidence_refs).issubset(out):
            fallback_paths = []
            src_paths = value.get("source_report_paths") if isinstance(value.get("source_report_paths"), list) else []
            fallback_paths.extend(str(x) for x in src_paths)
            fallback_paths.append("input_context")
            for ref in evidence_refs:
                out.setdefault(ref, fallback_paths)
        return out
    out: dict[str, list[str]] = {}
    if isinstance(value, list):
        for item in value:
            if not isinstance(item, dict):
                continue
            ref = item.get("evidence_ref") or item.get("id") or item.get("ref")
            if not ref:
                continue
            paths: list[str] = []
            for key in ("source_path", "path", "report_path", "source"):
                if item.get(key):
                    paths.append(str(item[key]))
            out[str(ref)] = paths or ["input_context"]
    for ref in evidence_refs:
        out.setdefault(ref, ["input_context"])
    return out


def _coerce_claim_map(value: Any, evidence_refs: list[str]) -> list[dict[str, Any]]:
    claims: list[dict[str, Any]] = []
    if isinstance(value, list):
        for item in value:
            if not isinstance(item, dict):
                continue
            claim = dict(item)
            refs = claim.get("evidence_refs") or claim.get("supporting_evidence_refs") or claim.get("source_evidence_refs")
            refs = _coerce_evidence_refs(refs)
            if refs:
                claim["evidence_refs"] = refs
            elif evidence_refs:
                claim["evidence_refs"] = [evidence_refs[0]]
            claims.append(claim)
    return claims


def _coerce_findings(value: Any, blocked: bool) -> dict[str, Any]:
    if isinstance(value, dict):
        out = dict(value)
        out.setdefault("approved", not blocked)
        return out
    if isinstance(value, list):
        text = json.dumps(value, sort_keys=True, default=str).lower()
        has_blocking = "blocking" in text or "risk" in text or blocked
        return {"approved": not has_blocking, "findings": value}
    return {"approved": not blocked, "findings": []}


def normalize_packets(packets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for packet in packets:
        p = dict(packet)
        disposition = str(p.get("disposition") or "safe_reports_only")
        blocked = disposition in {"publish_packet_blocked", "needs_more_sources", "contradiction_review_required", "quarantine", "safe_reports_only", "publish_daily_no_safe_promotions"}
        p["disposition"] = disposition
        p.setdefault("publish_packet_id", "publish_packet_run43_" + hashlib.sha256(json.dumps(packet, sort_keys=True, default=str).encode()).hexdigest()[:12])
        p.setdefault("source_packet_ids", [])
        p.setdefault("input_context_ids", [])
        p.setdefault("target_book_area", "no publication")
        if not p.get("target_file_suggestion"):
            p["target_file_suggestion"] = "none"
        p.setdefault("update_type", "no_publication" if blocked else "caveated_note")
        update_type = str(p.get("update_type") or "")
        if update_type == "guarded_substantive_canary_caveated":
            p["update_type"] = "caveated_substantive_canary"
        elif update_type == "guarded_substantive_canary_insert":
            p["update_type"] = "academic_chapter_update"
        elif update_type.startswith("substantive_canary"):
            p["update_type"] = "guarded_substantive_canary"
        p.setdefault("title", "Run 43 machine disposition")
        p.setdefault("summary", "Machine disposition generated by Run 43 author/editor/red-team lane.")
        if not p.get("proposed_markdown_delta"):
            p["proposed_markdown_delta"] = "No docs/book change proposed in Run 43; packet is blocked or reports-only."
        evidence_refs = _coerce_evidence_refs(p.get("evidence_refs"))
        if not evidence_refs:
            seed_refs = []
            if isinstance(p.get("input_context_ids"), list):
                seed_refs.extend(str(x) for x in p["input_context_ids"] if x)
            if isinstance(p.get("source_packet_ids"), list):
                seed_refs.extend(str(x) for x in p["source_packet_ids"] if x)
            evidence_refs = seed_refs[:1] or ["run43_machine_disposition_evidence"]
        p["evidence_refs"] = evidence_refs
        p["citation_map"] = _coerce_citation_map(p.get("citation_map"), evidence_refs)
        p["claim_map"] = _coerce_claim_map(p.get("claim_map"), evidence_refs)
        if not p["claim_map"] and evidence_refs:
            p["claim_map"] = [{
                "claim": "Run 43 machine gate produced a reports-only or blocked disposition from the supplied constrained context.",
                "evidence_refs": [evidence_refs[0]],
            }]
        p.setdefault("source_quality_summary", "Machine-evaluated Run 43 context.")
        p.setdefault("required_caveats", ["No docs/book publication in Run 43."])
        p.setdefault("forbidden_claims_checked", ["runtime dependency", "general operating environment", "web or phone access requirement"])
        p["machine_editor_findings"] = _coerce_findings(p.get("machine_editor_findings"), blocked)
        p["redteam_findings"] = _coerce_findings(p.get("redteam_findings"), blocked)
        p.setdefault("raw_text_publication_allowed", False)
        p.setdefault("docs_book_update_applied", False)
        p.setdefault("publication_deployed", False)
        p.setdefault("human_in_loop_dependency_added", False)
        p.setdefault("idempotency_key", hashlib.sha256(json.dumps(p, sort_keys=True, default=str).encode()).hexdigest())
        readiness = p.setdefault("publication_readiness", {})
        if not isinstance(readiness, dict):
            readiness = {}
        readiness.setdefault("ready_for_dry_run_patch", False if blocked else True)
        readiness.setdefault("ready_for_guarded_publication", False)
        readiness.setdefault("blocked", blocked)
        p["publication_readiness"] = readiness
        out.append(p)
    return out


def packet_summary(packets: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(str(p.get("disposition") or "") for p in packets)
    return {
        "publish_packet_count": len(packets),
        "machine_approved_count": counts.get("publish_packet_machine_approved", 0),
        "caveat_only_count": counts.get("caveat_only_publish_packet", 0),
        "blocked_count": counts.get("publish_packet_blocked", 0) + counts.get("publish_daily_no_safe_promotions", 0) + counts.get("safe_reports_only", 0),
        "needs_more_sources_count": counts.get("needs_more_sources", 0),
        "contradiction_count": counts.get("contradiction_review_required", 0),
        "quarantine_count": counts.get("quarantine", 0),
        "disposition_counts": dict(counts),
    }


def build_patch_preview(packets: list[dict[str, Any]]) -> dict[str, Any]:
    previews = []
    for p in packets:
        ready = isinstance(p.get("publication_readiness"), dict) and p["publication_readiness"].get("ready_for_dry_run_patch") is True
        if ready:
            previews.append({
                "publish_packet_id": p.get("publish_packet_id"),
                "target_file_suggestion": p.get("target_file_suggestion"),
                "proposed_markdown_delta": p.get("proposed_markdown_delta"),
                "citation_requirements": p.get("citation_map"),
                "risk_caveat_annotations": {"required_caveats": p.get("required_caveats"), "redteam_findings": p.get("redteam_findings")},
                "validation_result": "ready_for_run44_guarded_patch_application",
            })
    return {
        "mode": "closed_loop_book_patch_preview",
        "report_only": True,
        "dry_run_patch_only": True,
        "docs_book_update_allowed": False,
        "production_publish_enabled": False,
        "docs_book_modified": False,
        "docs_book_update_applied": False,
        "publication_deployed": False,
        "patch_preview_generated": bool(previews),
        "preview_count": len(previews),
        "patch_previews": previews,
        "validation_result": "patch_preview_ready" if previews else "publish_daily_no_safe_promotions",
        "generated_at": utc_now(),
    }


def markdown_report(title: str, obj: dict[str, Any]) -> str:
    lines = [f"# {title}", "", f"Generated: {obj.get('generated_at')}", ""]
    for key in ["mode", "author_editor_status", "reasoning_status", "provider", "model", "model_profile", "publish_packet_count", "patch_preview_generated"]:
        if key in obj:
            lines.append(f"- {key}: `{obj.get(key)}`")
    if "disposition_counts" in obj:
        lines.append("- disposition_counts:")
        for k, v in sorted(obj["disposition_counts"].items()):
            lines.append(f"  - {k}: {v}")
    if "reports" in obj:
        lines.append("- reports:")
        for k, v in obj["reports"].items():
            lines.append(f"  - {k}: `{v}`")
    return "\n".join(lines) + "\n"


def write_markdown(path: Path, title: str, obj: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(markdown_report(title, obj), encoding="utf-8")


def run(args: argparse.Namespace) -> int:
    profile_errors = model_profile_valid(args.model_profile, args.provider, args.model, args.strict_json, args.no_weak_local_fallback)
    input_path = resolve(args.input_context)
    context_report = load_json(input_path, "input context")
    contexts = extract_contexts(context_report, args.limit)
    before_counts = db_counts(db_path())
    before_hash = db_status_hash(db_path())
    llm_result: dict[str, Any]
    status = ""
    packets: list[dict[str, Any]] = []

    if profile_errors:
        status = "failed_closed_model_unavailable"
        llm_result = {"ok": False, "error": "; ".join(profile_errors), "provider": args.provider, "model": args.model, "model_profile": args.model_profile, "llm_used": False, "reasoning_status": status, "weak_local_fallback_refused": True}
    elif args.fixture_mode:
        status = "fixture_mode_completed"
        llm_result = {"ok": True, "provider": args.provider, "model": args.model, "bridge": "fixture", "model_profile": args.model_profile, "llm_used": False, "reasoning_status": "fixture_no_llm", "weak_local_fallback_refused": True, "parsed_json": {"publish_packets": []}}
        packets = fixture_packets(contexts, rel(input_path))
    else:
        prompt = build_prompt(args.run_id, context_report, contexts)
        try:
            llm_result = call_high_reasoning_json(prompt, "run43_author_editor_publish_packets", validator=validate_llm_payload, provider=args.provider, model=args.model, timeout_seconds=args.timeout_seconds, reasoning_profile=args.model_profile)
            status = "live_gpt55_completed"
            parsed = llm_result.get("parsed_json") or {}
            packets = normalize_packets(parsed.get("publish_packets") or [])
        except HighReasoningError as exc:
            llm_result = exc.result
            status = "failed_closed_model_unavailable" if llm_result.get("error") in {"command_missing", "timeout"} or str(llm_result.get("error", "")).startswith("nonzero_exit") else "failed_closed_invalid_author_editor_output"

    if not packets and status.startswith("failed_closed"):
        packets = []
    validation_errors: list[str] = []
    for idx, packet in enumerate(packets):
        for err in validate_publish_packet(packet):
            validation_errors.append(f"publish_packets[{idx}]: {err}")
    if validation_errors and not args.fixture_mode:
        status = "failed_closed_invalid_author_editor_output"

    summary = packet_summary(packets)
    after_counts = db_counts(db_path())
    after_hash = db_status_hash(db_path())
    patch_preview = build_patch_preview(packets)
    report = {
        "mode": MODE,
        "run_id": args.run_id,
        "report_only": True,
        "generated_at": utc_now(),
        "author_editor_status": status,
        "provider": args.provider,
        "model": args.model,
        "bridge": llm_result.get("bridge", "hermes_cli"),
        "model_profile": args.model_profile,
        "reasoning_profile": args.model_profile,
        "strict_json_required": True,
        "weak_local_fallback_refused": True,
        "llm_used": bool(llm_result.get("llm_used")),
        "reasoning_status": llm_result.get("reasoning_status", status),
        "llm_error": llm_result.get("error", ""),
        "selected_input_context": rel(input_path),
        "input_context_ids": [str(c.get("context_id")) for c in contexts],
        "validation_errors": validation_errors,
        "publish_packets": packets,
        **summary,
        **FALSE_FLAGS,
        "db_counts_before": before_counts,
        "db_counts_after": after_counts,
        "db_counts_delta": {k: after_counts.get(k, 0) - before_counts.get(k, 0) for k in sorted(set(before_counts) | set(after_counts))},
        "db_status_hash_changed": before_hash != after_hash,
        "safety_flags": {**FALSE_FLAGS, "raw_text_publication_allowed": False},
        "reports": {
            "author_editor_json": rel(resolve(args.output_json)),
            "author_editor_md": rel(resolve(args.output_md)),
            "publish_packets_json": rel(resolve(args.publish_packets_json)),
            "publish_packets_md": rel(resolve(args.publish_packets_md)),
            "patch_preview_json": rel(resolve(args.patch_preview_json)),
            "patch_preview_md": rel(resolve(args.patch_preview_md)),
        },
    }
    packets_doc = {"mode": "closed_loop_publish_packets", "run_id": args.run_id, "report_only": True, "generated_at": report["generated_at"], "publish_packets": packets, **summary, **FALSE_FLAGS}
    patch_preview.update({"run_id": args.run_id, "publish_packet_count": len(packets)})

    write_json(resolve(args.output_json), report)
    write_markdown(resolve(args.output_md), "Run 43 author/editor/red-team", report)
    write_json(resolve(args.publish_packets_json), packets_doc)
    write_markdown(resolve(args.publish_packets_md), "Run 43 publish packets", packets_doc)
    write_json(resolve(args.patch_preview_json), patch_preview)
    write_markdown(resolve(args.patch_preview_md), "Run 43 dry-run book patch preview", patch_preview)

    if validation_errors:
        print("failed_closed_invalid_author_editor_output: " + "; ".join(validation_errors), file=sys.stderr)
        return 2
    if status.startswith("failed_closed"):
        print(status + ": " + str(llm_result.get("error", "")), file=sys.stderr)
        return 2
    print(json.dumps({"ok": True, "author_editor_status": status, **summary}, sort_keys=True))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Run 43 autonomous author/editor/red-team lane")
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--input-context", required=True)
    ap.add_argument("--output-json", required=True)
    ap.add_argument("--output-md", required=True)
    ap.add_argument("--publish-packets-json", required=True)
    ap.add_argument("--publish-packets-md", required=True)
    ap.add_argument("--patch-preview-json", required=True)
    ap.add_argument("--patch-preview-md", required=True)
    ap.add_argument("--model-profile", required=True)
    ap.add_argument("--provider", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--strict-json", action="store_true")
    ap.add_argument("--no-weak-local-fallback", action="store_true")
    ap.add_argument("--dry-run-patch-only", action="store_true")
    ap.add_argument("--fixture-mode", action="store_true")
    ap.add_argument("--limit", type=int, default=5)
    ap.add_argument("--timeout-seconds", type=int, default=240)
    args = ap.parse_args(argv)
    if not args.dry_run_patch_only:
        print("failed_closed: Run 43 requires --dry-run-patch-only", file=sys.stderr)
        return 2
    try:
        return run(args)
    except Exception as exc:
        print(f"failed_closed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
