# Run 32 — promotion-contract authoring metadata evidence map — 2026-06-14

## Objective

Create and test a report-only closed-loop promotion-contract update plan for the Run 31-approved constrained authoring-metadata preflight state.

This run is deterministic control-plane/configuration work over existing reports. It does not call GPT-5.5, generate prose, persist metadata, or modify protected publication/status artifacts.

## Primary inputs

- `reports/editorial/citation-pipeline-test-20260612-constrained-authoring-metadata-preflight-run31.json`
- `reports/editorial/citation-pipeline-test-20260612-constrained-authoring-metadata-run30.json`
- `config/closed_loop_state_machine.json`

## Created artifacts

- `scripts/update_closed_loop_promotion_contract.py`
- `tests/test_update_closed_loop_promotion_contract.py`
- `reports/editorial/citation-pipeline-test-20260612-promotion-contract-authoring-metadata-run32.json`
- `reports/editorial/citation-pipeline-test-20260612-promotion-contract-authoring-metadata-run32.md`
- `reports/architecture/run32-promotion-contract-authoring-metadata-evidence-map-20260614.md`

## TDD evidence

Focused RED run before implementation:

```bash
.venv/bin/python -m pytest -q tests/test_update_closed_loop_promotion_contract.py
```

Result: `5 failed`; expected failure because `scripts/update_closed_loop_promotion_contract.py` did not exist.

Focused GREEN run after implementation and one test-helper fix:

```bash
.venv/bin/python -m pytest -q tests/test_update_closed_loop_promotion_contract.py
```

Result: `5 passed in 18.26s`.

## Live Run 32 command

```bash
.venv/bin/python scripts/update_closed_loop_promotion_contract.py \
  --run-id citation-pipeline-test-20260612 \
  --preflight-report reports/editorial/citation-pipeline-test-20260612-constrained-authoring-metadata-preflight-run31.json \
  --metadata-report reports/editorial/citation-pipeline-test-20260612-constrained-authoring-metadata-run30.json \
  --state-machine-config config/closed_loop_state_machine.json \
  --output-dir reports/editorial \
  --report-suffix run32
```

Result: exit `0`.

## Live Run 32 decision summary

- `selected_metadata_preflight_count`: `1`
- `promotion_contract_candidate_count`: `1`
- `excluded_metadata_preflight_count`: `0`
- `llm_used`: `false`
- `provider`: `null`
- `model`: `null`
- `bridge`: `null`
- `model_profile`: `null`
- `config_update_needed`: `true`
- `config_updated`: `false`
- `state_count_before`: `21`
- `state_count_after`: `21`
- `transition_count_before`: `10`
- `transition_count_after`: `10`
- `disposition_count_before`: `14`
- `disposition_count_after`: `14`
- `promotion_contract_decision_counts`: `{"config_update_needed": 1}`
- `transition_decision_counts`: `{"allowed_for_future_promotion_contract_update": 1}`
- `recommended_next_stage_counts`: `{"run_config_write_promotion_contract_update": 1}`
- `human_in_loop_dependency_added`: `false`

Counts before/after are unchanged because default mode is report-only and `--write-config` was not used.

## Proposed config additions

Run 32 proposed but did not apply additions for authoring-metadata promotion-contract vocabulary:

- states for constrained authoring metadata candidate/preflight/contract-ready/future context candidate, plus missing automated routing states
- dispositions for metadata preflight and promotion-contract routing
- transitions:
  - `constrained_authoring_metadata_candidate -> constrained_authoring_metadata_preflight_passed`
  - `constrained_authoring_metadata_preflight_passed -> authoring_metadata_promotion_contract_ready`
  - `authoring_metadata_promotion_contract_ready -> constrained_authoring_context_candidate` as future-run-only

The future context-candidate transition remains non-approving and must not imply authoring, publication, claim insertion, or docs/book update.

## Safety invariants verified by tests and report

- `author_allowed=false`
- `publication_approved=false`
- `eligible_for_claim_insertion=false`
- `eligible_for_authoring=false`
- `eligible_for_publication=false`
- `chapter_update_allowed=false`
- `human_in_loop_dependency_added=false`
- no `human_review_required` production dependency added
- no weak/local fallback used
- GPT-5.5 advisory reasoning remains non-human/editor approval
- blocked editorial state remains dominant over chapter mutation paths

## Verification commands

```bash
git status --short
.venv/bin/python -m pytest -q tests/test_update_closed_loop_promotion_contract.py
.venv/bin/python -m pytest -q
python3 scripts/verify_book_workspace.py
python3 scripts/verify_editorial_roles.py
python3 scripts/verify_book_citations.py
.venv/bin/python -m mkdocs build --strict
git status --short
```

Results:

- focused Run 32 tests: `5 passed in 18.55s`
- full pytest suite: `173 passed in 97.43s`
- `verify_book_workspace.py`: `status: ok`
- `verify_editorial_roles.py`: `status: ok`
- `verify_book_citations.py`: `status: ok`
- MkDocs strict: exit `0`; documentation built successfully, with existing nav/material warnings

## Protected artifact cleanup

Verification regenerated protected artifacts, then they were restored:

```bash
git restore data/source_registry.json docs/book docs/entities docs/research/claims.md
rm -f docs/entities/boris-cherny.md
```

Post-cleanup DB counts:

```json
{"claims": 181, "editorial_reviews": 10, "source_notes": 365}
```

Protected diff check for `data/source_registry.json`, `docs/book`, `docs/entities`, `docs/research/claims.md`, `data/schema.sql`, `scripts/daily_book_worker.py`, and `raw` returned no protected paths.

## Delta summary

- DB changed: `false`
- source_notes delta: `0`
- claims delta: `0`
- editorial_reviews delta: `0`
- source_registry changed: `false`
- raw captures changed: `false`
- docs/book changed: `false`
- schema changed: `false`
- daily worker changed: `false`
- source status changed: `false`
- claim status changed: `false`
- editorial status changed: `false`

## Recommendation

Run 33 should be an explicit report-only or opt-in config-write promotion-contract update run. If the user authorizes `--write-config`, it should apply the proposed authoring-metadata states/dispositions/transitions idempotently, then rerun the same test/verification suite. If not writing config, keep Run 33 as a dry-run review of the proposed additions before a later constrained authoring-context candidate stage.
