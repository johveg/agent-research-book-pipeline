# OPS unresolved auto-fix probe — 2026-06-20

- status: `partial_auto_repair_completed_destination_not_deliverable`
- severity: `warning`
- required alias: `AL-Hermoine-OPS`
- fallback channel used: `false`
- DM/home/default used as substitute: `false`

## What I found

Hermes can send/list Telegram targets, but both the default and `ops-bot` profile channel directories only expose `telegram:Marius (dm)`. The required alias `AL-Hermoine-OPS` is absent.

The ops Telegram identity exists as bot username `al_hermoine_ops_bot`, but that is a bot identity, not a deliverable chat/channel. Telegram rejected bot-to-bot sends:

- main bot → `@al_hermoine_ops_bot`: `USER_BOT_TO_BOT_DISABLED`
- ops bot → `@al_hermoine_ops_bot`: bot cannot send messages to itself/another bot

## Automatic repair outcome

I could verify credentials and identify the root cause, but I did not fabricate a channel-directory alias. Mapping `AL-Hermoine-OPS` to Marius/home/DM would violate the OPS routing rule, and mapping it to the ops bot username is not deliverable by Telegram.

## Required next step

Create or choose a real Telegram destination for OPS notifications, add/start `al_hermoine_ops_bot` there, and let Hermes discover it or provide the real destination target out of band. Then we can safely bind the alias `AL-Hermoine-OPS` to that real chat and run one explicit live test.

## Verification

Focused OPS routing/outbox tests: `24 passed`.
