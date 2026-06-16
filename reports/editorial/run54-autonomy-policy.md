# Closed-loop autonomy policy

```json
{
  "commit_allowed": true,
  "continue_allowed": true,
  "degradation_reasons": [
    "methodology_draft_report_only",
    "ops_alias_unresolved_but_status_queued",
    "production_daily_completed_self_heal_not_needed",
    "status_outbox_available",
    "telegram_live_send_failed_closed_no_fallback"
  ],
  "degraded_mode": true,
  "hard_stop_reasons": [],
  "healthy": false,
  "human_required": false,
  "manual_action_required": false,
  "optional_manual_action": null,
  "publication_allowed": false,
  "required_next_machine_action": "continue_report_only_and_retry_ops_delivery",
  "status_metadata": {
    "component": "closed_loop_autonomy_policy",
    "disposition": "ops_delivery_degraded_queued",
    "emitted_at_oslo_iso": "2026-06-16T21:43:50+02:00",
    "emitted_at_unix_ms": 1781639030599,
    "emitted_at_unix_s": 1781639030,
    "emitted_at_utc_iso": "2026-06-16T19:43:50Z",
    "run_id": "run54",
    "severity": "warning",
    "status": "ops_delivery_degraded_queued",
    "target_channel": "AL-Hermoine-OPS",
    "timezone": "Europe/Oslo"
  }
}
```
