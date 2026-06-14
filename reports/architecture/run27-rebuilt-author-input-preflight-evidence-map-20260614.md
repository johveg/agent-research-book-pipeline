# Run 27 — Report-only enriched author-draft input preflight gate evidence map

Date: 2026-06-14
Run ID: `citation-pipeline-test-20260612`
Mode: `llm_rebuilt_author_input_preflight`

## Objective

Use GPT-5.5 through the `closed_loop_editorial` profile to preflight/red-team the enriched Run 26 author-draft input package before any second controlled canary. This run decides whether the Run 26 input is suitable for a later controlled caveat-only draft canary, still too thin, unsafe for authoring, safe-reports-only, needs more sources, source-context unclear, or contradiction-review required.

Run 27 is report-only and advisory. It does not generate draft prose, generate chapter prose, write `docs/book`, insert claims, insert editorial reviews, write source notes, persist draft inputs, modify source/claim/editorial statuses, modify `source_registry.json`, modify raw captures, modify schema, modify the daily worker, approve authoring, approve publication, or allow chapter updates.

## Files created/changed in Run 27

Created:

- `scripts/llm_rebuilt_author_input_preflight.py`
- `tests/test_llm_rebuilt_author_input_preflight.py`
- `reports/editorial/citation-pipeline-test-20260612-rebuilt-author-input-preflight-run27.json`
- `reports/editorial/citation-pipeline-test-20260612-rebuilt-author-input-preflight-run27.md`
- `reports/architecture/run27-rebuilt-author-input-preflight-evidence-map-20260614.md`

No Run 27 changes were made to:

- `.var/book.sqlite`
- `data/source_registry.json`
- `raw/`
- `docs/book/`
- `docs/entities/`
- `docs/research/claims.md`
- `data/schema.sql`
- `scripts/daily_book_worker.py`

## Inputs

Primary input:

- `reports/editorial/citation-pipeline-test-20260612-author-draft-input-rebuild-run26.json`

Run 26 lineage embedded in the primary input includes:

- `reports/editorial/citation-pipeline-test-20260612-author-draft-canary-redteam-run25.json`
- `reports/editorial/citation-pipeline-test-20260612-author-draft-canary-run24.json`
- `reports/editorial/citation-pipeline-test-20260612-author-draft-input-preflight-run23.json`
- `reports/editorial/citation-pipeline-test-20260612-author-draft-input-run22b.json`
- `reports/editorial/citation-pipeline-test-20260612-closed-loop-state-machine-run22a.json`
- `reports/editorial/citation-pipeline-test-20260612-packet-redteam-gate-run21.json`
- `reports/editorial/citation-pipeline-test-20260612-narrative-packet-candidates-run20.json`
- `reports/editorial/citation-pipeline-test-20260612-source-support-rereview-run15.json`
- `reports/editorial/citation-pipeline-test-20260612-persisted-source-support-rereview-notes-run16.json`

Config/model inputs:

- `config/closed_loop_state_machine.json`
- `config/reasoning_models.json`
- `scripts/hermes_high_reasoning_json.py`
- `scripts/model_profiles.py`

## TDD sequence

Focused test command before implementation:

```bash
.venv/bin/python -m pytest -q tests/test_llm_rebuilt_author_input_preflight.py
```

Observed RED result before script creation:

- `4 failed`
- Failure cause: `scripts/llm_rebuilt_author_input_preflight.py` did not exist.

Implementation then added `scripts/llm_rebuilt_author_input_preflight.py`.

Focused final result:

```bash
.venv/bin/python -m pytest -q tests/test_llm_rebuilt_author_input_preflight.py
```

Result:

- `4 passed in 4.93s` during implementation check.
- `4 passed in 4.59s` during final verification.

## Test coverage added

`tests/test_llm_rebuilt_author_input_preflight.py` covers:

- Selects the current Run 26 enriched rebuilt input.
- Writes JSON/Markdown report-only outputs.
- Strict GPT-5.5 JSON result schema validation.
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
- Missing `do_not_say` fails closed.
- Missing `evidence_bound_factual_atoms` fails closed.
- Missing `narrative_function_suggestions` fails closed.
- Missing `later_canary_instruction_seed` fails closed.
- Rebuilt input containing final paragraph prose fails closed.
- Rebuilt input containing chapter-ready prose fails closed.
- `rebuilt_input_canary_ready` still keeps `author_allowed=false`.
- `rebuilt_input_canary_ready` still keeps `eligible_for_authoring=false`.
- `rebuilt_input_canary_ready` still keeps `chapter_update_allowed=false`.
- `still_safe_but_too_thin` routes only to `rebuild_author_draft_input_again` or `keep_safe_reports_only`.
- Weak/local fallback is not allowed.
- Missing `closed_loop_editorial` profile fails closed.
- Report-only mode does not modify copied SQLite DB counts or statuses.
- `source_registry.json`, raw captures, `docs/book`, `data/schema.sql`, and `scripts/daily_book_worker.py` remain unchanged in tests.

