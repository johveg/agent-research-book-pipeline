# Run 31 — constrained authoring-metadata preflight evidence map — 2026-06-14

## Objective

Use GPT-5.5 through `closed_loop_editorial` to preflight/red-team the Run 30 constrained authoring-metadata candidate as metadata only, before any later author-facing or promotion-contract stage.

## Scope and safety constraints

Run 31 is report-only and advisory. It must not generate author prose or chapter prose; must not write `docs/book`; must not insert claims, `editorial_reviews`, or `source_notes`; must not persist metadata to the database; must not modify source/claim/editorial statuses, `source_registry.json`, raw captures, `data/schema.sql`, or `scripts/daily_book_worker.py`; and must not approve authoring, publication, claim insertion, or chapter updates.

## Files created/changed in Run 31

- Created `scripts/llm_constrained_authoring_metadata_preflight.py`
- Created `tests/test_llm_constrained_authoring_metadata_preflight.py`
- Created `reports/editorial/citation-pipeline-test-20260612-constrained-authoring-metadata-preflight-run31.json`
- Created `reports/editorial/citation-pipeline-test-20260612-constrained-authoring-metadata-preflight-run31.md`
- Created `reports/architecture/run31-constrained-authoring-metadata-preflight-evidence-map-20260614.md`

## TDD evidence

Initial focused test run before implementation failed as expected because the Run 31 script did not exist:

```bash
.venv/bin/python -m pytest -q tests/test_llm_constrained_authoring_metadata_preflight.py
```

Result: `4 failed`, missing `scripts/llm_constrained_authoring_metadata_preflight.py`.

After implementation and a validation fix for negative-boundary guardrail strings, focused tests passed:

```bash
.venv/bin/python -m pytest -q tests/test_llm_constrained_authoring_metadata_preflight.py
```

Result: `4 passed in 7.19s`.

## Live Run 31 command

```bash
.venv/bin/python scripts/llm_constrained_authoring_metadata_preflight.py \
  --run-id citation-pipeline-test-20260612 \
  --metadata-report reports/editorial/citation-pipeline-test-20260612-constrained-authoring-metadata-run30.json \
  --output-dir reports/editorial \
  --report-suffix run31 \
  --reasoning-profile closed_loop_editorial \
  --timeout-seconds 300
```

Result: exit `0`.

## Live Run 31 result

- selected_metadata_count: `1`
- reviewed_metadata_count: `1`
- excluded_metadata_count: `0`
- llm_used: `true`
- provider/model/bridge/profile: `copilot` / `gpt-5.5` / `hermes_cli` / `closed_loop_editorial`
- reasoning_status: `high_reasoning_used`
- strict JSON: validated by `scripts/hermes_high_reasoning_json.py` and Run 31 schema validator
- preflight_decision_counts: `{"metadata_preflight_passed": 1}`
- metadata_readiness_counts: `{"ready_for_promotion_contract_update": 1}`
- closed_loop_disposition_counts: `{"caveat_only": 1}`
- recommended_next_stage_counts: `{"update_closed_loop_promotion_contract_for_authoring_metadata": 1}`

Selected metadata:

- `metadata_run30_constrained_authoring_4e8554045cfaf827bc68bcc5`

## Review interpretation

GPT-5.5 judged the candidate safe/useful as metadata only for a later promotion-contract update. It did not approve authoring, publication, claim insertion, or chapter updates. The review preserved:

- `author_allowed: false`
- `publication_approved: false`
- `eligible_for_claim_insertion: false`
- `eligible_for_authoring: false`
- `eligible_for_publication: false`
- `chapter_update_allowed: false`

## Verification commands and results

```bash
git status --short
.venv/bin/python -m pytest -q tests/test_llm_constrained_authoring_metadata_preflight.py
.venv/bin/python -m pytest -q
python3 scripts/verify_book_workspace.py
python3 scripts/verify_editorial_roles.py
python3 scripts/verify_book_citations.py
.venv/bin/python -m mkdocs build --strict
git status --short
```

Results:

- Focused Run 31 tests: `4 passed in 7.25s`
- Full pytest suite: `168 passed in 80.75s`
- `verify_book_workspace.py`: `status: ok`
- `verify_editorial_roles.py`: `status: ok`
- `verify_book_citations.py`: `status: ok`
- MkDocs strict build: exit `0`, documentation built successfully; existing nav warnings only

Post-verification protected artifact cleanup:

```bash
git restore data/source_registry.json docs/book docs/entities docs/research/claims.md
rm -f docs/entities/boris-cherny.md
python3 - <<'PY'
import sqlite3, json
con=sqlite3.connect('.var/book.sqlite')
print(json.dumps({t: con.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0] for t in ['source_notes','claims','editorial_reviews']}, sort_keys=True))
PY
git diff --name-only -- data/source_registry.json docs/book docs/entities docs/research/claims.md data/schema.sql scripts/daily_book_worker.py raw || true
git status --short
```

Results:

- DB counts after cleanup: `{"claims": 181, "editorial_reviews": 10, "source_notes": 365}`
- Protected diff command returned no protected paths.

## DB and protected artifact delta summary

From the Run 31 report:

- changed_db: `false`
- changed_source_notes: `false`
- source_notes delta: `0` (`365` before, `365` after)
- claims_inserted: `0` (`181` before, `181` after)
- editorial_reviews_inserted: `0` (`10` before, `10` after)
- source_status_changed: `false`
- claim_status_changed: `false`
- editorial_status_changed: `false`
- changed_source_registry: `false`
- changed_raw_captures: `false`
- changed_docs_book: `false`
- changed_schema: `false`
- changed_daily_worker: `false`

## Safety conclusion

Run 31 successfully preflighted the Run 30 constrained metadata candidate with GPT-5.5 through `closed_loop_editorial`. The output remains advisory/report-only. The positive decision means readiness for another controlled metadata/promotion-contract stage only, not authoring or publication.

## Recommendation for Run 32

Proceed to Run 32 as a report-only closed-loop promotion-contract update/test for authoring metadata. It should encode the Run 31-approved metadata-readiness transition while continuing to keep all authoring/publication/claim/chapter flags false and avoiding `docs/book`, DB/status, source registry, raw capture, schema, and daily-worker changes.
