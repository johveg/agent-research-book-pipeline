# Run 29 — Author-draft canary v2 red-team, containment, and usefulness review

Date: 2026-06-14
Run ID: `citation-pipeline-test-20260612`
Repository: `/home/hermoine/terefohealreboa`

## Objective

Red-team the Run 28 controlled caveat-only author-draft canary v2 using GPT-5.5 through the `closed_loop_editorial` profile. The review assesses safety containment, caveat preservation, do-not-say compliance, evidence-use correctness, provenance sufficiency, usefulness versus Run 24, residual risk, and whether the next stage may be another constrained metadata-only stage.

This run is advisory/report-only and does not approve authoring, publication, claim insertion, or chapter update.

## Inputs

Primary input:

- `reports/editorial/citation-pipeline-test-20260612-author-draft-canary-v2-run28.json`

Supporting inputs loaded or summarized:

- `reports/editorial/citation-pipeline-test-20260612-rebuilt-author-input-preflight-run27.json`
- `reports/editorial/citation-pipeline-test-20260612-author-draft-input-rebuild-run26.json`
- `reports/editorial/citation-pipeline-test-20260612-author-draft-canary-redteam-run25.json`
- `reports/editorial/citation-pipeline-test-20260612-author-draft-canary-run24.json`
- `reports/editorial/citation-pipeline-test-20260612-author-draft-input-preflight-run23.json`
- `reports/editorial/citation-pipeline-test-20260612-author-draft-input-run22b.json`
- `reports/editorial/citation-pipeline-test-20260612-closed-loop-state-machine-run22a.json`
- `reports/editorial/citation-pipeline-test-20260612-packet-redteam-gate-run21.json`
- `reports/editorial/citation-pipeline-test-20260612-narrative-packet-candidates-run20.json`
- `reports/editorial/citation-pipeline-test-20260612-cluster-quality-gate-run19.json`
- `reports/editorial/citation-pipeline-test-20260612-research-object-clusters-run18.json`
- `reports/editorial/citation-pipeline-test-20260612-downstream-eligibility-manifest-run17.json`
- `reports/editorial/citation-pipeline-test-20260612-persisted-source-support-rereview-notes-run16.json`
- `reports/editorial/citation-pipeline-test-20260612-source-support-rereview-run15.json`
- `config/closed_loop_state_machine.json`
- `config/reasoning_models.json`

## Files created by Run 29

- `scripts/llm_author_draft_canary_v2_redteam.py`
- `tests/test_llm_author_draft_canary_v2_redteam.py`
- `reports/editorial/citation-pipeline-test-20260612-author-draft-canary-v2-redteam-run29.json`
- `reports/editorial/citation-pipeline-test-20260612-author-draft-canary-v2-redteam-run29.md`
- `reports/architecture/run29-author-draft-canary-v2-redteam-evidence-map-20260614.md`

No intended Run 29 changes were made to:

- `docs/book`
- `.var/book.sqlite`
- `data/source_registry.json`
- raw captures
- `data/schema.sql`
- `scripts/daily_book_worker.py`
- source/claim/editorial statuses

## TDD sequence

1. Added `tests/test_llm_author_draft_canary_v2_redteam.py` before the production script existed.
2. Ran focused tests and observed expected red failure:

```bash
.venv/bin/python -m pytest -q tests/test_llm_author_draft_canary_v2_redteam.py
```

Result: `4 failed`, because `scripts/llm_author_draft_canary_v2_redteam.py` did not exist.

3. Implemented `scripts/llm_author_draft_canary_v2_redteam.py` with:

- strict JSON GPT-5.5 bridge call via `scripts/hermes_high_reasoning_json.py`
- `closed_loop_editorial` profile loading
- no weak/local fallback
- selection of only safe Run 28 canary v2 objects
- deterministic canary input safety validation
- deterministic review schema validation
- fail-closed handling for invalid JSON, invalid enums, missing flags, unsafe routing, and profile/model errors
- read-only DB access and before/after DB/status hash checks
- JSON and Markdown report output only

4. Reran focused tests:

```bash
.venv/bin/python -m pytest -q tests/test_llm_author_draft_canary_v2_redteam.py
```

Result: `4 passed in 6.46s`.

## Live Run 29 command

```bash
.venv/bin/python scripts/llm_author_draft_canary_v2_redteam.py --run-id citation-pipeline-test-20260612 --canary-v2-report reports/editorial/citation-pipeline-test-20260612-author-draft-canary-v2-run28.json --output-dir reports/editorial --report-suffix run29 --reasoning-profile closed_loop_editorial --timeout-seconds 300
```

Live result:

- exit code: `0`
- `selected_draft_canary_count`: `1`
- `reviewed_draft_canary_count`: `1`
- `excluded_draft_canary_count`: `0`
- JSON: `reports/editorial/citation-pipeline-test-20260612-author-draft-canary-v2-redteam-run29.json`
- Markdown: `reports/editorial/citation-pipeline-test-20260612-author-draft-canary-v2-redteam-run29.md`

