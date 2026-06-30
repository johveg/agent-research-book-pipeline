# Production daily scheduler status

# Production daily scheduler status

```yaml
status_metadata:
  emitted_at_unix_s: 1782813873
  emitted_at_unix_ms: 1782813873691
  emitted_at_utc_iso: "2026-06-30T10:04:33Z"
  emitted_at_oslo_iso: "2026-06-30T12:04:33+02:00"
  timezone: Europe/Oslo
  component: production_daily_scheduler
  run_id: production-daily-20260630
  status: production_daily_completed
  severity: success
  disposition: production_daily_completed
  target_channel: AL-Hermoine-OPS
  repo: /home/hermoine/agent-research-book-pipeline
  git_commit: null
  git_branch: main
  report_path: null
  log_path: logs/runs/production-daily-20260630.log
  run_started_at_unix_s: null
  run_finished_at_unix_s: null
  duration_seconds: null
```

Generated: 2026-06-30T10:04:33Z

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
- publication status: `event_driven_no_content_delta`
- substantive update applied: `False`
- daily status fallback applied: `True`
- docs/book files changed: `[]`
- source_registry/raw/DB deltas: `source registry export command completed; diff governed by mutation guard` / `web raw capture paths under raw/web/production-daily-20260630; LinkedIn authenticated capture skipped in execute-once to avoid browser-session stall` / `{}`
- mutation guard: `True` profile `production_daily_publish`
- citation verifier: `True`
- MkDocs strict: `True`
- tests result: `pending final verification`
- full verification: `pending final verification`
- commit hash: `pending`
- push result: `pending`
- final git status: `pending`
- daily schedule command: `/home/hermoine/agent-research-book-pipeline/scripts/run_production_daily_cron.sh`
- next expected daily run: `2026-07-01T05:30:00+01:00/+02:00 Europe/Oslo`
