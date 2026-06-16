# Run 52 OPS channel alias resolution evidence map

```json
{
  "alias_found": false,
  "alias_repaired": false,
  "available_send_targets": [
    "telegram:Marius (dm)"
  ],
  "candidate_selected": null,
  "channel_directory_files_inspected": [
    "/root/.hermes/channel_directory.json",
    "/root/.hermes/profiles/ops-bot/channel_directory.json",
    "/root/.hermes/profiles/travel-logger/channel_directory.json",
    "/root/.hermes/state-snapshots/20260611-051654-pre-update/channel_directory.json"
  ],
  "commit_hash": "pending",
  "failure_reason": "failed_closed_target_not_resolvable",
  "fallback_channel_used": false,
  "final_git_status": "## main...origin/main\n M reports/telegram/production-monitor-latest.md\n M scripts/protected_mutation_guard.py\n M tests/test_protected_mutation_guard.py\n?? reports/architecture/run52-ops-channel-alias-resolution-evidence-map-20260616.md\n?? reports/editorial/run52-full-verification.json\n?? reports/editorial/run52-full-verification.md\n?? reports/editorial/run52-hermes-channel-resolution-inventory.json\n?? reports/editorial/run52-hermes-channel-resolution-inventory.md\n?? reports/editorial/run52-mkdocs-strict.txt\n?? reports/editorial/run52-ops-alias-baseline.json\n?? reports/editorial/run52-ops-alias-baseline.md\n?? reports/editorial/run52-ops-live-test.json\n?? reports/editorial/run52-ops-target-resolution-test.json\n?? reports/editorial/run52-ops-target-resolution-test.md\n?? reports/editorial/run52-production-monitor-ops-routing-check.json\n?? reports/editorial/run52-production-scheduler-ops-routing-check.json\n?? reports/editorial/run52-production-scheduler-ops-routing-check.md\n?? reports/editorial/run52-protected-mutation-guard.json\n?? reports/editorial/run52-protected-mutation-guard.md\n?? reports/editorial/run52-verify-book-citations.json\n?? reports/editorial/run52-verify-book-workspace.json\n?? reports/editorial/run52-verify-editorial-roles.txt\n?? reports/telegram/run52-ops-live-test.md\n?? reports/telegram/run52-production-scheduler-ops-routing-check.md\n?? reports/telegram/run52-status.md",
  "focused_tests_result": "58 passed",
  "full_pytest_result": "365 passed",
  "manual_remediation": [
    "add or expose a Hermes channel-directory alias named AL-Hermoine-OPS",
    "ensure the Telegram connector can resolve it as the OPS channel",
    "rerun Run 52 live delivery test"
  ],
  "mutation_guard_result": {
    "failed_checks": [],
    "ok": true,
    "protected_path_delta": {
      ".var/book.sqlite": false,
      "data/schema.sql": false,
      "data/source_registry.json": false,
      "docs/book": false,
      "docs/entities": false,
      "docs/research/claims.md": false,
      "raw": false,
      "scripts/daily_book_worker.py": false
    }
  },
  "ops_live_test_attempted": false,
  "ops_live_test_message_id": null,
  "ops_live_test_send_succeeded": false,
  "production_monitor_routing_check_result": {
    "expected_run_id": "production-daily-20260616",
    "fallback_channel_used": false,
    "status": "production_daily_completed",
    "status_metadata_exists": true,
    "target_channel": "AL-Hermoine-OPS"
  },
  "protected_deltas": {
    ".var/book.sqlite": false,
    "data/schema.sql": false,
    "data/source_registry.json": false,
    "docs/book": false,
    "docs/entities": false,
    "docs/research/claims.md": false,
    "raw": false,
    "scripts/daily_book_worker.py": false
  },
  "push_result": "pending",
  "recommended_run53": "Manual Hermes channel-directory/Telegram connector repair, then rerun Run 52 live delivery test before Run 53 methodology work",
  "resolved_send_target": null,
  "scheduler_routing_check_result": {
    "fallback_channel_used": false,
    "status": "production_monitor_ok",
    "status_metadata_exists": true,
    "target_channel": "AL-Hermoine-OPS"
  },
  "secrets_scan_result": {
    "findings": [],
    "ok": true,
    "scanned_files": 25
  },
  "status_metadata": {
    "component": "run52_ops_channel_alias_resolution",
    "disposition": "run52_failed_closed_ops_alias_unresolved",
    "emitted_at_oslo_iso": "2026-06-16T15:17:22.259748+02:00",
    "emitted_at_unix_ms": 1781615842259,
    "emitted_at_unix_s": 1781615842,
    "emitted_at_utc_iso": "2026-06-16T13:17:22.259748Z",
    "run_id": "run52",
    "severity": "warning",
    "status": "run52_failed_closed_ops_alias_unresolved",
    "target_channel": "AL-Hermoine-OPS",
    "timezone": "Europe/Oslo"
  },
  "success": false,
  "workspace_editorial_citation_mkdocs_result": {
    "citations": "ok",
    "editorial_roles": "{'status': 'ok', 'errors': [], 'warnings': []}",
    "git_diff_check": "ok",
    "mkdocs_strict": "ok",
    "workspace": "ok"
  }
}
```
