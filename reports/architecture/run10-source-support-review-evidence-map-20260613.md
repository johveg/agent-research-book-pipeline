# Run 10 source-support review evidence map — 20260613

## Scope

Run 10 implemented a report-only source-support and corroboration pass for the five Run 9 filing/novelty evaluations.

Run 10 did **not** run external web searches, insert claims, promote sources/claims, create narrative packets, generate chapter prose, wire daily workers, approve author use, or approve publication.

## Files changed

Added:

- `scripts/llm_review_source_support.py`
- `tests/test_llm_review_source_support.py`
- `reports/editorial/citation-pipeline-test-20260612-source-support-review-run10.json`
- `reports/editorial/citation-pipeline-test-20260612-source-support-review-run10.md`
- `reports/architecture/run10-source-support-review-evidence-map-20260613.md`

## Files intentionally not changed

Protected surfaces intentionally not changed:

- `docs/book/`
- raw captures
- `.var/book.sqlite`
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

Final status includes intended untracked Run 10 report-only artifacts:

- `?? scripts/llm_review_source_support.py`
- `?? tests/test_llm_review_source_support.py`
- `?? reports/editorial/citation-pipeline-test-20260612-source-support-review-run10.json`
- `?? reports/editorial/citation-pipeline-test-20260612-source-support-review-run10.md`
- `?? reports/architecture/run10-source-support-review-evidence-map-20260613.md`

Existing prior Run 1–9 untracked artifacts remain. No protected tracked files remained modified after restoring verification-generated artifacts.

## Input reports used

Primary inputs:

- `reports/editorial/citation-pipeline-test-20260612-filing-novelty-evaluation-run9.json`
- `reports/editorial/citation-pipeline-test-20260612-editor-review-packet-run8.json`

Available provenance/context from prior runs:

- `reports/editorial/citation-pipeline-test-20260612-quality-gate-run7-full.json`
- `reports/editorial/citation-pipeline-test-20260612-source-card-drafts-high-reasoning-run7.json`
- `reports/editorial/citation-pipeline-test-20260612-semantic-object-drafts-high-reasoning-run7.json`
- `reports/editorial/citation-pipeline-test-20260612-reasoning-candidate-selection.json`

Run 5 evidence map remains unreliable/miswritten and was not used as source of truth.

## Filing evaluations available

From Run 9 filing/novelty report:

- filing evaluations available: `5`
- items reviewed by Run 10: `5`

## Provider/model/bridge used

Live source-support review used:

- provider: `copilot`
- model: `gpt-5.5`
- bridge: `hermes_cli`
- bridge script: `scripts/hermes_high_reasoning_json.py`
- `llm_used=true`
- `reasoning_status=high_reasoning_used`

No weak/local fallback was used. Invalid JSON and unapproved provider paths fail closed in tests.

## Source-support decision counts

Live GPT-5.5 Run 10 report:

```json
{
  "partially_supported": 1,
  "supported": 2,
  "unclear": 1,
  "unsupported": 1
}
```

## Corroboration decision counts

```json
{
  "corroboration_not_required": 2,
  "corroboration_required": 3
}
```

## Evidence-use decision counts

```json
{
  "eligible_as_caveat_only": 2,
  "needs_corroboration_before_filing": 2,
  "needs_source_review": 1
}
```

## Next-stage recommendation counts

```json
{
  "eligible_for_filing_persistence": 2,
  "needs_source_review": 1,
  "run_corroboration_research": 2
}
```

Additional counts:

- eligible-for-filing-persistence count: `2`
- eligible-as-caveat-only count: `2`
- needs-corroboration count: `5`
- do-not-use count: `0`

## Reviewed items

- `source_review_12c73455aa1816e5df8c` / `filing_eval_c39f3be4e7bef7f0dabe` → `unsupported`, `corroboration_required`, `needs_corroboration_before_filing`, `run_corroboration_research`
- `source_review_01be74039581152450ad` / `filing_eval_5a84c224eb58bf625f42` → `supported`, `corroboration_not_required`, `eligible_as_caveat_only`, `eligible_for_filing_persistence`
- `source_review_5baf68d86960f91b97ac` / `filing_eval_b82d67d436357d41bf72` → `partially_supported`, `corroboration_required`, `needs_corroboration_before_filing`, `run_corroboration_research`
- `source_review_e20631e18093139a8bc2` / `filing_eval_bd562e909f80e16a2bb3` → `unclear`, `corroboration_required`, `needs_source_review`, `needs_source_review`
- `source_review_a1bc597eb60322bee40e` / `filing_eval_224fd1bd260b4222fdfc` → `supported`, `corroboration_not_required`, `eligible_as_caveat_only`, `eligible_for_filing_persistence`

All items preserve filing/source/card/object/review provenance and set:

- `author_allowed=false`
- `publication_approved=false`
- `advisory_only=true`

## DB safety

Before and after DB/status snapshot:

```json
{
  "sources_count": 945,
  "claims_count": 146,
  "editorial_reviews_count": 10,
  "source_notes_count": 282,
  "source_card_draft_count": 10,
  "semantic_object_draft_count": 32,
  "sources_status_hash": "bde40f350904114e864f418a59b9eb8636ae6dc598d5a73d8422ef280cb446ba",
  "claims_status_hash": "2c2829622ff2988c13bc3c3f89c71dccd6139c1ec8ee06e28dc2f5e218d8df1c",
  "editorial_reviews_hash": "ed4c9b3e8704af05cdd641320bece13b8c57a9762d4a8449f6af10314585d087"
}
```

DB safety result:

- DB changed by default: `no`
- DB write scope: `none`
- claims inserted: `0`
- editorial reviews inserted: `0`
- source_notes count before/after: `282 / 282`
- source/claim/editorial status hashes: unchanged

## Chapter safety

Verification generated docs artifacts. They were restored with:

```bash
git restore data/source_registry.json docs/book docs/entities docs/research/claims.md
rm -f docs/entities/boris-cherny.md
```

Final chapter safety:

- `docs/book/` changed: `no`
- chapters modified: `false`
- long source excerpts written: `false`
- raw/private material written: `false`

## Verification results

Targeted tests:

```bash
.venv/bin/python -m pytest -q tests/test_llm_review_source_support.py
```

Result:

- `3 passed in 0.50s`

Full suite:

```bash
.venv/bin/python -m pytest -q
```

Result:

- `45 passed in 9.61s`

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

- Run 10 is advisory/report-only.
- GPT-5.5 source-support decisions are not human/editor approval.
- `supported` does not mean true.
- `eligible_for_filing_persistence` does not write to DB in Run 10.
- `eligible_as_caveat_only` is not author or publication approval.
- No external web corroboration was run by default.
- One item was marked unsupported, one unclear, and two need corroboration before filing.

## Recommendation for Run 11

Recommended Run 11:

- implement disabled-by-default persistence of source-review/filing notes to `source_notes` for the two `eligible_for_filing_persistence` caveat-only items, **or** run controlled live corroboration research for the two items recommended for `run_corroboration_research`.

Preferred sequence:

1. If preserving the review state is the priority: add opt-in `--write-source-notes` persistence for the two eligible caveat-only items only, with idempotency and no status changes.
2. If improving source strength is the priority: run a controlled corroboration research pass for the two corroboration-required items.

In either case, Run 11 should remain report-only/disabled-by-default unless explicitly authorized to persist source notes, and must not insert claims, alter statuses, approve author use, approve publication, or create chapter prose.
