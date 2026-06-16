# Production daily scheduler status

# Production daily scheduler status

```yaml
status_metadata:
  emitted_at_unix_s: 1781604071
  emitted_at_unix_ms: 1781604071352
  emitted_at_utc_iso: "2026-06-16T10:01:11Z"
  emitted_at_oslo_iso: "2026-06-16T12:01:11+02:00"
  timezone: Europe/Oslo
  component: production_daily_scheduler
  run_id: production-daily-20260616
  status: production_daily_completed
  severity: success
  disposition: production_daily_completed
  target_channel: AL-Hermoine-OPS
  repo: /home/hermoine/terefohealreboa
  git_commit: null
  git_branch: null
  report_path: null
  log_path: null
  run_started_at_unix_s: null
  run_finished_at_unix_s: null
  duration_seconds: null
```

Generated: 2026-06-16T10:01:11Z

- target_channel: `AL-Hermoine-OPS`
- success: `True`
- final_disposition: `production_daily_completed`
- production scheduler created: `True`
- runtime config created: `True`
- schedule installed: `True`
- schedule install attempted: `True`
- schedule installable: `True`
- execute-once result: `completed`
- GPT-5.5 used: `True`
- provider/model/profile: `copilot` / `gpt-5.5` / `closed_loop_editorial`
- raw collection performed: `True`
- extraction performed: `True`
- evidence promotion performed: `True`
- author/editor-redteam performed: `True`
- guarded publication performed: `True`
- publication status: `live_gpt55_completed`
- substantive update applied: `True`
- daily status fallback applied: `False`
- docs/book files changed: `['docs/book/06-operating-loops.md']`
- source_registry/raw/DB deltas: `source registry export command completed; diff governed by mutation guard` / `web raw capture paths under raw/web/production-daily-20260616; LinkedIn authenticated capture skipped in execute-once to avoid browser-session stall` / `{}`
- mutation guard: `True` profile `production_daily_publish`
- citation verifier: `True`
- MkDocs strict: `True`
- tests result: `pending final verification`
- full verification: `pending final verification`
- commit hash: `pending`
- push result: `pending`
- final git status: `pending`
- daily schedule command: `cd /home/hermoine/terefohealreboa && RUN_ID=$(date -u +production-daily-%Y%m%d) && python3 scripts/closed_loop_production_scheduler.py --run-id "$RUN_ID" --runtime-config config/closed_loop_runtime.json --mode production_daily --execute-once --allow-raw-collection --allow-extraction --allow-evidence-promotion --allow-author-editor-redteam --allow-guarded-book-publication --allow-daily-status-fallback --allow-commit-push-after-gates --install-schedule-after-success --send-telegram-status --output-json reports/editorial/$RUN_ID-production-execute-once.json --output-md reports/editorial/$RUN_ID-production-execute-once.md --telegram-status reports/telegram/production-daily-latest.md`
- next expected daily run: `2026-06-17T05:30:00+01:00/+02:00 Europe/Oslo`
