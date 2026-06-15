# Run 45 production scheduler

Generated: 2026-06-15T14:34:11Z

- run_id: `citation-pipeline-test-20260612`
- mode: `run45_schedule_install_artifact`
- final_disposition: `production_daily_completed`
- production_daily_completed: `True`
- schedule_installed: `True`
- schedule_installable: `True`

## Schedule command

```bash
cd /home/hermoine/terefohealreboa && RUN_ID=$(date -u +production-daily-%Y%m%d) && python3 scripts/closed_loop_production_scheduler.py --run-id "$RUN_ID" --runtime-config config/closed_loop_runtime.json --mode production_daily --execute-once --allow-raw-collection --allow-extraction --allow-evidence-promotion --allow-author-editor-redteam --allow-guarded-book-publication --allow-daily-status-fallback --allow-commit-push-after-gates --install-schedule-after-success --send-telegram-status --output-json reports/editorial/$RUN_ID-production-execute-once.json --output-md reports/editorial/$RUN_ID-production-execute-once.md --telegram-status reports/telegram/production-daily-latest.md
```
