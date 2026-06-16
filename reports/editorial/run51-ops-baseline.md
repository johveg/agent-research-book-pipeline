# Run 51 OPS baseline

```json
{
  "run_id": "run51",
  "generated_at_utc": "2026-06-16T05:49:26Z",
  "stale_fixed_run_jobs_found": true,
  "production_daily_crontab_found": true,
  "production_daily_monitor_found": true,
  "ops_telegram_channel_configured": true,
  "timestamp_contract_currently_present": false,
  "production_daily_20260616_artifacts_present": false,
  "iteration_budget_requested": 180,
  "iteration_budget_supported": false
}
```

## Suspected cause
- crontab uses date -u while monitor expects Europe/Oslo-dated production-daily run IDs
- crontab sets TZ variable but cron schedule still follows system cron timezone UTC; 05:30 entry runs at 05:30 UTC, not 05:30 Europe/Oslo
- inline crontab does not redirect stdout/stderr to run-specific logs, hiding scheduler failure details
- production-daily-20260616 report/status/log artifacts are absent after expected due time

## Git status
```text
## main...origin/main
 M reports/daily/citation-pipeline-test-20260612.md
 M reports/telegram/production-monitor-latest.md

```

## Latest commits
```text
69c322c research: daily book pipeline update citation-pipeline-test-20260612
8d65615 Run 50: record final status correction
b6ad2b3 Run 50: record final clean status
32b0829 Run 50: record final status
5ee688f Run 50: draft introduction thesis report

```

## Crontab
```text

TZ=Europe/Oslo
30 5 * * * cd /home/hermoine/terefohealreboa && RUN_ID=$(date -u +production-daily-%Y%m%d) && python3 scripts/closed_loop_production_scheduler.py --run-id "$RUN_ID" --runtime-config config/closed_loop_runtime.json --mode production_daily --execute-once --allow-raw-collection --allow-extraction --allow-evidence-promotion --allow-author-editor-redteam --allow-guarded-book-publication --allow-daily-status-fallback --allow-commit-push-after-gates --install-schedule-after-success --send-telegram-status --output-json reports/editorial/$RUN_ID-production-execute-once.json --output-md reports/editorial/$RUN_ID-production-execute-once.md --telegram-status reports/telegram/production-daily-latest.md

```