## GPT-5.5/profile evidence

From the Run 29 JSON report:

- `llm_used`: `true`
- `provider`: `copilot`
- `model`: `gpt-5.5`
- `bridge`: `hermes_cli`
- `model_profile`: `closed_loop_editorial`
- `reasoning_status`: `high_reasoning_used`
- strict JSON parsing succeeded: `stdout_json_valid=true`
- no timeout: `timed_out=false`

## Red-team result

Reviewed canary:

- `draft_canary_id`: `draft_canary_run28_caveat_only_v2_cluster_4e8554045cfaf827bc68bcc5`
- `rebuilt_input_id`: `rebuilt_input_run26_enriched_caveat_only_cluster_4e8554045cfaf827bc68bcc5`
- `prior_draft_input_id`: `draft_input_run22b_caveat_only_cluster_4e8554045cfaf827bc68bcc5`
- `draft_canary_type`: `caveat_only_author_draft_canary_v2`
- `draft_canary_use`: `caveat_only`

Counts:

- `redteam_decision_counts`: `{"draft_canary_v2_passed": 1}`
- `canary_usefulness_counts`: `{"improved_but_still_thin": 1}`
- `closed_loop_disposition_counts`: `{"caveat_only": 1}`
- `recommended_next_stage_counts`: `{"build_constrained_authoring_metadata_candidate": 1}`

Interpretation:

- GPT-5.5 found the canary contained enough safety/provenance/usefulness improvement to pass as a caveat-only v2 canary.
- It remains thin and singleton/narrow; usefulness is limited to another constrained metadata stage.
- It is not authoring approval, not publication approval, not claim insertion, and not chapter update permission.

## Safety flags preserved

Run 29 review kept:

- `advisory_only`: `true`
- `draft_canary_only`: `true`
- `author_allowed`: `false`
- `publication_approved`: `false`
- `eligible_for_claim_insertion`: `false`
- `eligible_for_authoring`: `false`
- `eligible_for_publication`: `false`
- `chapter_update_allowed`: `false`

## Verification commands and results

Executed:

```bash
git status --short
.venv/bin/python -m pytest -q tests/test_llm_author_draft_canary_v2_redteam.py
.venv/bin/python -m pytest -q
python3 scripts/verify_book_workspace.py
python3 scripts/verify_editorial_roles.py
python3 scripts/verify_book_citations.py
.venv/bin/python -m mkdocs build --strict
git status --short
```

Results:

- Focused Run 29 tests: `4 passed in 6.65s`
- Full pytest suite: `160 passed in 70.11s (0:01:10)`
- `python3 scripts/verify_book_workspace.py`: status `ok`, no errors, no warnings
- `python3 scripts/verify_editorial_roles.py`: status `ok`, no errors, no warnings
- `python3 scripts/verify_book_citations.py`: status `ok`, no raw ID hits, no unresolved hits
- `.venv/bin/python -m mkdocs build --strict`: exit `0`, documentation built successfully; emitted existing Material/MkDocs informational warning and nav warnings

Verification generated protected artifacts. Restored them with:

```bash
git restore data/source_registry.json docs/book docs/entities docs/research/claims.md
rm -f docs/entities/boris-cherny.md
```

Post-restore protected diff check:

```bash
git diff --name-only -- data/source_registry.json docs/book docs/entities docs/research/claims.md data/schema.sql scripts/daily_book_worker.py raw || true
```

Result: no protected paths.

## DB/status delta summary

From Run 29 JSON and direct DB count check:

- `source_notes`: `365 -> 365`
- `claims`: `181 -> 181`
- `editorial_reviews`: `10 -> 10`
- `changed_db`: `false`
- `changed_source_notes`: `false`
- `claims_inserted`: `0`
- `editorial_reviews_inserted`: `0`
- `source_status_changed`: `false`
- `claim_status_changed`: `false`
- `editorial_status_changed`: `false`

## Protected artifact delta summary

- `changed_source_registry`: `false`
- `changed_raw_captures`: `false`
- `changed_docs_book`: `false`
- `changed_schema`: `false`
- `changed_daily_worker`: `false`
- post-restore protected diff: none

## Conclusion

Run 29 passed the Run 28 v2 canary as a safe caveat-only canary for another constrained metadata stage. The result is explicitly not publication, authoring, claim insertion, chapter prose, chapter update, or human/editor approval. The key residual risk remains downstream prose-promotion from tooling adjacency into dependency or operating-environment language.

## Recommendation for Run 30

Proceed to a constrained authoring-metadata candidate stage only, still report-only. Run 30 should transform the passed canary into structured metadata for possible later author review, not chapter prose. It must preserve all false approval/eligibility/chapter flags, keep the caveat exact, keep source/candidate provenance explicit, and make no DB, status, source registry, raw capture, docs/book, schema, or daily worker changes.
