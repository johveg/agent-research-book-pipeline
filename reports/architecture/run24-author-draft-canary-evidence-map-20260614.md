# Run 24 — Controlled report-only caveat-only author-draft canary

Created: 2026-06-14

## Objective

Generate the first controlled caveat-only author-draft canary from the Run 22B draft-input package, using Run 23 preflight approval, while keeping the result report-only and non-publication-approved.

## Inputs

Primary inputs:

- `reports/editorial/citation-pipeline-test-20260612-author-draft-input-preflight-run23.json`
- `reports/editorial/citation-pipeline-test-20260612-author-draft-input-run22b.json`

Supporting lineage preserved in the selected draft input:

- `reports/editorial/citation-pipeline-test-20260612-closed-loop-state-machine-run22a.json`
- `reports/editorial/citation-pipeline-test-20260612-packet-redteam-gate-run21.json`
- `reports/editorial/citation-pipeline-test-20260612-narrative-packet-candidates-run20.json`
- `reports/editorial/citation-pipeline-test-20260612-cluster-quality-gate-run19.json`
- `reports/editorial/citation-pipeline-test-20260612-research-object-clusters-run18.json`
- `reports/editorial/citation-pipeline-test-20260612-downstream-eligibility-manifest-run17.json`
- `reports/editorial/citation-pipeline-test-20260612-persisted-source-support-rereview-notes-run16.json`
- `reports/editorial/citation-pipeline-test-20260612-source-support-rereview-run15.json`

## Files created

- `scripts/llm_author_draft_canary.py`
- `tests/test_llm_author_draft_canary.py`
- `reports/editorial/citation-pipeline-test-20260612-author-draft-canary-run24.json`
- `reports/editorial/citation-pipeline-test-20260612-author-draft-canary-run24.md`
- `reports/architecture/run24-author-draft-canary-evidence-map-20260614.md`

## TDD evidence

Red test before implementation:

```bash
.venv/bin/python -m pytest -q tests/test_llm_author_draft_canary.py
```

Expected result before script existed:

```text
5 failed
can't open file '/home/hermoine/terefohealreboa/scripts/llm_author_draft_canary.py': [Errno 2] No such file or directory
```

Focused tests after implementation:

```bash
.venv/bin/python -m pytest -q tests/test_llm_author_draft_canary.py
```

Result:

```text
5 passed in 5.84s
```

## Live GPT-5.5 run

Command:

```bash
python3 scripts/llm_author_draft_canary.py \
  --run-id citation-pipeline-test-20260612 \
  --preflight-report reports/editorial/citation-pipeline-test-20260612-author-draft-input-preflight-run23.json \
  --draft-input-report reports/editorial/citation-pipeline-test-20260612-author-draft-input-run22b.json \
  --output-dir reports/editorial \
  --report-suffix run24 \
  --reasoning-profile closed_loop_editorial \
  --timeout-seconds 300
```

First live attempt failed closed:

```text
schema_mismatch:caveat_compliance_notes must be non-empty string
```

This was treated as a correct fail-closed validation event. The prompt schema was tightened to state scalar/non-empty string requirements explicitly, then the live run was rerun.

Successful rerun summary:

```json
{
  "selected_draft_input_count": 1,
  "draft_canary_count": 1,
  "excluded_draft_input_count": 0,
  "draft_canary_type_counts": {"caveat_only_author_draft_canary": 1},
  "draft_canary_decision_counts": {"draft_canary_created": 1},
  "draft_canary_use_counts": {"caveat_only": 1},
  "target_chapter_status_counts": {"not_assigned": 1}
}
```

## Model/profile evidence

Live report metadata:

- `llm_used`: `true`
- `reasoning_status`: `high_reasoning_used`
- provider: `copilot`
- model: `gpt-5.5`
- bridge: `hermes_cli`
- model_profile: `closed_loop_editorial`
- strict JSON required: `true`
- weak/local fallback refused: `true`

## Selected object

- `draft_input_id`: `draft_input_run22b_caveat_only_cluster_4e8554045cfaf827bc68bcc5`
- `source_packet_id`: `packet_run20_caveat_only_cluster_4e8554045cfaf827bc68bcc5`
- `source_cluster_id`: `cluster_4e8554045cfaf827bc68bcc5`
- `target_chapter_status`: `not_assigned`

