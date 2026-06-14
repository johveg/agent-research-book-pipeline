# Run 14B candidate-source template evidence map — 20260613

## Scope

Run 14B implemented a template/worksheet stage for manually curated candidate sources for unresolved corroboration items.

Title: **Create curated candidate-source JSON template for unresolved corroboration items**

This run is template/report-only. It performs no live browsing and invents no URLs.

## Inputs

Primary input:

- `reports/editorial/citation-pipeline-test-20260612-corroboration-source-import-run14.json`

Additional context inputs:

- `reports/editorial/citation-pipeline-test-20260612-corroboration-source-collection-run13.json`
- `reports/editorial/citation-pipeline-test-20260612-corroboration-research-run12.json`
- `reports/editorial/citation-pipeline-test-20260612-source-support-review-run10.json`
- `reports/editorial/citation-pipeline-test-20260612-filing-novelty-evaluation-run9.json`
- `reports/editorial/citation-pipeline-test-20260612-editor-review-packet-run8.json`
- `reports/editorial/citation-pipeline-test-20260612-quality-gate-run7-full.json`
- `reports/editorial/citation-pipeline-test-20260612-source-card-drafts-high-reasoning-run7.json`
- `reports/editorial/citation-pipeline-test-20260612-semantic-object-drafts-high-reasoning-run7.json`
- `reports/editorial/citation-pipeline-test-20260612-reasoning-candidate-selection.json`

## Outputs

Created:

- `scripts/build_candidate_source_template.py`
- `tests/test_build_candidate_source_template.py`
- `reports/editorial/citation-pipeline-test-20260612-curated-candidate-sources-run14-template.json`
- `reports/editorial/citation-pipeline-test-20260612-curated-candidate-sources-run14-template.md`
- `reports/editorial/citation-pipeline-test-20260612-curated-candidate-sources-run14-template-run14b.json`
- `reports/editorial/citation-pipeline-test-20260612-curated-candidate-sources-run14-template-run14b.md`
- `reports/editorial/citation-pipeline-test-20260612-curated-candidate-sources-run14.json`
- `reports/architecture/run14b-candidate-source-template-evidence-map-20260613.md`

## Template status

The expected candidate JSON was created as a template-only worksheet:

- `template_only`: `true`
- `ready_for_import`: `false`
- top-level `candidate_sources`: `[]`
- unresolved items: `2`
- skipped items: `1`
- candidate sources count: `0`

The expected candidate JSON path is:

- `reports/editorial/citation-pipeline-test-20260612-curated-candidate-sources-run14.json`

It contains placeholders/instructions only; no accepted/real candidate URLs were added.

## Included unresolved items

Run 14B included only the two unresolved Run 14A/Run 13 source-review items:

1. `source_review_12c73455aa1816e5df8c`
   - item: `corrob_item_6e923bab58a413137532`
   - source: `src_6d7b6d80cda4e784877d`

2. `source_review_5baf68d86960f91b97ac`
   - item: `corrob_item_4039b66b55f0c200763a`
   - source: `src_6d7b6d80cda4e784877d`

## Skipped item

The skipped item remained excluded:

- `source_review_e20631e18093139a8bc2`
  - reason: `needs_editor_review_not_source_collection`

## Template schema

The template includes:

- candidate schema and required fields
- allowed source types:
  - `primary_source`
  - `official_report`
  - `academic_paper`
  - `reputable_industry_analysis`
  - `reputable_news_or_magazine`
  - `public_documentation`
  - `public_original_interview`
- disallowed source types:
  - `social_media_post`
  - `seo_content_farm`
  - `unsourced_blog_post`
  - `scraped_repost`
  - `ai_generated_summary`
  - `vendor_marketing_page`
  - `private_or_raw_capture`
  - `unverifiable_screenshot`
  - `unattributed_source`
- allowed support directions:
  - `supports`
  - `partially_supports`
  - `contradicts`
  - `context_only`
  - `unclear`
- allowed evidence strengths:
  - `strong`
  - `moderate`
  - `weak`
  - `unsuitable`
- max candidates per item: `5`
- `example_candidate_source_object` with placeholder-only values
- curation instructions and rerun instructions

## Commands run

Preflight:

```bash
git status --short && test -f reports/editorial/citation-pipeline-test-20260612-curated-candidate-sources-run14.json; echo EXPECTED_CANDIDATE_JSON_EXISTS=$?
```

Read-only report and DB/protected baseline inspection:

```bash
python3 - <<'PY'
# read-only report summary and SQLite/status/hash snapshot
PY
```

Targeted TDD failure before implementation:

```bash
.venv/bin/python -m pytest -q tests/test_build_candidate_source_template.py
```

Targeted tests after implementation:

```bash
.venv/bin/python -m pytest -q tests/test_build_candidate_source_template.py
```

Run 14B generation:

