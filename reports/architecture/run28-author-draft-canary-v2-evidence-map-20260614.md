# Run 28 — Second controlled report-only caveat-only author-draft canary

Date: 2026-06-14
Run ID: `citation-pipeline-test-20260612`
Repository: `/home/hermoine/terefohealreboa`

## Objective

Generate a second controlled caveat-only author-draft canary from the enriched Run 26 input, using the Run 27 preflight approval, with GPT-5.5 through the `closed_loop_editorial` profile.

This run is report-only. The generated draft canary exists only inside report artifacts and is not authoring approval, publication approval, claim insertion, chapter-ready prose, or a chapter update.

## Inputs

Primary inputs:

- `reports/editorial/citation-pipeline-test-20260612-rebuilt-author-input-preflight-run27.json`
- `reports/editorial/citation-pipeline-test-20260612-author-draft-input-rebuild-run26.json`

Supporting lineage was preserved through upstream report paths embedded in the selected Run 26/27 objects.

## Files created/changed by Run 28

Created:

- `scripts/llm_author_draft_canary_v2.py`
- `tests/test_llm_author_draft_canary_v2.py`
- `reports/editorial/citation-pipeline-test-20260612-author-draft-canary-v2-run28.json`
- `reports/editorial/citation-pipeline-test-20260612-author-draft-canary-v2-run28.md`
- `reports/architecture/run28-author-draft-canary-v2-evidence-map-20260614.md`

No intended Run 28 changes were made to:

- `docs/book`
- `.var/book.sqlite`
- `data/source_registry.json`
- raw captures
- `data/schema.sql`
- `scripts/daily_book_worker.py`
- source/claim/editorial statuses

## TDD sequence

1. Added `tests/test_llm_author_draft_canary_v2.py` before the production script existed.
2. Ran focused test and observed expected red failure:

```bash
.venv/bin/python -m pytest -q tests/test_llm_author_draft_canary_v2.py
```

Initial result: `4 failed`; root cause: `scripts/llm_author_draft_canary_v2.py` did not exist.

3. Implemented `scripts/llm_author_draft_canary_v2.py` with strict JSON validation, closed enums, safety flag validation, canary text validation, read-only SQLite access, and report-only outputs.
4. Ran focused test after implementation and observed one schema/safety ordering failure; patched validator to report do-not-say violations before evidence-atom absence where both apply.
5. Ran focused test again:

```bash
.venv/bin/python -m pytest -q tests/test_llm_author_draft_canary_v2.py
```

Result: `4 passed in 5.52s`.

6. Ran live Run 28 once and received a fail-closed schema mismatch because the LLM combined “migration and setup tooling contexts” in a way the atom detector did not recognize:

```bash
.venv/bin/python scripts/llm_author_draft_canary_v2.py --run-id citation-pipeline-test-20260612 --preflight-report reports/editorial/citation-pipeline-test-20260612-rebuilt-author-input-preflight-run27.json --rebuild-report reports/editorial/citation-pipeline-test-20260612-author-draft-input-rebuild-run26.json --output-dir reports/editorial --report-suffix run28 --reasoning-profile closed_loop_editorial --timeout-seconds 300
```

Result: exit `2`, error `schema_mismatch:draft_canary_text does not use an evidence-bound factual atom`.

7. Debugged the live output without trusting it as accepted output, using the same bridge with no validator to inspect the returned JSON. It clearly used the Run 26 atom as “documentation summaries name Hermes in migration and setup tooling contexts.” Patched the deterministic atom matcher to accept that conservative combined wording.
8. Reran focused tests and live command together:

```bash
.venv/bin/python -m pytest -q tests/test_llm_author_draft_canary_v2.py && .venv/bin/python scripts/llm_author_draft_canary_v2.py --run-id citation-pipeline-test-20260612 --preflight-report reports/editorial/citation-pipeline-test-20260612-rebuilt-author-input-preflight-run27.json --rebuild-report reports/editorial/citation-pipeline-test-20260612-author-draft-input-rebuild-run26.json --output-dir reports/editorial --report-suffix run28 --reasoning-profile closed_loop_editorial --timeout-seconds 300
```

Result:

- Focused tests: `4 passed in 5.57s`
- Live Run 28: exit `0`
- Output paths:
  - `reports/editorial/citation-pipeline-test-20260612-author-draft-canary-v2-run28.json`
  - `reports/editorial/citation-pipeline-test-20260612-author-draft-canary-v2-run28.md`

## Live Run 28 result

From `reports/editorial/citation-pipeline-test-20260612-author-draft-canary-v2-run28.json`:

- `selected_rebuilt_input_count`: `1`
- `draft_canary_count`: `1`
- `excluded_rebuilt_input_count`: `0`
- `llm_used`: `true`
- `provider`: `copilot`
- `model`: `gpt-5.5`
- `bridge`: `hermes_cli`
- `model_profile`: `closed_loop_editorial`
- `reasoning_status`: `high_reasoning_used`
- `draft_canary_type_counts`: `{"caveat_only_author_draft_canary_v2": 1}`
- `draft_canary_decision_counts`: `{"draft_canary_v2_created": 1}`
- `draft_canary_use_counts`: `{"caveat_only": 1}`
- `target_chapter_status_counts`: `{"suggested_only": 1}`
- `word_count`: `66`

Selected rebuilt input:

