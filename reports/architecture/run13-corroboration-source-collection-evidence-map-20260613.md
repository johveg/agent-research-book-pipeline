# Run 13 corroboration source collection evidence map — 20260613

## Scope

Run 13 implemented a controlled, report-only external source collection layer for Run 12 items with:

- `recommended_next_stage == "run_additional_source_collection"`
- `evidence_use_decision == "needs_more_sources"`
- `corroboration_status == "insufficient_evidence"`

The repository did not have a safe live web/source-collection tool wired into this pipeline, so Run 13 did **not** improvise uncontrolled browsing. It produced an exact collection plan using Run 12 search queries and source-type requirements, with `source_collection_status=collection_not_executed_tooling_unavailable`.

## Files changed

Added:

- `scripts/collect_corroboration_sources.py`
- `tests/test_collect_corroboration_sources.py`
- `reports/editorial/citation-pipeline-test-20260612-corroboration-source-collection-run13.json`
- `reports/editorial/citation-pipeline-test-20260612-corroboration-source-collection-run13.md`
- `reports/architecture/run13-corroboration-source-collection-evidence-map-20260613.md`

## Files intentionally not changed

- `.var/book.sqlite`
- `data/source_registry.json`
- raw captures (`data/raw`, `raw`, `captures`)
- `docs/book/`
- `data/schema.sql`
- `scripts/daily_book_worker.py`
- source status, claim status, editorial status
- `claims` table
- `editorial_reviews` table
- narrative packet outputs
- chapter prose
- author/publication approval paths

## Current git status before/after

Preflight branch/commit:

- branch: `main`
- short HEAD: `b103efb`

Final `git status --short` includes the intended Run 13 untracked files:

- `?? scripts/collect_corroboration_sources.py`
- `?? tests/test_collect_corroboration_sources.py`
- `?? reports/editorial/citation-pipeline-test-20260612-corroboration-source-collection-run13.json`
- `?? reports/editorial/citation-pipeline-test-20260612-corroboration-source-collection-run13.md`
- `?? reports/architecture/run13-corroboration-source-collection-evidence-map-20260613.md`

Prior Run 1–12 untracked artifacts remain present. No commit was made.

## Input reports used

Primary input:

- `reports/editorial/citation-pipeline-test-20260612-corroboration-research-run12.json`

Additional context inputs validated/read:

- `reports/editorial/citation-pipeline-test-20260612-source-support-review-run10.json`
- `reports/editorial/citation-pipeline-test-20260612-filing-novelty-evaluation-run9.json`
- `reports/editorial/citation-pipeline-test-20260612-editor-review-packet-run8.json`
- `reports/editorial/citation-pipeline-test-20260612-quality-gate-run7-full.json`
- `reports/editorial/citation-pipeline-test-20260612-source-card-drafts-high-reasoning-run7.json`
- `reports/editorial/citation-pipeline-test-20260612-semantic-object-drafts-high-reasoning-run7.json`
- `reports/editorial/citation-pipeline-test-20260612-reasoning-candidate-selection.json`

## Selection rule

Selected only Run 12 `corroboration_reviews` where all were true:

- `recommended_next_stage == "run_additional_source_collection"`
- `evidence_use_decision == "needs_more_sources"`
- `corroboration_status == "insufficient_evidence"`

## Selected / skipped counts

- selected item count: `2`
- skipped item count: `1`
- candidate source count: `0`

Selected:

- `source_review_12c73455aa1816e5df8c`
  - item_id: `corrob_item_6e923bab58a413137532`
  - source_id: `src_6d7b6d80cda4e784877d`
  - status: `insufficient_evidence`
  - evidence use: `needs_more_sources`
  - Run 12 next stage: `run_additional_source_collection`

- `source_review_5baf68d86960f91b97ac`
  - item_id: `corrob_item_4039b66b55f0c200763a`
  - source_id: `src_6d7b6d80cda4e784877d`
  - status: `insufficient_evidence`
  - evidence use: `needs_more_sources`
  - Run 12 next stage: `run_additional_source_collection`

Skipped:

- `source_review_e20631e18093139a8bc2`
  - item_id: `corrob_item_bc7742fc05d0c1e48b0c`
  - reason: `needs_editor_review_not_source_collection`

## Collection method

- source_collection_executed: `false`
- collection_method: `collection_plan_only_tooling_unavailable`

Reason: no safe live web/source-collection tooling was implemented for this repository stage. The script refused to improvise uncontrolled browsing and instead wrote bounded collection plans using Run 12 suggested queries and required source types.

