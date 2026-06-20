# OPS bot home routing fix — 2026-06-20

- status: `ops_delivery_live_verified`
- severity: `success`
- target channel: `AL-Hermoine-OPS`
- delivery profile: `ops-bot`
- delivery target: `telegram`
- bot: `@al_hermoine_ops_bot`
- fallback channel used: `false`

## Fix

The intended semantics are now explicit: OPS messages go to Marius **through** `@al_hermoine_ops_bot`, using the `ops-bot` profile Telegram home channel. `AL-Hermoine-OPS` is no longer treated as a default-profile channel alias that must appear in the main bot target list.

## Live verification

A live Telegram send using the ops-bot profile token and home channel succeeded. The result recorded only non-secret proof: bot username, chat type, and that a message id was present. No token or chat id is stored in this report.

The Terefo OPS delivery controller also completed with `ops_delivery_live_verified`, `queued_count=0`, and `delivered_count=1` for the isolated `ops-routing-fix-20260620` outbox.

## Tests

Focused OPS routing/outbox/controller tests: `26 passed`.

## Changed code

- `scripts/ops_channel_autodiscovery.py`
- `scripts/ops_channel_resolver.py`
- `scripts/ops_delivery_controller.py`
- `scripts/ops_delivery_outbox.py`
- `tests/test_ops_channel_resolver.py`
- `tests/test_ops_delivery_outbox.py`

The ops-bot profile channel directory was also given a non-secret logical alias entry for `AL-Hermoine-OPS` with `kind=ops_bot_home`.
