# Run 44 guarded book publication evidence map — 20260614

## Run title

Aggressive guarded book publication canary with evidence expansion and daily publish fallback.

## Strategic target

Run 44 implements the guarded `docs/book` publication path required before Run 45 daily autonomous production. The run is allowed to change `docs/book` only through machine-gated publisher infrastructure and protected mutation guard profile `docs_book_write`.

## Inputs

- Run 43 packets: `reports/editorial/citation-pipeline-test-20260612-publish-packets-run43.json`
- Run 42 context: `reports/editorial/citation-pipeline-test-20260612-constrained-authoring-context-run42.json`
- Existing SQLite evidence DB: `.var/book.sqlite` (read-only in Run 44)
- Existing reports/source mappings only; no new raw collection and no external web collection.

## New infrastructure

- `scripts/closed_loop_book_publisher.py`
  - validates publish packets using `closed_loop_publish_packet_validator.py`
  - rejects blocked/no-publication packets, missing citations/evidence, raw leakage markers, unsupported dispositions, and human-in-loop dependency terms
  - supports `--dry-run`, `--apply`, and `--max-packets`
  - applies either one substantive chapter delta or rolling daily no-safe-promotions status update
  - never commits/pushes internally
- `scripts/closed_loop_publication_orchestrator.py`
  - consumes Run 43 packets
  - broadens evidence from existing DB/context
  - forces `copilot` / `gpt-5.5` / `closed_loop_editorial`
  - refuses weak/local fallback
  - applies one guarded canary if machine-approved, otherwise daily status fallback
- `docs_book_write` protected mutation guard profile
  - permits `docs/book` plus Run 44 control-plane/report files
  - blocks DB/source registry/raw/schema/entities/research claim mutations

## Safety boundaries

- No raw text publication.
- No unsupported claims.
- No new raw collection.
- No web collection.
- No routine human-in-the-loop dependency.
- No scheduler/runtime production enablement.
- No `docs/entities`, `docs/research/claims.md`, source registry, schema, raw, DB, or daily worker mutation.

## Verification plan

- Focused TDD tests for publisher/orchestrator/validator/mutation guard.
- Live GPT-5.5 publication gate or fail-closed.
- JSON validation for all Run 44 reports.
- Workspace, editorial-role, citation, and MkDocs strict verification after docs/book change.
- Mutation guard compare with profile `docs_book_write`.
- Full pytest, diff check, and secrets scan before commit/push.
