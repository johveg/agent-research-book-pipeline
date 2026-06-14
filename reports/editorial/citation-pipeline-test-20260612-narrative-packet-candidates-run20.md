# Run 20 narrative packet candidates — citation-pipeline-test-20260612

## Summary

- Report-only: `True`
- GPT-5.5 used: `True`
- Provider/model/bridge/profile: `copilot` / `gpt-5.5` / `hermes_cli` / `closed_loop_editorial`
- Selected cluster reviews: `1`
- Packet candidates: `1`
- Excluded cluster reviews/items: `1`

## Selected cluster review

- `cluster_4e8554045cfaf827bc68bcc5`
  - quality_gate_decision: `caveat_only_packet_candidate_ready`
  - packet_readiness: `ready_for_caveat_only_packet`
  - recommended_next_stage: `build_caveat_only_packet_candidate`

## Packet candidates

- `packet_run20_caveat_only_cluster_4e8554045cfaf827bc68bcc5` — Caveat-only Hermes/OpenClaw setup context
  - type/decision/use: `caveat_only_packet_candidate` / `caveat_only_packet_candidate` / `caveat_only`
  - target_chapter_status: `not_assigned`
  - target_chapter_candidates: `not_assigned`
  - singleton_packet: `True`
  - summary: Caveat-only planning packet from a singleton cluster: OpenClaw docs name Hermes in migration/setup tooling contexts only.
  - angle: Track as a caveat-only planning packet about narrow Hermes mentions in OpenClaw migration/setup documentation, not as a dependency or runtime claim.

## Caveat-only constraints

- `packet_run20_caveat_only_cluster_4e8554045cfaf827bc68bcc5` caveat: Frame narrowly: OpenClaw documentation names Hermes in migration/setup tooling contexts; do not state that Hermes is a runtime dependency or general operating environment without additional sources.

## Do-not-say guidance

- Do not say Hermes is a runtime dependency of OpenClaw.
- Do not say Hermes is the general operating environment for OpenClaw.
- Do not say OpenClaw requires Hermes for web or phone access.
- Do not generalize beyond migration/setup/import tooling contexts unless additional sources support it.
- Do not use this packet as a factual claim without the caveat.
- Do not use this packet for chapter prose before later author/red-team gates pass.

## Safety

This is not claim insertion, not authoring, not publication approval, and not a chapter update. Packet summaries and angles are planning metadata only, not publishable prose. No DB writes, source-registry/raw-capture changes, docs/book changes, schema changes, daily-worker changes, claims, editorial reviews, or source notes were produced.

## Limitations and residual risk

The packet is singleton and caveat-only. It must not be generalized beyond migration/setup/import tooling contexts without additional sources and later review gates.

## Recommendation for Run 21

Run 21 should perform a report-only packet safety/red-team gate over the Run 20 packet candidate before any persistence, authoring, or publication path is considered.
