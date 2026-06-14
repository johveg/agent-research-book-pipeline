# Run 11 persisted review notes evidence map — 20260613

## Scope

Run 11 implemented disabled-by-default persistence of eligible Run 10 source-support / filing review notes into `source_notes`.

Run 11 persisted only the two source-review items that satisfied the default eligibility rules:

- `next_stage_recommendation == eligible_for_filing_persistence`
- `evidence_use_decision == eligible_as_caveat_only` or `eligible_for_filing_later`
- `source_support_decision == supported` or `partially_supported`
- `author_allowed=false`
- `publication_approved=false`
- `advisory_only=true`
- complete source/card/object/review/filing provenance

Run 11 did **not** implement live corroboration research, narrative packets, claim insertion, status promotion, daily-worker wiring, or publication approval.

## Files changed

Added:

- `scripts/persist_reasoning_review_notes.py`
- `tests/test_persist_reasoning_review_notes.py`
- `reports/editorial/citation-pipeline-test-20260612-persisted-review-notes-run11.json`
- `reports/editorial/citation-pipeline-test-20260612-persisted-review-notes-run11.md`
- `reports/architecture/run11-persist-review-notes-evidence-map-20260613.md`

## Files intentionally not changed

Protected surfaces intentionally not changed:

- `docs/book/`
- raw captures
- source status, claim status, editorial status
- publication decisions or chapter status
- `claims` table
- `editorial_reviews` table
- `scripts/daily_book_worker.py`
- commit allowlist
- `data/schema.sql`
- narrative packet outputs
- publishable chapter prose

## Current git status before/after

Preflight branch/commit:

- branch: `main`
- short HEAD: `b103efb`

Final status includes intended untracked Run 11 artifacts:

- `?? scripts/persist_reasoning_review_notes.py`
- `?? tests/test_persist_reasoning_review_notes.py`
- `?? reports/editorial/citation-pipeline-test-20260612-persisted-review-notes-run11.json`
- `?? reports/editorial/citation-pipeline-test-20260612-persisted-review-notes-run11.md`
- `?? reports/architecture/run11-persist-review-notes-evidence-map-20260613.md`

Existing prior Run 1–10 untracked artifacts remain. No protected tracked files remained modified after restoring verification-generated artifacts.

## Input reports used

Primary input:

- `reports/editorial/citation-pipeline-test-20260612-source-support-review-run10.json`

Available provenance/context:

- `reports/editorial/citation-pipeline-test-20260612-filing-novelty-evaluation-run9.json`
- `reports/editorial/citation-pipeline-test-20260612-editor-review-packet-run8.json`
- `reports/editorial/citation-pipeline-test-20260612-quality-gate-run7-full.json`
- `reports/editorial/citation-pipeline-test-20260612-source-card-drafts-high-reasoning-run7.json`
- `reports/editorial/citation-pipeline-test-20260612-semantic-object-drafts-high-reasoning-run7.json`
- `reports/editorial/citation-pipeline-test-20260612-reasoning-candidate-selection.json`

## source_notes schema inspected

`PRAGMA table_info(source_notes)` found compatible schema:

```json
[
  {"name": "id", "type": "TEXT", "pk": 1},
  {"name": "source_id", "type": "TEXT", "notnull": 1},
  {"name": "note", "type": "TEXT", "notnull": 1},
  {"name": "note_type", "type": "TEXT", "dflt_value": "'summary'"},
  {"name": "created_at", "type": "TEXT", "notnull": 1}
]
```

No schema migration was run. `data/schema.sql` was not modified.

## Source reviews available

From Run 10 source-support review report:

- source reviews available: `5`

## Eligible items available

Default eligibility selected:

- eligible items available: `2`
- items selected for persistence: `2`

Selected source reviews:

- `source_review_01be74039581152450ad` / `filing_eval_5a84c224eb58bf625f42`
- `source_review_a1bc597eb60322bee40e` / `filing_eval_224fd1bd260b4222fdfc`

## Items skipped and reasons

Skipped by default:

- `source_review_12c73455aa1816e5df8c` → `unsupported`
- `source_review_5baf68d86960f91b97ac` → `needs_corroboration`
- `source_review_e20631e18093139a8bc2` → `unclear`

Skipped reason counts:

```json
{
  "unsupported": 1,
  "needs_corroboration": 1,
  "unclear": 1
}
```

No unsupported, unclear, source-review-needed, or corroboration-required item was persisted.

## Persistence design

Persistence target:

- table: `source_notes`
- note type: `reasoning_review_filing_draft`
- note schema: `reasoning_review_filing_draft.v1`

Deterministic ID strategy:

```text
note_<sha256(note_type + source_review_id + output_hash)[:24]>
```

Persisted note IDs:

- `note_5c7cbc1ee1d3c0fd72fe7b74`
- `note_7e2e6c98208d303c662fff0a`

