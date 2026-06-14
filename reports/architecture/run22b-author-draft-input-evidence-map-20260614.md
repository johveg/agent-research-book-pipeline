# Run 22B — Report-only caveat-only author-draft input package construction

Created: 2026-06-14

## Objective

Construct a report-only, caveat-only author-draft input package from the Run 21 red-team-approved packet using the Run 22A closed-loop state-machine contract.

This run creates controlled input metadata for a later authoring run. It is not authoring, not prose generation, not chapter prose, not publication approval, and not source/claim/editorial approval.

## Files created

- `scripts/build_author_draft_input.py`
- `tests/test_build_author_draft_input.py`
- `reports/editorial/citation-pipeline-test-20260612-author-draft-input-run22b.json`
- `reports/editorial/citation-pipeline-test-20260612-author-draft-input-run22b.md`
- `reports/architecture/run22b-author-draft-input-evidence-map-20260614.md`

## Inputs

- `reports/editorial/citation-pipeline-test-20260612-closed-loop-state-machine-run22a.json`
- `reports/editorial/citation-pipeline-test-20260612-packet-redteam-gate-run21.json`
- `reports/editorial/citation-pipeline-test-20260612-narrative-packet-candidates-run20.json`

Supporting context remained report-only and protected artifacts were not mutated.

## Model usage

Run 22B did not call GPT-5.5. It used deterministic packaging over existing GPT-5.5 outputs from Runs 20 and 21 plus the Run 22A state-machine contract.

- `llm_used`: false
- `reasoning_status`: `deterministic_packaging_existing_gpt55_outputs`

## TDD evidence

Red phase command:

```bash
.venv/bin/python -m pytest -q tests/test_build_author_draft_input.py
```

Initial expected failure before implementation:

```text
6 failed
can't open file '/home/hermoine/terefohealreboa/scripts/build_author_draft_input.py': [Errno 2] No such file or directory
```

Green phase:

```bash
.venv/bin/python -m pytest -q tests/test_build_author_draft_input.py
```

Result:

```text
6 passed in 1.21s
```

## Report generation

Command:

```bash
python3 scripts/build_author_draft_input.py \
  --run-id citation-pipeline-test-20260612 \
  --state-machine-report reports/editorial/citation-pipeline-test-20260612-closed-loop-state-machine-run22a.json \
  --packet-redteam-report reports/editorial/citation-pipeline-test-20260612-packet-redteam-gate-run21.json \
  --packet-report reports/editorial/citation-pipeline-test-20260612-narrative-packet-candidates-run20.json \
  --output-dir reports/editorial \
  --report-suffix run22b
```

Result:

```json
{
  "ok": true,
  "selected_transition_count": 1,
  "draft_input_package_count": 1,
  "excluded_transition_count": 0,
  "draft_input_type_counts": {"caveat_only_author_draft_input": 1},
  "draft_input_decision_counts": {"caveat_only_draft_input_candidate": 1},
  "draft_input_use_counts": {"caveat_only": 1},
  "target_chapter_status_counts": {"not_assigned": 1}
}
```

## Package created

- `draft_input_id`: `draft_input_run22b_caveat_only_cluster_4e8554045cfaf827bc68bcc5`
- `source_packet_id`: `packet_run20_caveat_only_cluster_4e8554045cfaf827bc68bcc5`
- `draft_input_type`: `caveat_only_author_draft_input`
- `draft_input_decision`: `caveat_only_draft_input_candidate`
- `draft_input_use`: `caveat_only`
- `target_chapter_status`: `not_assigned`

Required caveat preserved:

> Frame narrowly: OpenClaw documentation names Hermes in migration/setup tooling contexts; do not state that Hermes is a runtime dependency or general operating environment without additional sources.

Required do-not-say guidance was included, including runtime dependency, general operating environment, web/phone access, unsupported generalization, factual-claim-without-caveat, and chapter-prose-before-later-gates prohibitions.

## Safety flags

The package keeps:

- `advisory_only`: true
- `author_allowed`: false
- `publication_approved`: false
- `eligible_for_claim_insertion`: false
- `eligible_for_authoring`: false
- `eligible_for_publication`: false
- `chapter_update_allowed`: false

It contains planning metadata only and no chapter-ready prose fields.

## Verification commands and results

```bash
git status --short
.venv/bin/python -m pytest -q tests/test_build_author_draft_input.py
.venv/bin/python -m pytest -q
python3 scripts/verify_book_workspace.py
python3 scripts/verify_editorial_roles.py
python3 scripts/verify_book_citations.py
.venv/bin/python -m mkdocs build --strict
git status --short
```

Results:

- Focused Run 22B tests: `6 passed in 1.09s`
- Full suite: `129 passed in 34.89s`
- `python3 scripts/verify_book_workspace.py`: `status: ok`
- `python3 scripts/verify_editorial_roles.py`: `status: ok`
- `python3 scripts/verify_book_citations.py`: `status: ok`
- `.venv/bin/python -m mkdocs build --strict`: passed, with existing Material/MkDocs warning and nav informational messages only.

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

Run 22B report states:

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

## Recommendation for next run

Proceed to Run 23 as a report-only author-draft construction canary or author-input red-team preflight. The next stage must still avoid chapter prose/publication unless a separate explicit authoring gate is implemented, tested, and verified.
