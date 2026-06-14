# Source-card drafts advisory report: citation-pipeline-test-20260612

## Executive summary

- Run ID: `citation-pipeline-test-20260612`
- Generated at: 2026-06-13T18:35:45Z
- Sample count: 3 sources
- LLM used: True
- Reasoning status: `high_reasoning_used`
- Provider: `copilot`
- Model: `gpt-5.5`
- Confidence level: `high`
- Safety status: advisory-only source-card drafts; not publication approval and not chapter prose.
- `--write-source-notes` used: False
- DB modified: False
- DB write scope: `none`
- Chapters changed: False; statuses changed: False; daily worker changed: False; commit allowlist changed: False.

## Source-card draft table

| source_id | title | source_type | quality_score | privacy status | evidence strength | recommended use | likely chapter target | risk flags |
|---|---|---|---|---|---|---|---|---|
| [internal-id] | Feed post David Aw • 3rd+ A one man agile team \| CISSP \| 13x AWS Certs \| Golden Jacket 41… | linkedin_search_result | D | human_review | reject | do_not_use | 04-loop-engineering, 05-context-memory-architecture | social_or_private_adjacent_discovery_signal, privacy_review_required |
| [internal-id] | Feed post Ameet C. • 3rd+ Driving innovation in technology and product development strate… | linkedin_search_result | D | human_review | reject | do_not_use | 04-loop-engineering | social_or_private_adjacent_discovery_signal, privacy_review_required |
| [internal-id] | I’m starting to wonder… how heavily subsidized are the AI monthly subscriptions… especial… | linkedin_search_result | D | human_review | reject | do_not_use | 04-loop-engineering | social_or_private_adjacent_discovery_signal, privacy_review_required |

## Source-card details

### `source_card_draft_src_13864c81172f978b55bd`
- Source ID: `src_13864c81172f978b55bd`
- Safe summary: LinkedIn search result for David Aw references a prompt-engineering post about how to ask, with context and loop engineer terms present.
- Main thesis: A LinkedIn search snippet shows David Aw posting about prompt engineering and asking questions, with context and loop engineer appearing in the result.
- Useful observations:
  - The snippet links prompt engineering, context, and a loop engineer search term, but provides too little detail for evidentiary use.
- Candidate claims:
  - (none identified in draft mode)
- Candidate examples:
  - (none identified in draft mode)
- Candidate counterpoints:
  - (none identified in draft mode)
- Named entities:
  - David Aw
  - CISSP
  - AWS Certs
  - Golden Jacket
  - Context
- Technical terms:
  - context
  - loop
  - CISSP
  - AWS
- Risk flags:
  - social_or_private_adjacent_discovery_signal
  - privacy_review_required
- Recommended use: `do_not_use`
- Semantic-extraction later: not yet; Privacy/publication status requires review before any use.

### `source_card_draft_src_3e3a7fd1388feb172ac5`
- Source ID: `src_3e3a7fd1388feb172ac5`
- Safe summary: LinkedIn search result for Ameet C. describes technology and product-development work and includes a truncated post snippet plus loop engineer search term.
- Main thesis: A LinkedIn search result identifies Ameet C. with a technology and product-development profile, followed by a truncated post snippet mentioning a question.
- Useful observations:
  - The result is a short LinkedIn snippet with insufficient context; it should not support a substantive claim.
- Candidate claims:
  - (none identified in draft mode)
- Candidate examples:
  - (none identified in draft mode)
- Candidate counterpoints:
  - (none identified in draft mode)
- Named entities:
  - Ameet
  - Driving
- Technical terms:
  - loop
- Risk flags:
  - social_or_private_adjacent_discovery_signal
  - privacy_review_required
- Recommended use: `do_not_use`
- Semantic-extraction later: not yet; Privacy/publication status requires review before any use.

### `source_card_draft_src_9471e5ba147ec4be19b6`
- Source ID: `src_9471e5ba147ec4be19b6`
- Safe summary: Truncated LinkedIn snippet questions whether AI subscriptions are subsidized, apparently in relation to high token use and loop engineer search context.
- Main thesis: A truncated LinkedIn search snippet questions AI subscription economics, suggesting possible subsidy concerns tied to heavy token consumption.
- Useful observations:
  - The snippet may flag an AI-cost discussion, but it is incomplete, private-adjacent, and unsuitable as evidence without review.
- Candidate claims:
  - The snippet raises a question about whether monthly AI subscriptions may be subsidized, connected to token usage concerns.
- Candidate examples:
  - (none identified in draft mode)
- Candidate counterpoints:
  - (none identified in draft mode)
- Named entities:
  - Based
- Technical terms:
  - loop
  - AI
- Risk flags:
  - social_or_private_adjacent_discovery_signal
  - privacy_review_required
- Recommended use: `do_not_use`
- Semantic-extraction later: not yet; Privacy/publication status requires review before any use.

## Persistence summary

- source_notes table schema inspected: True
- source_notes schema supports persistence: True
- source_notes columns: id, source_id, note, note_type, created_at
- Note type used: `source_card_draft`
- Cards generated: 3
- Notes inserted: 0
- Notes updated: 0
- Notes skipped existing: 0
- Notes failed: 0
- Idempotent: True

## Source-card shape assessment

- Future semantic extraction: source cards provide safer structured inputs than raw source snippets, but no extraction should run until card drafts are reviewed.
- Future filing/novelty evaluation: card hashes, risk flags, and recommended-use fields can support novelty review later.
- Future claim clustering: candidate claims are present but remain unapproved candidates only.
- Future narrative packets: defer; cards are not narrative packets and must not become chapter prose.

## Reuse-vs-schema assessment

- **can reuse source_notes** — `source_notes`: The generated card object can be serialized as JSON in source_notes.note with note_type='source_card_draft' in a later run. Recommendation: Use report-only output in Run 2; consider source_notes persistence in Run 3 after review.
- **should add columns** — `sources`: No new source columns are needed yet. Existing quality/privacy/duplicate fields are enough for draft generation. Recommendation: Defer source table columns until real lifecycle states are proven necessary.
- **should add dedicated source_cards table** — `source_cards`: A dedicated table could help later with versioning, model metadata, editor approval, and card hashes, but Run 2 does not prove it is required. Recommendation: Defer dedicated table until at least one reviewed source_notes persistence run.
- **defer decision** — `semantic extraction / clusters / narrative packets`: Source cards look like a useful substrate, but semantic extraction and narrative packets remain higher-risk downstream steps. Recommendation: Do not implement these in Run 2; revisit after source-card persistence safety is reviewed.

## Safety assessment

- DB modified: no
- DB write scope: `none`
- Chapters modified: no
- Source/claim/editorial statuses modified: no
- Daily worker modified: no
- Commit allowlist modified: no
- Raw/private material written into reports: no
- Long source excerpts written into reports: no

## Recommended Run 4

Review persisted source-card drafts, then proceed to semantic extraction from persisted cards only if card quality and safety are acceptable; otherwise refine source-card heuristics/prompt first.

Rationale: source_notes can hold draft JSON without schema migration, but no-LLM cards are low-confidence and should be reviewed before semantic extraction.

Risks:
- No-LLM source cards are structural and low-confidence.
- Real LLM prompts may produce unstable JSON unless schema-validated.
- Sanitized source text may still include too much wording if max-summary limits are raised.
- source_notes is generic and may be too limited for long-term source-card lifecycle/versioning.
- A dedicated source_cards table may still be needed after persistence review.
- Social/private-adjacent sources must remain discovery-only or needs-review until corroborated.
- Vector DB chunks are not source authority and are not used by this script.
