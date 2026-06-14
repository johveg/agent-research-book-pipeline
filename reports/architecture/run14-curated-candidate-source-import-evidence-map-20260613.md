# Run 14A curated candidate-source import evidence map — 20260613

## Scope

Run 14A implemented a curated candidate-source import mode for unresolved corroboration items from Run 13.

Title: **Curated candidate-source import for unresolved corroboration items**

Primary input:

- `reports/editorial/citation-pipeline-test-20260612-corroboration-source-collection-run13.json`

Default curated candidate-source input expected:

- `reports/editorial/citation-pipeline-test-20260612-curated-candidate-sources-run14.json`

Output reports:

- `reports/editorial/citation-pipeline-test-20260612-corroboration-source-import-run14.json`
- `reports/editorial/citation-pipeline-test-20260612-corroboration-source-import-run14.md`

## Outcome

The curated candidate-source JSON was **not present**. Run 14A therefore failed closed and produced a clear report rather than inventing URLs or performing uncontrolled browsing.

Observed output summary:

```json
{
  "candidate_json_present": false,
  "candidate_sources_json": "reports/editorial/citation-pipeline-test-20260612-curated-candidate-sources-run14.json",
  "mode": "corroboration_source_import",
  "collection_method": "curated_candidate_json_missing",
  "source_collection_executed": false,
  "selected_items_count": 2,
  "skipped_items_count": 1,
  "candidate_sources_submitted_count": 0,
  "candidate_sources_accepted_count": 0,
  "candidate_sources_rejected_count": 0,
  "duplicate_url_count": 0,
  "preliminary_collection_assessment_counts": {
    "needs_more_collection": 2
  },
  "recommended_next_stage_counts": {
    "run_additional_source_collection": 2
  }
}
```

The report also records a fail-closed missing-input reason:

```json
[
  {
    "path": "reports/editorial/citation-pipeline-test-20260612-curated-candidate-sources-run14.json",
    "reason": "curated_candidate_json_missing"
  }
]
```

## Selected items

Run 14A selected the two unresolved Run 13 items:

1. `source_review_12c73455aa1816e5df8c`
   - item: `corrob_item_6e923bab58a413137532`
   - source: `src_6d7b6d80cda4e784877d`

2. `source_review_5baf68d86960f91b97ac`
   - item: `corrob_item_4039b66b55f0c200763a`
   - source: `src_6d7b6d80cda4e784877d`

## Skipped items

Run 14A preserved the Run 13 skip:

- `source_review_e20631e18093139a8bc2`
  - reason: `needs_editor_review_not_source_collection`

## Implementation evidence

Updated:

- `scripts/collect_corroboration_sources.py`
  - added Run 14A import mode: `corroboration_source_import`
  - added default candidate JSON path
  - added `--require-candidate-sources`
  - added fail-closed missing-candidate report generation
  - accepts Run 13 collection reports as primary input
  - preserves Run 13 skipped items in Run 14A output
  - normalizes allowed source types to canonical enum values
  - validates candidate URL shape, title, publisher, access type, raw-content flag, source type, support direction, and evidence strength
  - detects duplicate URLs per item
  - detects same URL reused across selected items
  - enforces maximum five candidate sources per item
  - generates deterministic `candidate_source_id` from normalized URL and item/source-review context

Updated:

- `tests/test_collect_corroboration_sources.py`
  - missing candidate JSON fails closed
  - Run 14A accepts candidates only for selected unresolved items
  - `needs_editor_review` item rejects candidate import
  - unknown item/source-review IDs reject candidate import
  - maximum five candidates per item enforced
  - deterministic candidate IDs preserved by existing schema path
  - duplicate URLs detected
  - disallowed source types rejected
  - `raw_content_stored=true` rejected
  - non-public access type rejected
  - invalid URL shape rejected
  - DB/source-registry/docs/schema/daily-worker safety verified

## Commands run

Preflight:

```bash
git status --short && test -f reports/editorial/citation-pipeline-test-20260612-curated-candidate-sources-run14.json; echo CANDIDATE_JSON_EXISTS=$?
```

Run 13/report and DB/protected baseline inspection:

```bash
python3 - <<'PY'
# read-only report summary and SQLite/status/hash snapshot
PY
```

Targeted tests after implementation:

```bash
.venv/bin/python -m pytest -q tests/test_collect_corroboration_sources.py
```

Run 14A fail-closed command:

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
  --require-candidate-sources \
  --report-suffix run14
```

The script exited `2` intentionally for the fail-closed missing candidate JSON condition; the wrapper verified that exit code as expected.

Full verification:

```bash
.venv/bin/python -m pytest -q tests/test_collect_corroboration_sources.py
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

Final status and snapshot:

```bash
git status --short
python3 - <<'PY'
# final read-only DB/source-registry/raw/schema/daily-worker snapshot
PY
```

## Verification results

Targeted Run 14A tests:

```text
4 passed in 2.25s
```

Full test suite:

```text
55 passed in 12.82s
```

Workspace/editorial/citation/MkDocs:

- `scripts/verify_book_workspace.py`: `status=ok`
- `scripts/verify_editorial_roles.py`: `status=ok`
- `scripts/verify_book_citations.py`: `status=ok`
- `mkdocs build --strict`: exit `0`

MkDocs emitted the existing Material for MkDocs warning and existing nav warnings, but strict build completed successfully.

## Final DB/protected snapshot

```json
{
  "claims_count": 146,
  "claims_status_hash": "2c2829622ff2988c13bc3c3f89c71dccd6139c1ec8ee06e28dc2f5e218d8df1c",
  "data/schema.sql_sha256": "c2fe112ae800db4bcc2389c15306dcc9bcacdae24963c885191e0e433c134ade",
  "data/source_registry.json_sha256": "b9dba2f5273a28ead82b05469381e675e151a03538b3de54444c2e77ec664fca",
  "editorial_reviews_count": 10,
  "editorial_reviews_hash": "ed4c9b3e8704af05cdd641320bece13b8c57a9762d4a8449f6af10314585d087",
  "raw_file_count": 0,
  "raw_path_exists": false,
  "scripts/daily_book_worker.py_sha256": "4e5933e94f60f1233862b1f78055307149b9eb880f0c31ad0203d5755ed7490d",
  "source_notes_count": 284,
  "sources_count": 945,
  "sources_status_hash": "bde40f350904114e864f418a59b9eb8636ae6dc598d5a73d8422ef280cb446ba"
}
```

## Safety confirmation

Run 14A remained report-only.

Confirmed:

- `.var/book.sqlite` not mutated
- `source_notes` unchanged
- `claims` unchanged
- `editorial_reviews` unchanged
- source statuses unchanged
- claim statuses unchanged
- editorial-review statuses unchanged
- `data/source_registry.json` unchanged
- raw captures unchanged / no raw capture path exists
- no raw page content stored
- `docs/book/` unchanged after restore
- `data/schema.sql` unchanged
- `scripts/daily_book_worker.py` unchanged
- no narrative packets created
- no chapter prose generated
- no author approval
- no publication approval
- no candidate links treated as source-registry entries
- no candidate sources treated as validated support

## Recommended next step

Run 15 should **not** perform source-support re-review yet because Run 14A accepted zero candidate sources.

Recommended next action:

- Create/provide `reports/editorial/citation-pipeline-test-20260612-curated-candidate-sources-run14.json` with bounded public candidate sources for the two selected items, then rerun Run 14A.

Only after candidate sources are accepted should a later Run 15 perform GPT-5.5 source-support re-review.
