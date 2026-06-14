# Run 25 — Report-only author-draft canary red-team and usefulness gate evidence map

Date: 2026-06-14
Repository: `/home/hermoine/terefohealreboa`
Run ID: `citation-pipeline-test-20260612`

## Objective

Run 25 red-teamed the Run 24 caveat-only author-draft canary with GPT-5.5 through the `closed_loop_editorial` profile. The goal was to assess safety containment and usefulness without treating the canary as publishable prose or as authoring/publication approval.

## Created / changed in this run

- Created: `scripts/llm_author_draft_canary_redteam.py`
- Created: `tests/test_llm_author_draft_canary_redteam.py`
- Created: `reports/editorial/citation-pipeline-test-20260612-author-draft-canary-redteam-run25.json`
- Created: `reports/editorial/citation-pipeline-test-20260612-author-draft-canary-redteam-run25.md`
- Created: `reports/architecture/run25-author-draft-canary-redteam-evidence-map-20260614.md`

No commit was made.

## Primary input

- `reports/editorial/citation-pipeline-test-20260612-author-draft-canary-run24.json`

## Selection rule evidence

Selected only draft canaries matching:

- `draft_canary_type == caveat_only_author_draft_canary`
- `draft_canary_decision == draft_canary_created`
- `draft_canary_use == caveat_only`
- `draft_canary_only == true`
- `advisory_only == true`
- `author_allowed == false`
- `publication_approved == false`
- `eligible_for_claim_insertion == false`
- `eligible_for_authoring == false`
- `eligible_for_publication == false`
- `chapter_update_allowed == false`
- `draft_canary_text` exists and has `word_count <= 90`
- required caveat present
- do-not-say guidance present
- no raw-capture dependency
- no forbidden OpenClaw/Hermes overclaims or publication/chapter-readiness language

Selected canary:

- `draft_canary_run24_caveat_only_cluster_4e8554045cfaf827bc68bcc5`
- derived from draft input: `draft_input_run22b_caveat_only_cluster_4e8554045cfaf827bc68bcc5`

## Test-first evidence

Initial focused test run before implementation failed because the Run 25 script did not exist:

```text
.venv/bin/python -m pytest -q tests/test_llm_author_draft_canary_redteam.py
4 failed ... can't open file '/home/hermoine/terefohealreboa/scripts/llm_author_draft_canary_redteam.py': [Errno 2] No such file or directory
```

After implementation, an intermediate focused run found one validator-order issue: the text mutation tests hit `draft_canary_text word_count mismatch` before the specific forbidden-claim diagnostic. The validator was reordered to check forbidden claim patterns before word-count mismatch so the fail-closed reason is precise.

Final focused tests:

```text
.venv/bin/python -m pytest -q tests/test_llm_author_draft_canary_redteam.py
4 passed in 5.21s
```

## Test coverage added

`tests/test_llm_author_draft_canary_redteam.py` covers:

- selecting the current Run 24 caveat-only draft canary
- writing JSON/Markdown reports in report-only mode
- strict GPT-5.5/profile metadata propagation
- invalid LLM JSON fail-closed behavior
- invalid enum fail-closed behavior
- missing review safety flags fail closed
- `author_allowed=true` fail-closed
- `publication_approved=true` fail-closed
- `eligible_for_claim_insertion=true` fail-closed
- `eligible_for_authoring=true` fail-closed
- `eligible_for_publication=true` fail-closed
- `chapter_update_allowed=true` fail-closed
- `draft_canary_only=false` fail-closed
- missing caveat fail-closed
- missing do-not-say guidance fail-closed
- draft text over 90 words fail-closed
- runtime dependency claim fail-closed
- general operating-environment claim fail-closed
- web/phone access requirement claim fail-closed
- overgeneralization beyond migration/setup/import tooling fail-closed
- publication approval language fail-closed
- chapter-ready language fail-closed
- `draft_canary_passed` still keeps authoring/publication/chapter flags false
- `safe_but_not_useful` routes only to `rebuild_author_draft_input` or `keep_safe_reports_only`
- weak/local fallback refused
- missing profile fail-closed
- DB counts unchanged
- source registry, raw captures, docs/book, schema, and daily worker unchanged
- source/claim/editorial status hashes unchanged

## Live GPT-5.5 red-team command

```bash
python3 scripts/llm_author_draft_canary_redteam.py \
  --run-id citation-pipeline-test-20260612 \
  --canary-report reports/editorial/citation-pipeline-test-20260612-author-draft-canary-run24.json \
  --output-dir reports/editorial \
  --report-suffix run25 \
  --reasoning-profile closed_loop_editorial \
  --timeout-seconds 300
```

