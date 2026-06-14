# Run 26 — Report-only enriched caveat-only author-draft input rebuild evidence map

Date: 2026-06-14
Run ID: `citation-pipeline-test-20260612`
Mode: `llm_rebuild_author_draft_input`

## Objective

Rebuild the Run 22B author-draft input package after Run 25 found the Run 24 draft canary safe but not useful. This run enriches structured authoring input only. It does not generate prose, approve authoring, approve publication, insert claims, insert editorial reviews, write source notes, mutate docs/book, change source registry, change raw captures, change schema, or modify the daily worker.

## Inputs

Primary inputs:

- `reports/editorial/citation-pipeline-test-20260612-author-draft-canary-redteam-run25.json`
- `reports/editorial/citation-pipeline-test-20260612-author-draft-canary-run24.json`
- `reports/editorial/citation-pipeline-test-20260612-author-draft-input-preflight-run23.json`
- `reports/editorial/citation-pipeline-test-20260612-author-draft-input-run22b.json`

Supporting lineage checked through embedded provenance:

- `reports/editorial/citation-pipeline-test-20260612-source-support-rereview-run15.json`
- `reports/editorial/citation-pipeline-test-20260612-persisted-source-support-rereview-notes-run16.json`
- `reports/editorial/citation-pipeline-test-20260612-narrative-packet-candidates-run20.json`
- `reports/editorial/citation-pipeline-test-20260612-packet-redteam-gate-run21.json`
- `reports/editorial/citation-pipeline-test-20260612-closed-loop-state-machine-run22a.json`

## Files created/changed in Run 26

Created:

- `scripts/llm_rebuild_author_draft_input.py`
- `tests/test_llm_rebuild_author_draft_input.py`
- `reports/editorial/citation-pipeline-test-20260612-author-draft-input-rebuild-run26.json`
- `reports/editorial/citation-pipeline-test-20260612-author-draft-input-rebuild-run26.md`
- `reports/architecture/run26-author-draft-input-rebuild-evidence-map-20260614.md`

No Run 26 changes were made to:

- `.var/book.sqlite`
- `data/source_registry.json`
- `raw/`
- `docs/book/`
- `docs/entities/`
- `docs/research/claims.md`
- `data/schema.sql`
- `scripts/daily_book_worker.py`

## TDD sequence

Focused test command before implementation:

```bash
.venv/bin/python -m pytest -q tests/test_llm_rebuild_author_draft_input.py
```

Observed RED result before script creation:

- `4 failed`
- Failure cause: `scripts/llm_rebuild_author_draft_input.py` did not exist.

Implementation then added `scripts/llm_rebuild_author_draft_input.py` and tightened validation after focused failures uncovered:

- Run 22B used equivalent wording: `Do not use this packet as a factual claim without the caveat.`
- Negative guardrail strings containing phrases such as runtime dependency or final prose must be allowed when they are explicitly do-not-say / no / does-not-establish constraints.

Focused final result:

```bash
.venv/bin/python -m pytest -q tests/test_llm_rebuild_author_draft_input.py
```

Result:

- `4 passed in 4.07s`

## Test coverage added

`tests/test_llm_rebuild_author_draft_input.py` covers:

- Selects current Run 25 `safe_but_not_useful` / `not_useful_restates_caveat_only` / `needs_better_authoring_input` / `rebuild_author_draft_input` result.
- Excludes/fails closed for unsafe or non-rebuild recommendations.
- Strict JSON result schema validation.
- Invalid LLM JSON fails closed.
- Invalid enum fails closed.
- Missing safety flags fail closed.
- `author_allowed=true` fails closed.
- `publication_approved=true` fails closed.
- `eligible_for_claim_insertion=true` fails closed.
- `eligible_for_authoring=true` fails closed.
- `eligible_for_publication=true` fails closed.
- `chapter_update_allowed=true` fails closed.
- Missing required caveat fails closed.
- Missing do-not-say guidance fails closed.
- Rebuilt input preserves required caveat.
- Rebuilt input includes `evidence_bound_factual_atoms`.
- Rebuilt input includes `narrative_function_suggestions`.
- Rebuilt input includes `why_prior_canary_was_not_useful`.
- Rebuilt input contains no chapter-ready prose field.
- Later canary instruction seed is instructions only, not final prose.
- `rebuilt_draft_input_candidate` keeps author/publication/chapter flags false.
- Weak/local fallback is refused.
- Missing `closed_loop_editorial` profile fails closed.
- Report-only mode leaves DB counts/statuses and protected artifacts unchanged.

## Live Run 26 command

```bash
.venv/bin/python scripts/llm_rebuild_author_draft_input.py \
  --run-id citation-pipeline-test-20260612 \
  --redteam-report reports/editorial/citation-pipeline-test-20260612-author-draft-canary-redteam-run25.json \
  --canary-report reports/editorial/citation-pipeline-test-20260612-author-draft-canary-run24.json \
  --preflight-report reports/editorial/citation-pipeline-test-20260612-author-draft-input-preflight-run23.json \
  --draft-input-report reports/editorial/citation-pipeline-test-20260612-author-draft-input-run22b.json \
  --output-dir reports/editorial \
  --report-suffix run26 \
  --reasoning-profile closed_loop_editorial \
  --timeout-seconds 300
```

Result:

