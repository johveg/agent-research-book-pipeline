#!/usr/bin/env python3
"""Run 19 cluster quality gate and packet-readiness review.

This stage calls the closed_loop_editorial GPT-5.5 profile through the shared
Hermes high-reasoning strict-JSON bridge and produces advisory/report-only
quality reviews for Run 18 cluster candidates. It does not persist clusters,
create narrative packets, insert claims/editorial reviews/source notes, or
modify publication artifacts.
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

from hermes_high_reasoning_json import HighReasoningError, call_high_reasoning_json  # noqa: E402
from model_profiles import ModelProfileError, load_model_profile  # noqa: E402
from research_common import DB_PATH as DEFAULT_DB_PATH, sha256_text  # noqa: E402

RUN_ID_DEFAULT = "citation-pipeline-test-20260612"
MODE = "llm_cluster_quality_gate"
DEFAULT_CLUSTER_REPORT = f"reports/editorial/{RUN_ID_DEFAULT}-research-object-clusters-run18.json"

SELECTABLE_CLUSTER_DECISIONS = {"cluster_candidate", "caveat_only_cluster_candidate"}
EXCLUDE_DECISIONS = {
    "source_context_unclear",
    "needs_more_sources",
    "contradiction_review_required",
    "exclude_from_clustering",
    "exclude_from_pipeline",
    "do_not_use",
    "safe_reports_only",
}
ALLOWED_QUALITY_GATE_DECISIONS = {
    "packet_candidate_ready",
    "caveat_only_packet_candidate_ready",
    "needs_more_sources",
    "source_context_unclear",
    "safe_reports_only",
    "exclude_from_packetization",
    "contradiction_review_required",
}
ALLOWED_PACKET_READINESS = {
    "ready_for_caveat_only_packet",
    "ready_for_context_packet",
    "not_ready_needs_more_sources",
    "not_ready_source_context_unclear",
    "not_ready_safe_reports_only",
    "not_ready_exclude",
    "not_ready_contradiction_review",
}
ALLOWED_DISPOSITIONS = {
    "caveat_only",
    "needs_more_sources",
    "source_context_unclear",
    "safe_reports_only",
    "exclude_from_pipeline",
    "contradiction_review_required",
    "eligible_for_packet_candidate",
}
ALLOWED_NEXT_STAGES = {
    "build_caveat_only_packet_candidate",
    "run_additional_source_collection",
    "keep_safe_reports_only",
    "exclude_from_pipeline",
    "run_contradiction_review",
    "run_source_context_review",
}
REQUIRED_REVIEW_FIELDS = [
    "cluster_id",
    "cluster_type",
    "cluster_use",
    "singleton_cluster",
    "quality_gate_decision",
    "packet_readiness",
    "closed_loop_disposition",
    "traceability_assessment",
    "evidence_strength_assessment",
    "caveat_integrity_assessment",
    "packet_readiness_assessment",
    "safety_assessment",
    "required_caveats",
    "limitations",
    "residual_risk",
    "do_not_say",
    "recommended_next_stage",
    "advisory_only",
    "author_allowed",
    "publication_approved",
    "eligible_for_claim_insertion",
    "eligible_for_authoring",
    "eligible_for_publication",
]
FALSE_FLAGS = [
    "author_allowed",
    "publication_approved",
    "eligible_for_claim_insertion",
    "eligible_for_authoring",
    "eligible_for_publication",
]


class ClusterQualityGateError(RuntimeError):
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
        raise ClusterQualityGateError(f"missing input {label}: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ClusterQualityGateError(f"invalid JSON in {label}: {exc}") from exc
    if not isinstance(data, dict):
        raise ClusterQualityGateError(f"{label} must be a JSON object")
    return data


def compact_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


def connect_readonly(path: Path) -> sqlite3.Connection:
    if not path.exists():
        raise ClusterQualityGateError(f"missing SQLite DB: {path}")
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA query_only = ON")
    return con


def table_count(con: sqlite3.Connection, table: str) -> int:
    return int(con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def status_snapshots(con: sqlite3.Connection) -> dict[str, str]:
    specs = {
        "sources_status_hash": "SELECT id, quality_score, privacy_publication_status, duplicate_status FROM sources ORDER BY id",
        "claims_status_hash": "SELECT id, status, publication_decision, contradiction_status FROM claims ORDER BY id",
        "editorial_reviews_hash": "SELECT id, run_id, review_type, status, summary, report_path, created_at FROM editorial_reviews ORDER BY id",
    }
    return {name: sha256_text(compact_json([tuple(r) for r in con.execute(sql).fetchall()])) for name, sql in specs.items()}


def validate_cluster_report(report: dict[str, Any]) -> None:
    if report.get("mode") != "llm_cluster_research_objects":
        raise ClusterQualityGateError("Run 18 cluster report mode mismatch")
    if report.get("report_only") is not True:
        raise ClusterQualityGateError("Run 18 cluster report must be report_only")
    if not isinstance(report.get("cluster_candidates"), list):
        raise ClusterQualityGateError("Run 18 cluster report missing cluster_candidates list")
    if not isinstance(report.get("excluded_manifest_items"), list):
        raise ClusterQualityGateError("Run 18 cluster report missing excluded_manifest_items list")
    safety = report.get("safety_flags")
    if not isinstance(safety, dict):
        raise ClusterQualityGateError("Run 18 cluster report missing safety_flags")
    expected = {
        "advisory_only": True,
        "author_allowed": False,
        "publication_approved": False,
        "eligible_for_claim_insertion": False,
        "eligible_for_authoring": False,
        "eligible_for_publication": False,
        "narrative_packets_created": False,
        "chapter_prose_generated": False,
        "source_notes_written": False,
    }
    for key, expected_value in expected.items():
        if safety.get(key) is not expected_value:
            raise ClusterQualityGateError(f"Run 18 cluster report safety flag invalid: {key}")


def validate_cluster_safety(cluster: dict[str, Any]) -> None:
    if cluster.get("advisory_only") is not True:
        raise ClusterQualityGateError(f"cluster {cluster.get('cluster_id')} safety flag invalid: advisory_only")
    for key in FALSE_FLAGS:
        if cluster.get(key) is not False:
            raise ClusterQualityGateError(f"cluster {cluster.get('cluster_id')} safety flag invalid: {key}")
    if cluster.get("raw_capture_dependency") is True or cluster.get("raw_content_stored") is True:
        raise ClusterQualityGateError(f"cluster {cluster.get('cluster_id')} has forbidden raw capture dependency")


def cluster_exclusion_decision(cluster: dict[str, Any]) -> str | None:
    for field in ("cluster_decision", "cluster_use", "closed_loop_disposition", "packet_readiness"):
        value = cluster.get(field)
        if value in EXCLUDE_DECISIONS:
            return str(value)
    if cluster.get("raw_capture_dependency") is True or cluster.get("raw_content_stored") is True:
        return "do_not_use"
    return None


def select_clusters(report: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    selected: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for cluster in report.get("cluster_candidates", []):
        if not isinstance(cluster, dict):
            raise ClusterQualityGateError("cluster candidate must be object")
        validate_cluster_safety(cluster)
        ex = cluster_exclusion_decision(cluster)
        if ex:
            copy = dict(cluster)
            copy["exclusion_decision"] = ex
            copy["excluded_reason"] = "blocked_or_excluded_cluster_decision"
            excluded.append(copy)
            continue
        if cluster.get("cluster_decision") not in SELECTABLE_CLUSTER_DECISIONS:
            copy = dict(cluster)
            copy["exclusion_decision"] = str(cluster.get("cluster_decision") or "not_selected")
            copy["excluded_reason"] = "not_selected_for_quality_gate"
            excluded.append(copy)
            continue
        selected.append(cluster)
    for item in report.get("excluded_manifest_items", []):
        if not isinstance(item, dict):
            raise ClusterQualityGateError("excluded manifest item must be object")
        copy = dict(item)
        copy.setdefault("exclusion_decision", item.get("downstream_manifest_decision") or item.get("closed_loop_disposition") or item.get("cluster_decision") or "upstream_excluded")
        copy.setdefault("excluded_reason", "upstream_excluded_from_run18_clustering")
        excluded.append(copy)
    return selected, excluded


def as_nonempty_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be non-empty string")
    return value


def as_list(value: Any, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be list")
    return value


def validate_single_review(review: dict[str, Any], selected_by_id: dict[str, dict[str, Any]]) -> None:
    if not isinstance(review, dict):
        raise ValueError("cluster review must be object")
    for field in REQUIRED_REVIEW_FIELDS:
        if field not in review:
            raise ValueError(f"cluster review missing required field: {field}")
    cluster_id = as_nonempty_string(review.get("cluster_id"), "cluster_id")
    if cluster_id not in selected_by_id:
        raise ValueError(f"unexpected cluster_id: {cluster_id}")
    source_cluster = selected_by_id[cluster_id]
    if review.get("cluster_type") != source_cluster.get("cluster_type"):
        raise ValueError(f"cluster_type mismatch for {cluster_id}")
    if review.get("cluster_use") != source_cluster.get("cluster_use"):
        raise ValueError(f"cluster_use mismatch for {cluster_id}")
    if review.get("singleton_cluster") is not source_cluster.get("singleton_cluster"):
        raise ValueError(f"singleton_cluster mismatch for {cluster_id}")
    if review.get("quality_gate_decision") not in ALLOWED_QUALITY_GATE_DECISIONS:
        raise ValueError(f"invalid quality_gate_decision: {review.get('quality_gate_decision')}")
    if review.get("packet_readiness") not in ALLOWED_PACKET_READINESS:
        raise ValueError(f"invalid packet_readiness: {review.get('packet_readiness')}")
    if review.get("closed_loop_disposition") not in ALLOWED_DISPOSITIONS:
        raise ValueError(f"invalid closed_loop_disposition: {review.get('closed_loop_disposition')}")
    if review.get("recommended_next_stage") not in ALLOWED_NEXT_STAGES:
        raise ValueError(f"invalid recommended_next_stage: {review.get('recommended_next_stage')}")
    for field in [
        "traceability_assessment",
        "evidence_strength_assessment",
        "caveat_integrity_assessment",
        "packet_readiness_assessment",
        "safety_assessment",
        "residual_risk",
    ]:
        as_nonempty_string(review.get(field), field)
    for field in ["required_caveats", "limitations", "do_not_say"]:
        as_list(review.get(field), field)
    if review.get("advisory_only") is not True:
        raise ValueError("review advisory_only must be true")
    for key in FALSE_FLAGS:
        if review.get(key) is not False:
            raise ValueError(f"review {key} must be false")
    if source_cluster.get("cluster_use") == "caveat_only" or source_cluster.get("caveat_required") is True:
        if review.get("quality_gate_decision") not in {"caveat_only_packet_candidate_ready", "needs_more_sources", "source_context_unclear", "safe_reports_only", "exclude_from_packetization", "contradiction_review_required"}:
            raise ValueError("caveat-only cluster cannot become normal packet/claim candidate")
        if review.get("packet_readiness") not in {"ready_for_caveat_only_packet", "not_ready_needs_more_sources", "not_ready_source_context_unclear", "not_ready_safe_reports_only", "not_ready_exclude", "not_ready_contradiction_review"}:
            raise ValueError("caveat-only cluster has invalid packet_readiness")
        if review.get("recommended_next_stage") == "build_caveat_only_packet_candidate" and review.get("quality_gate_decision") != "caveat_only_packet_candidate_ready":
            raise ValueError("build_caveat_only_packet_candidate requires caveat_only_packet_candidate_ready")


def make_validator(selected: list[dict[str, Any]]):
    selected_by_id = {str(c["cluster_id"]): c for c in selected}

    def validator(obj: dict[str, Any]) -> None:
        reviews = obj.get("cluster_reviews")
        if not isinstance(reviews, list):
            raise ValueError("LLM JSON must contain cluster_reviews list")
        if len(reviews) != len(selected_by_id):
            raise ValueError(f"expected {len(selected_by_id)} cluster review(s), got {len(reviews)}")
        seen = set()
        for review in reviews:
            validate_single_review(review, selected_by_id)
            cid = review["cluster_id"]
            if cid in seen:
                raise ValueError(f"duplicate cluster review: {cid}")
            seen.add(cid)
    return validator


def build_prompt(selected: list[dict[str, Any]], excluded: list[dict[str, Any]], run_id: str) -> str:
    schema = {
        "cluster_reviews": [
            {
                "cluster_id": "string",
                "cluster_type": "string from input",
                "cluster_use": "string from input",
                "singleton_cluster": "boolean from input",
                "quality_gate_decision": sorted(ALLOWED_QUALITY_GATE_DECISIONS),
                "packet_readiness": sorted(ALLOWED_PACKET_READINESS),
                "closed_loop_disposition": sorted(ALLOWED_DISPOSITIONS),
                "traceability_assessment": "non-empty string",
                "evidence_strength_assessment": "non-empty string",
                "caveat_integrity_assessment": "non-empty string",
                "packet_readiness_assessment": "non-empty string",
                "safety_assessment": "non-empty string",
                "required_caveats": ["string"],
                "limitations": ["string"],
                "residual_risk": "non-empty string",
                "do_not_say": ["string"],
                "recommended_next_stage": sorted(ALLOWED_NEXT_STAGES),
                "advisory_only": True,
                "author_allowed": False,
                "publication_approved": False,
                "eligible_for_claim_insertion": False,
                "eligible_for_authoring": False,
                "eligible_for_publication": False,
            }
        ]
    }
    payload = {
        "run_id": run_id,
        "task": "Run 19 cluster quality gate and packet-readiness review",
        "strict_json_required": True,
        "selected_clusters": selected,
        "excluded_context": excluded,
        "allowed_schema": schema,
        "instructions": [
            "Return JSON only. No markdown, no prose outside JSON.",
            "Review every selected cluster exactly once.",
            "Do not approve authoring, publication, chapter prose, claim insertion, editorial review insertion, or narrative packet creation.",
            "For caveat-only clusters, do not convert the caveat into a confident claim or normal packet candidate.",
            "Choose exactly one allowed string for every enum field; do not return arrays for enum fields.",
            "If traceability/evidence/caveats are insufficient, choose safe_reports_only, needs_more_sources, source_context_unclear, exclude_from_packetization, or contradiction_review_required.",
        ],
    }
    return "Return strict JSON matching this schema and input:\n" + json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False)


def safety_flags() -> dict[str, bool]:
    return {
        "advisory_only": True,
        "author_allowed": False,
        "publication_approved": False,
        "eligible_for_claim_insertion": False,
        "eligible_for_authoring": False,
        "eligible_for_publication": False,
        "claims_inserted": False,
        "editorial_reviews_inserted": False,
        "source_notes_written": False,
        "source_registry_promoted": False,
        "raw_content_stored": False,
        "narrative_packets_created": False,
        "chapter_prose_generated": False,
        "clusters_persisted": False,
        "gpt55_is_human_or_editor_approval": False,
    }


def build_payload(args: argparse.Namespace) -> dict[str, Any]:
    cluster_path = resolve(args.cluster_report)
    cluster_report = load_json(cluster_path, "Run 18 cluster report")
    validate_cluster_report(cluster_report)
    try:
        profile = load_model_profile(args.reasoning_profile)
    except ModelProfileError as exc:
        raise ClusterQualityGateError(f"model_profile_error:{exc}") from exc
    db = db_path()
    selected, excluded = select_clusters(cluster_report)
    if not selected:
        raise ClusterQualityGateError("no selected clusters for quality gate")

    with connect_readonly(db) as con:
        before_counts = {"source_notes": table_count(con, "source_notes"), "claims": table_count(con, "claims"), "editorial_reviews": table_count(con, "editorial_reviews")}
        before_status = status_snapshots(con)
        prompt = build_prompt(selected, excluded, args.run_id)
        try:
            llm = call_high_reasoning_json(
                prompt,
                schema_name="run19_cluster_quality_gate",
                validator=make_validator(selected),
                provider=args.provider,
                model=args.model,
                timeout_seconds=args.timeout_seconds,
                reasoning_profile=args.reasoning_profile,
            )
        except HighReasoningError as exc:
            raise ClusterQualityGateError(str(exc.result.get("error") or exc)) from exc
        after_counts = {"source_notes": table_count(con, "source_notes"), "claims": table_count(con, "claims"), "editorial_reviews": table_count(con, "editorial_reviews")}
        after_status = status_snapshots(con)

    reviews = llm["parsed_json"]["cluster_reviews"]
    q_counts = Counter(r["quality_gate_decision"] for r in reviews)
    p_counts = Counter(r["packet_readiness"] for r in reviews)
    d_counts = Counter(r["closed_loop_disposition"] for r in reviews)
    n_counts = Counter(r["recommended_next_stage"] for r in reviews)
    changed_source_notes = before_counts["source_notes"] != after_counts["source_notes"]
    payload = {
        "run_id": args.run_id,
        "generated_at": utc_now(),
        "mode": MODE,
        "input_paths": {"cluster_report": rel(cluster_path), "sqlite_db": rel(db)},
        "report_only": True,
        "llm_used": bool(llm.get("llm_used")),
        "reasoning_status": llm.get("reasoning_status"),
        "provider": llm.get("provider") or profile["provider"],
        "model": llm.get("model") or profile["model"],
        "bridge": llm.get("bridge") or profile["bridge"],
        "model_profile": llm.get("model_profile") or profile["profile_name"],
        "strict_json_required": bool(llm.get("strict_json_required", profile["strict_json_required"])),
        "weak_local_fallback_refused": bool(llm.get("weak_local_fallback_refused", True)),
        "selected_cluster_count": len(selected),
        "reviewed_cluster_count": len(reviews),
        "excluded_cluster_count": len(excluded),
        "quality_gate_decision_counts": dict(q_counts),
        "packet_readiness_counts": dict(p_counts),
        "closed_loop_disposition_counts": dict(d_counts),
        "recommended_next_stage_counts": dict(n_counts),
        "selected_clusters": selected,
        "excluded_clusters": excluded,
        "cluster_reviews": reviews,
        "failed_quality_checks": [],
        "llm_metadata": {k: llm.get(k) for k in ["ok", "stdout_json_valid", "exit_code", "timed_out", "elapsed_seconds", "stdout_hash", "prompt_hash", "command_shape"]},
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
        "claims_count_before": before_counts["claims"],
        "claims_count_after": after_counts["claims"],
        "editorial_reviews_count_before": before_counts["editorial_reviews"],
        "editorial_reviews_count_after": after_counts["editorial_reviews"],
        "safety_flags": safety_flags(),
    }
    if not payload["llm_used"] or payload["reasoning_status"] != "high_reasoning_used":
        raise ClusterQualityGateError("high reasoning was not used")
    if payload["provider"] != "copilot" or payload["model"] != "gpt-5.5" or payload["bridge"] != "hermes_cli" or payload["model_profile"] != args.reasoning_profile:
        raise ClusterQualityGateError("unexpected high-reasoning provider/model/bridge/profile")
    if payload["changed_source_notes"] or payload["claims_inserted"] or payload["editorial_reviews_inserted"] or payload["source_status_changed"] or payload["claim_status_changed"] or payload["editorial_status_changed"]:
        raise ClusterQualityGateError("forbidden DB/status delta detected during report-only quality gate")
    return payload


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        f"# Run 19 cluster quality gate — {payload['run_id']}", "",
        "## Summary", "",
        f"- Report-only: `{payload['report_only']}`",
        f"- GPT-5.5 used: `{payload['llm_used']}`",
        f"- Provider/model/bridge/profile: `{payload['provider']}` / `{payload['model']}` / `{payload['bridge']}` / `{payload['model_profile']}`",
        f"- Selected clusters: `{payload['selected_cluster_count']}`",
        f"- Reviewed clusters: `{payload['reviewed_cluster_count']}`",
        f"- Excluded clusters/items: `{payload['excluded_cluster_count']}`",
        "", "## Quality gate decisions", "",
    ]
    for r in payload["cluster_reviews"]:
        lines += [
            f"- `{r['cluster_id']}`",
            f"  - type/use: `{r['cluster_type']}` / `{r['cluster_use']}`",
            f"  - quality_gate_decision: `{r['quality_gate_decision']}`",
            f"  - packet_readiness: `{r['packet_readiness']}`",
            f"  - closed_loop_disposition: `{r['closed_loop_disposition']}`",
            f"  - recommended_next_stage: `{r['recommended_next_stage']}`",
            f"  - caveats: {', '.join(r.get('required_caveats') or [])}",
            f"  - limitations: {', '.join(r.get('limitations') or [])}",
            f"  - residual_risk: {r.get('residual_risk', '')}",
            "",
        ]
    lines += ["## Excluded clusters/items", ""]
    for item in payload["excluded_clusters"]:
        ident = item.get("cluster_id") or item.get("manifest_item_id") or item.get("source_review_id") or "unknown"
        lines += [
            f"- `{ident}`",
            f"  - exclusion_decision: `{item.get('exclusion_decision', '')}`",
            f"  - reason: `{item.get('excluded_reason', item.get('skip_reason', ''))}`",
            "",
        ]
    lines += [
        "## Caveat-only constraints", "",
        "The reviewed cluster remains advisory and caveat-only. The quality gate does not convert it into a claim, normal support cluster, chapter prose, author approval, or publication approval.",
        "", "## Why no persistence/publication changes were made", "",
        "Run 19 is an advisory report-only review. It reads the Run 18 cluster report and SQLite counts/statuses read-only, calls the strict-JSON GPT-5.5 bridge, and writes JSON/Markdown reports only. It does not insert claims, editorial reviews, source notes, modify statuses, update source registry/raw captures/docs/book/schema/daily worker, create narrative packets, or approve authoring/publication.",
        "", "## Recommendation for Run 20", "",
        "Run 20 may build a report-only caveat-only narrative packet candidate only for clusters whose Run 19 quality gate selected `build_caveat_only_packet_candidate`. It should remain disabled from DB/prose/publication writes unless a later explicit persistence/publication gate is designed and tested.",
    ]
    return "\n".join(lines) + "\n"


def write_reports(payload: dict[str, Any], output_dir: Path, suffix: str) -> dict[str, str]:
    out_dir = output_dir if output_dir.is_absolute() else ROOT / output_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{payload['run_id']}-cluster-quality-gate-{suffix}" if suffix else f"{payload['run_id']}-cluster-quality-gate"
    json_path = out_dir / f"{stem}.json"
    md_path = out_dir / f"{stem}.md"
    payload["output_paths"] = {"json": rel(json_path), "markdown": rel(md_path)}
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(payload), encoding="utf-8")
    return payload["output_paths"]


def parse_args(argv: list[str]) -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", default=RUN_ID_DEFAULT)
    ap.add_argument("--cluster-report", default=DEFAULT_CLUSTER_REPORT)
    ap.add_argument("--output-dir", default="reports/editorial")
    ap.add_argument("--report-suffix", default="run19")
    ap.add_argument("--reasoning-profile", default="closed_loop_editorial")
    ap.add_argument("--provider", default=None)
    ap.add_argument("--model", default=None)
    ap.add_argument("--timeout-seconds", type=int, default=300)
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        payload = build_payload(args)
        write_reports(payload, resolve(args.output_dir), args.report_suffix)
        print(json.dumps({
            "ok": True,
            "output_paths": payload["output_paths"],
            "selected_cluster_count": payload["selected_cluster_count"],
            "reviewed_cluster_count": payload["reviewed_cluster_count"],
            "excluded_cluster_count": payload["excluded_cluster_count"],
            "quality_gate_decision_counts": payload["quality_gate_decision_counts"],
            "packet_readiness_counts": payload["packet_readiness_counts"],
            "closed_loop_disposition_counts": payload["closed_loop_disposition_counts"],
            "recommended_next_stage_counts": payload["recommended_next_stage_counts"],
        }, sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
