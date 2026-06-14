# Run 15 — GPT-5.5 source-support re-review using accepted curated candidate sources

Created: 2026-06-14

## Objective

Use GPT-5.5, through the existing Hermes high-reasoning JSON bridge, to perform an advisory/report-only source-support re-review for unresolved corroboration items that had accepted curated candidate sources from the Run 14 import path.

Run 15 did not perform chapter work, did not touch the daily worker, and did not use the expanded nightly DB as the evidence base. The primary input was the accepted Run 14 import report:

- `reports/editorial/citation-pipeline-test-20260612-corroboration-source-import-run14.json`

Candidate-source provenance input:

- `reports/editorial/citation-pipeline-test-20260612-curated-candidate-sources-run14.json`

## Created artifacts

- `scripts/llm_source_support_rereview.py`
- `tests/test_llm_source_support_rereview.py`
- `reports/editorial/citation-pipeline-test-20260612-source-support-rereview-run15.json`
- `reports/editorial/citation-pipeline-test-20260612-source-support-rereview-run15.md`
- `reports/architecture/run15-source-support-rereview-evidence-map-20260614.md`

## Selection rule implemented

Selected only collection/import items where:

- accepted public candidate source count was greater than zero;
- `recommended_next_stage == "run_source_support_re_review"` or `preliminary_collection_assessment == "enough_candidates_for_re_review"`;
- source review ID was known in Run 10 source-support provenance;
- item was present in accepted curated candidate-source provenance;
- candidate sources were public, did not store raw content, and were not rejected by Run 14 import.

Skipped:

- needs-editor-review items;
- already eligible/persisted caveat-only Run 11-path items;
- unknown source review IDs;
- items with no accepted candidate sources;
- non-public, raw-content-stored, disallowed, malformed, duplicate, or Run 14 rejected candidates.

## Live Run 15 result

- selected_items_count: `2`
- reviewed_items_count: `2`
- skipped_items_count: `5`
- accepted_candidate_sources_count: `7`
- rejected_candidate_sources_ignored_count: `2`
- llm_used: `true`
- provider: `copilot`
- model: `gpt-5.5`
- bridge: `hermes_cli`

Selected source-review IDs:

- `source_review_12c73455aa1816e5df8c`
- `source_review_5baf68d86960f91b97ac`

## GPT-5.5 advisory decisions

Support decision counts:

- `partially_supported`: `2`

Corroboration decision counts:

- `partially_corroborated`: `2`

Evidence-use decision counts:

- `eligible_as_caveat_only_after_corroboration`: `1`
- `eligible_for_filing_later_after_corroboration`: `1`

Recommended next-stage counts:

- `eligible_for_review_note_persistence`: `1`
- `needs_editor_review`: `1`

Per-item summary:

- `source_review_12c73455aa1816e5df8c`
  - support decision: `partially_supported`
  - corroboration decision: `partially_corroborated`
  - evidence-use decision: `eligible_as_caveat_only_after_corroboration`
  - recommended next stage: `needs_editor_review`
  - interpretation: candidate sources support OpenClaw web/mobile access generally, but do not prove a Hermes Agent-specific web/phone interface. Requires caveat and source-context review.

- `source_review_5baf68d86960f91b97ac`
  - support decision: `partially_supported`
  - corroboration decision: `partially_corroborated`
  - evidence-use decision: `eligible_for_filing_later_after_corroboration`
  - recommended next stage: `eligible_for_review_note_persistence`
  - interpretation: candidate sources support the limited point that OpenClaw documentation names Hermes in migration/setup/import tooling, but not a broad Hermes runtime/dependency claim.

## Safety confirmations from output payload

- report_only: `true`
- changed_db: `false`
- changed_source_registry: `false`
- changed_raw_captures: `false`
- changed_docs_book: `false`
- changed_schema: `false`
- changed_daily_worker: `false`
- claims_inserted: `0`
- editorial_reviews_inserted: `0`
- source_status_changed: `false`
- claim_status_changed: `false`
- editorial_status_changed: `false`
- advisory_only: `true`
- author_allowed: `false`
- publication_approved: `false`

## Tests added

`tests/test_llm_source_support_rereview.py` covers:

- only items with accepted candidate sources are selected;
- rejected/non-public/raw-content candidate sources are ignored;
- needs-editor-review item is skipped;
- already persisted/eligible Run 11-path item is skipped;
- unknown source review ID is skipped/fails closed;
- invalid/missing Run 14 import report fails closed;
- no accepted candidate source means no GPT-5.5 review for that item;
- invalid LLM JSON fails closed;
- invalid enum values fail closed;
- missing hard safety flags fail closed;
- no weak/local fallback when high reasoning is required;
- report-only mode does not modify `.var/book.sqlite`;
- `source_registry.json` is not modified;
- raw captures are not modified;
- `docs/book` is not modified;
- `data/schema.sql` is not modified;
- `scripts/daily_book_worker.py` is not modified;
- no claims/editorial_reviews/status hashes change.

## Verification commands run

```bash
git status --short
.venv/bin/python -m pytest -q tests/test_llm_source_support_rereview.py
.venv/bin/python -m pytest -q
python3 scripts/verify_book_workspace.py
python3 scripts/verify_editorial_roles.py
python3 scripts/verify_book_citations.py
.venv/bin/python -m mkdocs build --strict
git status --short
```

Results:

- focused Run 15 test file: `4 passed in 2.67s`
- full test suite: `66 passed in 17.16s`
- `verify_book_workspace.py`: `status: ok`
- `verify_editorial_roles.py`: `status: ok`
- `verify_book_citations.py`: `status: ok`
- `mkdocs build --strict`: passed; existing Material/MkDocs warning and nav informational messages only.

After verification, protected/generated artifacts were restored as instructed:

```bash
git restore data/source_registry.json docs/book docs/entities docs/research/claims.md \
  reports/architecture/run1-llm-reasoning-dry-run-evidence-map-20260614.md \
  reports/architecture/run3-source-card-persistence-evidence-map-20260614.md \
  reports/architecture/run4-semantic-object-extraction-evidence-map-20260614.md \
  reports/architecture/run5-high-reasoning-bridge-evidence-map-20260614.md
rm -f docs/entities/boris-cherny.md
```

The extra architecture report restores were needed because verification rewrote minor generated timestamp/content lines in existing accumulated architecture artifacts; they were not part of Run 15 and were restored.

## Remaining intended git delta

Expected uncommitted Run 15 files:

- `reports/editorial/citation-pipeline-test-20260612-source-support-rereview-run15.json`
- `reports/editorial/citation-pipeline-test-20260612-source-support-rereview-run15.md`
- `reports/architecture/run15-source-support-rereview-evidence-map-20260614.md`
- `scripts/llm_source_support_rereview.py`
- `tests/test_llm_source_support_rereview.py`

## Recommended Run 16

Run 16 should be a disabled-by-default, report-first source-note/review-note persistence planning run. It should consider only Run 15 items recommended as `eligible_for_review_note_persistence`, preserve `advisory_only=true`, `author_allowed=false`, `publication_approved=false`, and require a fresh report-only dry run before any opt-in persistence. It should not insert claims, create narrative packets, or generate chapter prose.
