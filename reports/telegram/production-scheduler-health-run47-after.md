# Run 46 production scheduler health

Generated: 2026-06-15T17:14:44Z

- mode: `production_status`
- gpt55_used: `False`
- raw_collection_performed: `False`
- extraction_performed: `False`
- evidence_promotion_performed: `False`

## Schedule command

```bash
30 5 * * * cd /home/hermoine/terefohealreboa && RUN_ID=$(date -u +production-daily-%Y%m%d) && python3 scripts/closed_loop_production_scheduler.py --run-id "$RUN_ID" --runtime-config config/closed_loop_runtime.json --mode production_daily --execute-once --allow-raw-collection --allow-extraction --allow-evidence-promotion --allow-author-editor-redteam --allow-guarded-book-publication --allow-daily-status-fallback --allow-commit-push-after-gates --install-schedule-after-success --send-telegram-status --output-json reports/editorial/$RUN_ID-production-execute-once.json --output-md reports/editorial/$RUN_ID-production-execute-once.md --telegram-status reports/telegram/production-daily-latest.md
```