Result:

```json
{
  "ok": true,
  "selected_draft_canary_count": 1,
  "reviewed_draft_canary_count": 1,
  "excluded_draft_canary_count": 0,
  "redteam_decision_counts": {"safe_but_not_useful": 1},
  "canary_usefulness_counts": {"not_useful_restates_caveat_only": 1},
  "closed_loop_disposition_counts": {"needs_better_authoring_input": 1},
  "recommended_next_stage_counts": {"rebuild_author_draft_input": 1}
}
```

## Model/profile evidence

Run 25 used the shared strict-JSON bridge:

- Helper: `scripts/hermes_high_reasoning_json.py`
- Provider: `copilot`
- Model: `gpt-5.5`
- Bridge: `hermes_cli`
- Profile: `closed_loop_editorial`
- `llm_used: true`
- `reasoning_status: high_reasoning_used`
- `strict_json_required: true`
- `weak_local_fallback_refused: true`
- Bridge exit code: `0`
- `stdout_json_valid: true`
- Timed out: `false`

## Red-team result

GPT-5.5 judged the canary safe but not useful:

- `redteam_decision_counts: {"safe_but_not_useful": 1}`
- `canary_usefulness_counts: {"not_useful_restates_caveat_only": 1}`
- `closed_loop_disposition_counts: {"needs_better_authoring_input": 1}`
- `recommended_next_stage_counts: {"rebuild_author_draft_input": 1}`

Key assessment:

- Safety containment: adequate while report-only and caveat-only.
- Caveat integrity: required caveat preserved exactly.
- Do-not-say compliance: no forbidden OpenClaw/Hermes overclaims.
- Provenance: traceable to upstream reports and identifiers.
- Usefulness: not useful as author-draft material because it merely restates the caveat.
- Residual risk: controlled while not promoted; overclaiming risk remains if later converted into prose.

## Verification commands and results

Commands run:

```bash
git status --short
.venv/bin/python -m pytest -q tests/test_llm_author_draft_canary_redteam.py
.venv/bin/python -m pytest -q
python3 scripts/verify_book_workspace.py
python3 scripts/verify_editorial_roles.py
python3 scripts/verify_book_citations.py
.venv/bin/python -m mkdocs build --strict
git restore data/source_registry.json docs/book docs/entities docs/research/claims.md || true
rm -f docs/entities/boris-cherny.md
git status --short
git diff -- data/source_registry.json docs/book docs/entities docs/research/claims.md data/schema.sql scripts/daily_book_worker.py
git status --short raw .var logs
```

Verification results:

- Focused Run 25 tests: `4 passed in 5.21s`
- Full pytest suite: `144 passed in 49.21s`
- Workspace verification: `status: ok`
- Editorial roles verification: `status: ok`
- Citation verification: `status: ok`
- MkDocs strict: built successfully
- Protected diff after restore: empty
- `raw .var logs` status after verification: empty

A first verification shell block failed immediately because `printf` interpreted a leading `---` format string as an option. It did not run the checks. The block was rerun using `echo` and completed successfully.

## DB / protected-artifact delta summary

From Run 25 report and post-verification checks:

- `source_notes`: `365 -> 365`
- `claims`: `181 -> 181`
- `editorial_reviews`: `10 -> 10`
- `changed_db: false`
- `changed_source_notes: false`
- `claims_inserted: 0`
- `editorial_reviews_inserted: 0`
- `source_status_changed: false`
- `claim_status_changed: false`
- `editorial_status_changed: false`
- `changed_source_registry: false`
- `changed_raw_captures: false`
- `changed_docs_book: false`
- `changed_schema: false`
- `changed_daily_worker: false`

Protected `git diff` after verification/restores was empty for:

- `data/source_registry.json`
- `docs/book`
- `docs/entities`
- `docs/research/claims.md`
- `data/schema.sql`
- `scripts/daily_book_worker.py`

## Safety conclusion

Run 25 does not approve authoring, publication, claim insertion, editorial-review insertion, source-note persistence, source/status promotion, chapter updates, or docs/book mutation. GPT-5.5 reasoning remains advisory and report-only, not human/editor approval.

## Recommendation for Run 26

Recommended Run 26: report-only rebuild/enrichment of the author-draft input package, because the Run 24 canary was safe but not useful and merely restated the caveat. Run 26 should enrich planning context without generating chapter-ready prose, without writing docs/book, without mutating DB/status/source registry/raw captures/schema/daily worker, and without approving authoring or publication.
