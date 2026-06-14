# Run 12 corroboration research evidence map — 20260613

## Scope

Run 12 implemented a controlled, report-only-by-default corroboration research planning layer for Run 10 source-review items requiring corroboration.

Run 12 did **not** browse the web, collect external sources, persist notes, insert claims, insert editorial reviews, modify source registry, modify `docs/book/`, modify `data/schema.sql`, modify `scripts/daily_book_worker.py`, change statuses, create narrative packets, generate chapter prose, approve author use, or approve publication.

## Files changed

Added:

- `scripts/llm_corroboration_research.py`
- `tests/test_llm_corroboration_research.py`
- `reports/editorial/citation-pipeline-test-20260612-corroboration-research-run12.json`
- `reports/editorial/citation-pipeline-test-20260612-corroboration-research-run12.md`
- `reports/architecture/run12-corroboration-research-evidence-map-20260613.md`

## Files intentionally not changed

Protected surfaces intentionally not changed:

- `docs/book/`
- raw captures
- `.var/book.sqlite`
- source registry
- source status, claim status, editorial status
- publication decisions or chapter status
- `claims` table
- `editorial_reviews` table
- `data/schema.sql`
- `scripts/daily_book_worker.py`
- commit allowlist
- narrative packet outputs
- publishable chapter prose

## Current git status before/after

Preflight branch/commit:

- branch: `main`
- short HEAD: `b103efb`

Final status includes intended untracked Run 12 artifacts:

- `?? scripts/llm_corroboration_research.py`
- `?? tests/test_llm_corroboration_research.py`
- `?? reports/editorial/citation-pipeline-test-20260612-corroboration-research-run12.json`
- `?? reports/editorial/citation-pipeline-test-20260612-corroboration-research-run12.md`
- `?? reports/architecture/run12-corroboration-research-evidence-map-20260613.md`

Existing prior Run 1–11 untracked artifacts remain. No protected tracked files remained modified after restoring verification-generated artifacts.

## Input reports used

Primary input:

- `reports/editorial/citation-pipeline-test-20260612-source-support-review-run10.json`

Additional context/provenance inputs validated/read:

- `reports/editorial/citation-pipeline-test-20260612-filing-novelty-evaluation-run9.json`
- `reports/editorial/citation-pipeline-test-20260612-editor-review-packet-run8.json`
- `reports/editorial/citation-pipeline-test-20260612-quality-gate-run7-full.json`
- `reports/editorial/citation-pipeline-test-20260612-source-card-drafts-high-reasoning-run7.json`
- `reports/editorial/citation-pipeline-test-20260612-semantic-object-drafts-high-reasoning-run7.json`
- `reports/editorial/citation-pipeline-test-20260612-reasoning-candidate-selection.json`

## Selection rule

Selected any Run 10 source-review item where at least one was true:

- `next_stage_recommendation == "run_corroboration_research"`
- `evidence_use_decision == "needs_corroboration_before_filing"`
- `corroboration_decision == "corroboration_required"`

The count was derived from the Run 10 JSON rather than hard-coded.

## Selected item count

- selected item count: `3`
- reviewed item count: `3`
- skipped item count: `2`

Selected items:

- `source_review_12c73455aa1816e5df8c` — `unsupported`, `corroboration_required`, `needs_corroboration_before_filing`, `run_corroboration_research`
- `source_review_5baf68d86960f91b97ac` — `partially_supported`, `corroboration_required`, `needs_corroboration_before_filing`, `run_corroboration_research`
- `source_review_e20631e18093139a8bc2` — `unclear`, `corroboration_required`, `needs_source_review`, `needs_source_review`

Skipped items:

- `source_review_01be74039581152450ad` — `already_eligible_or_persisted`
- `source_review_a1bc597eb60322bee40e` — `already_eligible_or_persisted`

Note: the handoff expected two `run_corroboration_research` items, but the Run 10 JSON also contained one `needs_source_review` item with `corroboration_decision == corroboration_required`, so Run 12 selected three items according to the requested primary rule.

## Provider/model/bridge

Live Run 12 used:

- provider: `copilot`
- model: `gpt-5.5`
- bridge: `hermes_cli`
- bridge helper: `scripts/hermes_high_reasoning_json.py`
- `llm_used=true`
- `reasoning_status=high_reasoning_used`

Weak/local fallback was refused. Invalid JSON and malformed schema fail closed in tests. The first live attempt failed closed because GPT-5.5 returned arrays for fields that required single strings; the prompt/validator was tightened and rerun successfully.

## Corroboration status counts

```json
{
  "insufficient_evidence": 2,
  "source_context_unclear": 1
}
```

## Evidence-use counts

```json
{
  "needs_more_sources": 2,
  "needs_source_review": 1
}
```

## Recommended next-stage counts

```json
{
  "run_additional_source_collection": 2,
  "needs_editor_review": 1
}
```

## DB safety

Preflight and final DB snapshots:

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

DB safety result:

- DB changed: `no`
- claims inserted: `0`
- editorial_reviews inserted: `0`
- source_notes count before/after: `284 / 284`
- claims count before/after: `146 / 146`
- editorial_reviews count before/after: `10 / 10`
- source/claim/editorial status hashes: unchanged

## Schema and worker safety

Preflight/final hashes:

```text
c2fe112ae800db4bcc2389c15306dcc9bcacdae24963c885191e0e433c134ade  data/schema.sql
4e5933e94f60f1233862b1f78055307149b9eb880f0c31ad0203d5755ed7490d  scripts/daily_book_worker.py
```

Results:

- schema changed: `no`
- daily worker changed: `no`

## Chapter safety

Verification generated docs artifacts. They were restored with:

```bash
git restore data/source_registry.json docs/book docs/entities docs/research/claims.md
rm -f docs/entities/boris-cherny.md
```

Final chapter safety:

- `docs/book/` changed: `no`
- raw/private material written: `false`
- long source excerpts written: `false`

## Verification commands and results

Targeted tests:

```bash
.venv/bin/python -m pytest -q tests/test_llm_corroboration_research.py
```

Result:

- `3 passed in 0.71s`

Full suite:

```bash
.venv/bin/python -m pytest -q
```

Result:

- `51 passed in 10.62s`

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

Final status command:

```bash
git status --short
```

Result: intended untracked Run 12 artifacts plus prior untracked Run artifacts; no commit made.

## Risks and limitations

- Run 12 did not perform live web/source collection.
- GPT-5.5 produced a corroboration planning assessment, not human/editor approval.
- No item was corroborated; two need additional source collection and one needs source review/editor review.
- `run_additional_source_collection` is a recommendation for a future controlled run; no sources were collected in Run 12.
- Persisted Run 11 caveat-only notes were intentionally skipped and not treated as claims.

## Recommendation for Run 13

Recommended Run 13:

- controlled external source collection for the two items with `recommended_next_stage == run_additional_source_collection`, report-only by default.

Run 13 should:

- use explicit source-collection scope and allowlist/source-type constraints
- avoid uncontrolled browsing
- write only reports by default
- not modify raw captures/source registry unless separately and explicitly authorized
- not insert claims, editorial reviews, or statuses
- not create narrative packets or chapter prose
- keep author/publication approval false

Do not proceed to clustering or narrative packets until corroboration-required items are resolved or explicitly excluded.
