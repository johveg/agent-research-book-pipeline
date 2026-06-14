# Semantic object drafts: citation-pipeline-test-20260612

## Executive summary

- Run ID: `citation-pipeline-test-20260612`
- Generated at: 2026-06-13T18:36:31Z
- Source-card notes read: 3
- Semantic objects generated: 3
- LLM used: True
- Reasoning status: `high_reasoning_used`
- High-reasoning canary passed: True
- Safety status: advisory-only; no chapter/status/publication changes.

## High-reasoning canary

- Provider/model checked: `copilot` / `gpt-5.5`
- High-reasoning configured: True
- Canary succeeded: True
- Non-secret reason: Hermes CLI bridge canary returned strict valid JSON.
- Weak/local fallback refused: True

## Semantic object table

| object_id | type | source_id | source_note_id | chapter target | evidence strength | recommended use | risk flags | author_allowed | publication_approved |
|---|---|---|---|---|---|---|---|---|---|
| semantic_object_draft_db6ceb5790045cce4d3a | interpretation | [internal-id] | note_c740440f695e712c6ce6 | 04-loop-engineering, 05-context-memory-architecture | reject | do_not_use | social_or_private_adjacent_discovery_signal, privacy_review_required | False | False |
| semantic_object_draft_9aa9ffb0b7f788f57ee1 | interpretation | [internal-id] | note_c740440f695e712c6ce6 | 04-loop-engineering | reject | do_not_use | social_or_private_adjacent_discovery_signal, privacy_review_required | False | False |
| semantic_object_draft_2cb9451bf751ff120116 | interpretation | [internal-id] | note_c740440f695e712c6ce6 | 04-loop-engineering | reject | do_not_use | social_or_private_adjacent_discovery_signal, privacy_review_required | False | False |

## Per-source-card extraction summary

### `source_card_draft_src_13864c81172f978b55bd`
- Source ID: `src_13864c81172f978b55bd`
- Semantic object counts by type: `{'interpretation': 3}`
- Notable caveats:
  - none
- Later use: needs review; not approved for chapter use or publication.

## Persistence summary

- Write semantic notes requested: False
- Inserted: 0
- Updated: 0
- Skipped existing: 0
- Failed: 0
- Idempotent: True

## Safety assessment

- DB modified: no
- DB write scope: `none`
- Chapters modified: no
- Source/claim/editorial statuses modified: no
- Schema modified: no
- Daily worker modified: no
- Commit allowlist modified: no
- Raw/private material written: no
- Long excerpts written: no

## Recommendation for Run 5

review semantic drafts before filing/novelty evaluation

Rationale: Canary passed and outputs are schema-valid, but still advisory-only.
