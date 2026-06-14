# Run 20 — Report-only caveat-only narrative packet candidate construction

Created: 2026-06-14

## Objective

Build a report-only caveat-only narrative packet candidate from the Run 19 cluster quality-gate result without generating chapter prose, approving authoring, approving publication, inserting claims/editorial reviews, writing source notes, changing statuses, or mutating protected source/book artifacts.

## Inputs

Primary input:

- `reports/editorial/citation-pipeline-test-20260612-cluster-quality-gate-run19.json`

Supporting upstream provenance retained through Run 19/Run 18/Run 17/Run 16/Run 15 report links and packet candidate fields:

- `reports/editorial/citation-pipeline-test-20260612-research-object-clusters-run18.json`
- `reports/editorial/citation-pipeline-test-20260612-downstream-eligibility-manifest-run17.json`
- `reports/editorial/citation-pipeline-test-20260612-persisted-source-support-rereview-notes-run16.json`
- `reports/editorial/citation-pipeline-test-20260612-source-support-rereview-run15.json`

## Files created

- `scripts/llm_build_narrative_packets.py`
- `tests/test_llm_build_narrative_packets.py`
- `reports/editorial/citation-pipeline-test-20260612-narrative-packet-candidates-run20.json`
- `reports/editorial/citation-pipeline-test-20260612-narrative-packet-candidates-run20.md`
- `reports/architecture/run20-narrative-packet-candidates-evidence-map-20260614.md`

## Implementation summary

`scripts/llm_build_narrative_packets.py`:

- Loads the `closed_loop_editorial` profile from `scripts/model_profiles.py` / `config/reasoning_models.json`.
- Calls `scripts/hermes_high_reasoning_json.py` through `call_high_reasoning_json`.
- Requires live high-reasoning metadata:
  - provider: `copilot`
  - model: `gpt-5.5`
  - bridge: `hermes_cli`
  - model profile: `closed_loop_editorial`
  - strict JSON required: true
  - weak/local fallback refused: true
- Selects only Run 19 cluster reviews matching:
  - `quality_gate_decision == caveat_only_packet_candidate_ready`
  - `packet_readiness == ready_for_caveat_only_packet`
  - `closed_loop_disposition == caveat_only`
  - `recommended_next_stage == build_caveat_only_packet_candidate`
  - advisory only and all approval/eligibility flags false.
- Excludes not-ready / safe-reports-only / unclear / needs-more-sources items.
- Validates GPT output with closed vocabularies for packet type/decision/use/target status.
- Rejects invalid JSON, invalid enum, missing safety flags, approval/eligibility flag violations, missing required caveat, missing do-not-say guidance, chapter-update eligibility, and chapter-ready prose fields.
- Opens SQLite read-only/query-only and checks counts/status hashes before/after.
- Writes JSON/Markdown reports only.

## TDD evidence

Red phase:

```bash
.venv/bin/python -m pytest -q tests/test_llm_build_narrative_packets.py
```

Initial expected failure before script implementation:

```text
7 failed
can't open file '/home/hermoine/terefohealreboa/scripts/llm_build_narrative_packets.py': [Errno 2] No such file or directory
```

Green phase after implementation:

```bash
.venv/bin/python -m pytest -q tests/test_llm_build_narrative_packets.py
```

Result:

```text
7 passed in 3.06s
```

After prompt/schema tightening:

```text
7 passed in 3.23s
```

## Live Run 20 command

```bash
python3 scripts/llm_build_narrative_packets.py \
  --run-id citation-pipeline-test-20260612 \
  --quality-gate-report reports/editorial/citation-pipeline-test-20260612-cluster-quality-gate-run19.json \
  --output-dir reports/editorial \
  --report-suffix run20 \
  --reasoning-profile closed_loop_editorial \
  --timeout-seconds 300
```

Result:

```json
{
  "ok": true,
  "selected_cluster_review_count": 1,
  "packet_candidate_count": 1,
  "excluded_cluster_review_count": 1,
  "packet_type_counts": {"caveat_only_packet_candidate": 1},
  "packet_decision_counts": {"caveat_only_packet_candidate": 1},
  "packet_use_counts": {"caveat_only": 1},
  "target_chapter_status_counts": {"not_assigned": 1}
}
```