- `rebuilt_input_id`: `rebuilt_input_run26_enriched_caveat_only_cluster_4e8554045cfaf827bc68bcc5`
- `rebuilt_input_type`: `enriched_caveat_only_author_draft_input`
- `rebuilt_input_use`: `caveat_only`

Generated canary:

- `draft_canary_id`: `draft_canary_run28_caveat_only_v2_cluster_4e8554045cfaf827bc68bcc5`
- `draft_canary_type`: `caveat_only_author_draft_canary_v2`
- `draft_canary_decision`: `draft_canary_v2_created`
- `draft_canary_use`: `caveat_only`
- `draft_canary_only`: `true`
- `advisory_only`: `true`
- `author_allowed`: `false`
- `publication_approved`: `false`
- `eligible_for_claim_insertion`: `false`
- `eligible_for_authoring`: `false`
- `eligible_for_publication`: `false`
- `chapter_update_allowed`: `false`

## Tests added

`tests/test_llm_author_draft_canary_v2.py` covers:

- Selection of the current Run 27 canary-ready rebuilt input.
- Exclusion/fail-closed behavior for unsafe upstream inputs.
- Strict JSON schema validation with mocked GPT-5.5 bridge output.
- Invalid LLM JSON fail-closed behavior.
- Invalid enum fail-closed behavior.
- Missing safety flags fail-closed behavior.
- Approval/eligibility flag violations fail closed:
  - `author_allowed=true`
  - `publication_approved=true`
  - `eligible_for_claim_insertion=true`
  - `eligible_for_authoring=true`
  - `eligible_for_publication=true`
  - `chapter_update_allowed=true`
- Missing caveat/do-not-say/atoms fail closed.
- Canary text validation:
  - over 110 words fails closed
  - merely restating the caveat fails closed
  - missing evidence-bound factual atom fails closed
  - runtime-dependency claim fails closed
  - general operating-environment claim fails closed
  - web/phone access requirement claim fails closed
  - overgeneralization beyond migration/setup/import tooling fails closed
  - publication approval implication fails closed
  - chapter-readiness implication fails closed
- Weak/local provider fallback refused.
- Missing `closed_loop_editorial` profile fails closed.
- Report-only run against copied DB leaves source_notes, claims, editorial_reviews, statuses, source registry, raw captures, docs/book, schema, and daily worker unchanged.

## Verification commands and results

Executed:

```bash
git status --short
.venv/bin/python -m pytest -q tests/test_llm_author_draft_canary_v2.py
.venv/bin/python -m pytest -q
python3 scripts/verify_book_workspace.py
python3 scripts/verify_editorial_roles.py
python3 scripts/verify_book_citations.py
.venv/bin/python -m mkdocs build --strict
git status --short
```

Results:

- Focused Run 28 tests: `4 passed in 5.77s`
- Full pytest suite: `156 passed in 63.58s (0:01:03)`
- `python3 scripts/verify_book_workspace.py`: status `ok`, no errors, no warnings
- `python3 scripts/verify_editorial_roles.py`: status `ok`, no errors, no warnings
- `python3 scripts/verify_book_citations.py`: status `ok`, no raw ID hits, no unresolved hits
- `.venv/bin/python -m mkdocs build --strict`: exit `0`, documentation built successfully; MkDocs emitted existing informational nav warnings and Material for MkDocs warning

Verification generated protected artifacts. Restored them with:

```bash
git restore data/source_registry.json docs/book docs/entities docs/research/claims.md
rm -f docs/entities/boris-cherny.md
```

Post-restore protected diff checks:

```bash
git diff --name-only -- docs/book
git diff --name-only -- data/source_registry.json docs/book docs/entities docs/research/claims.md data/schema.sql scripts/daily_book_worker.py raw || true
```

Both returned no protected paths.

## DB/status delta summary

Counts from live Run 28 report and direct post-run DB check:

- `source_notes`: `365 -> 365`
- `claims`: `181 -> 181`
- `editorial_reviews`: `10 -> 10`
- `claims_inserted`: `0`
- `editorial_reviews_inserted`: `0`
- `changed_db`: `false`
- `changed_source_notes`: `false`
- `source_status_changed`: `false`
- `claim_status_changed`: `false`
- `editorial_status_changed`: `false`

## Protected artifact delta summary

From Run 28 report and post-restore diff checks:

- `changed_source_registry`: `false`
- `changed_raw_captures`: `false`
- `changed_docs_book`: `false`
- `changed_schema`: `false`
- `changed_daily_worker`: `false`
- `docs/book` diff after restore: none
- protected artifact diff after restore: none

## Safety conclusion

Run 28 created a short controlled caveat-only draft canary v2 inside report artifacts only. It is explicitly marked advisory/report-only and draft-canary-only. It does not approve authoring or publication, does not insert claims/editorial_reviews/source_notes, does not change statuses, does not mutate `docs/book`, and does not enable chapter updates.

## Recommendation for Run 29

Proceed to Run 29 as a report-only author-draft canary v2 red-team/containment and usefulness review. Run 29 should select only the Run 28 canary with all approval/eligibility/chapter flags false, revalidate the text and provenance, use GPT-5.5 through `closed_loop_editorial`, and decide whether the canary is safe/useful enough for another constrained metadata stage or should remain safe-reports-only. It must still not write DB rows, statuses, source registry, raw captures, docs/book, schema, or daily worker changes.
