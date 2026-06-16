# Run 52 Hermes channel resolution inventory

```json
{
  "al_hermoine_ops_exists": false,
  "aliases_found": [
    {
      "file": "/root/.hermes/channel_directory.json",
      "name": "Marius",
      "platform": "telegram",
      "type": "dm"
    },
    {
      "file": "/root/.hermes/profiles/ops-bot/channel_directory.json",
      "name": "Marius",
      "platform": "telegram",
      "type": "dm"
    },
    {
      "file": "/root/.hermes/profiles/travel-logger/channel_directory.json",
      "name": "Marius",
      "platform": "telegram",
      "type": "dm"
    },
    {
      "file": "/root/.hermes/state-snapshots/20260611-051654-pre-update/channel_directory.json",
      "name": "Marius",
      "platform": "telegram",
      "type": "dm"
    }
  ],
  "candidate_resolvable_aliases": [
    {
      "candidate": "telegram:Marius",
      "resolvable": true,
      "resolver_model": "channel_directory_exact_or_unambiguous_prefix",
      "safe_for_live_send": false,
      "semantically_ops_target": false
    }
  ],
  "files_inspected": [
    {
      "exists": true,
      "path": "/root/.hermes/channel_directory.json",
      "readable": true,
      "updated_at": "2026-06-16T13:09:24.787985"
    },
    {
      "exists": true,
      "path": "/root/.hermes/profiles/ops-bot/channel_directory.json",
      "readable": true,
      "updated_at": "2026-06-16T13:10:09.185607"
    },
    {
      "exists": true,
      "path": "/root/.hermes/profiles/travel-logger/channel_directory.json",
      "readable": true,
      "updated_at": "2026-06-11T05:15:38.882289"
    },
    {
      "exists": true,
      "path": "/root/.hermes/state-snapshots/20260611-051654-pre-update/channel_directory.json",
      "readable": true,
      "updated_at": "2026-06-11T05:13:13.058642"
    }
  ],
  "recommended_repair": "AL-Hermoine-OPS is not present in Hermes channel_directory for default or ops-bot profiles. Add/expose a Telegram channel-directory entry named AL-Hermoine-OPS for the OPS bot/channel, then rerun Run 52. Do not map to telegram:Marius because that is not the OPS channel.",
  "redaction_status": "numeric chat IDs and sensitive fields redacted; no token/session values included",
  "spelling_differs": false,
  "status_metadata": {
    "component": "run52_ops_alias_resolution",
    "disposition": "inventory_only",
    "emitted_at_oslo_iso": "2026-06-16T15:11:30.057659+02:00",
    "emitted_at_unix_ms": 1781615490057,
    "emitted_at_unix_s": 1781615490,
    "emitted_at_utc_iso": "2026-06-16T13:11:30.057659Z",
    "run_id": "run52",
    "severity": "info",
    "status": "channel_inventory",
    "target_channel": "AL-Hermoine-OPS",
    "timezone": "Europe/Oslo"
  },
  "target_syntax_different_from_telegram_colon_alias": false,
  "telegram_channel_aliases_found": [
    {
      "entry": {
        "id": "<redacted_numeric_id>",
        "name": "Marius",
        "thread_id": null,
        "type": "dm"
      },
      "file": "/root/.hermes/channel_directory.json"
    },
    {
      "entry": {
        "id": "<redacted_numeric_id>",
        "name": "Marius",
        "thread_id": null,
        "type": "dm"
      },
      "file": "/root/.hermes/profiles/ops-bot/channel_directory.json"
    },
    {
      "entry": {
        "id": "<redacted_numeric_id>",
        "name": "Marius",
        "thread_id": null,
        "type": "dm"
      },
      "file": "/root/.hermes/profiles/travel-logger/channel_directory.json"
    },
    {
      "entry": {
        "id": "<redacted_numeric_id>",
        "name": "Marius",
        "thread_id": null,
        "type": "dm"
      },
      "file": "/root/.hermes/state-snapshots/20260611-051654-pre-update/channel_directory.json"
    }
  ]
}
```
