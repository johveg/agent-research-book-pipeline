#!/usr/bin/env python3
"""Run 18 report-only clustering of downstream-eligible research objects.

Consumes the Run 17 downstream eligibility manifest and emits advisory cluster
candidates only. This script does not call an LLM unless a future mode is added;
it loads the closed_loop_editorial model profile for explicit routing/safety
metadata and performs deterministic closed-loop clustering over sanitized
manifest items.
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
MODE = "llm_cluster_research_objects"
DEFAULT_MANIFEST = f"reports/editorial/{RUN_ID_DEFAULT}-downstream-eligibility-manifest-run17.json"
SELECTABLE_DECISIONS = {"eligible_for_clustering", "caveat_only_cluster_candidate"}
EXCLUDED_DECISIONS = {
    "source_context_unclear",
    "needs_more_sources",
    "exclude_from_clustering",
    "exclude_from_pipeline",
    "contradiction_review_required",
    "safe_reports_only",
    "do_not_use",
}
ALLOWED_CLUSTER_TYPES = {
    "caveat_cluster",
    "caveat_only_support_cluster",
    "support_cluster",
    "example_cluster",
    "trend_signal_cluster",
    "counterpoint_cluster",
    "source_context_cluster",
}
ALLOWED_CLUSTER_USES = {
    "caveat_only",
    "support_context_only",
    "example_context_only",
    "trend_context_only",
    "counterpoint_context_only",
    "not_for_claiming",
}
ALLOWED_CLUSTER_DECISIONS = {
    "cluster_candidate",
    "caveat_only_cluster_candidate",
    "needs_more_sources",
    "source_context_unclear",
    "exclude_from_clustering",
    "contradiction_review_required",
}
REQUIRED_FALSE_FLAGS = [
    "author_allowed",
    "publication_approved",
    "eligible_for_claim_insertion",
    "eligible_for_authoring",
    "eligible_for_publication",
]


class ClusterResearchObjectsError(RuntimeError):
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
        raise ClusterResearchObjectsError(f"missing input {label}: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ClusterResearchObjectsError(f"invalid JSON in {label}: {exc}") from exc
    if not isinstance(data, dict):
        raise ClusterResearchObjectsError(f"{label} must be a JSON object")
    return data


def compact_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


def connect_readonly(path: Path) -> sqlite3.Connection:
    if not path.exists():
        raise ClusterResearchObjectsError(f"missing SQLite DB: {path}")
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


def validate_manifest(manifest: dict[str, Any]) -> None:
    if manifest.get("mode") != "audit_persisted_rereview_notes":
        raise ClusterResearchObjectsError("Run 17 manifest mode mismatch")
    if manifest.get("report_only") is not True:
        raise ClusterResearchObjectsError("Run 17 manifest must be report_only")
    safety = manifest.get("safety_flags")
    if not isinstance(safety, dict):
        raise ClusterResearchObjectsError("Run 17 manifest missing safety_flags")
    expected = {
        "advisory_only": True,
        "author_allowed": False,
        "publication_approved": False,
        "eligible_for_claim_insertion": False,
        "eligible_for_authoring": False,
        "eligible_for_publication": False,
    }
    for key, expected_value in expected.items():
        if safety.get(key) is not expected_value:
            raise ClusterResearchObjectsError(f"Run 17 manifest safety flag invalid: {key}")
    if not isinstance(manifest.get("manifest_items"), list) or not isinstance(manifest.get("excluded_items"), list):
        raise ClusterResearchObjectsError("Run 17 manifest requires manifest_items and excluded_items lists")


def validate_item_safety(item: dict[str, Any]) -> None:
    if item.get("advisory_only") is not True:
        raise ClusterResearchObjectsError(f"manifest item {item.get('manifest_item_id')} safety flag invalid: advisory_only")
    for key in REQUIRED_FALSE_FLAGS:
        if item.get(key) is not False:
            raise ClusterResearchObjectsError(f"manifest item {item.get('manifest_item_id')} safety flag invalid: {key}")


def exclusion_decision(item: dict[str, Any]) -> str | None:
    decision = item.get("downstream_manifest_decision")
    disposition = item.get("closed_loop_disposition")
    if item.get("contradiction_flag") is True or decision == "contradiction_review_required" or disposition == "contradiction_review_required":
        return "contradiction_review_required"
    if item.get("do_not_use") is True or item.get("evidence_use_decision") == "do_not_use" or decision == "do_not_use" or disposition == "do_not_use":
        if item.get("contradiction_flag") is True:
            return "contradiction_review_required"
        return "exclude_from_clustering"
    if decision in EXCLUDED_DECISIONS:
        return str(decision)
    if disposition in EXCLUDED_DECISIONS:
        return str(disposition)
    return None


def classify_item(item: dict[str, Any]) -> tuple[str, str, str]:
    decision = item.get("downstream_manifest_decision")
    if decision == "caveat_only_cluster_candidate" or item.get("caveat_required") is True:
        return "caveat_only_support_cluster", "caveat_only", "caveat_only_cluster_candidate"
    return "support_cluster", "support_context_only", "cluster_candidate"


def cluster_id_for(items: list[dict[str, Any]], cluster_type: str, cluster_use: str) -> str:
    ids = "|".join(sorted(str(i["manifest_item_id"]) for i in items))
    return "cluster_" + sha256_text(f"run18:{cluster_type}:{cluster_use}:{ids}")[:24]


def uniq(values: list[Any]) -> list[Any]:
    out = []
    seen = set()
    for v in values:
        marker = compact_json(v)
        if marker not in seen:
            seen.add(marker)
            out.append(v)
    return out


def make_cluster(items: list[dict[str, Any]]) -> dict[str, Any]:
    if not items:
        raise ClusterResearchObjectsError("cannot make empty cluster")
    cluster_type, cluster_use, cluster_decision = classify_item(items[0])
    for item in items:
        t, u, d = classify_item(item)
        if (t, u, d) != (cluster_type, cluster_use, cluster_decision):
            raise ClusterResearchObjectsError("mixed cluster classes are not supported in Run 18")
    if cluster_type not in ALLOWED_CLUSTER_TYPES or cluster_use not in ALLOWED_CLUSTER_USES or cluster_decision not in ALLOWED_CLUSTER_DECISIONS:
        raise ClusterResearchObjectsError("invalid cluster vocabulary")
    source_review_ids = uniq([i.get("source_review_id") for i in items if i.get("source_review_id")])
    manifest_ids = uniq([i.get("manifest_item_id") for i in items if i.get("manifest_item_id")])
    note_ids = uniq([i.get("note_id") for i in items if i.get("note_id")])
    source_ids = uniq([i.get("source_id") for i in items if i.get("source_id")])
    candidate_ids: list[str] = []
    for item in items:
        candidate_ids.extend(item.get("accepted_candidate_source_ids") or item.get("candidate_source_ids") or [])
    caveat_required = any(bool(i.get("caveat_required")) for i in items)
    caveat_texts = uniq([i.get("caveat_text") for i in items if i.get("caveat_text")])
    limitations = uniq([i.get("limitations") for i in items if i.get("limitations")])
    residual_risks = uniq([i.get("residual_risk") for i in items if i.get("residual_risk")])
    title = "Caveat-only Hermes/OpenClaw support context" if cluster_use == "caveat_only" else "Source-support context cluster"
    summary = "Singleton caveat-only cluster candidate derived from one downstream-eligible persisted rereview note." if len(items) == 1 and cluster_use == "caveat_only" else "Report-only source-support cluster candidate derived from downstream-eligible manifest items."
    thesis = caveat_texts[0] if caveat_texts else "Use only as advisory support context; not a claim or publication-ready statement."
    return {
        "cluster_id": cluster_id_for(items, cluster_type, cluster_use),
        "cluster_type": cluster_type,
        "cluster_use": cluster_use,
        "cluster_decision": cluster_decision,
        "singleton_cluster": len(items) == 1,
        "title": title,
        "cluster_summary": summary,
        "cluster_thesis_or_caveat": thesis,
        "source_ids": source_ids,
        "note_ids": note_ids,
        "source_review_ids": source_review_ids,
        "manifest_item_ids": manifest_ids,
        "candidate_source_ids": uniq(candidate_ids),
        "support_decisions": uniq([i.get("support_decision") for i in items if i.get("support_decision")]),
        "corroboration_decisions": uniq([i.get("corroboration_decision") for i in items if i.get("corroboration_decision")]),
        "evidence_use_decisions": uniq([i.get("evidence_use_decision") for i in items if i.get("evidence_use_decision")]),
        "caveat_required": caveat_required,
        "caveat_text": "\n".join(caveat_texts),
        "limitations": "\n".join(limitations),
        "residual_risk": "\n".join(residual_risks),
        "excluded_from_claiming_reason": "This Run 18 cluster is organizational/advisory only, not a claim, not narrative packet material, and not author/publication approval.",
        "provenance_paths": uniq([i.get("provenance_paths") for i in items if i.get("provenance_paths")]),
        "advisory_only": True,
        "author_allowed": False,
        "publication_approved": False,
        "eligible_for_claim_insertion": False,
        "eligible_for_authoring": False,
        "eligible_for_publication": False,
    }


def select_and_cluster(manifest: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    selected: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    for item in manifest.get("manifest_items", []):
        if not isinstance(item, dict):
            raise ClusterResearchObjectsError("manifest item must be object")
        validate_item_safety(item)
        ex = exclusion_decision(item)
        if ex:
            copy = dict(item)
            copy["downstream_manifest_decision"] = ex
            copy["excluded_reason"] = "blocked_or_excluded_manifest_decision"
            excluded.append(copy)
            continue
        if item.get("downstream_manifest_decision") not in SELECTABLE_DECISIONS:
            copy = dict(item)
            copy["excluded_reason"] = "not_selected_for_clustering"
            excluded.append(copy)
            continue
        selected.append(item)
    for item in manifest.get("excluded_items", []):
        if not isinstance(item, dict):
            raise ClusterResearchObjectsError("excluded item must be object")
        copy = dict(item)
        copy.setdefault("excluded_reason", "upstream_excluded_from_manifest")
        excluded.append(copy)
    clusters: list[dict[str, Any]] = []
    if selected:
        # Run 18 intentionally supports singleton clusters. Future runs can group
        # multiple selected items by richer semantics after more eligible items exist.
        for item in selected:
            clusters.append(make_cluster([item]))
    return selected, excluded, clusters, failed


def build_payload(args: argparse.Namespace) -> dict[str, Any]:
    manifest_path = resolve(args.downstream_manifest)
    manifest = load_json(manifest_path, "Run 17 downstream manifest")
    validate_manifest(manifest)
    profile = load_model_profile("closed_loop_editorial")
    db = db_path()
    with connect_readonly(db) as con:
        before_counts = {"source_notes": table_count(con, "source_notes"), "claims": table_count(con, "claims"), "editorial_reviews": table_count(con, "editorial_reviews")}
        before_status = status_snapshots(con)
        selected, excluded, clusters, failed = select_and_cluster(manifest)
        after_counts = {"source_notes": table_count(con, "source_notes"), "claims": table_count(con, "claims"), "editorial_reviews": table_count(con, "editorial_reviews")}
        after_status = status_snapshots(con)
    cluster_decision_counts = Counter(c["cluster_decision"] for c in clusters)
    cluster_type_counts = Counter(c["cluster_type"] for c in clusters)
    cluster_use_counts = Counter(c["cluster_use"] for c in clusters)
    changed_source_notes = before_counts["source_notes"] != after_counts["source_notes"]
    payload = {
        "run_id": args.run_id,
        "generated_at": utc_now(),
        "mode": MODE,
        "input_paths": {"downstream_manifest": rel(manifest_path), "sqlite_db": rel(db)},
        "model_profile": {
            "profile_name": profile["profile_name"],
            "provider": profile["provider"],
            "model": profile["model"],
            "bridge": profile["bridge"],
            "strict_json_required": profile["strict_json_required"],
            "weak_local_fallback_refused": profile["weak_local_fallback_refused"],
            "llm_used": False,
            "reasoning_status": "deterministic_report_only_clustering_no_llm_needed",
        },
        "report_only": True,
        "selected_manifest_items_count": len(selected),
        "excluded_manifest_items_count": len(excluded),
        "cluster_candidates_count": len(clusters),
        "singleton_cluster_count": sum(1 for c in clusters if c["singleton_cluster"]),
        "caveat_only_cluster_count": cluster_use_counts.get("caveat_only", 0),
        "support_cluster_count": cluster_type_counts.get("support_cluster", 0),
        "cluster_decision_counts": dict(cluster_decision_counts),
        "cluster_type_counts": dict(cluster_type_counts),
        "cluster_use_counts": dict(cluster_use_counts),
        "selected_manifest_items": selected,
        "excluded_manifest_items": excluded,
        "cluster_candidates": clusters,
        "failed_cluster_checks": failed,
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
        "safety_flags": {
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
            "cluster_candidates_are_claims": False,
        },
    }
    if payload["changed_source_notes"] or payload["claims_inserted"] or payload["editorial_reviews_inserted"] or payload["source_status_changed"] or payload["claim_status_changed"] or payload["editorial_status_changed"]:
        raise ClusterResearchObjectsError("forbidden DB/status delta detected during report-only clustering")
    return payload


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        f"# Run 18 research-object clusters — {payload['run_id']}", "",
        "## Summary", "",
        f"- Report-only: `{payload['report_only']}`",
        f"- Selected manifest items: `{payload['selected_manifest_items_count']}`",
        f"- Excluded manifest items: `{payload['excluded_manifest_items_count']}`",
        f"- Cluster candidates: `{payload['cluster_candidates_count']}`",
        f"- Singleton clusters: `{payload['singleton_cluster_count']}`",
        f"- Caveat-only clusters: `{payload['caveat_only_cluster_count']}`",
        "", "## Selected manifest items", "",
    ]
    for item in payload["selected_manifest_items"]:
        lines += [
            f"- `{item['manifest_item_id']}`",
            f"  - decision: `{item['downstream_manifest_decision']}`",
            f"  - source_review_id: `{item.get('source_review_id', '')}`",
            f"  - caveat_required: `{item.get('caveat_required')}`",
            "",
        ]
    lines += ["## Excluded manifest items", ""]
    for item in payload["excluded_manifest_items"]:
        lines += [
            f"- `{item.get('manifest_item_id', item.get('source_review_id', 'unknown'))}`",
            f"  - decision: `{item.get('downstream_manifest_decision', '')}`",
            f"  - disposition: `{item.get('closed_loop_disposition', '')}`",
            f"  - reason: `{item.get('excluded_reason', item.get('skip_reason', ''))}`",
            "",
        ]
    lines += ["## Cluster candidates", ""]
    for c in payload["cluster_candidates"]:
        lines += [
            f"- `{c['cluster_id']}` — {c['title']}",
            f"  - type/use/decision: `{c['cluster_type']}` / `{c['cluster_use']}` / `{c['cluster_decision']}`",
            f"  - singleton_cluster: `{c['singleton_cluster']}`",
            f"  - manifest_item_ids: `{', '.join(c['manifest_item_ids'])}`",
            f"  - thesis/caveat: {c['cluster_thesis_or_caveat']}",
            "",
        ]
    lines += [
        "## Why singleton caveat-only clustering is allowed", "",
        "Run 18 is a report-only pipeline-structure proof. With one downstream-eligible caveat-only manifest item, a singleton cluster is structurally valid but evidence-narrow. It preserves caveats and remains excluded from claiming, authoring, and publication.",
        "", "## Safety", "",
        "These cluster candidates are organizational/advisory only. They are not claims, not narrative packets, not chapter prose, and not author/publication approval. No DB writes or protected file changes are performed.",
        "", "## Limitations and residual risk", "",
        "The current cluster has one source-support object and must remain caveat-only. It should not be generalized beyond the persisted caveat text and limitations.",
        "", "## Recommendation for Run 19", "",
        "Run 19 may audit the Run 18 cluster report and, if still report-first, prepare a disabled-by-default cluster persistence design or a richer clustering pass when more eligible manifest items exist. It should not insert claims, create narrative packets, generate prose, or approve publication by default.",
    ]
    return "\n".join(lines) + "\n"


def write_reports(payload: dict[str, Any], output_dir: Path, suffix: str) -> dict[str, str]:
    out_dir = output_dir if output_dir.is_absolute() else ROOT / output_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{payload['run_id']}-research-object-clusters-{suffix}" if suffix else f"{payload['run_id']}-research-object-clusters"
    json_path = out_dir / f"{stem}.json"
    md_path = out_dir / f"{stem}.md"
    payload["output_paths"] = {"json": rel(json_path), "markdown": rel(md_path)}
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(payload), encoding="utf-8")
    return payload["output_paths"]


def parse_args(argv: list[str]) -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", default=RUN_ID_DEFAULT)
    ap.add_argument("--downstream-manifest", default=DEFAULT_MANIFEST)
    ap.add_argument("--output-dir", default="reports/editorial")
    ap.add_argument("--report-suffix", default="run18")
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        payload = build_payload(args)
        write_reports(payload, resolve(args.output_dir), args.report_suffix)
        print(json.dumps({
            "ok": True,
            "output_paths": payload["output_paths"],
            "selected_manifest_items_count": payload["selected_manifest_items_count"],
            "excluded_manifest_items_count": payload["excluded_manifest_items_count"],
            "cluster_candidates_count": payload["cluster_candidates_count"],
            "singleton_cluster_count": payload["singleton_cluster_count"],
            "caveat_only_cluster_count": payload["caveat_only_cluster_count"],
        }, sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
