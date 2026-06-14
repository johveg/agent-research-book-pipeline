# Run 6 Correction/audit reviewer quality gate: citation-pipeline-test-20260612

## Executive summary

- Run ID: `citation-pipeline-test-20260612`
- Generated at: 2026-06-13T19:44:05Z
- LLM used: True
- Provider/model/bridge: `copilot` / `gpt-5.5` / `hermes_cli`
- Reasoning status: `high_reasoning_used`
- Source cards reviewed: 5
- Semantic objects reviewed: 10
- Decision counts: `{'pass': 13, 'warn': 2, 'fail': 0}`
- Legacy mapping counts: `{'blocked': 0, 'needs_revision': 2, 'ready_for_editor_review': 13}`
- Downstream eligible count: 13
- Next allowed stage: `revise_high_reasoning_drafts`

## Decision mapping

- `ready_for_editor_review -> pass`
- `needs_revision -> warn`
- `blocked -> fail`

## Audit findings

- Prior Run 6 assessment: `partially_valid_but_misaligned`

Matched intended Run 6:
- Read Run 5 high-reasoning source-card and semantic-object JSON reports.
- Verified input llm_used/reasoning_status/provider/model.
- Produced report-only safety decisions with no DB/chapter/status/schema/daily-worker/allowlist writes.

Did not match intended Run 6:
- Previous quality gate did not call GPT-5.5 for reviewer-quality judgment; it used deterministic reviewer rules only.
- Previous item schema lacked explicit pass/warn/fail compatibility fields and several required reviewer fields.
- Existing Run 5 evidence map path is miswritten with Run 2 placeholder content; this correction did not overwrite it.

Patched:
- Added --no-llm deterministic mode and --require-high-reasoning GPT-5.5 reviewer mode.
- Added pass/warn/fail decisions with explicit legacy mapping.
- Added downstream eligibility, recommended stage, scores/rules, strengths/weaknesses/fixes/risks, safety booleans, and input/output hashes per item.
- Changed generated report names to *-quality-gate-corrected.* for this correction/audit run.

## Source-card reviews

| target_id | source_id | decision | downstream eligibility | required fixes |
|---|---|---|---|---|
| source_card_draft_src_c6b80c86cd5637ddd0b8 | [internal-id] | pass | eligible_for_human_editor_review |  |
| source_card_draft_src_bebe03beb8a33c199ce8 | [internal-id] | pass | eligible_for_human_editor_review |  |
| source_card_draft_src_6d7b6d80cda4e784877d | [internal-id] | pass | eligible_for_human_editor_review |  |
| source_card_draft_src_89933e373b741e71c5c6 | [internal-id] | warn | revise_before_editor_review | Link or account for the missing semantic object before downstream use. |
| source_card_draft_src_e9bb5a4bcd1c1f9e9744 | [internal-id] | warn | revise_before_editor_review | Link or account for the missing semantic object before downstream use. |

## Semantic-object reviews

| target_id | source_id | source_card_id | decision | downstream eligibility | required fixes |
|---|---|---|---|---|---|
| semantic_object_draft_496337fece8a8137b67c | [internal-id] | source_card_draft_src_c6b80c86cd5637ddd0b8 | pass | eligible_for_human_editor_review |  |
| semantic_object_draft_473484d8201e178d6dd5 | [internal-id] | source_card_draft_src_c6b80c86cd5637ddd0b8 | pass | eligible_for_human_editor_review |  |
| semantic_object_draft_46b12d2f69c1b1fb74e9 | [internal-id] | source_card_draft_src_c6b80c86cd5637ddd0b8 | pass | eligible_for_human_editor_review |  |
| semantic_object_draft_8905ce1c477a0e798fa8 | [internal-id] | source_card_draft_src_c6b80c86cd5637ddd0b8 | pass | eligible_for_human_editor_review |  |
| semantic_object_draft_789a7a503aa5c9f79650 | [internal-id] | source_card_draft_src_bebe03beb8a33c199ce8 | pass | eligible_for_human_editor_review |  |
| semantic_object_draft_d79d29b8684f53476f83 | [internal-id] | source_card_draft_src_bebe03beb8a33c199ce8 | pass | eligible_for_human_editor_review |  |
| semantic_object_draft_8e955fe05f9c23f816b3 | [internal-id] | source_card_draft_src_bebe03beb8a33c199ce8 | pass | eligible_for_human_editor_review |  |
| semantic_object_draft_4b498b3935ed37eec827 | [internal-id] | source_card_draft_src_bebe03beb8a33c199ce8 | pass | eligible_for_human_editor_review |  |
| semantic_object_draft_741f09ec6bd33efa6930 | [internal-id] | source_card_draft_src_bebe03beb8a33c199ce8 | pass | eligible_for_human_editor_review |  |
| semantic_object_draft_425a074033ba640ec639 | [internal-id] | source_card_draft_src_6d7b6d80cda4e784877d | pass | eligible_for_human_editor_review |  |

## Safety assessment

- db_modified: `False`
- chapters_modified: `False`
- statuses_modified: `False`
- schema_modified: `False`
- daily_worker_modified: `False`
- commit_allowlist_modified: `False`
- raw_or_vector_authority_used: `False`
- narrative_packets_created: `False`
- chapter_prose_generated: `False`
- publication_approval_granted: `False`
- long_source_excerpt_written: `False`

## Run 7 recommendation

Revise high-reasoning drafts before any downstream stage.

Candidate: revise high-reasoning drafts or select a safer/public-source sample, then rerun this quality gate; do not proceed to Run 7 automation yet.
