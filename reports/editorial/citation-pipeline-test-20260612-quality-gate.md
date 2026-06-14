# Reviewer quality gate: citation-pipeline-test-20260612

## Executive summary

- Run ID: `citation-pipeline-test-20260612`
- Generated at: 2026-06-13T19:04:20Z
- Source cards reviewed: 3
- Semantic objects reviewed: 3
- Quality-gate LLM used: False
- Input source-card reasoning: `high_reasoning_used`
- Input semantic reasoning: `high_reasoning_used`
- Decisions: `{'blocked': 0, 'needs_revision': 6, 'ready_for_editor_review': 0}`
- Blocking issue count: 0
- Revision issue count: 6
- Next allowed stage: `revise_high_reasoning_drafts`

## Source-card reviews

| item_id | source_id | decision | issues | positive signals |
|---|---|---|---|---|
| source_card_draft_src_13864c81172f978b55bd | [internal-id] | needs_revision | recommended_use is do_not_use; keep blocked from downstream use; evidence_strength is rej… | stable card_output_hash present; Run 5 high-reasoning metadata present; linked semantic o… |
| source_card_draft_src_3e3a7fd1388feb172ac5 | [internal-id] | needs_revision | recommended_use is do_not_use; keep blocked from downstream use; evidence_strength is rej… | stable card_output_hash present; Run 5 high-reasoning metadata present |
| source_card_draft_src_9471e5ba147ec4be19b6 | [internal-id] | needs_revision | recommended_use is do_not_use; keep blocked from downstream use; evidence_strength is rej… | stable card_output_hash present; Run 5 high-reasoning metadata present |

## Semantic-object reviews

| item_id | source_id | source_card_id | decision | issues | positive signals |
|---|---|---|---|---|---|
| semantic_object_draft_db6ceb5790045cce4d3a | [internal-id] | source_card_draft_src_13864c81172f978b55bd | needs_revision | recommended_use is do_not_use; keep blocked from downstream use; evidence_strength is rej… | stable object_output_hash present; source_card_id links to reviewed source-card report; p… |
| semantic_object_draft_9aa9ffb0b7f788f57ee1 | [internal-id] | source_card_draft_src_13864c81172f978b55bd | needs_revision | recommended_use is do_not_use; keep blocked from downstream use; evidence_strength is rej… | stable object_output_hash present; source_card_id links to reviewed source-card report; p… |
| semantic_object_draft_2cb9451bf751ff120116 | [internal-id] | source_card_draft_src_13864c81172f978b55bd | needs_revision | recommended_use is do_not_use; keep blocked from downstream use; evidence_strength is rej… | stable object_output_hash present; source_card_id links to reviewed source-card report; p… |

## Safety assessment

- DB modified: False
- DB write scope: `none`
- Chapters modified: False
- Source/claim/editorial statuses modified: False
- Schema modified: False
- Daily worker modified: False
- Commit allowlist modified: False
- Raw/vector authority used: False
- Narrative packets created: False
- Chapter prose generated: False
- Publication approval granted: False

## Run 7 recommendation

Revise high-reasoning drafts before any downstream stage.

Candidate: human editor review packet or draft revision loop; still no claim clustering/narrative packets/chapter prose until editor criteria pass.

## Risks

- Deterministic gate checks schema/linkage/safety; it does not prove factual truth.
- Run 5 GPT-5.5 drafts remain advisory-only and not publication-approved.
- Social/private-adjacent sources require human review before any use.
- No raw captures or vector DB chunks were consulted by this quality gate.
