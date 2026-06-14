# Run 19 — Cluster quality gate and packet-readiness review

Created: 2026-06-14

## Objective

Use the `closed_loop_editorial` GPT-5.5 profile to perform an advisory quality gate over Run 18 cluster candidates and determine whether the selected cluster is ready to become a narrative packet candidate later.

Run 19 remained report-only:

- no cluster persistence
- no narrative packets
- no claims
- no editorial_reviews
- no source_notes writes
- no source/claim/editorial status changes
- no source_registry changes
- no raw capture changes
- no docs/book changes
- no schema changes
- no daily worker changes
- no chapter prose
- no authoring approval
- no publication approval
- GPT-5.5 advisory reasoning is not treated as human/editor approval

## Inputs

Primary input:

- `reports/editorial/citation-pipeline-test-20260612-research-object-clusters-run18.json`

Runtime/provenance inputs used by Run 18 cluster object:

- `reports/editorial/citation-pipeline-test-20260612-downstream-eligibility-manifest-run17.json`
- `reports/editorial/citation-pipeline-test-20260612-persisted-source-support-rereview-notes-run16.json`
- `reports/editorial/citation-pipeline-test-20260612-source-support-rereview-run15.json`

SQLite was opened read-only via `.var/book.sqlite` and `PRAGMA query_only = ON`.

## Files created

- `scripts/llm_cluster_quality_gate.py`
- `tests/test_llm_cluster_quality_gate.py`
- `reports/editorial/citation-pipeline-test-20260612-cluster-quality-gate-run19.json`
- `reports/editorial/citation-pipeline-test-20260612-cluster-quality-gate-run19.md`
- `reports/architecture/run19-cluster-quality-gate-evidence-map-20260614.md`

## Test-first evidence

Focused tests were added before the production script existed.

Initial red-phase command:

```bash
.venv/bin/python -m pytest -q tests/test_llm_cluster_quality_gate.py
```

Expected failure:

- `scripts/llm_cluster_quality_gate.py` missing
- 7 failing tests

After implementation and one fail-closed error-message patch:

```bash
.venv/bin/python -m pytest -q tests/test_llm_cluster_quality_gate.py
```

Result:

- `7 passed in 2.76s`

## Implementation summary

`scripts/llm_cluster_quality_gate.py`:

- reads the Run 18 cluster report
- validates report-only safety flags
- selects only cluster candidates where:
  - `cluster_decision in {cluster_candidate, caveat_only_cluster_candidate}`
  - `advisory_only == true`
  - `author_allowed == false`
  - `publication_approved == false`
  - `eligible_for_claim_insertion == false`
  - `eligible_for_authoring == false`
  - `eligible_for_publication == false`
- excludes blocked/source-context items
- loads `closed_loop_editorial` from `config/reasoning_models.json`
- calls `scripts/hermes_high_reasoning_json.py` via `call_high_reasoning_json(...)`
- validates strict JSON with schema and enum checks
- fails closed on invalid JSON, invalid enums, missing safety flags, forbidden promotion flags, weak/local provider, missing profile, missing inputs, malformed inputs, and forbidden DB/status deltas
- writes JSON and Markdown reports only

## GPT-5.5 live run

Command:

```bash
python3 scripts/llm_cluster_quality_gate.py \
  --run-id citation-pipeline-test-20260612 \
  --cluster-report reports/editorial/citation-pipeline-test-20260612-research-object-clusters-run18.json \
  --output-dir reports/editorial \
  --report-suffix run19 \
  --reasoning-profile closed_loop_editorial \
  --timeout-seconds 300
```

Result:

```json
{
  "selected_cluster_count": 1,
  "reviewed_cluster_count": 1,
  "excluded_cluster_count": 1,
  "quality_gate_decision_counts": {
    "caveat_only_packet_candidate_ready": 1
  },
  "packet_readiness_counts": {
    "ready_for_caveat_only_packet": 1
  },
  "closed_loop_disposition_counts": {
    "caveat_only": 1
  },
  "recommended_next_stage_counts": {
    "build_caveat_only_packet_candidate": 1
  }
}
```

Model metadata from report:

- `llm_used: true`
- `reasoning_status: high_reasoning_used`
- `provider: copilot`
- `model: gpt-5.5`
- `bridge: hermes_cli`
- `model_profile: closed_loop_editorial`
- `strict_json_required: true`
- `weak_local_fallback_refused: true`
- `exit_code: 0`
- `stdout_json_valid: true`
- `timed_out: false`
- elapsed seconds: `29.043`

