# Production daily monitor

# Production daily monitor

```yaml
status_metadata:
  emitted_at_unix_s: 1781589759
  emitted_at_unix_ms: 1781589759026
  emitted_at_utc_iso: "2026-06-16T06:02:39Z"
  emitted_at_oslo_iso: "2026-06-16T08:02:39+02:00"
  timezone: Europe/Oslo
  component: production_daily_monitor
  run_id: production-daily-20260616
  status: production_daily_missing_after_due
  severity: failure
  disposition: production_daily_missing_after_due
  target_channel: AL-Hermoine-OPS
  repo: /home/hermoine/terefohealreboa
  git_commit: 69c322c
  git_branch: main
  report_path: /home/hermoine/terefohealreboa/reports/editorial/production-daily-20260616-production-execute-once.json
  log_path: /home/hermoine/terefohealreboa/logs/runs/production-daily-20260616.log
  run_started_at_unix_s: null
  run_finished_at_unix_s: null
  duration_seconds: null
```

Generated: `2026-06-16T06:02:39Z`

- status: `production_daily_missing_after_due`
- target_channel: `AL-Hermoine-OPS`
- ok: `False`
- expected_run_id: `production-daily-20260616`
- schedule due: `True`
- crontab production command found: `True`
- production report JSON: `/home/hermoine/terefohealreboa/reports/editorial/production-daily-20260616-production-execute-once.json` exists `False`
- production report MD: `/home/hermoine/terefohealreboa/reports/editorial/production-daily-20260616-production-execute-once.md` exists `False`
- telegram status path: `/home/hermoine/terefohealreboa/reports/telegram/production-daily-latest.md` exists `False`
- log path: `/home/hermoine/terefohealreboa/logs/runs/production-daily-20260616.log` exists `False`
- disposition: `None`