The script supports a future bounded curated input via `--candidate-sources-json` and validates candidate source type, support direction, evidence strength, deterministic IDs, disallowed source types, duplicate URLs, and `--max-candidates-per-item <= 5`.

## Candidate source counts

Because collection was not executed in production Run 13:

```json
{
  "collected_candidate_sources_count": 0,
  "candidate_source_type_counts": {},
  "support_direction_counts": {},
  "evidence_strength_counts": {}
}
```

## Recommended next-stage counts

```json
{
  "run_additional_source_collection": 2
}
```

Both selected items remain `needs_more_collection` with `source_collection_status=collection_not_executed_tooling_unavailable`.

## DB safety

Final DB snapshot:

```json
{
  "sources_count": 945,
  "source_notes_count": 284,
  "claims_count": 146,
  "editorial_reviews_count": 10,
  "sources_status_hash": "bde40f350904114e864f418a59b9eb8636ae6dc598d5a73d8422ef280cb446ba",
  "claims_status_hash": "2c2829622ff2988c13bc3c3f89c71dccd6139c1ec8ee06e28dc2f5e218d8df1c",
  "editorial_reviews_hash": "ed4c9b3e8704af05cdd641320bece13b8c57a9762d4a8449f6af10314585d087"
}
```

DB safety result:

- DB changed: `false`
- source_notes changed: `false` (`284 -> 284`)
- claims inserted: `0` (`146 -> 146`)
- editorial_reviews inserted: `0` (`10 -> 10`)
- source status changed: `false`
- claim status changed: `false`
- editorial status changed: `false`

## Source registry and raw-capture safety

Final hashes / snapshots:

```json
{
  "data/source_registry.json_sha256": "b9dba2f5273a28ead82b05469381e675e151a03538b3de54444c2e77ec664fca",
  "raw_path_exists": false,
  "raw_file_count": 0
}
```

Results:

- source registry changed: `false`
- raw captures changed: `false`
- full raw page content stored: `false`
- candidate links treated as source-registry entries: `false`

## Schema and daily worker safety

Final hashes:

```text
c2fe112ae800db4bcc2389c15306dcc9bcacdae24963c885191e0e433c134ade  data/schema.sql
4e5933e94f60f1233862b1f78055307149b9eb880f0c31ad0203d5755ed7490d  scripts/daily_book_worker.py
```

Results:

- schema changed: `false`
- daily worker changed: `false`

## Chapter safety

Verification generated docs artifacts. They were restored with:

```bash
git restore data/source_registry.json docs/book docs/entities docs/research/claims.md
rm -f docs/entities/boris-cherny.md
```

Final result:

- `docs/book/` changed: `false`
- narrative packets created: `false`
- chapter prose generated: `false`

## Verification commands and results

Targeted tests:

```bash
.venv/bin/python -m pytest -q tests/test_collect_corroboration_sources.py
```

Result:

- `3 passed in 1.82s`

Full suite:

```bash
.venv/bin/python -m pytest -q
```

Result:

- `54 passed in 12.38s`

Workspace/editorial/citation/MkDocs verification:

```bash
python3 scripts/verify_book_workspace.py
python3 scripts/verify_editorial_roles.py
python3 scripts/verify_book_citations.py
.venv/bin/python -m mkdocs build --strict
```

Results:

- workspace verifier: `status=ok`
- editorial roles verifier: `status=ok`
- citation verifier: `status=ok`
- MkDocs strict: exit `0`; docs built successfully with existing MkDocs Material warning

Final status command:

```bash
git status --short
```

Result: intended untracked Run 13 artifacts plus prior untracked Run artifacts; no commit made.

## Risks and limitations

- Live source collection was not executed because safe repository-specific tooling was unavailable.
- Candidate source count is therefore `0` in production Run 13.
- Run 13 did not prove or corroborate the two items; it preserved exact queries/source-type requirements and a safe future collection interface.
- Candidate sources, if later imported through `--candidate-sources-json`, are still not source-registry entries and are not validated support until a later source-support re-review.
- The `needs_editor_review` Run 12 item was intentionally skipped, not processed as source collection.

## Recommendation for Run 14

Recommended Run 14:

- Run a controlled curated candidate-source import or safe source-collection integration for the two selected items, using `--candidate-sources-json` or an explicitly designed safe collector, still report-only by default.

After candidate sources exist, a later run should perform source-support re-review. Do not create narrative packets or chapter prose until source-support re-review passes or items are explicitly excluded.