## Draft canary result

- `draft_canary_type`: `caveat_only_author_draft_canary`
- `draft_canary_decision`: `draft_canary_created`
- `draft_canary_use`: `caveat_only`
- `draft_canary_only`: `true`
- `advisory_only`: `true`
- `singleton_canary`: `true`
- `word_count`: `26`

Draft canary text:

> Frame narrowly: OpenClaw documentation names Hermes in migration/setup tooling contexts; do not state that Hermes is a runtime dependency or general operating environment without additional sources.

## Safety validation implemented

The script validates:

- Run 23 preflight is `llm_author_draft_input_preflight`, report-only, GPT-5.5, `closed_loop_editorial`.
- Run 24 selects only preflight reviews with:
  - `preflight_decision=draft_input_canary_ready`
  - `author_canary_readiness=ready_for_controlled_caveat_only_author_draft_canary`
  - `closed_loop_disposition=caveat_only`
  - `recommended_next_stage=run_controlled_caveat_only_author_draft_canary`
  - all hard approval/publication/chapter flags false.
- Run 22B package cross-checks:
  - `draft_input_type=caveat_only_author_draft_input`
  - `draft_input_decision=caveat_only_draft_input_candidate`
  - `draft_input_use=caveat_only`
  - required caveat present
  - do-not-say guidance present
  - `target_chapter_status=not_assigned`
  - all hard approval/publication/chapter flags false.
- LLM JSON schema checks:
  - required fields present
  - scalar enums only
  - invalid JSON fails closed
  - invalid enums fail closed
  - missing/unsafe safety flags fail closed
  - weak/local fallback refused
  - missing profile fails closed
  - draft canary text must be one paragraph and <=90 words
  - draft canary text must preserve required caveat exactly
  - runtime-dependency, general-operating-environment, web/phone-access, overgeneralization, publication approval, and chapter-readiness language fails closed.

## Verification

Commands:

```bash
git status --short
.venv/bin/python -m pytest -q tests/test_llm_author_draft_canary.py
.venv/bin/python -m pytest -q
python3 scripts/verify_book_workspace.py
python3 scripts/verify_editorial_roles.py
python3 scripts/verify_book_citations.py
.venv/bin/python -m mkdocs build --strict
git status --short
```

Results:

- Focused Run 24 tests: `5 passed in 5.83s`
- Full suite: `140 passed in 44.27s`
- `verify_book_workspace.py`: `status: ok`
- `verify_editorial_roles.py`: `status: ok`
- `verify_book_citations.py`: `status: ok`
- `mkdocs build --strict`: passed

MkDocs emitted the existing Material/MkDocs 2.0 warning and existing nav informational messages.

## Protected artifact restoration

Verification generated protected artifacts. Restored with:

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

## DB and protected deltas

From the Run 24 live report:

- `changed_db`: `false`
- `changed_source_notes`: `false`
- `changed_source_registry`: `false`
- `changed_raw_captures`: `false`
- `changed_docs_book`: `false`
- `changed_schema`: `false`
- `changed_daily_worker`: `false`
- `claims_inserted`: `0`
- `editorial_reviews_inserted`: `0`
- `source_status_changed`: `false`
- `claim_status_changed`: `false`
- `editorial_status_changed`: `false`
- `source_notes_count_before`: `365`
- `source_notes_count_after`: `365`
- `claims_count_before`: `181`
- `claims_count_after`: `181`
- `editorial_reviews_count_before`: `10`
- `editorial_reviews_count_after`: `10`

## Conclusion

Run 24 produced one controlled, caveat-only, non-publication-approved draft canary in report artifacts only. It did not write chapter prose or mutate `docs/book`; it did not insert claims, editorial reviews, or source notes; and it did not change source/claim/editorial statuses, source registry, raw captures, schema, or the daily worker.

## Recommendation for Run 25

Proceed, if approved, to a report-only author-draft canary red-team/containment review. Run 25 should review the Run 24 canary for caveat preservation, overclaiming, provenance sufficiency, and prose-promotion risk before any broader authoring, publication gate, claim insertion, or chapter-update candidate is considered.