## Selected cluster

Selected:

- `cluster_4e8554045cfaf827bc68bcc5`
- type: `caveat_only_support_cluster`
- use: `caveat_only`
- singleton: `true`
- source review: `source_review_5baf68d86960f91b97ac`
- note: `note_a30056d3f19faa7deb0c9dbc`
- manifest item: `manifest_2901cc01a0bc7a2252b35183`

Excluded:

- `source_review_12c73455aa1816e5df8c`
- exclusion decision: `source_context_unclear`

## Quality-gate result

For `cluster_4e8554045cfaf827bc68bcc5`:

- `quality_gate_decision: caveat_only_packet_candidate_ready`
- `packet_readiness: ready_for_caveat_only_packet`
- `closed_loop_disposition: caveat_only`
- `recommended_next_stage: build_caveat_only_packet_candidate`

Important constraints preserved:

- advisory only
- not claim insertion
- not authoring approval
- not publication approval
- not chapter prose
- not narrative packet creation in Run 19
- caveat-only framing required

Required caveat from GPT-5.5:

> Frame narrowly: OpenClaw documentation names Hermes in migration/setup tooling contexts; do not state that Hermes is a runtime dependency or general operating environment without additional sources.

## Verification

Required verification command block:

```bash
git status --short
.venv/bin/python -m pytest -q tests/test_llm_cluster_quality_gate.py
.venv/bin/python -m pytest -q
python3 scripts/verify_book_workspace.py
python3 scripts/verify_editorial_roles.py
python3 scripts/verify_book_citations.py
.venv/bin/python -m mkdocs build --strict
git status --short
```

Results:

- focused Run 19 tests: `7 passed in 2.78s`
- full suite: `103 passed in 27.21s`
- `verify_book_workspace.py`: `status: ok`
- `verify_editorial_roles.py`: `status: ok`
- `verify_book_citations.py`: `status: ok`
- MkDocs strict build: passed

MkDocs emitted the existing Material/MkDocs warning and existing nav informational messages only.

## Restore after verification

Verification generated protected artifacts. Restored with:

```bash
git restore data/source_registry.json docs/book docs/entities docs/research/claims.md \
  reports/architecture/run1-llm-reasoning-dry-run-evidence-map-20260614.md \
  reports/architecture/run3-source-card-persistence-evidence-map-20260614.md \
  reports/architecture/run4-semantic-object-extraction-evidence-map-20260614.md \
  reports/architecture/run5-high-reasoning-bridge-evidence-map-20260614.md
rm -f docs/entities/boris-cherny.md
```

Final protected artifacts were restored.

## DB/status deltas

Run 19 report counts:

- `source_notes: 365 -> 365`
- `claims: 181 -> 181`
- `editorial_reviews: 10 -> 10`

Report flags:

- `changed_db: false`
- `changed_source_notes: false`
- `claims_inserted: 0`
- `editorial_reviews_inserted: 0`
- `source_status_changed: false`
- `claim_status_changed: false`
- `editorial_status_changed: false`

## Protected artifact deltas

No final intended diff after restore:

- `data/source_registry.json`
- raw captures
- `docs/book`
- `docs/entities`
- `docs/research/claims.md`
- `data/schema.sql`
- `scripts/daily_book_worker.py`

## Report paths

JSON:

- `reports/editorial/citation-pipeline-test-20260612-cluster-quality-gate-run19.json`

Markdown:

- `reports/editorial/citation-pipeline-test-20260612-cluster-quality-gate-run19.md`

Architecture evidence map:

- `reports/architecture/run19-cluster-quality-gate-evidence-map-20260614.md`

## Recommendation for Run 20

Run 20 may build a report-only caveat-only narrative packet candidate for `cluster_4e8554045cfaf827bc68bcc5`, because Run 19 recommended `build_caveat_only_packet_candidate`.

Run 20 should remain report-only by default and must still avoid:

- claims insertion
- editorial_reviews insertion
- source_notes writes unless a separate disabled-by-default persistence run is explicitly designed
- status changes
- source_registry/raw capture changes
- docs/book changes
- chapter prose
- authoring approval
- publication approval

A safe Run 20 title would be:

> Report-only caveat-only narrative packet candidate construction
