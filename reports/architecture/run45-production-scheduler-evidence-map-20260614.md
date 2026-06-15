# Run 45 production scheduler evidence map

Generated: 2026-06-15

## Purpose

Run 45 enables daily autonomous book production v1 by adding a production runtime config, scheduler wrapper, schedule artifact, and production mutation guard profile.

## Wired components

- `scripts/daily_book_worker.py`: daily raw capture and extraction entry point.
- `scripts/closed_loop_daily_runner.py`: prior preflight runner contract, retained as a wired dependency.
- `scripts/closed_loop_event_ledger.py`: event ledger attempt start/status events.
- `scripts/closed_loop_publication_orchestrator.py`: GPT-5.5 evidence expansion and publication packet gate.
- `scripts/closed_loop_book_publisher.py`: guarded docs/book publisher or daily status fallback.
- `scripts/closed_loop_author_editor.py`: author/editor/red-team packet normalization precedent.
- `scripts/protected_mutation_guard.py`: before/after protected mutation comparison.
- `config/closed_loop_runtime.json`: production v1 safety and enablement flags.
- `config/reasoning_models.json`: model disposition/routing configuration.

## Safety gates

- GPT-5.5 required for author/editor/red-team and publication gate.
- Weak/local fallback is blocked.
- Routine human-in-loop dependency is disabled.
- At most one substantive docs/book update per production run.
- Daily no-safe-promotions fallback remains allowed.
- Citation, workspace, editorial, MkDocs strict, and mutation guard gates are required before success.
- Commit/push is external to the scheduler unless a future controlled final step is added after all gates.

## Production mutation scope

Allowed when reported and expected:

- `docs/book/**` guarded publication or daily status fallback.
- `reports/editorial/*run45*`, `reports/architecture/run45-*.md`, `reports/telegram/run45-status.md`.
- `logs/closed_loop/events.jsonl`.
- `config/closed_loop_runtime.json` and installable schedule artifacts.
- `raw/**` only when raw collection is performed and reported.
- `data/source_registry.json` only when source registry export is performed and reported.
- `.var/book.sqlite` logical deltas only when production daily stages report expected DB writes.

Blocked unless a future explicit verified profile changes this:

- `data/schema.sql`.
- unexpected `docs/entities/**` and `docs/research/claims.md` changes.
- unsupported raw text leakage into public book pages.
- unresolved citations or raw IDs in public book pages.
- publication without GPT-5.5 and verification gates.

## Schedule

Installable cron artifact: `config/schedules/closed-loop-production-daily.cron.example`.

Daily target: 05:30 Europe/Oslo.
