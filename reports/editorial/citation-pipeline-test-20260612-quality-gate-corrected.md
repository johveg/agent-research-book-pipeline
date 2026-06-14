# Run 6 Correction/audit reviewer quality gate: citation-pipeline-test-20260612

## Executive summary

- Run ID: `citation-pipeline-test-20260612`
- Generated at: 2026-06-13T19:26:40Z
- LLM used: True
- Provider/model/bridge: `copilot` / `gpt-5.5` / `hermes_cli`
- Reasoning status: `high_reasoning_used`
- Source cards reviewed: 3
- Semantic objects reviewed: 3
- Decision counts: `{'pass': 0, 'warn': 6, 'fail': 0}`
- Legacy mapping counts: `{'blocked': 0, 'needs_revision': 6, 'ready_for_editor_review': 0}`
- Downstream eligible count: 0
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
| source_card_draft_src_13864c81172f978b55bd | [internal-id] | warn | revise_before_editor_review | Keep blocked from downstream use; Complete human privacy/publication review; Do not use f… |
| source_card_draft_src_3e3a7fd1388feb172ac5 | [internal-id] | warn | revise_before_editor_review | Keep blocked from downstream use; Complete human privacy/publication review; Resolve miss… |
| source_card_draft_src_9471e5ba147ec4be19b6 | [internal-id] | warn | revise_before_editor_review | Keep blocked from downstream use; Complete human privacy/publication review; Resolve miss… |

## Semantic-object reviews

| target_id | source_id | source_card_id | decision | downstream eligibility | required fixes |
|---|---|---|---|---|---|
| semantic_object_draft_db6ceb5790045cce4d3a | [internal-id] | source_card_draft_src_13864c81172f978b55bd | warn | revise_before_editor_review | Keep blocked from downstream use; Do not use for filing, novelty work, or author drafting… |
| semantic_object_draft_9aa9ffb0b7f788f57ee1 | [internal-id] | source_card_draft_src_13864c81172f978b55bd | warn | revise_before_editor_review | Keep blocked from downstream use; Do not use for filing, novelty work, or author drafting… |
| semantic_object_draft_2cb9451bf751ff120116 | [internal-id] | source_card_draft_src_13864c81172f978b55bd | warn | revise_before_editor_review | Keep blocked from downstream use; Do not use for filing, novelty work, or author drafting… |

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
