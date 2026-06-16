# Run 46 production scheduler health

# Run 46 production scheduler health

```yaml
status_metadata:
  emitted_at_unix_s: 1781615528
  emitted_at_unix_ms: 1781615528955
  emitted_at_utc_iso: "2026-06-16T13:12:08Z"
  emitted_at_oslo_iso: "2026-06-16T15:12:08+02:00"
  timezone: Europe/Oslo
  component: production_daily_scheduler
  run_id: production-status
  status: production_monitor_ok
  severity: success
  disposition: production_monitor_ok
  target_channel: AL-Hermoine-OPS
  repo: /home/hermoine/terefohealreboa
  git_commit: b057951
  git_branch: null
  report_path: /home/hermoine/terefohealreboa/reports/editorial/production-daily-20260616-production-execute-once.json
  log_path: null
  run_started_at_unix_s: null
  run_finished_at_unix_s: null
  duration_seconds: null
```

Generated: 2026-06-16T13:12:08Z

- target_channel: `AL-Hermoine-OPS`
- mode: `production_status`
- gpt55_used: `False`
- raw_collection_performed: `False`
- extraction_performed: `False`
- evidence_promotion_performed: `False`

## Schedule command

```bash
30 5 * * * /home/hermoine/terefohealreboa/scripts/run_production_daily_cron.sh
```
