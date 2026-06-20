# Run 55 LinkedIn capture/model hardening

- LinkedIn repo: `/home/hermoine/linkedin-24h-watch`
- Files changed: `scripts/daily_linkedin_capture.sh`
- ops-bot config changed: `true`
- ops-bot config versioned: `false`
- Previous model: `gpt-5.5`
- New model: `gpt-5`
- Reason: ops-bot default gpt-5.5 produced model_not_supported; config is not versioned, and current default gpt-5 is supported by copilot provider. Kept broad default because ops-bot scheduled jobs inherit the profile default and no versioned job-specific preflight mechanism is present in this profile config.
- Model preflight status: configuration_read: provider copilot, default gpt-5; live model API preflight not invoked to avoid side effects, but change removes known unsupported gpt-5.5 default.
- Deterministic capture fallback behavior: optional vector DB update/inspection failures now emit dependency_degraded_optional while preserving successful capture/push/summary status; no live broad capture was run.
- Checks: passed (`bash -n`; no tests directory present)
- Commit: `9d3d971`
- Push result: `pushed`
- Status: `checks_passed_committed_pushed`
