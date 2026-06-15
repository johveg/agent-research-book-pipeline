# Scheduler wrapper contract — Run 38

Generated: 2026-06-15T08:43:49Z

## Summary

Run 38 upgrades the deterministic, report-only scheduler wrapper contract so the wrapper itself runs the protected mutation guard before snapshot, after snapshot, and compare subprocesses. It builds the safe daily-worker command contract but does not execute `scripts/daily_book_worker.py`, does not enable unattended production writes, and keeps wrapper-level commit/push authorization blocked.

## Selected scheduler mode

- mode: `report_only_daily`
- disposition: `safe_reports_only`
- selected verification profile: `report_only`

## Command that would be run later

```bash
python3 scripts/daily_book_worker.py citation-pipeline-test-20260612 --skip-capture --no-commit --skip-vector
```

Why it was not executed: Run 38 is dry-run/report-only, and future daily-worker execution still needs narrower mode controls plus mutation-guard enforcement before commit/push.

## Mutation guard before/after/compare flow

- mutation_guard_executed: `True`
- mutation_guard_ok: `True`
- profile used: `report_only`
- before snapshot: `/tmp/run38-before.json`
- after snapshot: `/tmp/run38-after.json`
- report path: `reports/editorial/citation-pipeline-test-20260612-mutation-guard-run38.json`
- failed checks: `[]`
- unexpected changed paths: `[]`

## Mutation guard strategy

- take before snapshot at scheduler wrapper start
- execute only a profile-approved safe command after future gates exist
- take after snapshot after worker exits
- compare before/after using selected verification profile
- block commit/push on guard failure, unexpected protected paths, DB/status deltas, hard flags, human-in-loop dependency, diff-check failure, or secrets

## Commit/push block strategy

- commit_allowed: `False`
- push_allowed: `False`
- commit block reasons: `['report_only_contract_blocks_commit']`
- push block reasons: `['report_only_contract_blocks_push']`

## Daily-worker write surfaces still blocked

- `capture_scripts`
- `entity_and_claim_extraction`
- `docs_entities_and_claims_pages`
- `source_registry_export`
- `chapter_publication_path`
- `git_commit_push`
- `runs_table_update`

## What remains missing before unattended execution

- daily worker mode split or flags that can disable extraction/entity/docs/source-registry side effects
- transition-engine evaluation wired before any mutation path
- mutation-guard compare wired before commit/push
- future explicit gates for source-note, claim, docs/book, and publication profiles
- machine-only safety reports proving no human-review production dependency

## Safety confirmations

- human_in_loop_dependency_added: `False`
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
- execution_performed: `False`

## Recommendation for Run 39

Add the next machine-only scheduler gate: require explicit daily-worker no-write flags or a wrapper-enforced no-op worker mode before any unattended execution path can be enabled.
