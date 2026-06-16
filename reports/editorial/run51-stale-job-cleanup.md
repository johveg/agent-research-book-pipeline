# Run 51 stale job cleanup

```json
{
  "component": "stale_job_cleanup",
  "disposition": "stale_job_removed",
  "gpt55_used": false,
  "operator_followup_required": false,
  "production_monitor_job": {
    "enabled": true,
    "id": "b8189ef795c3",
    "schedule": {
      "display": "20 * * * *",
      "expr": "20 * * * *",
      "kind": "cron"
    },
    "state": "scheduled",
    "store": "/root/.hermes/cron/jobs.json"
  },
  "production_monitor_preserved": true,
  "production_scheduler_preserved": true,
  "repo": "/home/hermoine/terefohealreboa",
  "run_id": "run51",
  "safe_reports_only": true,
  "severity": "success",
  "stale_jobs_not_controllable": [],
  "stale_jobs_remaining": [],
  "stale_jobs_removed": [
    {
      "id": "dd69aced67cb",
      "method": "cronjob_tool_remove_and_ops_profile_registry_cleanup",
      "name": "Terefo Heal Reboa book loop start"
    },
    {
      "id": "0858e829f548",
      "method": "ops_profile_registry_cleanup",
      "name": "Terefo Heal Reboa book loop status"
    }
  ],
  "status": "stale_job_removed",
  "target_channel": "AL-Hermoine-OPS",
  "verified_at_utc": "2026-06-16T10:13:46.944526Z"
}
```
