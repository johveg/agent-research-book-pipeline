# Candidate-source template — citation-pipeline-test-20260612

## Summary

- unresolved items: 2
- skipped items: 1
- template only: true
- ready for import: false
- template path: `reports/editorial/citation-pipeline-test-20260612-curated-candidate-sources-run14-template.json`
- expected candidate JSON path: `reports/editorial/citation-pipeline-test-20260612-curated-candidate-sources-run14.json`

## Unresolved items

### source_review_12c73455aa1816e5df8c

- item_id: `corrob_item_6e923bab58a413137532`
- source_id: `src_6d7b6d80cda4e784877d`
- what needs corroboration: (not available)
- why current evidence is insufficient: (not available)
- suggested search queries:
  - (not available)
- required source types:
  - (not available)

### source_review_5baf68d86960f91b97ac

- item_id: `corrob_item_4039b66b55f0c200763a`
- source_id: `src_6d7b6d80cda4e784877d`
- what needs corroboration: (not available)
- why current evidence is insufficient: (not available)
- suggested search queries:
  - (not available)
- required source types:
  - (not available)

## How to fill the candidate JSON

1. Open the template JSON and add at most five public candidate source objects per unresolved item.
2. Use only the allowed source_type/support_direction/evidence_strength values listed in the schema.
3. Keep `access_type` as `public` and `raw_content_stored` as `false`.
4. Do not paste full page text, cookies, credentials, screenshots, raw captures, or private-account material.
5. Set `ready_for_import` to `true` only after real curated candidates are added.

## Rerun Run 14A after candidates are added

```bash
python3 scripts/collect_corroboration_sources.py \
  --run-id citation-pipeline-test-20260612 \
  --output-dir reports/editorial \
  --corroboration-research-report reports/editorial/citation-pipeline-test-20260612-corroboration-source-collection-run13.json \
  --candidate-sources-json reports/editorial/citation-pipeline-test-20260612-curated-candidate-sources-run14.json \
  --require-candidate-sources \
  --report-suffix run14
```

## Safety confirmations

- no live browsing performed
- no URLs invented
- no DB writes
- no source registry writes
- no raw captures
- no docs/book, schema, or daily-worker changes
- no claims/editorial_reviews/status changes
- no author or publication approval

## Recommended next step

Manually curate bounded public candidate sources into the expected candidate JSON, rerun Run 14A, and proceed to GPT-5.5 source-support re-review only after candidates are accepted.
