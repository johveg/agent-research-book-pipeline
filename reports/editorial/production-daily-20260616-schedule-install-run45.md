# Run 45 schedule install

# Run 45 schedule install

```yaml
status_metadata:
  emitted_at_unix_s: 1781604009
  emitted_at_unix_ms: 1781604009154
  emitted_at_utc_iso: "2026-06-16T10:00:09Z"
  emitted_at_oslo_iso: "2026-06-16T12:00:09+02:00"
  timezone: Europe/Oslo
  component: production_daily_scheduler
  run_id: production-daily-20260616
  status: production_monitor_ok
  severity: success
  disposition: production_monitor_ok
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

Generated: 2026-06-16T10:00:09Z

- target_channel: `AL-Hermoine-OPS`
- run_id: `production-daily-20260616`
- mode: `run45_schedule_install_artifact`
- schedule_installed: `False`
- schedule_installable: `True`

## Schedule command

```bash
cd /home/hermoine/terefohealreboa && RUN_ID=$(date -u +production-daily-%Y%m%d) && python3 scripts/closed_loop_production_scheduler.py --run-id "$RUN_ID" --runtime-config config/closed_loop_runtime.json --mode production_daily --execute-once --allow-raw-collection --allow-extraction --allow-evidence-promotion --allow-author-editor-redteam --allow-guarded-book-publication --allow-daily-status-fallback --allow-commit-push-after-gates --install-schedule-after-success --send-telegram-status --output-json reports/editorial/$RUN_ID-production-execute-once.json --output-md reports/editorial/$RUN_ID-production-execute-once.md --telegram-status reports/telegram/production-daily-latest.md
```
