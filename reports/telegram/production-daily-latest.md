# Production daily scheduler status

# Production daily scheduler status

```yaml
status_metadata:
  emitted_at_unix_s: 1782444661
  emitted_at_unix_ms: 1782444661591
  emitted_at_utc_iso: "2026-06-26T03:31:01Z"
  emitted_at_oslo_iso: "2026-06-26T05:31:01+02:00"
  timezone: Europe/Oslo
  component: production_daily_scheduler
  run_id: production-daily-20260626
  status: production_daily_completed
  severity: success
  disposition: production_daily_completed
  target_channel: AL-Hermoine-OPS
  repo: /home/hermoine/terefohealreboa
  git_commit: null
  git_branch: main
  report_path: null
  log_path: logs/runs/production-daily-20260626.log
  run_started_at_unix_s: null
  run_finished_at_unix_s: null
  duration_seconds: null
```

Generated: 2026-06-26T03:31:01Z

- target_channel: `AL-Hermoine-OPS`
- success: `True`
- final_disposition: `production_daily_completed`
- production scheduler created: `True`
- runtime config created: `True`
- schedule installed: `False`
- schedule install attempted: `False`
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
- source_registry/raw/DB deltas: `source registry export command completed; diff governed by mutation guard` / `web raw capture paths under raw/web/production-daily-20260626; LinkedIn authenticated capture skipped in execute-once to avoid browser-session stall` / `{}`
- mutation guard: `True` profile `production_daily_publish`
- citation verifier: `True`
- MkDocs strict: `True`
- tests result: `pending final verification`
- full verification: `pending final verification`
- commit hash: `pending`
- push result: `pending`
- final git status: `pending`
- daily schedule command: `/home/hermoine/terefohealreboa/scripts/run_production_daily_cron.sh`
- next expected daily run: `2026-06-27T05:30:00+01:00/+02:00 Europe/Oslo`
