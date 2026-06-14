# Run 16 — Disabled-by-default persistence of Run 15 eligible source-support re-review outcome

Created: 2026-06-14

## Objective

Convert only the Run 15 advisory source-support re-review item eligible for review-note persistence into a durable `source_notes` record, behind an explicit `--write-source-notes` flag.

This run is not authoring, not clustering, not narrative packet creation, not source-registry promotion, not claim insertion, not editorial-review insertion, not human/editor approval, and not publication approval.

## Primary input

- `reports/editorial/citation-pipeline-test-20260612-source-support-rereview-run15.json`

## Created files

- `scripts/persist_source_support_rereview_notes.py`
- `tests/test_persist_source_support_rereview_notes.py`
- `reports/editorial/citation-pipeline-test-20260612-persisted-source-support-rereview-notes-run16.json`
- `reports/editorial/citation-pipeline-test-20260612-persisted-source-support-rereview-notes-run16.md`
- `reports/architecture/run16-persist-source-support-rereview-notes-evidence-map-20260614.md`

## Selection rule implemented

The script persists only Run 15 `rereviews` where all are true:

- `recommended_next_stage == eligible_for_review_note_persistence`
- `advisory_only == true`
- `author_allowed == false`
- `publication_approved == false`
- `support_decision in {supported, partially_supported}`
- `corroboration_decision in {corroborated, partially_corroborated}`
- `evidence_use_decision in {eligible_as_caveat_only_after_corroboration, eligible_for_filing_later_after_corroboration}`

Expected eligible item:

- `source_review_5baf68d86960f91b97ac`

Expected skipped item:

- `source_review_12c73455aa1816e5df8c`
- skipped with automated closed-loop disposition: `source_context_unclear`
- not persisted
- not described as human-only required action

## Persistence behavior

Target table:

- `source_notes`

Target note type:

- `source_support_rereview_draft`

Deterministic note ID strategy:

- `note_<sha256(note_type + source_review_id + output_hash)[:24]>`

Inserted note ID:

- `note_a30056d3f19faa7deb0c9dbc`

Persistence mode:

- default: report-only, no DB write
- opt-in: `--write-source-notes`, writes only to `source_notes`

Idempotency:

- second opt-in write detected the existing identical deterministic note and skipped it
- no duplicate was created

Conflict behavior:

- tests create a deterministic ID collision with different content in a temporary DB
- script fails closed and rolls back

## Live command results

Initial production DB counts before Run 16 write:

- `source_notes`: 364
- `source_support_rereview_draft`: 0
- `claims`: 181
- `editorial_reviews`: 10

Report-only run:

- `inserted_notes_count`: 0
- `existing_notes_count`: 0
- DB unchanged

First write run:

- `inserted_notes_count`: 1
- `existing_notes_count`: 0
- `source_notes`: 364 → 365
- `source_support_rereview_draft`: 0 → 1
- inserted note ID: `note_a30056d3f19faa7deb0c9dbc`
- inserted note source ID: `src_6d7b6d80cda4e784877d`

Idempotency write rerun:

- `inserted_notes_count`: 0
- `existing_notes_count`: 1
- `source_notes`: 365 → 365
- `source_support_rereview_draft`: 1 → 1

Final Run 16 report reflects the idempotency rerun, so it reports existing-identical rather than the first insertion.

Final report summary:

```json
{
  "closed_loop_disposition_counts": {
    "eligible_for_review_note_persistence": 1,
    "source_context_unclear": 1
  },
  "conflicted_notes_count": 0,
  "eligible_items_count": 1,
  "existing_notes_count": 1,
  "failed_notes_count": 0,
  "inserted_notes_count": 0,
  "report_only": false,
  "reviewed_items_count": 2,
  "skipped_items_count": 1,
  "source_notes_count_after": 365,
  "source_notes_count_before": 365,
  "source_support_rereview_draft_count_after": 1,
  "source_support_rereview_draft_count_before": 1,
  "write_source_notes": true
}
```

## Tests

