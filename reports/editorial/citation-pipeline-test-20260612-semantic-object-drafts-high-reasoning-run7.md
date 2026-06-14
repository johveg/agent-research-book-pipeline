# Semantic object drafts: citation-pipeline-test-20260612

## Executive summary

- Run ID: `citation-pipeline-test-20260612`
- Generated at: 2026-06-13T19:42:10Z
- Source-card notes read: 5
- Semantic objects generated: 14
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
| semantic_object_draft_496337fece8a8137b67c | trend_signal | [internal-id] | report_note_c9ec63935313e9e7e39c | 01-the-agent-loop, 02-hermes, 03-openclaw | weak | needs_review | thin_source_text | False | False |
| semantic_object_draft_473484d8201e178d6dd5 | counterpoint | [internal-id] | report_note_c9ec63935313e9e7e39c | 01-the-agent-loop, 02-hermes, 03-openclaw | weak | needs_review | thin_source_text | False | False |
| semantic_object_draft_46b12d2f69c1b1fb74e9 | trend_signal | [internal-id] | report_note_c9ec63935313e9e7e39c | 01-the-agent-loop, 02-hermes, 03-openclaw | weak | needs_review | thin_source_text | False | False |
| semantic_object_draft_8905ce1c477a0e798fa8 | factual_claim | [internal-id] | report_note_c9ec63935313e9e7e39c | 01-the-agent-loop, 02-hermes, 03-openclaw | weak | needs_review | thin_source_text | False | False |
| semantic_object_draft_789a7a503aa5c9f79650 | counterpoint | [internal-id] | report_note_02cdd0001e18d222c378 | 02-hermes, 01-the-agent-loop, 03-openclaw | weak | needs_review | thin_source_text | False | False |
| semantic_object_draft_d79d29b8684f53476f83 | factual_claim | [internal-id] | report_note_02cdd0001e18d222c378 | 02-hermes, 01-the-agent-loop, 03-openclaw | weak | needs_review | thin_source_text | False | False |
| semantic_object_draft_8e955fe05f9c23f816b3 | trend_signal | [internal-id] | report_note_02cdd0001e18d222c378 | 02-hermes, 01-the-agent-loop, 03-openclaw | weak | needs_review | thin_source_text | False | False |
| semantic_object_draft_4b498b3935ed37eec827 | counterpoint | [internal-id] | report_note_02cdd0001e18d222c378 | 02-hermes, 01-the-agent-loop, 03-openclaw | weak | needs_review | thin_source_text | False | False |
| semantic_object_draft_741f09ec6bd33efa6930 | factual_claim | [internal-id] | report_note_02cdd0001e18d222c378 | 02-hermes, 01-the-agent-loop, 03-openclaw | weak | needs_review | thin_source_text | False | False |
| semantic_object_draft_425a074033ba640ec639 | trend_signal | [internal-id] | report_note_ccea79fdd5360a900b70 | 02-hermes, 03-openclaw | weak | needs_review |  | False | False |
| semantic_object_draft_0aed99a302b307d6fdd3 | counterpoint | [internal-id] | report_note_ccea79fdd5360a900b70 | 02-hermes, 03-openclaw | weak | needs_review |  | False | False |
| semantic_object_draft_5df8116fc7dc2d06b2e7 | factual_claim | [internal-id] | report_note_ccea79fdd5360a900b70 | 02-hermes, 03-openclaw | weak | needs_review |  | False | False |
| semantic_object_draft_5558303e45f77723657a | factual_claim | [internal-id] | report_note_ccea79fdd5360a900b70 | 02-hermes, 03-openclaw | weak | needs_review |  | False | False |
| semantic_object_draft_18e5d778bd54802d41b3 | counterpoint | [internal-id] | report_note_ccea79fdd5360a900b70 | 02-hermes, 03-openclaw | weak | needs_review |  | False | False |

## Per-source-card extraction summary

### `source_card_draft_src_c6b80c86cd5637ddd0b8`
- Source ID: `src_c6b80c86cd5637ddd0b8`
- Semantic object counts by type: `{'trend_signal': 2, 'counterpoint': 1, 'factual_claim': 1}`
- Notable caveats:
  - none
- Later use: needs review; not approved for chapter use or publication.

### `source_card_draft_src_bebe03beb8a33c199ce8`
- Source ID: `src_bebe03beb8a33c199ce8`
- Semantic object counts by type: `{'counterpoint': 2, 'factual_claim': 2, 'trend_signal': 1}`
- Notable caveats:
  - none
- Later use: needs review; not approved for chapter use or publication.

### `source_card_draft_src_6d7b6d80cda4e784877d`
- Source ID: `src_6d7b6d80cda4e784877d`
- Semantic object counts by type: `{'trend_signal': 1, 'counterpoint': 2, 'factual_claim': 2}`
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
