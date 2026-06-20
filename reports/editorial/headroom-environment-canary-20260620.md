# Headroom environment canary — 2026-06-20

- decision: `no_broad_environment_rollout_yet`
- allowed next step: `selective_use_for_openclaw_results_openclaw_events_linkedin_posts_only_with_quality_gate_and_raw_fallback`
- blocked next step: `global_proxy_or_compress_all_jsonl_event_ledgers`
- durable install: `/home/hermoine/headroom-venv`
- runner: `/home/hermoine/headroom-canary-runner.py`
- inputs: `7`
- tokens before: `45527`
- tokens after: `12883`
- tokens saved: `32644`
- aggregate compression ratio: `71.7%`
- average compression wall time: `158.767 ms`
- all quality gates pass: `False`
- all secret scans pass: `True`

## Selective artifacts that passed and saved tokens
- `openclaw_results`: `8380` tokens saved (`62.0%`) — `/home/hermoine/openclaw-hermes-web-watch/data/web-captures/openclaw-hermes/20260616T230017Z/results.jsonl`
- `openclaw_events`: `6038` tokens saved (`68.7%`) — `/home/hermoine/openclaw-hermes-web-watch/data/web-captures/openclaw-hermes/20260616T230017Z/events.jsonl`
- `linkedin_posts`: `1536` tokens saved (`63.2%`) — `/home/hermoine/linkedin-24h-watch/data/search-captures/20260616T040011Z-openclaw-hermes/posts.jsonl`

## Safe but no benefit artifacts
- `terefo_production_log`: transforms `router:noop` — use raw/fallback
- `terefo_ops_controller_log`: transforms `router:protected:error_output` — use raw/fallback
- `openclaw_full_index`: transforms `router:noop` — use raw/fallback

## Failed artifacts / do not compress yet
- `terefo_events`: failed gates `error_preserved, paths_preserved, status_preserved` — `/home/hermoine/terefohealreboa/logs/closed_loop/events.jsonl`

## Operational recommendation

Do not enable Headroom globally or as a proxy for the whole environment yet. Use it selectively for web/search/capture artifacts that passed the quality gate, with raw fallback enabled. Terefo event-ledger JSONL needs a custom preservation profile before compression can be trusted.
