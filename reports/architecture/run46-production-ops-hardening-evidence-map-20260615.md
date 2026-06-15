# Run 46 production ops hardening evidence map

- Baseline: `reports/editorial/production-ops-baseline-run46.json`
- Production monitor: `scripts/production_daily_monitor.py` and `reports/editorial/production-monitor-run46.json`
- Scheduler health: `scripts/closed_loop_production_scheduler.py --mode production_status --status-only` and `reports/editorial/production-scheduler-health-run46.json`
- SSH push helper: `scripts/git_push_with_hermes_key.sh`
- Mutation guard profile: `production_ops_hardening`
- Scope guard: no Run 46 docs/book, raw, source registry, DB logical, schema, docs/entities, or claims publication mutations.
