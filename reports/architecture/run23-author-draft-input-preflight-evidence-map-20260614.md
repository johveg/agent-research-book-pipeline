# Run 23 — Report-only author-draft input quality and preflight gate

Created: 2026-06-14

## Objective

Use GPT-5.5 through the `closed_loop_editorial` model profile to perform a strict-JSON quality/preflight gate over the Run 22B author-draft input package before any controlled author-draft canary is allowed.

This run is advisory/report-only. It does not generate author prose, chapter prose, publishable wording, claim insertions, editorial review rows, source notes, status changes, source registry changes, raw captures, docs/book changes, schema changes, daily-worker changes, authoring approval, publication approval, or chapter-update permission.

## Files created

- `scripts/llm_author_draft_input_preflight.py`
- `tests/test_llm_author_draft_input_preflight.py`
- `reports/editorial/citation-pipeline-test-20260612-author-draft-input-preflight-run23.json`
- `reports/editorial/citation-pipeline-test-20260612-author-draft-input-preflight-run23.md`
- `reports/architecture/run23-author-draft-input-preflight-evidence-map-20260614.md`

## Primary input

- `reports/editorial/citation-pipeline-test-20260612-author-draft-input-run22b.json`

## Model/profile used

Run 23 called GPT-5.5 through the repo's shared Hermes strict-JSON bridge.

- provider: `copilot`
- model: `gpt-5.5`
- bridge: `hermes_cli`
- profile: `closed_loop_editorial`
- strict JSON required: `true`
- weak/local fallback refused: `true`

## TDD evidence

Red phase command:

```bash
.venv/bin/python -m pytest -q tests/test_llm_author_draft_input_preflight.py
```

Initial expected failure before implementation:

```text
6 failed
can't open file '/home/hermoine/terefohealreboa/scripts/llm_author_draft_input_preflight.py': [Errno 2] No such file or directory
```

Green phase:

```bash
.venv/bin/python -m pytest -q tests/test_llm_author_draft_input_preflight.py
```

Result:

```text
6 passed in 3.90s
```

## Live report generation

Command:

```bash
python3 scripts/llm_author_draft_input_preflight.py \
  --run-id citation-pipeline-test-20260612 \
  --draft-input-report reports/editorial/citation-pipeline-test-20260612-author-draft-input-run22b.json \
  --output-dir reports/editorial \
  --report-suffix run23 \
  --reasoning-profile closed_loop_editorial \
  --timeout-seconds 300
```

Result:

```json
{
  "ok": true,
  "selected_draft_input_count": 1,
  "reviewed_draft_input_count": 1,
  "excluded_draft_input_count": 0,
  "preflight_decision_counts": {"draft_input_canary_ready": 1},
  "author_canary_readiness_counts": {"ready_for_controlled_caveat_only_author_draft_canary": 1},
  "closed_loop_disposition_counts": {"caveat_only": 1},
  "recommended_next_stage_counts": {"run_controlled_caveat_only_author_draft_canary": 1}
}
```

## Draft input reviewed

- `draft_input_id`: `draft_input_run22b_caveat_only_cluster_4e8554045cfaf827bc68bcc5`
- `draft_input_type`: `caveat_only_author_draft_input`
- `draft_input_use`: `caveat_only`

GPT-5.5 review outcome:

- `preflight_decision`: `draft_input_canary_ready`
- `author_canary_readiness`: `ready_for_controlled_caveat_only_author_draft_canary`
- `closed_loop_disposition`: `caveat_only`
- `recommended_next_stage`: `run_controlled_caveat_only_author_draft_canary`

Important interpretation: this means the package is ready only for a later controlled caveat-only author-draft canary. It does not approve authoring, publication, claim insertion, or chapter update.

## Required caveat and safety flags

Required caveat remains present:

> Frame narrowly: OpenClaw documentation names Hermes in migration/setup tooling contexts; do not state that Hermes is a runtime dependency or general operating environment without additional sources.

Run 23 preflight review keeps:

- `advisory_only`: true
- `author_allowed`: false
- `publication_approved`: false
- `eligible_for_claim_insertion`: false
- `eligible_for_authoring`: false
- `eligible_for_publication`: false
- `chapter_update_allowed`: false

## Verification commands and results

```bash
git status --short
.venv/bin/python -m pytest -q tests/test_llm_author_draft_input_preflight.py
.venv/bin/python -m pytest -q
python3 scripts/verify_book_workspace.py
python3 scripts/verify_editorial_roles.py
python3 scripts/verify_book_citations.py
.venv/bin/python -m mkdocs build --strict
git status --short
```

Results:

- Focused Run 23 tests: `6 passed in 3.94s`
- Full suite: `135 passed in 39.00s`
- `python3 scripts/verify_book_workspace.py`: `status: ok`
- `python3 scripts/verify_editorial_roles.py`: `status: ok`
- `python3 scripts/verify_book_citations.py`: `status: ok`
- `.venv/bin/python -m mkdocs build --strict`: passed, with existing Material/MkDocs warning and existing nav informational messages only.

Verification generated protected artifacts; restored with:

```bash
git restore data/source_registry.json docs/book docs/entities docs/research/claims.md \
  reports/architecture/run1-llm-reasoning-dry-run-evidence-map-20260614.md \
  reports/architecture/run3-source-card-persistence-evidence-map-20260614.md \
  reports/architecture/run4-semantic-object-extraction-evidence-map-20260614.md \
  reports/architecture/run5-high-reasoning-bridge-evidence-map-20260614.md
rm -f docs/entities/boris-cherny.md
```

Final protected checks:

```bash
git diff -- data/source_registry.json docs/book docs/entities docs/research/claims.md data/schema.sql scripts/daily_book_worker.py --stat
git status --short raw .var logs
```

Both returned empty output.

## No-write evidence

Run 23 report states:

- `changed_db`: false
- `changed_source_notes`: false
- `changed_source_registry`: false
- `changed_raw_captures`: false
- `changed_docs_book`: false
- `changed_schema`: false
- `changed_daily_worker`: false
- `claims_inserted`: 0
- `editorial_reviews_inserted`: 0
- `source_status_changed`: false
- `claim_status_changed`: false
- `editorial_status_changed`: false

DB counts:

- `source_notes`: 365 → 365
- `claims`: 181 → 181
- `editorial_reviews`: 10 → 10

## Recommendation for Run 24

Proceed to Run 24 as a controlled report-only caveat-only author-draft canary only if the user explicitly approves that next stage. Run 24 must still avoid docs/book mutation, claim insertion, editorial review insertion, source-note writes, status changes, publication approval, and chapter-update permission unless a separate explicit gate is designed, tested, and verified.