## Live Run 27 command

```bash
.venv/bin/python scripts/llm_rebuilt_author_input_preflight.py \
  --run-id citation-pipeline-test-20260612 \
  --rebuild-report reports/editorial/citation-pipeline-test-20260612-author-draft-input-rebuild-run26.json \
  --output-dir reports/editorial \
  --report-suffix run27 \
  --reasoning-profile closed_loop_editorial \
  --timeout-seconds 300
```

Result:

```json
{
  "ok": true,
  "selected_rebuilt_input_count": 1,
  "reviewed_rebuilt_input_count": 1,
  "excluded_rebuilt_input_count": 0,
  "preflight_decision_counts": {"rebuilt_input_canary_ready": 1},
  "canary_readiness_counts": {"ready_for_second_controlled_caveat_only_author_draft_canary": 1},
  "closed_loop_disposition_counts": {"caveat_only": 1},
  "recommended_next_stage_counts": {"run_second_controlled_caveat_only_author_draft_canary": 1}
}
```

## GPT-5.5/profile evidence

Run 27 report records:

- `llm_used: true`
- `reasoning_status: high_reasoning_used`
- `provider: copilot`
- `model: gpt-5.5`
- `bridge: hermes_cli`
- `model_profile: closed_loop_editorial`
- `strict_json_required: true`
- `weak_local_fallback_refused: true`
- `stdout_json_valid: true`
- `exit_code: 0`
- `timed_out: false`
- `elapsed_seconds: 24.889`

## Selected/reviewed object

Selected and reviewed rebuilt input:

- `rebuilt_input_id: rebuilt_input_run26_enriched_caveat_only_cluster_4e8554045cfaf827bc68bcc5`
- `rebuilt_input_type: enriched_caveat_only_author_draft_input`
- `rebuilt_input_use: caveat_only`

Preflight review result:

- `preflight_decision: rebuilt_input_canary_ready`
- `canary_readiness: ready_for_second_controlled_caveat_only_author_draft_canary`
- `closed_loop_disposition: caveat_only`
- `recommended_next_stage: run_second_controlled_caveat_only_author_draft_canary`

The review found that Run 26 materially improved usefulness compared with Run 22B/Run 24 by adding evidence-bound factual atoms, limitations, narrative-function constraints, placement suggestions, citation requirements, provenance paths, and canary instructions while preserving caveat-only containment and avoiding finished prose.

The required caveat is preserved exactly:

> Frame narrowly: OpenClaw documentation names Hermes in migration/setup tooling contexts; do not state that Hermes is a runtime dependency or general operating environment without additional sources.

## Safety state

Run 27 report records:

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

Every preflight review keeps:

- `advisory_only: true`
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
.venv/bin/python -m pytest -q tests/test_llm_rebuilt_author_input_preflight.py
.venv/bin/python -m pytest -q
python3 scripts/verify_book_workspace.py
python3 scripts/verify_editorial_roles.py
python3 scripts/verify_book_citations.py
.venv/bin/python -m mkdocs build --strict
git status --short
```

Results:

- Focused tests: `4 passed in 4.59s`
- Full suite: `152 passed in 58.11s`
- `verify_book_workspace.py`: `status: ok`
- `verify_editorial_roles.py`: `status: ok`
- `verify_book_citations.py`: `status: ok`, no raw ID hits, no unresolved hits
- `mkdocs build --strict`: passed; documentation built in `4.01 seconds`

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

## Recommendation for Run 28

Proceed to Run 28 as a second controlled caveat-only author-draft canary, still report-only. Run 28 may generate a short canary text only inside `reports/editorial/*.json` and `*.md`; it must not write `docs/book`, insert claims/editorial reviews/source notes, change statuses, approve authoring/publication, or allow chapter updates. The Run 28 canary should preserve the exact required caveat or be more conservative, respect all do-not-say constraints, and be followed by a separate red-team/usefulness gate before any broader authoring or publication step.