Each persisted note is compact deterministic JSON and preserves:

- `source_review_id`
- `filing_evaluation_id`
- `packet_item_id`
- `source_id`
- `source_card_id`
- `semantic_object_id`
- `quality_review_id`
- source metadata
- semantic object text, truncated/compact
- filing/novelty/source-support decisions
- rationale, blockers, risk flags, required editor decisions
- `author_allowed=false`
- `publication_approved=false`
- `advisory_only=true`
- provider/model/bridge/reasoning metadata from Run 10

## DB safety

Initial preflight DB snapshot:

```json
{
  "sources_count": 945,
  "claims_count": 146,
  "editorial_reviews_count": 10,
  "source_notes_count": 282,
  "reasoning_review_filing_draft_count": 0,
  "sources_status_hash": "bde40f350904114e864f418a59b9eb8636ae6dc598d5a73d8422ef280cb446ba",
  "claims_status_hash": "2c2829622ff2988c13bc3c3f89c71dccd6139c1ec8ee06e28dc2f5e218d8df1c",
  "editorial_reviews_hash": "ed4c9b3e8704af05cdd641320bece13b8c57a9762d4a8449f6af10314585d087"
}
```

Default report-only run:

- DB changed by default: `no`
- DB write scope: `none`
- notes inserted: `0`
- notes skipped existing: `0`
- notes failed: `0`
- notes conflicted: `0`

Opt-in persistence run with `--write-source-notes`:

- DB changed by opt-in: `yes`
- DB write scope: `source_notes`
- notes inserted: `2`
- notes skipped existing: `0`
- notes failed: `0`
- notes conflicted: `0`
- source_notes count: `282 -> 284`

Idempotency rerun with `--write-source-notes`:

- DB changed by idempotency rerun: `no`
- DB write scope in final rerun report: `none`
- notes inserted: `0`
- notes skipped existing: `2`
- notes failed: `0`
- notes conflicted: `0`
- idempotent: `true`
- source_notes count: `284 -> 284`

Final DB snapshot:

```json
{
  "sources_count": 945,
  "claims_count": 146,
  "editorial_reviews_count": 10,
  "source_notes_count": 284,
  "reasoning_review_filing_draft_count": 2,
  "sources_status_hash": "bde40f350904114e864f418a59b9eb8636ae6dc598d5a73d8422ef280cb446ba",
  "claims_status_hash": "2c2829622ff2988c13bc3c3f89c71dccd6139c1ec8ee06e28dc2f5e218d8df1c",
  "editorial_reviews_hash": "ed4c9b3e8704af05cdd641320bece13b8c57a9762d4a8449f6af10314585d087"
}
```

DB safety results:

- claims count before/after: `146 / 146`
- editorial_reviews count before/after: `10 / 10`
- source/claim/editorial status hashes before/after: unchanged
- claims inserted: `0`
- editorial reviews inserted: `0`
- source/claim/editorial statuses changed: `no`

## Chapter safety

Verification generated docs artifacts. They were restored with:

```bash
git restore data/source_registry.json docs/book docs/entities docs/research/claims.md
rm -f docs/entities/boris-cherny.md
```

Final chapter safety:

- `docs/book/` changed: `no`
- chapters modified: `false`
- raw/private material written: `false`
- long source excerpts written: `false`

## Verification results

Targeted tests:

```bash
.venv/bin/python -m pytest -q tests/test_persist_reasoning_review_notes.py
```

Result:

- `3 passed in 0.51s`

Full suite:

```bash
.venv/bin/python -m pytest -q
```

Result:

- `48 passed in 10.01s`

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
- MkDocs strict: exit `0`; docs built successfully, with the existing MkDocs Material warning

## Risks and limitations

- Persisted notes are advisory review/filing draft metadata, not claims.
- Persisted notes are not source promotion, claim promotion, author approval, or publication approval.
- Only two caveat-only eligible items were persisted.
- Corroboration-required, unclear, and unsupported items remain unresolved and were intentionally skipped.
- No external web search or corroboration research ran in Run 11.
- The final Run 11 JSON report reflects the idempotency rerun state: `notes_inserted=0`, `notes_skipped_existing=2`, with `source_notes_count_before=284` and `source_notes_count_after=284`. The first opt-in run inserted the two notes.

## Recommendation for Run 12

Recommended Run 12:

- controlled corroboration research for the items requiring corroboration, report-only by default.

Reason:

- exactly two eligible caveat-only notes were preserved in `source_notes`
- two Run 10 items remain in `run_corroboration_research` path
- one item remains unclear / needs source review

Do not recommend narrative packets until the corroboration-required items are resolved or explicitly excluded. Run 12 should not insert claims, change statuses, approve author use, approve publication, or create chapter prose.
