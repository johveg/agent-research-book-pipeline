# Run 45 status — Enable daily autonomous book production scheduler

Generated: 2026-06-15T17:13:18Z

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
- source_registry/raw/DB deltas: `source registry export command completed; diff governed by mutation guard` / `web raw capture paths under raw/web/production-daily-manual-20260615T171122Z; LinkedIn authenticated capture skipped in execute-once to avoid browser-session stall` / `{}`
- mutation guard: `True` profile `production_daily_publish`
- citation verifier: `True`
- MkDocs strict: `True`
- tests result: `pending final verification`
- full verification: `pending final verification`
- commit hash: `pending`
- push result: `pending`
- final git status: `pending`
- daily schedule command: `cd /home/hermoine/terefohealreboa && RUN_ID=$(date -u +production-daily-%Y%m%d) && python3 scripts/closed_loop_production_scheduler.py --run-id "$RUN_ID" --runtime-config config/closed_loop_runtime.json --mode production_daily --execute-once --allow-raw-collection --allow-extraction --allow-evidence-promotion --allow-author-editor-redteam --allow-guarded-book-publication --allow-daily-status-fallback --allow-commit-push-after-gates --install-schedule-after-success --send-telegram-status --output-json reports/editorial/$RUN_ID-production-execute-once.json --output-md reports/editorial/$RUN_ID-production-execute-once.md --telegram-status reports/telegram/production-daily-latest.md`
- next expected daily run: `2026-06-16T05:30:00+01:00/+02:00 Europe/Oslo`
