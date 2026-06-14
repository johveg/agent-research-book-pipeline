#!/usr/bin/env python3
"""Run 14B candidate-source template builder.

Creates a template/worksheet for manually curated candidate sources. It performs
no live browsing and does not mutate SQLite, source registry, raw captures,
docs/book, schema, daily worker, statuses, claims, or editorial reviews.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from research_common import DB_PATH as DEFAULT_DB_PATH, ROOT as REPO_ROOT, sha256_text  # noqa: E402

MODE = "candidate_source_template"
ALLOWED_SOURCE_TYPES = [
    "primary_source",
    "official_report",
    "academic_paper",
    "reputable_industry_analysis",
    "reputable_news_or_magazine",
    "public_documentation",
    "public_original_interview",
]
DISALLOWED_SOURCE_TYPES = [
    "social_media_post",
    "seo_content_farm",
    "unsourced_blog_post",
    "scraped_repost",
    "ai_generated_summary",
    "vendor_marketing_page",
    "private_or_raw_capture",
    "unverifiable_screenshot",
    "unattributed_source",
]
SUPPORT_DIRECTIONS = ["supports", "partially_supports", "contradicts", "context_only", "unclear"]
EVIDENCE_STRENGTHS = ["strong", "moderate", "weak", "unsuitable"]
DEFAULT_RUN_ID = "citation-pipeline-test-20260612"


class TemplateError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def resolve(path: str) -> Path:
    p = Path(path)
    return p if p.is_absolute() else REPO_ROOT / p


def repo_relative(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def clean(value: Any, max_len: int = 800) -> str:
    text = " ".join(str(value or "").split())
    if len(text) > max_len:
        return text[: max_len - 1].rstrip() + "…"
    return text


def listify(value: Any, max_len: int = 260) -> list[str]:
    if isinstance(value, list):
        return [clean(v, max_len) for v in value if clean(v, max_len)]
    if isinstance(value, str) and value.strip():
        return [clean(value, max_len)]
    return []


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise TemplateError(f"missing input report: {path}")
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise TemplateError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(obj, dict):
        raise TemplateError(f"input JSON must be an object: {path}")
    return obj


def validate_safe_report(report: dict[str, Any]) -> None:
    if report.get("mode") not in {"corroboration_source_import", "corroboration_source_collection"}:
        raise TemplateError("input mode must be corroboration_source_import or corroboration_source_collection")
    checks = {
        "changed_db": False,
        "changed_source_registry": False,
        "changed_raw_captures": False,
        "changed_docs_book": False,
        "changed_schema": False,
        "changed_daily_worker": False,
        "claims_inserted": 0,
        "editorial_reviews_inserted": 0,
        "source_status_changed": False,
        "claim_status_changed": False,
        "editorial_status_changed": False,
    }
    for key, expected in checks.items():
        if report.get(key) not in (expected, None):
            raise TemplateError(f"input report unsafe: {key}={report.get(key)!r}")
    if not isinstance(report.get("selected_items"), list):
        raise TemplateError("input report missing selected_items list")


def selected_unresolved(report: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for item in report.get("selected_items", []):
        if not isinstance(item, dict):
            continue
        if item.get("recommended_next_stage") == "run_additional_source_collection":
            out.append(item)
    return out


def skipped_items(report: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for item in report.get("skipped_items", []):
        if not isinstance(item, dict):
            continue
        out.append({
            "item_id": item.get("item_id", ""),
            "source_review_id": item.get("source_review_id", ""),
            "source_id": item.get("source_id", ""),
            "recommended_next_stage": item.get("recommended_next_stage", ""),
            "skip_reason": item.get("skip_reason", "not_unresolved_source_collection_item"),
        })
    return out


def candidate_schema() -> dict[str, Any]:
    return {
        "required_fields": [
            "source_review_id",
            "item_id",
            "url",
            "title",
            "publisher",
            "publication_date",
            "author",
            "source_type",
            "access_type",
            "candidate_relevance",
            "support_direction",
            "evidence_strength",
            "reason_for_inclusion",
            "limitations",
            "safe_summary",
            "raw_content_stored",
        ],
        "source_type_allowed_values": ALLOWED_SOURCE_TYPES,
        "support_direction_allowed_values": SUPPORT_DIRECTIONS,
        "evidence_strength_allowed_values": EVIDENCE_STRENGTHS,
        "access_type_required_value": "public",
        "raw_content_stored_required_value": False,
        "max_candidates_per_item": 5,
        "url_requirement": "Use a stable public http(s) URL. Do not use private accounts, cookies, tokens, paywall-only material, screenshots, raw captures, or generated summaries.",
    }


def example_object(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_review_id": item.get("source_review_id", ""),
        "item_id": item.get("item_id", ""),
        "url": "https://example.invalid/replace-with-real-public-source",
        "title": "PLACEHOLDER: replace with real public source title",
        "publisher": "PLACEHOLDER: replace with real publisher",
        "publication_date": "PLACEHOLDER: YYYY-MM-DD or null",
        "author": "PLACEHOLDER: author name or null",
        "source_type": "official_report",
        "access_type": "public",
        "candidate_relevance": "PLACEHOLDER: why this source may corroborate, contradict, or contextualize the item",
        "support_direction": "unclear",
        "evidence_strength": "weak",
        "reason_for_inclusion": "PLACEHOLDER: why the curator included this candidate",
        "limitations": "PLACEHOLDER: limitations, caveats, date/source-type constraints, uncertainty",
        "safe_summary": "PLACEHOLDER: short summary only; do not paste long excerpts or raw page content",
        "raw_content_stored": False,
    }


def template_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_review_id": item.get("source_review_id", ""),
        "item_id": item.get("item_id", ""),
        "original_source_id": item.get("source_id", ""),
        "original_statement": clean(item.get("original_statement"), 1200),
        "what_needs_corroboration": clean(item.get("what_needs_corroboration"), 1200),
        "why_current_evidence_is_insufficient": clean(item.get("why_current_evidence_is_insufficient") or item.get("collection_limitations") or item.get("preliminary_collection_assessment"), 1200),
        "suggested_search_queries": listify(item.get("suggested_search_queries")),
        "required_source_types": listify(item.get("required_source_types")),
        "disallowed_source_types": DISALLOWED_SOURCE_TYPES,
        "max_candidates_per_item": 5,
        "candidate_sources": [],
        "changed_db": False,
        "changed_source_registry": False,
        "changed_raw_captures": False,
        "changed_docs_book": False,
        "changed_schema": False,
        "changed_daily_worker": False,
        "claims_inserted": 0,
        "editorial_reviews_inserted": 0,
        "source_status_changed": False,
        "claim_status_changed": False,
        "editorial_status_changed": False,
        "curation_instructions": [
            "Add at most five bounded candidate source objects for this item.",
            "Use only stable public URLs and canonical pages when possible.",
            "Do not paste raw page content or long excerpts; use safe_summary only.",
            "Set raw_content_stored=false and access_type=public for every candidate.",
            "Candidate sources are not validated support, source-registry entries, claims, or publication approval.",
        ],
        "validation_schema": candidate_schema(),
        "example_candidate_source_object": example_object(item),
        "advisory_only": True,
        "author_allowed": False,
        "publication_approved": False,
    }


def build_template(run_id: str, report: dict[str, Any], input_paths: dict[str, str], template_path: str, expected_path: str) -> tuple[dict[str, Any], dict[str, Any]]:
    unresolved = selected_unresolved(report)
    skipped = skipped_items(report)
    items = [template_item(item) for item in unresolved]
    template = {
        "run_id": run_id,
        "generated_at": utc_now(),
        "template_only": True,
        "ready_for_import": False,
        "input_paths": input_paths,
        "unresolved_items_count": len(items),
        "skipped_items_count": len(skipped),
        "template_path": template_path,
        "expected_candidate_json_path": expected_path,
        "max_candidates_per_item": 5,
        "allowed_source_type_values": ALLOWED_SOURCE_TYPES,
        "disallowed_source_type_values": DISALLOWED_SOURCE_TYPES,
        "allowed_support_direction_values": SUPPORT_DIRECTIONS,
        "allowed_evidence_strength_values": EVIDENCE_STRENGTHS,
        "candidate_source_schema": candidate_schema(),
        "items": items,
        "skipped_items": skipped,
        "candidate_sources": [],
        "curation_instructions": [
            "Fill candidate_sources either at the top level or inside each item, then set ready_for_import=true only after real bounded public candidates are added.",
            "Do not invent URLs. Do not perform uncontrolled browsing. Prefer primary/official/academic/reputable public sources.",
            "Do not include social media, SEO farms, unsourced posts, AI summaries, private/raw captures, screenshots, or unattributed material as standalone corroboration.",
            "After filling, rerun Run 14A with --candidate-sources-json pointing to the expected candidate JSON path.",
        ],
        "safety_flags": safety_flags(),
    }
    report_payload = {
        "run_id": run_id,
        "generated_at": utc_now(),
        "mode": MODE,
        "input_paths": input_paths,
        "unresolved_items_count": len(items),
        "skipped_items_count": len(skipped),
        "template_path": template_path,
        "expected_candidate_json_path": expected_path,
        "template_only": True,
        "ready_for_import": False,
        "changed_db": False,
        "changed_source_registry": False,
        "changed_raw_captures": False,
        "changed_docs_book": False,
        "changed_schema": False,
        "changed_daily_worker": False,
        "claims_inserted": 0,
        "editorial_reviews_inserted": 0,
        "source_status_changed": False,
        "claim_status_changed": False,
        "editorial_status_changed": False,
        "unresolved_items": items,
        "skipped_items": skipped,
        "safety_flags": safety_flags(),
        "next_step": "Manually add bounded public candidate sources, then rerun Run 14A. Do not proceed to source-support re-review until candidates are accepted.",
    }
    return template, report_payload


def safety_flags() -> dict[str, bool]:
    return {
        "template_only": True,
        "advisory_only": True,
        "author_allowed": False,
        "publication_approved": False,
        "raw_content_stored": False,
        "no_live_browsing": True,
        "no_invented_urls": True,
        "no_db_writes": True,
        "no_source_registry_writes": True,
        "no_raw_capture_writes": True,
        "no_claim_insertion": True,
        "no_editorial_review_insertion": True,
        "no_status_changes": True,
        "no_docs_book_changes": True,
        "no_schema_changes": True,
        "no_daily_worker_changes": True,
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# Candidate-source template — {report['run_id']}",
        "",
        "## Summary",
        "",
        f"- unresolved items: {report['unresolved_items_count']}",
        f"- skipped items: {report['skipped_items_count']}",
        f"- template only: {str(report['template_only']).lower()}",
        f"- ready for import: {str(report['ready_for_import']).lower()}",
        f"- template path: `{report['template_path']}`",
        f"- expected candidate JSON path: `{report['expected_candidate_json_path']}`",
        "",
        "## Unresolved items",
        "",
    ]
    for item in report["unresolved_items"]:
        lines += [
            f"### {item['source_review_id']}",
            "",
            f"- item_id: `{item['item_id']}`",
            f"- source_id: `{item['original_source_id']}`",
            f"- what needs corroboration: {item['what_needs_corroboration'] or '(not available)'}",
            f"- why current evidence is insufficient: {item['why_current_evidence_is_insufficient'] or '(not available)'}",
            "- suggested search queries:",
        ]
        if item["suggested_search_queries"]:
            lines += [f"  - {q}" for q in item["suggested_search_queries"]]
        else:
            lines.append("  - (not available)")
        lines.append("- required source types:")
        if item["required_source_types"]:
            lines += [f"  - {q}" for q in item["required_source_types"]]
        else:
            lines.append("  - (not available)")
        lines.append("")
    lines += [
        "## How to fill the candidate JSON",
        "",
        "1. Open the template JSON and add at most five public candidate source objects per unresolved item.",
        "2. Use only the allowed source_type/support_direction/evidence_strength values listed in the schema.",
        "3. Keep `access_type` as `public` and `raw_content_stored` as `false`.",
        "4. Do not paste full page text, cookies, credentials, screenshots, raw captures, or private-account material.",
        "5. Set `ready_for_import` to `true` only after real curated candidates are added.",
        "",
        "## Rerun Run 14A after candidates are added",
        "",
        "```bash",
        "python3 scripts/collect_corroboration_sources.py \\",
        "  --run-id citation-pipeline-test-20260612 \\",
        "  --output-dir reports/editorial \\",
        "  --corroboration-research-report reports/editorial/citation-pipeline-test-20260612-corroboration-source-collection-run13.json \\",
        "  --candidate-sources-json reports/editorial/citation-pipeline-test-20260612-curated-candidate-sources-run14.json \\",
        "  --require-candidate-sources \\",
        "  --report-suffix run14",
        "```",
        "",
        "## Safety confirmations",
        "",
        "- no live browsing performed",
        "- no URLs invented",
        "- no DB writes",
        "- no source registry writes",
        "- no raw captures",
        "- no docs/book, schema, or daily-worker changes",
        "- no claims/editorial_reviews/status changes",
        "- no author or publication approval",
        "",
        "## Recommended next step",
        "",
        "Manually curate bounded public candidate sources into the expected candidate JSON, rerun Run 14A, and proceed to GPT-5.5 source-support re-review only after candidates are accepted.",
        "",
    ]
    return "\n".join(lines)


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build Run 14B curated candidate-source template")
    p.add_argument("--run-id", default=DEFAULT_RUN_ID)
    p.add_argument("--output-dir", default="reports/editorial")
    p.add_argument("--source-import-report", default="reports/editorial/citation-pipeline-test-20260612-corroboration-source-import-run14.json")
    p.add_argument("--source-collection-report", default="reports/editorial/citation-pipeline-test-20260612-corroboration-source-collection-run13.json")
    p.add_argument("--corroboration-research-report", default="reports/editorial/citation-pipeline-test-20260612-corroboration-research-run12.json")
    p.add_argument("--source-support-review-report", default="reports/editorial/citation-pipeline-test-20260612-source-support-review-run10.json")
    p.add_argument("--filing-novelty-report", default="reports/editorial/citation-pipeline-test-20260612-filing-novelty-evaluation-run9.json")
    p.add_argument("--editor-packet-report", default="reports/editorial/citation-pipeline-test-20260612-editor-review-packet-run8.json")
    p.add_argument("--quality-gate-report", default="reports/editorial/citation-pipeline-test-20260612-quality-gate-run7-full.json")
    p.add_argument("--source-card-report", default="reports/editorial/citation-pipeline-test-20260612-source-card-drafts-high-reasoning-run7.json")
    p.add_argument("--semantic-object-report", default="reports/editorial/citation-pipeline-test-20260612-semantic-object-drafts-high-reasoning-run7.json")
    p.add_argument("--candidate-selection-report", default="reports/editorial/citation-pipeline-test-20260612-reasoning-candidate-selection.json")
    p.add_argument("--template-path", default="")
    p.add_argument("--expected-candidate-json-path", default="")
    p.add_argument("--create-expected-candidate-json", action="store_true", default=True)
    p.add_argument("--no-create-expected-candidate-json", action="store_false", dest="create_expected_candidate_json")
    p.add_argument("--report-suffix", default="")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        source_import_path = resolve(args.source_import_report)
        report = load_json(source_import_path)
        validate_safe_report(report)
        output_dir = resolve(args.output_dir)
        run_id = args.run_id if args.run_id != "latest" else report.get("run_id", DEFAULT_RUN_ID)
        template_path = resolve(args.template_path) if args.template_path else output_dir / f"{run_id}-curated-candidate-sources-run14-template.json"
        expected_path = resolve(args.expected_candidate_json_path) if args.expected_candidate_json_path else output_dir / f"{run_id}-curated-candidate-sources-run14.json"
        input_paths = {
            "source_import_report": repo_relative(source_import_path),
            "source_collection_report": repo_relative(resolve(args.source_collection_report)),
            "corroboration_research_report": repo_relative(resolve(args.corroboration_research_report)),
            "source_support_review_report": repo_relative(resolve(args.source_support_review_report)),
            "filing_novelty_report": repo_relative(resolve(args.filing_novelty_report)),
            "editor_packet_report": repo_relative(resolve(args.editor_packet_report)),
            "quality_gate_report": repo_relative(resolve(args.quality_gate_report)),
            "source_card_report": repo_relative(resolve(args.source_card_report)),
            "semantic_object_report": repo_relative(resolve(args.semantic_object_report)),
            "candidate_selection_report": repo_relative(resolve(args.candidate_selection_report)),
        }
        template, report_payload = build_template(run_id, report, input_paths, repo_relative(template_path), repo_relative(expected_path))
        write_json(template_path, template)
        template_md = template_path.with_suffix(".md")
        # The requested template markdown path is distinct from the run report markdown.
        # It intentionally contains instructions only and no candidate URLs beyond placeholder text.
        template_md.write_text(markdown(report_payload), encoding="utf-8")
        if args.create_expected_candidate_json:
            expected = {k: template[k] for k in template if k not in {"items"}}
            expected_items = json.loads(json.dumps(template["items"]))
            for item in expected_items:
                example = item.get("example_candidate_source_object", {})
                if isinstance(example, dict):
                    example["url"] = "PLACEHOLDER_PUBLIC_URL_REPLACE_BEFORE_IMPORT"
            expected["items"] = expected_items
            expected["candidate_sources"] = []
            expected["template_only"] = True
            expected["ready_for_import"] = False
            write_json(expected_path, expected)
        stem = f"{run_id}-curated-candidate-sources-run14-template-{args.report_suffix}" if args.report_suffix else f"{run_id}-curated-candidate-sources-run14-template"
        report_json = output_dir / f"{stem}.json"
        report_md = output_dir / f"{stem}.md"
        write_json(report_json, report_payload)
        report_md.write_text(markdown(report_payload), encoding="utf-8")
        print(json.dumps({
            "status": "ok",
            "template_path": repo_relative(template_path),
            "expected_candidate_json_path": repo_relative(expected_path) if args.create_expected_candidate_json else "",
            "report_json": repo_relative(report_json),
            "report_markdown": repo_relative(report_md),
            "template_markdown": repo_relative(template_md),
            "unresolved_items_count": report_payload["unresolved_items_count"],
            "skipped_items_count": report_payload["skipped_items_count"],
            "ready_for_import": False,
        }, indent=2, sort_keys=True))
        return 0
    except TemplateError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
