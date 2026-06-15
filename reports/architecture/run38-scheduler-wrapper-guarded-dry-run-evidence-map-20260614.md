# Run 38 scheduler wrapper guarded dry-run evidence map

Run ID: `citation-pipeline-test-20260612`

Run title: Scheduler wrapper end-to-end mutation-guard dry run

## Scope

Run 38 upgrades `scripts/scheduler_wrapper_contract.py` so report-only scheduler wrapper mode can run its own protected mutation guard before snapshot, after snapshot, and compare subprocesses while still refusing to execute `scripts/daily_book_worker.py`.

## Files changed or created

- Changed: `scripts/scheduler_wrapper_contract.py`
- Changed: `tests/test_scheduler_wrapper_contract.py`
- Created: `reports/editorial/citation-pipeline-test-20260612-scheduler-wrapper-contract-run38.json`
- Created: `reports/editorial/citation-pipeline-test-20260612-scheduler-wrapper-contract-run38.md`
- Created: `reports/editorial/citation-pipeline-test-20260612-mutation-guard-run38.json`
- Created: `reports/editorial/citation-pipeline-test-20260612-mutation-guard-run38.md`
- Created: `reports/architecture/run38-scheduler-wrapper-guarded-dry-run-evidence-map-20260614.md`

`reports/daily/citation-pipeline-test-20260612.md` was already modified before this Run 38 work began and is not a Run 38 mutation.

## Deterministic behavior evidence

- GPT-5.5 used: `false`
- LLM/provider/model/bridge/profile in wrapper report: `null`
- Wrapper mode: `report_only_daily`
- Disposition: `safe_reports_only`
- Selected verification profile for modeled worker mode: `report_only`
- Wrapper remains report-only: `true`
- Wrapper dry-run: `true`

## Daily-worker execution evidence

Daily-worker command contract:

```bash
python3 scripts/daily_book_worker.py citation-pipeline-test-20260612 --skip-capture --no-commit --skip-vector
```

- `daily_worker_command_would_execute`: `false`
- `execution_enabled`: `false`
- `execution_performed`: `false`
- `scripts/daily_book_worker.py` executed: `false`
- `scripts/daily_book_worker.py` modified: `false`

Execution remains refused because the current daily worker still lacks explicit flags to disable entity/claim extraction, docs/entities and claims-page mutation, source-registry export, and runs-table metadata writes.

## Internal mutation guard flow evidence

Live Run 38 command performed by the wrapper:

1. `snapshot --output /tmp/run38-before.json`
2. Build safe daily-worker command contract without executing it.
3. `snapshot --output /tmp/run38-after.json`
4. `compare --before /tmp/run38-before.json --after /tmp/run38-after.json --profile report_only --output reports/editorial/citation-pipeline-test-20260612-mutation-guard-run38.json`
5. Read and embed the mutation guard JSON into `reports/editorial/citation-pipeline-test-20260612-scheduler-wrapper-contract-run38.json`.

Mutation guard result:

- `mutation_guard_executed`: `true`
- `mutation_guard_ok`: `true`
- `failed_checks`: `[]`
- `unexpected_changed_paths`: `[]`
- `db_delta`: `{}`
- `status_hash_delta`: `{}`
- `protected_path_delta` all false for:
  - `.var/book.sqlite`
  - `data/schema.sql`
  - `data/source_registry.json`
  - `docs/book`
  - `docs/entities`
  - `docs/research/claims.md`
  - `raw`
  - `scripts/daily_book_worker.py`

## Wrapper commit/push policy evidence

Wrapper-level policy remains blocked in report-only contract mode:

- `commit_allowed`: `false`
- `push_allowed`: `false`
- `commit_block_reasons`: `['report_only_contract_blocks_commit']`
- `push_block_reasons`: `['report_only_contract_blocks_push']`

External repository commit/push remains allowed only after deterministic tests, mutation guard, reduced verification, secrets scan, and protected path checks pass.

## Focused test evidence

Command:

```bash
.venv/bin/python -m pytest -q tests/test_scheduler_wrapper_contract.py
```

Result:

```text
10 passed
```

Coverage added for command builders, dry-run no-execution, embedding guard ok=true, blocking on ok=false/unexpected paths/human-in-loop/hard flags, fail-closed subprocess and missing artifact cases, report-only commit/push blocks, selected profile mapping, safe command contract flags, and protected no-write checks.

## Reduced verification evidence

Commands executed:

```bash
python3 -m json.tool reports/editorial/citation-pipeline-test-20260612-scheduler-wrapper-contract-run38.json >/dev/null
python3 -m json.tool reports/editorial/citation-pipeline-test-20260612-mutation-guard-run38.json >/dev/null
git diff --check
git diff --name-only -- data/source_registry.json docs/book docs/entities docs/research/claims.md data/schema.sql scripts/daily_book_worker.py raw || true
python3 - <<'PY'
import sqlite3, json
con=sqlite3.connect('.var/book.sqlite')
print(json.dumps({t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ["source_notes","claims","editorial_reviews"]}, sort_keys=True))
con.close()
PY
```

Observed DB counts:

```json
{"claims": 218, "editorial_reviews": 10, "source_notes": 445}
```

Protected path diff command returned no paths.

## Safety confirmations

- `human_in_loop_dependency_added`: `false`
- `changed_db`: `false`
- `changed_source_notes`: `false`
- `changed_source_registry`: `false`
- `changed_raw_captures`: `false`
- `changed_docs_book`: `false`
- `changed_schema`: `false`
- `changed_daily_worker`: `false`
- `claims_inserted`: `0`
- `editorial_reviews_inserted`: `0`
- `source_status_changed`: `false`
- `claim_status_changed`: `false`
- `editorial_status_changed`: `false`
- author/publication/chapter hard flags: all `false`

## What remains missing before unattended execution

- Daily-worker mode split or flags that can disable extraction/entity/docs/source-registry side effects.
- Transition-engine evaluation wired before any mutation path.
- Future explicit gates for source-note, claim, docs/book, and publication profiles.
- Machine-only safety reports proving no human-review production dependency.
- Commit/push authorization remains outside report-only wrapper mode.

## Recommendation for Run 39

Add the next machine-only scheduler gate: require explicit daily-worker no-write flags or a wrapper-enforced no-op worker mode before any unattended execution path can be enabled.