```bash
python3 scripts/build_candidate_source_template.py \
  --run-id citation-pipeline-test-20260612 \
  --output-dir reports/editorial \
  --source-import-report reports/editorial/citation-pipeline-test-20260612-corroboration-source-import-run14.json \
  --source-collection-report reports/editorial/citation-pipeline-test-20260612-corroboration-source-collection-run13.json \
  --corroboration-research-report reports/editorial/citation-pipeline-test-20260612-corroboration-research-run12.json \
  --source-support-review-report reports/editorial/citation-pipeline-test-20260612-source-support-review-run10.json \
  --filing-novelty-report reports/editorial/citation-pipeline-test-20260612-filing-novelty-evaluation-run9.json \
  --editor-packet-report reports/editorial/citation-pipeline-test-20260612-editor-review-packet-run8.json \
  --quality-gate-report reports/editorial/citation-pipeline-test-20260612-quality-gate-run7-full.json \
  --source-card-report reports/editorial/citation-pipeline-test-20260612-source-card-drafts-high-reasoning-run7.json \
  --semantic-object-report reports/editorial/citation-pipeline-test-20260612-semantic-object-drafts-high-reasoning-run7.json \
  --candidate-selection-report reports/editorial/citation-pipeline-test-20260612-reasoning-candidate-selection.json \
  --create-expected-candidate-json \
  --report-suffix run14b
```

Verification:

```bash
.venv/bin/python -m pytest -q tests/test_build_candidate_source_template.py tests/test_collect_corroboration_sources.py
.venv/bin/python -m pytest -q
python3 scripts/verify_book_workspace.py
python3 scripts/verify_editorial_roles.py
python3 scripts/verify_book_citations.py
.venv/bin/python -m mkdocs build --strict
```

Generated protected artifact restore:

```bash
git restore data/source_registry.json docs/book docs/entities docs/research/claims.md
rm -f docs/entities/boris-cherny.md
```

Final read-only status/snapshot:

```bash
git status --short
python3 - <<'PY'
# final read-only DB/source-registry/raw/schema/daily-worker/template snapshot
PY
```

## Verification results

Targeted Run 14B tests:

```text
2 passed in 0.34s
```

Run 14B + Run 14A source-collection/import tests:

```text
6 passed in 2.64s
```

Full test suite:

```text
57 passed in 13.24s
```

Workspace/editorial/citation/MkDocs:

- `scripts/verify_book_workspace.py`: `status=ok`
- `scripts/verify_editorial_roles.py`: `status=ok`
- `scripts/verify_book_citations.py`: `status=ok`
- `.venv/bin/python -m mkdocs build --strict`: exit `0`

MkDocs emitted the existing Material for MkDocs warning and existing nav warnings, but strict build completed successfully.

## Final protected snapshot

```json
{
  "sources_count": 945,
  "source_notes_count": 284,
  "claims_count": 146,
  "editorial_reviews_count": 10,
  "sources_status_hash": "bde40f350904114e864f418a59b9eb8636ae6dc598d5a73d8422ef280cb446ba",
  "claims_status_hash": "2c2829622ff2988c13bc3c3f89c71dccd6139c1ec8ee06e28dc2f5e218d8df1c",
  "editorial_reviews_hash": "ed4c9b3e8704af05cdd641320bece13b8c57a9762d4a8449f6af10314585d087",
  "data/source_registry.json_sha256": "b9dba2f5273a28ead82b05469381e675e151a03538b3de54444c2e77ec664fca",
  "data/schema.sql_sha256": "c2fe112ae800db4bcc2389c15306dcc9bcacdae24963c885191e0e433c134ade",
  "scripts/daily_book_worker.py_sha256": "4e5933e94f60f1233862b1f78055307149b9eb880f0c31ad0203d5755ed7490d",
  "raw_path_exists": false,
  "raw_file_count": 0
}
```

## Safety confirmation

Run 14B was template/report-only.

Confirmed:

- no live browsing
- no invented URLs
- no `.var/book.sqlite` mutation
- no source_notes writes
- no claims inserted
- no editorial_reviews inserted
- no source/claim/editorial status changes
- no source_registry writes
- no raw captures
- no raw page content stored
- no docs/book changes after restore
- no schema changes
- no daily-worker changes
- no narrative packets
- no chapter prose
- no author approval
- no publication approval

## Rerun command for Run 14A after manual curation

After adding real bounded public candidate sources to:

- `reports/editorial/citation-pipeline-test-20260612-curated-candidate-sources-run14.json`

run:

```bash
python3 scripts/collect_corroboration_sources.py \
  --run-id citation-pipeline-test-20260612 \
  --output-dir reports/editorial \
  --corroboration-research-report reports/editorial/citation-pipeline-test-20260612-corroboration-source-collection-run13.json \
  --source-support-review-report reports/editorial/citation-pipeline-test-20260612-source-support-review-run10.json \
  --filing-novelty-report reports/editorial/citation-pipeline-test-20260612-filing-novelty-evaluation-run9.json \
  --editor-packet-report reports/editorial/citation-pipeline-test-20260612-editor-review-packet-run8.json \
  --quality-gate-report reports/editorial/citation-pipeline-test-20260612-quality-gate-run7-full.json \
  --source-card-report reports/editorial/citation-pipeline-test-20260612-source-card-drafts-high-reasoning-run7.json \
  --semantic-object-report reports/editorial/citation-pipeline-test-20260612-semantic-object-drafts-high-reasoning-run7.json \
  --candidate-selection-report reports/editorial/citation-pipeline-test-20260612-reasoning-candidate-selection.json \
  --candidate-sources-json reports/editorial/citation-pipeline-test-20260612-curated-candidate-sources-run14.json \
  --require-candidate-sources \
  --report-suffix run14
```

## Recommended next step

Manually curate bounded public candidate sources into the expected candidate JSON, rerun Run 14A, and proceed to GPT-5.5 source-support re-review only after candidates are accepted.
