# Run 18 — Report-only clustering of downstream-eligible caveat/support objects

Created: 2026-06-14

## Objective

Create report-only cluster candidates from Run 17 downstream manifest items marked:

- `eligible_for_clustering`
- `caveat_only_cluster_candidate`

The current Run 17 manifest contains one caveat-only cluster candidate, so Run 18 proves the clustering structure with a singleton caveat-only cluster while preserving all advisory/no-publication constraints.

## Created files

- `scripts/llm_cluster_research_objects.py`
- `tests/test_llm_cluster_research_objects.py`
- `reports/editorial/citation-pipeline-test-20260612-research-object-clusters-run18.json`
- `reports/editorial/citation-pipeline-test-20260612-research-object-clusters-run18.md`
- `reports/architecture/run18-research-object-clustering-evidence-map-20260614.md`

## Primary input

- `reports/editorial/citation-pipeline-test-20260612-downstream-eligibility-manifest-run17.json`

## Model-profile use

The script loads `closed_loop_editorial` from `config/reasoning_models.json` through `scripts/model_profiles.py` to preserve explicit profile metadata and weak/local-fallback policy.

No GPT-5.5 call was needed for Run 18 because clustering is deterministic over the already sanitized Run 17 manifest.

Recorded profile metadata:

- profile: `closed_loop_editorial`
- provider: `copilot`
- model: `gpt-5.5`
- bridge: `hermes_cli`
- strict JSON required: `true`
- weak/local fallback refused: `true`
- `llm_used: false`
- reasoning status: `deterministic_report_only_clustering_no_llm_needed`

## Selection and exclusion rules implemented

Selected only manifest items whose `downstream_manifest_decision` is:

- `eligible_for_clustering`
- `caveat_only_cluster_candidate`

Excluded items whose downstream decision or closed-loop disposition is:

- `source_context_unclear`
- `needs_more_sources`
- `exclude_from_clustering`
- `exclude_from_pipeline`
- `contradiction_review_required`
- `safe_reports_only`
- `do_not_use`

Also excluded contradiction/do-not-use test fixtures.

## Cluster produced

Cluster candidate:

- `cluster_id`: `cluster_4e8554045cfaf827bc68bcc5`
- `cluster_type`: `caveat_only_support_cluster`
- `cluster_use`: `caveat_only`
- `cluster_decision`: `caveat_only_cluster_candidate`
- `singleton_cluster`: `true`
- manifest item: `manifest_2901cc01a0bc7a2252b35183`
- note: `note_a30056d3f19faa7deb0c9dbc`
- source review: `source_review_5baf68d86960f91b97ac`

Reasoning:

- The Run 17 item is downstream eligible only as `caveat_only_cluster_candidate`.
- `caveat_required` is true.
- Therefore the cluster must remain caveat-only and cannot become a support claim, narrative packet, authoring input, or publication input.

Excluded item preserved:

- source review: `source_review_12c73455aa1816e5df8c`
- decision: `source_context_unclear`
- remains excluded from clustering.

## Final Run 18 report summary

```json
{
  "selected_manifest_items_count": 1,
  "excluded_manifest_items_count": 1,
  "cluster_candidates_count": 1,
  "singleton_cluster_count": 1,
  "caveat_only_cluster_count": 1,
  "support_cluster_count": 0,
  "cluster_decision_counts": {
    "caveat_only_cluster_candidate": 1
  },
  "cluster_type_counts": {
    "caveat_only_support_cluster": 1
  },
  "cluster_use_counts": {
    "caveat_only": 1
  }
}
```

## DB/source_notes delta

Run 18 is report-only. SQLite was opened read-only with `PRAGMA query_only=ON`.

Final counts:

- `source_notes`: 365 → 365
- `claims`: 181 → 181
- `editorial_reviews`: 10 → 10

No source_notes writes occurred.

## Protected-file delta

Final protected diff stat was empty for:

- `data/source_registry.json`
- `docs/book`
- `docs/entities`
- `docs/research/claims.md`
- `data/schema.sql`
- `scripts/daily_book_worker.py`

Raw/.var/log git status check showed no tracked/untracked changes in those paths beyond the already intended persisted Run 16 DB state.

## Tests

Added `tests/test_llm_cluster_research_objects.py` covering:

- selects only `eligible_for_clustering` and `caveat_only_cluster_candidate` manifest items
- excludes `source_context_unclear` item
- creates exactly one cluster candidate for current Run 17 manifest
- creates singleton cluster when only one item is eligible
- `caveat_only_cluster_candidate` becomes caveat-only cluster use
- caveat-only cluster is not eligible for claim insertion
- caveat-only cluster is not eligible for authoring
- caveat-only cluster is not eligible for publication
- `author_allowed` remains false
- `publication_approved` remains false
- `advisory_only` remains true
- malformed manifest fails closed
- missing manifest fails closed
- contradiction / `do_not_use` / `source_context_unclear` items are excluded
- report-only mode does not modify SQLite
- source_notes unchanged
- claims unchanged
- editorial_reviews unchanged
- source/claim/editorial statuses unchanged
- source_registry unchanged
- raw captures unchanged
- docs/book unchanged
- schema unchanged
- daily worker unchanged

Focused test result:

- `7 passed in 2.13s`

Full suite result:

- `96 passed in 24.13s`

## Verification commands run

```bash
git status --short
.venv/bin/python -m pytest -q tests/test_llm_cluster_research_objects.py
.venv/bin/python -m pytest -q
python3 scripts/verify_book_workspace.py
python3 scripts/verify_editorial_roles.py
python3 scripts/verify_book_citations.py
.venv/bin/python -m mkdocs build --strict
git status --short
```

Verifier results:

- `python3 scripts/verify_book_workspace.py`: `status: ok`
- `python3 scripts/verify_editorial_roles.py`: `status: ok`
- `python3 scripts/verify_book_citations.py`: `status: ok`
- `.venv/bin/python -m mkdocs build --strict`: passed, with existing Material/MkDocs warning and existing nav informational messages only

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

## Safety confirmations

Confirmed unchanged / not performed:

- no DB writes
- no source_notes writes
- no claims inserted
- no editorial_reviews inserted
- no source/claim/editorial status changes
- no source_registry changes
- no raw capture changes
- no docs/book changes
- no schema changes
- no daily worker changes
- no narrative packets
- no chapter prose
- no authoring approval
- no publication approval
- cluster candidates are not claims

## Recommendation for Run 19

Run 19 should audit the Run 18 cluster candidate and decide the next report-first path. A safe next step would be a disabled-by-default cluster persistence design or a richer clustering pass if more eligible manifest items are available. It should not insert claims, create narrative packets, generate chapter prose, or approve authoring/publication by default.