```json
{
  "ok": true,
  "selected_canary_redteam_count": 1,
  "rebuilt_input_count": 1,
  "excluded_canary_redteam_count": 0,
  "rebuilt_input_type_counts": {"enriched_caveat_only_author_draft_input": 1},
  "rebuilt_input_decision_counts": {"rebuilt_draft_input_candidate": 1},
  "rebuilt_input_use_counts": {"caveat_only": 1},
  "target_chapter_status_counts": {"suggested_only": 1}
}
```

## GPT-5.5/profile evidence

Run 26 report records:

- `llm_used: true`
- `provider: copilot`
- `model: gpt-5.5`
- `bridge: hermes_cli`
- `model_profile: closed_loop_editorial`
- `reasoning_status: high_reasoning_used`
- `strict_json_required: true`
- `weak_local_fallback_refused: true`
- `stdout_json_valid: true`
- `exit_code: 0`
- `timed_out: false`
- `elapsed_seconds: 40.095`

## Rebuilt input package

Output package:

- `rebuilt_input_id: rebuilt_input_run26_enriched_caveat_only_cluster_4e8554045cfaf827bc68bcc5`
- `prior_draft_input_id: draft_input_run22b_caveat_only_cluster_4e8554045cfaf827bc68bcc5`
- `prior_draft_canary_id: draft_canary_run24_caveat_only_cluster_4e8554045cfaf827bc68bcc5`
- `source_packet_id: packet_run20_caveat_only_cluster_4e8554045cfaf827bc68bcc5`
- `source_cluster_id: cluster_4e8554045cfaf827bc68bcc5`
- `source_note_ids: [note_a30056d3f19faa7deb0c9dbc]`
- `source_review_ids: [source_review_5baf68d86960f91b97ac]`
- `source_ids: [src_6d7b6d80cda4e784877d]`
- `manifest_item_ids: [manifest_2901cc01a0bc7a2252b35183]`
- `rebuilt_input_type: enriched_caveat_only_author_draft_input`
- `rebuilt_input_decision: rebuilt_draft_input_candidate`
- `rebuilt_input_use: caveat_only`
- `target_chapter_status: suggested_only`

The package adds structured non-prose authoring context:

- evidence-bound factual atoms
- allowed author scope
- forbidden author scope
- narrative function suggestions
- placement suggestions only
- evidence limitations
- citation requirements
- later canary instruction seed
- usefulness improvement notes
- explanation of why Run 24 canary was not useful

The required caveat is preserved exactly:

> Frame narrowly: OpenClaw documentation names Hermes in migration/setup tooling contexts; do not state that Hermes is a runtime dependency or general operating environment without additional sources.

## Safety state

Run 26 report records:

- `changed_db: false`
- `changed_source_notes: false`
- `changed_source_registry: false`
- `changed_raw_captures: false`
- `changed_docs_book: false`
- `changed_schema: false`
- `changed_daily_worker: false`
- `claims_inserted: 0`
- `editorial_reviews_inserted: 0`
- `source_status_changed: false`
- `claim_status_changed: false`
- `editorial_status_changed: false`
- `author_allowed: false`
- `publication_approved: false`
- `eligible_for_claim_insertion: false`
- `eligible_for_authoring: false`
- `eligible_for_publication: false`
- `chapter_update_allowed: false`

DB counts before/after from report:

- `source_notes: 365 -> 365`
- `claims: 181 -> 181`
- `editorial_reviews: 10 -> 10`

## Verification commands and results

Commands run:

```bash
git status --short
.venv/bin/python -m pytest -q tests/test_llm_rebuild_author_draft_input.py
.venv/bin/python -m pytest -q
python3 scripts/verify_book_workspace.py
python3 scripts/verify_editorial_roles.py
python3 scripts/verify_book_citations.py
.venv/bin/python -m mkdocs build --strict
git status --short
```

Results:

- Focused tests: `4 passed in 4.08s`
- Full suite: `148 passed in 53.57s`
- `verify_book_workspace.py`: `status: ok`
- `verify_editorial_roles.py`: `status: ok`
- `verify_book_citations.py`: `status: ok`, no raw ID hits, no unresolved hits
- `mkdocs build --strict`: passed; documentation built in `3.60 seconds`

MkDocs emitted existing informational warnings about pages not included in nav and a Material for MkDocs team warning; build still exited successfully.

## Verification-generated protected artifact restoration

Verification dirtied generated/protected artifacts. Restored with:

```bash
git restore data/source_registry.json docs/book docs/entities docs/research/claims.md \
  reports/architecture/run1-llm-reasoning-dry-run-evidence-map-20260614.md \
  reports/architecture/run3-source-card-persistence-evidence-map-20260614.md \
  reports/architecture/run4-semantic-object-extraction-evidence-map-20260614.md \
  reports/architecture/run5-high-reasoning-bridge-evidence-map-20260614.md
rm -f docs/entities/boris-cherny.md
```

Post-restore checks:

```bash
git diff -- data/source_registry.json docs/book docs/entities docs/research/claims.md data/schema.sql scripts/daily_book_worker.py
git status --short raw logs .var
```

Results:

- Protected diff empty.
- `raw/`, `logs/`, and `.var/` status empty.
- DB counts after restore check:
  - `source_notes: 365`
  - `claims: 181`
  - `editorial_reviews: 10`

## Recommendation for Run 27

Proceed to a report-only preflight/red-team gate over the enriched Run 26 input before any later controlled canary. Run 27 should validate whether the enriched input is suitable as input to a later controlled draft-only canary while preserving all false author/publication/claim/chapter flags. It should not create chapter prose, mutate `docs/book`, insert DB rows, change statuses, or approve authoring/publication.
