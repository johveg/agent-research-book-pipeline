# Run 30 — Constrained authoring-metadata candidate

Date: 2026-06-14
Run ID: `citation-pipeline-test-20260612`
Repository: `/home/hermoine/terefohealreboa`

## Objective

Transform the Run 29-passed v2 canary into a constrained authoring-metadata candidate as structured metadata only. This stage must not create new author prose, expanded prose, chapter-ready prose, claim insertion, authoring approval, publication approval, or chapter-update permission.

## Inputs

Primary input:

- `reports/editorial/citation-pipeline-test-20260612-author-draft-canary-v2-redteam-run29.json`

Cross-check inputs:

- `reports/editorial/citation-pipeline-test-20260612-author-draft-canary-v2-run28.json`
- `reports/editorial/citation-pipeline-test-20260612-author-draft-input-rebuild-run26.json`

Supporting lineage paths recorded in the report:

- `reports/editorial/citation-pipeline-test-20260612-rebuilt-author-input-preflight-run27.json`
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

## Files created by Run 30

- `scripts/build_constrained_authoring_metadata.py`
- `tests/test_build_constrained_authoring_metadata.py`
- `reports/editorial/citation-pipeline-test-20260612-constrained-authoring-metadata-run30.json`
- `reports/editorial/citation-pipeline-test-20260612-constrained-authoring-metadata-run30.md`
- `reports/architecture/run30-constrained-authoring-metadata-evidence-map-20260614.md`

## TDD evidence

1. Added `tests/test_build_constrained_authoring_metadata.py` before the script existed.
2. Ran focused test and observed expected red failure:

```bash
.venv/bin/python -m pytest -q tests/test_build_constrained_authoring_metadata.py
```

Result: `4 failed`, with missing script error:

```text
can't open file '/home/hermoine/terefohealreboa/scripts/build_constrained_authoring_metadata.py': [Errno 2] No such file or directory
```

3. Implemented `scripts/build_constrained_authoring_metadata.py` as deterministic packaging only.
4. Reran focused tests:

```bash
.venv/bin/python -m pytest -q tests/test_build_constrained_authoring_metadata.py
```

Result: `4 passed in 3.18s`.

## Live Run 30 command

```bash
.venv/bin/python scripts/build_constrained_authoring_metadata.py \
  --run-id citation-pipeline-test-20260612 \
  --redteam-report reports/editorial/citation-pipeline-test-20260612-author-draft-canary-v2-redteam-run29.json \
  --canary-v2-report reports/editorial/citation-pipeline-test-20260612-author-draft-canary-v2-run28.json \
  --rebuild-report reports/editorial/citation-pipeline-test-20260612-author-draft-input-rebuild-run26.json \
  --output-dir reports/editorial \
  --report-suffix run30
```

Result:

- exit code: `0`
- `selected_redteam_count`: `1`
- `metadata_candidate_count`: `1`
- `excluded_redteam_count`: `0`
- `metadata_type_counts`: `{"constrained_authoring_metadata_candidate": 1}`
- `metadata_decision_counts`: `{"metadata_candidate_created": 1}`
- `metadata_use_counts`: `{"caveat_only": 1}`
- `canary_usefulness_counts`: `{"improved_but_still_thin": 1}`
- `target_chapter_status_counts`: `{"suggested_only": 1}`

## GPT/profile evidence

Run 30 did not call GPT-5.5. It performed deterministic packaging over existing GPT-5.5 outputs from Runs 26–29.

From the JSON report:

- `llm_used`: `false`
- `provider`: `null`
- `model`: `null`
- `bridge`: `null`
- `model_profile`: `null`
- `reasoning_status`: `deterministic_packaging_only`
- `weak_local_fallback_refused`: `true`

## Metadata candidate

Created candidate:

- `metadata_id`: `metadata_run30_constrained_authoring_4e8554045cfaf827bc68bcc5`
- `draft_canary_id`: `draft_canary_run28_caveat_only_v2_cluster_4e8554045cfaf827bc68bcc5`
- `rebuilt_input_id`: `rebuilt_input_run26_enriched_caveat_only_cluster_4e8554045cfaf827bc68bcc5`
- `prior_draft_input_id`: `draft_input_run22b_caveat_only_cluster_4e8554045cfaf827bc68bcc5`
- `metadata_type`: `constrained_authoring_metadata_candidate`
- `metadata_decision`: `metadata_candidate_created`
- `metadata_use`: `caveat_only`
- `canary_usefulness`: `improved_but_still_thin`
- `target_chapter_status`: `suggested_only`

The candidate includes:

- exact lineage fields: source review, note, manifest, cluster, packet, rebuilt input, canary, red-team
- Run 28 canary text quoted as report-only canary text, not prose approval
- Run 29 usefulness/thinness warning
- allowed authoring intent metadata
- forbidden authoring intent metadata
- allowed evidence-bound factual atoms
- unsupported inferences
- required caveat
- do-not-say requirements
- provenance requirements
- target placement suggestions only
- promotion blockers
- next-stage options excluding docs/book integration
- residual risks
- hard safety flags

## Safety flags preserved

The candidate keeps:

- `advisory_only`: `true`
- `singleton_metadata_candidate`: `true`
- `author_allowed`: `false`
- `publication_approved`: `false`
- `eligible_for_claim_insertion`: `false`
- `eligible_for_authoring`: `false`
- `eligible_for_publication`: `false`
- `chapter_update_allowed`: `false`

No field named `draft_prose`, `new_draft_prose`, `chapter_ready_prose`, `chapter_prose`, `publishable_wording`, or `citation_resolved_chapter_text` is emitted.

## Verification commands and results

Executed:

```bash
git status --short
.venv/bin/python -m pytest -q tests/test_build_constrained_authoring_metadata.py
.venv/bin/python -m pytest -q
python3 scripts/verify_book_workspace.py
python3 scripts/verify_editorial_roles.py
python3 scripts/verify_book_citations.py
.venv/bin/python -m mkdocs build --strict
git status --short
```

Results:

- Focused Run 30 tests: `4 passed in 3.09s`
- Full pytest suite: `164 passed in 72.89s (0:01:12)`
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

From the Run 30 report and direct DB count check:

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

Run 30 successfully created a constrained authoring-metadata candidate from the Run 29-passed canary. It is structured metadata only and does not approve authoring, publication, claim insertion, chapter prose, or chapter updates.

## Recommendation for Run 31

Run a report-only constrained authoring-metadata preflight/red-team gate. It should verify that this metadata object is useful and safe as metadata only before any later author-facing stage, while preserving all approval/publication/chapter flags as false and avoiding DB/status/source-registry/raw/docs/book/schema/daily-worker changes.
