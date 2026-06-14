# Run 15B — Centralize model profiles for coding-agent and reasoning-agent use

Created: 2026-06-14

## Objective

Add a small, safe model-profile abstraction so future pipeline runs can clearly distinguish:

- editorial/research reasoning tasks using GPT-5.5 through the Hermes CLI high-reasoning bridge;
- future coding-agent tasks using an explicit Codex coding profile where available;
- closed-loop editorial disposition tasks with strict JSON and automated disposition metadata;
- forbidden weak/local fallback for safety-critical reasoning.

This run was configuration/refactor only. It did not change Run 15 decisions, did not persist Run 15 outcomes, did not run Run 16 persistence, and did not modify `docs/book`, schema, source registry, raw captures, or protected DB state.

## Files created/changed

Created:

- `config/reasoning_models.json`
- `scripts/model_profiles.py`
- `tests/test_model_profiles.py`
- `reports/architecture/run15b-model-profile-routing-evidence-map-20260614.md`

Updated:

- `scripts/hermes_high_reasoning_json.py`
  - Added optional `--reasoning-profile` support.
  - Preserved explicit `--provider` / `--model` backward compatibility.
  - Includes model-profile metadata in high-reasoning result payloads.
- `scripts/llm_source_support_rereview.py`
  - Added optional `--reasoning-profile` argument for future low-risk profile use.
  - Existing explicit `--provider copilot --model gpt-5.5 --require-high-reasoning` behavior remains supported.

Existing uncommitted Run 15 artifacts remain present and unchanged in purpose:

- `scripts/llm_source_support_rereview.py`
- `tests/test_llm_source_support_rereview.py`
- `reports/editorial/citation-pipeline-test-20260612-source-support-rereview-run15.json`
- `reports/editorial/citation-pipeline-test-20260612-source-support-rereview-run15.md`
- `reports/architecture/run15-source-support-rereview-evidence-map-20260614.md`

## Model profile config

`config/reasoning_models.json` was added.

Available profiles:

- `editorial_reasoning`
  - provider: `copilot`
  - model: `gpt-5.5`
  - bridge: `hermes_cli`
  - reasoning_effort: `high`
  - task_class: `editorial_reasoning`
  - allow_weak_fallback: `false`
  - allow_local_fallback: `false`
  - strict_json_required: `true`

- `coding_agent`
  - provider: `codex`
  - model: `gpt-5.3-codex`
  - bridge: `codex_cli`
  - reasoning_effort: `high`
  - task_class: `coding`
  - allow_weak_fallback: `false`
  - allow_local_fallback: `false`
  - strict_json_required: `false`

- `closed_loop_editorial`
  - provider: `copilot`
  - model: `gpt-5.5`
  - bridge: `hermes_cli`
  - reasoning_effort: `high`
  - task_class: `closed_loop_editorial_disposition`
  - allow_weak_fallback: `false`
  - allow_local_fallback: `false`
  - strict_json_required: `true`
  - allowed dispositions include:
    - `auto_quarantine`
    - `discovery_only`
    - `needs_more_sources`
    - `caveat_only`
    - `exclude_from_pipeline`
    - `contradiction_review_required`
    - `safe_reports_only`
    - `eligible_for_review_note_persistence`
    - `blocked_for_publication_by_policy`
    - `source_context_unclear`

Defaults:

- default editorial reasoning profile: `editorial_reasoning`
- default coding-agent profile: `coding_agent`
- default closed-loop editorial profile: `closed_loop_editorial`

## Fail-closed behavior

Implemented in `scripts/model_profiles.py`:

- missing config fails closed unless explicit provider/model CLI args are supplied;
- missing profile fails closed;
- invalid profile enum fails closed;
- missing provider/model or required fields fail closed;
- editorial/closed-loop profiles must require strict JSON;
- weak/local fallback must remain disabled;
- closed-loop editorial dispositions are validated against an allowlist.

## Backward compatibility

Confirmed by tests:

- Existing `scripts/hermes_high_reasoning_json.py --provider copilot --model gpt-5.5` canary path still works.
- Strict JSON validation still fails closed on invalid JSON, nonzero exit, timeout, or schema mismatch.
- Optional `--reasoning-profile editorial_reasoning` works and reports:
  - provider: `copilot`
  - model: `gpt-5.5`
  - model_profile: `editorial_reasoning`
  - strict_json_required: `true`
  - weak_local_fallback_refused: `true`

## Tests added

`tests/test_model_profiles.py` covers:

- loads `editorial_reasoning` profile;
- loads `coding_agent` profile;
- loads `closed_loop_editorial` profile;
- missing config fails closed;
- explicit provider/model works even if config is missing;
- missing profile fails closed;
- invalid profile missing provider/model fails closed;
- editorial reasoning disallows weak/local fallback;
- closed-loop editorial includes automated dispositions;
- explicit provider/model CLI args remain backward compatible;
- high-reasoning helper profile CLI preserves strict JSON metadata;
- profile loading/helper operations do not modify DB, source registry, raw captures, docs/book, schema, or daily worker.

Existing helper tests also passed:

- `tests/test_hermes_high_reasoning_json.py`

## Verification commands run

```bash
git status --short
.venv/bin/python -m pytest -q tests/test_model_profiles.py
.venv/bin/python -m pytest -q tests/test_hermes_high_reasoning_json.py
.venv/bin/python -m pytest -q
python3 scripts/verify_book_workspace.py
python3 scripts/verify_editorial_roles.py
python3 scripts/verify_book_citations.py
.venv/bin/python -m mkdocs build --strict
git status --short
```

Additional focused compatibility command run during development:

```bash
.venv/bin/python -m pytest -q tests/test_model_profiles.py tests/test_hermes_high_reasoning_json.py tests/test_llm_source_support_rereview.py
```

Results:

- `tests/test_model_profiles.py`: `9 passed in 1.04s`
- `tests/test_hermes_high_reasoning_json.py`: `4 passed in 1.52s`
- focused model/helper/Run15 compatibility set: `17 passed in 5.30s`
- full suite: `75 passed in 17.94s`
- `verify_book_workspace.py`: `status: ok`
- `verify_editorial_roles.py`: `status: ok`
- `verify_book_citations.py`: `status: ok`
- `mkdocs build --strict`: passed, with existing Material/MkDocs warning and existing nav informational messages only.

After verification, generated protected artifacts were restored:

```bash
git restore data/source_registry.json docs/book docs/entities docs/research/claims.md \
  reports/architecture/run1-llm-reasoning-dry-run-evidence-map-20260614.md \
  reports/architecture/run3-source-card-persistence-evidence-map-20260614.md \
  reports/architecture/run4-semantic-object-extraction-evidence-map-20260614.md \
  reports/architecture/run5-high-reasoning-bridge-evidence-map-20260614.md
rm -f docs/entities/boris-cherny.md
```

## Protected artifact delta summary

Final protected diff/status checks showed no diffs for:

- `data/source_registry.json`
- `docs/book`
- `docs/entities`
- `docs/research/claims.md`
- `data/schema.sql`
- `scripts/daily_book_worker.py`

Final raw/DB/log status check showed no git-status changes for:

- `raw`
- `.var`
- `logs`

Therefore Run 15B made no DB/source-registry/raw/docs/book/schema/daily-worker protected changes.

## Safety confirmations

Confirmed unchanged / not performed:

- no DB writes;
- no `source_notes` writes;
- no claims inserted;
- no editorial_reviews inserted;
- no source/claim/editorial status changes;
- no source registry changes;
- no raw capture changes;
- no docs/book changes;
- no schema changes;
- no daily worker changes;
- no narrative packets;
- no chapter prose;
- no authoring approval;
- no publication approval.

## Recommendation for Run 16

Proceed to Run 16 only as a disabled-by-default, report-first source-note/review-note persistence planning run. It should consume Run 15 outputs and consider only items recommended as `eligible_for_review_note_persistence`, while preserving advisory-only safety flags and continuing to avoid claim insertion, narrative packets, chapter prose, or publication approval.
