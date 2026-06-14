# Run 22A — Closed-loop state machine and promotion contract

Created: 2026-06-14

## Objective

Create a deterministic closed-loop state machine and promotion-contract layer for the Terefo Heal Reboa editorial pipeline before any author-draft-input construction.

This run is a control-plane/configuration run. It does not create draft-input packages, author prose, persist packets, insert claims, insert editorial reviews, write source notes, change source/claim/editorial statuses, change `source_registry.json`, raw captures, `docs/book`, `data/schema.sql`, or `scripts/daily_book_worker.py`.

## Files created

- `config/closed_loop_state_machine.json`
- `scripts/closed_loop_state_machine.py`
- `tests/test_closed_loop_state_machine.py`
- `reports/editorial/citation-pipeline-test-20260612-closed-loop-state-machine-run22a.json`
- `reports/editorial/citation-pipeline-test-20260612-closed-loop-state-machine-run22a.md`
- `reports/architecture/run22a-closed-loop-state-machine-evidence-map-20260614.md`

## Primary inputs

- `reports/editorial/citation-pipeline-test-20260612-packet-redteam-gate-run21.json`
- `reports/editorial/citation-pipeline-test-20260612-narrative-packet-candidates-run20.json`
- `reports/editorial/citation-pipeline-test-20260612-cluster-quality-gate-run19.json`
- `reports/editorial/citation-pipeline-test-20260612-research-object-clusters-run18.json`
- `reports/editorial/citation-pipeline-test-20260612-downstream-eligibility-manifest-run17.json`
- `reports/editorial/citation-pipeline-test-20260612-persisted-source-support-rereview-notes-run16.json`
- `reports/editorial/citation-pipeline-test-20260612-source-support-rereview-run15.json`
- `config/reasoning_models.json`

Run 22A used deterministic validation only. No live GPT-5.5 or Codex call was needed.

## State machine contract

The config defines:

- states: 21
- transitions: 10
- automated dispositions: 14

Hard invariants are machine-readable and require these remain false until future explicit gates:

- authoring permission
- publication approval
- publication eligibility
- chapter-update permission
- GPT-5.5 advisory reasoning as human/editor approval
- report files implying persistence
- persistence implying authoring
- packets implying prose
- draft-input readiness implying authoring approval
- author draft implying publication
- blocked editorial state allowing chapter mutation
- weak/local fallback for safety-critical editorial reasoning

## TDD evidence

Red phase command:

```bash
.venv/bin/python -m pytest -q tests/test_closed_loop_state_machine.py
```

Initial expected failure before implementation:

```text
7 failed
FileNotFoundError: scripts/closed_loop_state_machine.py
```

Green phase:

```bash
.venv/bin/python -m pytest -q tests/test_closed_loop_state_machine.py
```

Result:

```text
7 passed in 0.30s
```

Final focused result after a small provenance-path fix:

```text
7 passed in 0.32s
```

## Report generation

Command:

```bash
python3 scripts/closed_loop_state_machine.py \
  --run-id citation-pipeline-test-20260612 \
  --packet-redteam-report reports/editorial/citation-pipeline-test-20260612-packet-redteam-gate-run21.json \
  --state-machine-config config/closed_loop_state_machine.json \
  --output-dir reports/editorial \
  --report-suffix run22a
```

Result:

```json
{
  "ok": true,
  "states_count": 21,
  "transitions_count": 10,
  "dispositions_count": 14,
  "current_object_count": 1,
  "transition_decision_counts": {"allowed_for_future_run": 1},
  "proposed_next_state_counts": {"draft_input_candidate": 1},
  "allowed_for_future_run_count": 1,
  "blocked_count": 0
}
```

## Current object classification

Object:

- `packet_run20_caveat_only_cluster_4e8554045cfaf827bc68bcc5`

Classification:

- current_state: `packet_redteam_reviewed`
- proposed_next_state: `draft_input_candidate`
- transition_decision: `allowed_for_future_run`
- allowed_future_run: `build_caveat_only_author_draft_input`
- automated_disposition: `caveat_only_author_input_ready`

Satisfied guards:

- `redteam_decision_caveat_only_author_input_ready`
- `author_allowed_false`
- `publication_approved_false`
- `eligible_for_authoring_false`
- `eligible_for_publication_false`
- `chapter_update_allowed_false`

Failed guards: none.

Safety flags remain:

- `author_allowed`: false
- `publication_approved`: false
- `eligible_for_authoring`: false
- `eligible_for_publication`: false
- `chapter_update_allowed`: false

## No-write evidence

Run 22A report states:

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

Final protected diff check:

```bash
git diff -- data/source_registry.json docs/book docs/entities docs/research/claims.md data/schema.sql scripts/daily_book_worker.py --stat
```

Output: empty.

Final raw/.var/logs check:

```bash
git status --short raw .var logs
```

Output: empty.

## Verification commands and results

```bash
git status --short
.venv/bin/python -m pytest -q tests/test_closed_loop_state_machine.py
.venv/bin/python -m pytest -q
python3 scripts/verify_book_workspace.py
python3 scripts/verify_editorial_roles.py
python3 scripts/verify_book_citations.py
.venv/bin/python -m mkdocs build --strict
git status --short
```

Results:

- Focused Run 22A tests: `7 passed in 0.28s`
- Full suite: `123 passed in 33.84s`
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

## Recommendation for next run

Proceed to Run 22B as report-only caveat-only author-draft input package construction using the Run 22A state-machine contract. Run 22B may produce controlled draft-input package metadata only. It must not author prose, generate chapter prose, insert claims/editorial reviews/source notes, persist packets, or approve publication.
