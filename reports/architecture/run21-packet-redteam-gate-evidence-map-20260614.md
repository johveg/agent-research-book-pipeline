# Run 21 — Report-only packet safety and red-team gate

Created: 2026-06-14

## Objective

Use the `closed_loop_editorial` GPT-5.5 profile to red-team the Run 20 packet candidate for safety, caveat integrity, do-not-say compliance, provenance completeness, residual risk, and readiness for a later controlled author-draft input stage.

This run is advisory/report-only. It does not author, persist packets, insert claims, insert editorial reviews, write source notes, change statuses, modify protected files, generate chapter prose, or approve publication.

## Inputs

Primary input:

- `reports/editorial/citation-pipeline-test-20260612-narrative-packet-candidates-run20.json`

Upstream provenance remains linked through the Run 20 packet and earlier reports:

- `reports/editorial/citation-pipeline-test-20260612-cluster-quality-gate-run19.json`
- `reports/editorial/citation-pipeline-test-20260612-research-object-clusters-run18.json`
- `reports/editorial/citation-pipeline-test-20260612-downstream-eligibility-manifest-run17.json`
- `reports/editorial/citation-pipeline-test-20260612-persisted-source-support-rereview-notes-run16.json`
- `reports/editorial/citation-pipeline-test-20260612-source-support-rereview-run15.json`

## Files created

- `scripts/llm_packet_redteam_gate.py`
- `tests/test_llm_packet_redteam_gate.py`
- `reports/editorial/citation-pipeline-test-20260612-packet-redteam-gate-run21.json`
- `reports/editorial/citation-pipeline-test-20260612-packet-redteam-gate-run21.md`
- `reports/architecture/run21-packet-redteam-gate-evidence-map-20260614.md`

## Implementation summary

`scripts/llm_packet_redteam_gate.py`:

- Loads `closed_loop_editorial` from `config/reasoning_models.json` / `scripts/model_profiles.py`.
- Calls `scripts/hermes_high_reasoning_json.py` via `call_high_reasoning_json`.
- Requires:
  - provider: `copilot`
  - model: `gpt-5.5`
  - bridge: `hermes_cli`
  - model profile: `closed_loop_editorial`
  - strict JSON: true
  - weak/local fallback refused: true
- Selects only caveat-only Run 20 packets with all approval/eligibility/update flags false.
- Fails closed on unsafe packet flags, missing required caveat, missing do-not-say guidance, raw-capture dependency, chapter-ready prose fields, invalid/missing inputs, invalid JSON, invalid LLM JSON, invalid enum, missing required fields, missing safety flags, weak/local fallback, or missing model profile.
- Opens SQLite read-only/query-only and compares source_notes/claims/editorial_reviews counts and status hashes before/after.
- Writes only JSON/Markdown report artifacts.

## TDD evidence

Red phase command:

```bash
.venv/bin/python -m pytest -q tests/test_llm_packet_redteam_gate.py
```

Expected initial failure before implementation:

```text
6 failed
can't open file '/home/hermoine/terefohealreboa/scripts/llm_packet_redteam_gate.py': [Errno 2] No such file or directory
```

Green phase after implementation:

```bash
.venv/bin/python -m pytest -q tests/test_llm_packet_redteam_gate.py
```

Result:

```text
6 passed in 3.18s
```

## Live Run 21 command

```bash
python3 scripts/llm_packet_redteam_gate.py \
  --run-id citation-pipeline-test-20260612 \
  --packet-report reports/editorial/citation-pipeline-test-20260612-narrative-packet-candidates-run20.json \
  --output-dir reports/editorial \
  --report-suffix run21 \
  --reasoning-profile closed_loop_editorial \
  --timeout-seconds 300
```

Result:

```json
{
  "ok": true,
  "selected_packet_count": 1,
  "reviewed_packet_count": 1,
  "excluded_packet_count": 0,
  "redteam_decision_counts": {"caveat_only_author_input_ready": 1},
  "author_input_readiness_counts": {"ready_for_caveat_only_draft_input": 1},
  "closed_loop_disposition_counts": {"caveat_only": 1},
  "recommended_next_stage_counts": {"build_caveat_only_author_draft_input": 1}
}
```

## Live GPT-5.5 metadata

From the generated report:

- `llm_used`: true
- `reasoning_status`: `high_reasoning_used`
- `provider`: `copilot`
- `model`: `gpt-5.5`
- `bridge`: `hermes_cli`
- `model_profile`: `closed_loop_editorial`
- `llm_metadata.ok`: true
- `llm_metadata.stdout_json_valid`: true
- `llm_metadata.exit_code`: 0
- `llm_metadata.timed_out`: false
- `llm_metadata.elapsed_seconds`: 22.345

## Red-team result

Counts:

- selected packet count: 1
- reviewed packet count: 1
- excluded packet count: 0
- redteam decision counts: `{"caveat_only_author_input_ready": 1}`
- author-input readiness counts: `{"ready_for_caveat_only_draft_input": 1}`
- closed-loop disposition counts: `{"caveat_only": 1}`
- recommended next-stage counts: `{"build_caveat_only_author_draft_input": 1}`

Reviewed packet:

- `packet_id`: `packet_run20_caveat_only_cluster_4e8554045cfaf827bc68bcc5`
- `redteam_decision`: `caveat_only_author_input_ready`
- `author_input_readiness`: `ready_for_caveat_only_draft_input`
- `closed_loop_disposition`: `caveat_only`
- `recommended_next_stage`: `build_caveat_only_author_draft_input`

Safety flags remain false despite author-input readiness:

- `author_allowed`: false
- `eligible_for_authoring`: false
- `publication_approved`: false
- `eligible_for_publication`: false
- `chapter_update_allowed`: false

## No-write evidence

Generated report states:

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

Final protected diff checks after restoring verification-generated artifacts:

```bash
git diff -- data/source_registry.json docs/book docs/entities docs/research/claims.md data/schema.sql scripts/daily_book_worker.py --stat
```

Output: empty.

```bash
git status --short raw .var logs
```

Output: empty.

## Verification commands and results

```bash
git status --short
.venv/bin/python -m pytest -q tests/test_llm_packet_redteam_gate.py
.venv/bin/python -m pytest -q
python3 scripts/verify_book_workspace.py
python3 scripts/verify_editorial_roles.py
python3 scripts/verify_book_citations.py
.venv/bin/python -m mkdocs build --strict
git status --short
```

Results:

- Focused Run 21 tests: `6 passed in 3.20s`
- Full suite: `116 passed in 33.04s`
- `python3 scripts/verify_book_workspace.py`: `status: ok`
- `python3 scripts/verify_editorial_roles.py`: `status: ok`
- `python3 scripts/verify_book_citations.py`: `status: ok`
- `.venv/bin/python -m mkdocs build --strict`: passed, with existing Material/MkDocs warning and nav informational messages only.

Verification-generated protected artifacts were restored with:

```bash
git restore data/source_registry.json docs/book docs/entities docs/research/claims.md \
  reports/architecture/run1-llm-reasoning-dry-run-evidence-map-20260614.md \
  reports/architecture/run3-source-card-persistence-evidence-map-20260614.md \
  reports/architecture/run4-semantic-object-extraction-evidence-map-20260614.md \
  reports/architecture/run5-high-reasoning-bridge-evidence-map-20260614.md
rm -f docs/entities/boris-cherny.md
```

## Run 22 recommendation

Proceed to Run 22 as a report-only caveat-only author-draft input package construction stage. It may package controlled draft-input guidance from the Run 21-approved packet, but must still keep `author_allowed=false`, `publication_approved=false`, `eligible_for_authoring=false`, `eligible_for_publication=false`, and `chapter_update_allowed=false` unless a later explicitly scoped gate changes those semantics.
