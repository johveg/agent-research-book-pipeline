# Run 33 config-write promotion-contract evidence map

Generated: 2026-06-14T16:49:25.244721Z

## Scope

Run 33 applied the Run 32 authoring-metadata promotion-contract update to `config/closed_loop_state_machine.json` using `scripts/update_closed_loop_promotion_contract.py --write-config`, then reran the same write command to prove idempotency.

This was a deterministic config-write/control-plane run. It did not perform authoring, publication, claim insertion, DB mutation, source-registry mutation, raw capture mutation, docs/book mutation, docs/entities mutation, schema mutation, or daily-worker mutation.

## Commands executed

- Baseline captured: git status, config counts/hash, protected path hashes, DB counts/status hashes.
- Pre-write focused tests: `.venv/bin/python -m pytest -q tests/test_update_closed_loop_promotion_contract.py` -> `5 passed in 17.77s`.
- First config write: `.venv/bin/python scripts/update_closed_loop_promotion_contract.py ... --report-suffix run33 --write-config` -> `ok=true`, `config_update_needed=true`, `config_updated=true`.
- Second config write/idempotency rerun: same command -> `ok=true`, `config_update_needed=false`, `config_updated=false`.
- Post-write focused tests: `.venv/bin/python -m pytest -q tests/test_update_closed_loop_promotion_contract.py` -> `5 passed in 18.42s`.
- Reduced DB verification: `source_notes=365`, `claims=181`, `editorial_reviews=10`.
- Protected diff check: `git diff --name-only -- data/source_registry.json docs/book docs/entities docs/research/claims.md data/schema.sql scripts/daily_book_worker.py raw` -> empty output.
- JSON validation: `python3 -m json.tool` passed for Run 33 JSON report and `config/closed_loop_state_machine.json`.

## Baseline and result counts

- Baseline state count: 21
- First write state count: 21 -> 28
- Idempotency rerun state count: 28 -> 28
- Baseline transition count: 10
- First write transition count: 10 -> 13
- Idempotency rerun transition count: 13 -> 13
- Baseline disposition count: 14
- First write disposition count: 14 -> 18
- Idempotency rerun disposition count: 18 -> 18

## Applied config additions

### States
- `constrained_authoring_metadata_candidate`
- `constrained_authoring_metadata_preflight_passed`
- `authoring_metadata_promotion_contract_ready`
- `constrained_authoring_context_candidate`
- `needs_more_sources`
- `needs_better_authoring_metadata`
- `exclude_from_pipeline`

### Automated dispositions
- `metadata_preflight_passed`
- `ready_for_promotion_contract_update`
- `update_closed_loop_promotion_contract_for_authoring_metadata`
- `needs_better_authoring_metadata`

### Transitions
- `constrained_authoring_metadata_candidate` -> `constrained_authoring_metadata_preflight_passed` (`current_or_past_stage`; allowed future run: `None`)
- `constrained_authoring_metadata_preflight_passed` -> `authoring_metadata_promotion_contract_ready` (`future_run_only`; allowed future run: `update_closed_loop_promotion_contract_for_authoring_metadata`)
- `authoring_metadata_promotion_contract_ready` -> `constrained_authoring_context_candidate` (`future_run_only`; allowed future run: `build_constrained_authoring_context_candidate`)

## Required vocabulary validation

All required Run 33 states, dispositions, and transitions are represented after the config write. The third transition remains `future_run_only` and includes guards that keep authoring approval, publication approval, claim insertion, and docs/book updates false/not implied.

Required states checked:
- `constrained_authoring_metadata_candidate`
- `constrained_authoring_metadata_preflight_passed`
- `authoring_metadata_promotion_contract_ready`
- `constrained_authoring_context_candidate`
- `needs_more_sources`
- `needs_better_authoring_metadata`
- `source_context_unclear`
- `exclude_from_pipeline`
- `contradiction_review_required`
- `safe_reports_only`
- `blocked_for_publication_by_policy`

Required dispositions checked:
- `metadata_preflight_passed`
- `ready_for_promotion_contract_update`
- `update_closed_loop_promotion_contract_for_authoring_metadata`
- `needs_better_authoring_metadata`
- `caveat_only`
- `safe_reports_only`
- `needs_more_sources`
- `source_context_unclear`
- `exclude_from_pipeline`
- `contradiction_review_required`

Required transitions checked:
- `constrained_authoring_metadata_candidate -> constrained_authoring_metadata_preflight_passed`
- `constrained_authoring_metadata_preflight_passed -> authoring_metadata_promotion_contract_ready`
- `authoring_metadata_promotion_contract_ready -> constrained_authoring_context_candidate`

## Hard invariant evidence

- `human_in_loop_dependency_added`: first write `False`, second write `False`.
- `author_allowed`: `False`
- `publication_approved`: `False`
- `eligible_for_claim_insertion`: `False`
- `eligible_for_authoring`: `False`
- `eligible_for_publication`: `False`
- `chapter_update_allowed`: `False`
- `required_production_human_stop_added`: `False`
- `source_notes_written`: `False`
- `claims_inserted`: `False`
- `editorial_reviews_inserted`: `False`
- `docs_book_modified`: `False`
- `schema_modified`: `False`
- `daily_worker_modified`: `False`
- `human_review_required` / `requires_human_review`: not present in config validation scan.

## DB and protected-path evidence

DB count deltas:
- `claims`: `0`
- `editorial_reviews`: `0`
- `source_notes`: `0`

DB status/content hash changes:
- `claims_status` changed: `False`
- `editorial_reviews` changed: `False`
- `source_notes` changed: `False`
- `sources_status` changed: `False`

Protected path changes:
- `data/schema.sql` changed: `False`
- `data/source_registry.json` changed: `False`
- `docs/book` changed: `False`
- `docs/entities` changed: `False`
- `docs/research/claims.md` changed: `False`
- `raw` changed: `False`
- `scripts/daily_book_worker.py` changed: `False`

## Reports

- `reports/editorial/citation-pipeline-test-20260612-promotion-contract-authoring-metadata-run33.json`
- `reports/editorial/citation-pipeline-test-20260612-promotion-contract-authoring-metadata-run33.md`
- `reports/architecture/run33-config-write-promotion-contract-evidence-map-20260614.md`

## Recommendation

Recommended Run 34: build a reusable closed-loop transition engine that consumes the state machine and promotion-contract vocabulary as source-of-truth, supports dry-run/write-mode separation, centralizes guard evaluation, and emits deterministic reports. It must not integrate into the daily worker or enable docs/book, DB, claim, source-note, authoring, or publication writes yet.