Added `tests/test_persist_source_support_rereview_notes.py` covering:

- report-only mode does not modify SQLite
- `--write-source-notes` writes only the eligible Run 15 item
- expected eligible count is 1
- `needs_editor_review` item is skipped with automated closed-loop disposition, not human-only wording
- deterministic note ID
- idempotency on second write
- deterministic-ID conflict fails closed and rolls back
- no claims inserted
- no editorial_reviews inserted
- source/claim/editorial statuses unchanged
- source_registry unchanged
- raw captures unchanged
- docs/book unchanged
- schema unchanged
- daily worker unchanged
- missing input fails closed
- missing hard safety flags fail closed
- unsupported/contradicted/do_not_use items are not persisted
- no author approval
- no publication approval

Focused test result:

- `7 passed in 2.12s`

Full suite result:

- `82 passed in 20.11s`

## Verification commands

```bash
git status --short
.venv/bin/python -m pytest -q tests/test_persist_source_support_rereview_notes.py
.venv/bin/python -m pytest -q
python3 scripts/verify_book_workspace.py
python3 scripts/verify_editorial_roles.py
python3 scripts/verify_book_citations.py
.venv/bin/python -m mkdocs build --strict
git status --short
```

Additional live Run 16 commands:

```bash
python3 scripts/persist_source_support_rereview_notes.py \
  --run-id citation-pipeline-test-20260612 \
  --source-support-rereview-report reports/editorial/citation-pipeline-test-20260612-source-support-rereview-run15.json \
  --output-dir reports/editorial \
  --report-suffix run16

python3 scripts/persist_source_support_rereview_notes.py \
  --run-id citation-pipeline-test-20260612 \
  --source-support-rereview-report reports/editorial/citation-pipeline-test-20260612-source-support-rereview-run15.json \
  --output-dir reports/editorial \
  --report-suffix run16 \
  --write-source-notes

python3 scripts/persist_source_support_rereview_notes.py \
  --run-id citation-pipeline-test-20260612 \
  --source-support-rereview-report reports/editorial/citation-pipeline-test-20260612-source-support-rereview-run15.json \
  --output-dir reports/editorial \
  --report-suffix run16 \
  --write-source-notes
```

Verifier results:

- `python3 scripts/verify_book_workspace.py`: `status: ok`
- `python3 scripts/verify_editorial_roles.py`: `status: ok`
- `python3 scripts/verify_book_citations.py`: `status: ok`
- `.venv/bin/python -m mkdocs build --strict`: passed, with existing Material/MkDocs warning and existing nav informational messages only

## Protected artifact restoration

Verification regenerated protected artifacts. They were restored with:

```bash
git restore data/source_registry.json docs/book docs/entities docs/research/claims.md \
  reports/architecture/run1-llm-reasoning-dry-run-evidence-map-20260614.md \
  reports/architecture/run3-source-card-persistence-evidence-map-20260614.md \
  reports/architecture/run4-semantic-object-extraction-evidence-map-20260614.md \
  reports/architecture/run5-high-reasoning-bridge-evidence-map-20260614.md
rm -f docs/entities/boris-cherny.md
```

Final protected diff stat was empty for:

- `data/source_registry.json`
- `docs/book`
- `docs/entities`
- `docs/research/claims.md`
- `data/schema.sql`
- `scripts/daily_book_worker.py`

## Safety confirmations

Confirmed unchanged / not performed:

- no claims inserted
- no editorial_reviews inserted
- no source/claim/editorial status changes
- no source_registry changes
- no raw capture changes
- no docs/book changes
- no schema changes
- no daily worker changes
- no narrative packets
- no chapter prose
- no authoring approval
- no publication approval

Only intended production DB change:

- one `source_notes` row inserted with `note_type='source_support_rereview_draft'`

## Recommendation for Run 17

Run 17 should audit the persisted draft note and decide whether any additional source-context review is needed before downstream extraction. It should remain report-first and must not create claims, narrative packets, chapter prose, author approval, or publication approval.
