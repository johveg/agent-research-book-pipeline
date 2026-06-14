# Run 37 scheduler wrapper contract evidence map

Generated: 2026-06-14T20:31:17Z

## Scope

Run 37 creates a deterministic, report-only scheduler wrapper contract for future before/after mutation-guard enforcement around the daily worker. It does not edit `scripts/daily_book_worker.py`, does not execute the daily worker, and does not enable unattended production writes.

- GPT-5.5 used: `false`
- report_only: `true`
- dry_run: `true`
- execution_performed: `false`
- human_in_loop_dependency_added: `false`

## Files created or changed

- `scripts/scheduler_wrapper_contract.py`
- `tests/test_scheduler_wrapper_contract.py`
- `scripts/protected_mutation_guard.py`
- `reports/editorial/citation-pipeline-test-20260612-scheduler-wrapper-contract-run37.json`
- `reports/editorial/citation-pipeline-test-20260612-scheduler-wrapper-contract-run37.md`
- `reports/editorial/citation-pipeline-test-20260612-mutation-guard-run37.json`
- `reports/editorial/citation-pipeline-test-20260612-mutation-guard-run37.md`
- `reports/architecture/run37-scheduler-wrapper-contract-evidence-map-20260614.md`

`scripts/protected_mutation_guard.py` was updated only to classify Run 37 scheduler wrapper/test files as allowed control-plane code under `control_plane_code_only`.

## Scheduler contract

- mode: `report_only_daily`
- disposition: `safe_reports_only`
- selected_verification_profile: `report_only`
- commit_allowed: `False`
- push_allowed: `False`
- commit_block_reasons: `['report_only_contract_blocks_commit']`
- push_block_reasons: `['report_only_contract_blocks_push']`

Daily-worker command contract:
```bash
python3 scripts/daily_book_worker.py citation-pipeline-test-20260612 --skip-capture --no-commit --skip-vector
```

Execution is refused by default and in Run 37 because the current daily worker still lacks explicit flags to disable entity/claim extraction, docs/entities and claims-page mutation, source-registry export, and runs-table metadata writes.

## Mutation guard comparison

- profile: `control_plane_code_only`
- ok: `True`
- failed_checks: `[]`
- recommendation: `proceed_with_profile_scope`

Allowed changed paths:
- `reports/editorial/citation-pipeline-test-20260612-mutation-guard-run37.json`
- `reports/editorial/citation-pipeline-test-20260612-mutation-guard-run37.md`
- `reports/editorial/citation-pipeline-test-20260612-scheduler-wrapper-contract-run37.json`
- `reports/editorial/citation-pipeline-test-20260612-scheduler-wrapper-contract-run37.md`
- `scripts/protected_mutation_guard.py`
- `scripts/scheduler_wrapper_contract.py`
- `tests/test_scheduler_wrapper_contract.py`

Unexpected changed paths:
- none

## DB and status deltas

DB delta:
```json
{}
```

Status hash delta:
```json
{}
```

Reduced DB counts: `{"claims": 181, "editorial_reviews": 10, "source_notes": 365}`

## Protected path summary

- `.var/book.sqlite` changed: `False`
- `data/schema.sql` changed: `False`
- `data/source_registry.json` changed: `False`
- `docs/book` changed: `False`
- `docs/entities` changed: `False`
- `docs/research/claims.md` changed: `False`
- `raw` changed: `False`
- `scripts/daily_book_worker.py` changed: `False`
- protected diff output empty: `True`

## Safety confirmations

- changed_db: `False`
- changed_source_notes: `False`
- changed_source_registry: `False`
- changed_raw_captures: `False`
- changed_docs_book: `False`
- changed_schema: `False`
- changed_daily_worker: `False`
- claims_inserted: `0`
- editorial_reviews_inserted: `0`
- source_status_changed: `False`
- claim_status_changed: `False`
- editorial_status_changed: `False`
- human_in_loop_dependency_added: `False`

Hard flags:
- author_allowed: `False`
- publication_approved: `False`
- eligible_for_claim_insertion: `False`
- eligible_for_authoring: `False`
- eligible_for_publication: `False`
- chapter_update_allowed: `False`

## Verification evidence

- Before snapshot: `/tmp/run37-before.json`
- Focused RED observed before implementation: `5 failed` because `scripts/scheduler_wrapper_contract.py` was missing.
- Focused scheduler wrapper tests: `5 passed`.
- Focused mutation guard regression tests: `9 passed`.
- Scheduler wrapper dry-run wrote JSON/Markdown reports and did not execute the daily worker.
- Mutation guard compare passed with `control_plane_code_only`.
- JSON validation passed for scheduler contract and mutation guard reports.
- Protected diff command output was empty.

## Current git status before final commit checks

```text
M scripts/protected_mutation_guard.py
?? reports/editorial/citation-pipeline-test-20260612-mutation-guard-run37.json
?? reports/editorial/citation-pipeline-test-20260612-mutation-guard-run37.md
?? reports/editorial/citation-pipeline-test-20260612-scheduler-wrapper-contract-run37.json
?? reports/editorial/citation-pipeline-test-20260612-scheduler-wrapper-contract-run37.md
?? scripts/scheduler_wrapper_contract.py
?? tests/test_scheduler_wrapper_contract.py
```

## Recommendation for Run 38

Add a report-only scheduler wrapper dry-run that invokes the protected mutation guard snapshot/compare subprocesses itself while still not executing `daily_book_worker.py`. Keep daily-worker edits and unattended writes disabled until the wrapper can prove profile-specific DB/status/protected-path safety end-to-end.
