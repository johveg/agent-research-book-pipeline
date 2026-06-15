# Protected mutation guard report

Generated: 2026-06-15T10:39:20Z

- ok: `False`
- profile: `closed_loop_runner_shell`
- recommendation: `stop_and_investigate_unexpected_mutation`
- human_in_loop_dependency_added: `False`

## Changed paths

Allowed:
- `logs/`
- `reports/architecture/run41-closed-loop-daily-runner-evidence-map-20260614.md`
- `reports/editorial/citation-pipeline-test-20260612-closed-loop-daily-runner-run41.json`
- `reports/editorial/citation-pipeline-test-20260612-closed-loop-daily-runner-run41.md`
- `reports/editorial/citation-pipeline-test-20260612-mutation-guard-run41.json`
- `reports/editorial/citation-pipeline-test-20260612-mutation-guard-run41.md`
- `reports/telegram/`
- `scripts/closed_loop_daily_runner.py`
- `scripts/closed_loop_event_ledger.py`
- `scripts/daily_book_worker.py`
- `scripts/protected_mutation_guard.py`
- `tests/test_closed_loop_daily_runner.py`
- `tests/test_closed_loop_event_ledger.py`
- `tests/test_daily_book_worker_no_write_controls.py`

Unexpected:

## DB delta

```json
{}
```

## Failed checks

- `protected_path_changed:.var/book.sqlite`