## Live GPT-5.5 metadata

From the generated JSON report:

- `llm_used`: true
- `reasoning_status`: `high_reasoning_used`
- `provider`: `copilot`
- `model`: `gpt-5.5`
- `bridge`: `hermes_cli`
- `model_profile`: `closed_loop_editorial`
- `strict_json_required`: true
- `weak_local_fallback_refused`: true
- `llm_metadata.ok`: true
- `llm_metadata.stdout_json_valid`: true
- `llm_metadata.exit_code`: 0
- `llm_metadata.timed_out`: false
- `llm_metadata.elapsed_seconds`: 28.838

## Packet candidate outcome

Counts:

- selected cluster review count: 1
- packet candidate count: 1
- excluded cluster review count: 1
- packet type counts: `{"caveat_only_packet_candidate": 1}`
- packet decision counts: `{"caveat_only_packet_candidate": 1}`
- packet use counts: `{"caveat_only": 1}`
- target chapter status counts: `{"not_assigned": 1}`

Packet:

- `packet_id`: `packet_run20_caveat_only_cluster_4e8554045cfaf827bc68bcc5`
- `packet_type`: `caveat_only_packet_candidate`
- `packet_decision`: `caveat_only_packet_candidate`
- `packet_use`: `caveat_only`
- `target_chapter_status`: `not_assigned`
- `singleton_packet`: true
- `advisory_only`: true
- `author_allowed`: false
- `publication_approved`: false
- `eligible_for_claim_insertion`: false
- `eligible_for_authoring`: false
- `eligible_for_publication`: false
- `chapter_update_allowed`: false

Required caveat preserved:

> Frame narrowly: OpenClaw documentation names Hermes in migration/setup tooling contexts; do not state that Hermes is a runtime dependency or general operating environment without additional sources.

## Safety and no-write evidence

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
.venv/bin/python -m pytest -q tests/test_llm_build_narrative_packets.py
.venv/bin/python -m pytest -q
python3 scripts/verify_book_workspace.py
python3 scripts/verify_editorial_roles.py
python3 scripts/verify_book_citations.py
.venv/bin/python -m mkdocs build --strict
git status --short
```

Results:

- Focused Run 20 tests: `7 passed in 3.08s`
- Full suite: `110 passed in 30.13s`
- `python3 scripts/verify_book_workspace.py`: `status: ok`
- `python3 scripts/verify_editorial_roles.py`: `status: ok`
- `python3 scripts/verify_book_citations.py`: `status: ok`
- `.venv/bin/python -m mkdocs build --strict`: passed, with existing Material/MkDocs warning and existing nav informational messages only.

Verification-generated protected artifacts were restored with:

```bash
git restore data/source_registry.json docs/book docs/entities docs/research/claims.md \
  reports/architecture/run1-llm-reasoning-dry-run-evidence-map-20260614.md \
  reports/architecture/run3-source-card-persistence-evidence-map-20260614.md \
  reports/architecture/run4-semantic-object-extraction-evidence-map-20260614.md \
  reports/architecture/run5-high-reasoning-bridge-evidence-map-20260614.md
rm -f docs/entities/boris-cherny.md
```

## Important correction during live run

The first live attempt failed closed with:

```text
schema_mismatch:unhashable type: 'list'
```

The cause was GPT returning arrays where scalar closed-vocabulary enum strings were required. The validator was tightened to reject non-string enum values with clearer errors and the prompt schema was tightened to say: choose exactly one string; do not return arrays or objects. The rerun then succeeded.

This follows the staged strict-JSON fail-closed pattern: no coercion, no weak fallback, prompt/schema tightened, rerun recorded.

## Run 21 recommendation

Proceed to Run 21 as a report-only packet safety/red-team gate over the Run 20 packet candidate. It should verify the packet’s caveat-only scope, provenance, do-not-say constraints, and non-authoring/non-publication status before any persistence, authoring, or publication path is considered.
