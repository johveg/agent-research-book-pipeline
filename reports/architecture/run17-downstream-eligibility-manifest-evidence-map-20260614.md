# Run 17 — Closed-loop audit of persisted source-support rereview notes and downstream eligibility manifest

Created: 2026-06-14

## Objective

Audit the persisted Run 16 `source_support_rereview_draft` note and produce a report-only downstream eligibility manifest for a future clustering run.

This run did not cluster, create claims, insert editorial reviews, modify statuses, update source registry, alter raw captures, edit `docs/book`, change schema, change the daily worker, create narrative packets, generate chapter prose, approve authoring, or approve publication.

## Primary inputs

- `reports/editorial/citation-pipeline-test-20260612-persisted-source-support-rereview-notes-run16.json`
- `reports/editorial/citation-pipeline-test-20260612-source-support-rereview-run15.json`
- `.var/book.sqlite` / `source_notes`

## Created files

- `scripts/audit_persisted_rereview_notes.py`
- `tests/test_audit_persisted_rereview_notes.py`
- `reports/editorial/citation-pipeline-test-20260612-downstream-eligibility-manifest-run17.json`
- `reports/editorial/citation-pipeline-test-20260612-downstream-eligibility-manifest-run17.md`
- `reports/architecture/run17-downstream-eligibility-manifest-evidence-map-20260614.md`

## Model-profile use

The script loads `closed_loop_editorial` from `config/reasoning_models.json` through `scripts/model_profiles.py` to enforce the closed-loop profile metadata and weak/local-fallback policy.

No GPT-5.5 call was needed for Run 17 because the audit and manifest decisions are deterministic over already persisted sanitized advisory note JSON.

Recorded profile metadata:

- profile: `closed_loop_editorial`
- provider: `copilot`
- model: `gpt-5.5`
- bridge: `hermes_cli`
- strict JSON required: `true`
- weak/local fallback refused: `true`
- `llm_used: false`
- reasoning status: `deterministic_closed_loop_audit_no_llm_needed`

## Audit target

Persisted note audited:

- note ID: `note_a30056d3f19faa7deb0c9dbc`
- note type: `source_support_rereview_draft`
- source ID: `src_6d7b6d80cda4e784877d`
- source review ID: `source_review_5baf68d86960f91b97ac`
- closed-loop disposition: `eligible_for_review_note_persistence`

The source_notes table contained exactly one `source_support_rereview_draft` row at the time of audit.

## Checks implemented

The script validates:

- Run 16 report mode and safety flags
- Run 15 report mode and advisory safety flags
- persisted row existence by deterministic note ID from Run 16
- persisted row `note_type`
- persisted note JSON parses as an object
- deterministic note ID derived from note type + source review ID + output hash/source review hash
- safety flags:
  - `advisory_only: true`
  - `author_allowed: false`
  - `publication_approved: false`
  - `claim_inserted: false`
  - `editorial_review_inserted: false`
  - `source_registry_promoted: false`
- provenance fields:
  - `source_review_id`
  - `item_id`
  - `original_source_id`
  - `candidate_source_ids`
  - Run 15 report path
  - Run 16 report path
  - `support_decision`
  - `corroboration_decision`
  - `evidence_use_decision`
  - caveat or limitation fields
- skipped Run 16 source-context-unclear item remains excluded from downstream eligibility

## Downstream eligibility decision

The persisted note became:

- downstream manifest decision: `caveat_only_cluster_candidate`

Reason:

- support decision: `partially_supported`
- corroboration decision: `partially_corroborated`
- evidence-use decision: `eligible_for_filing_later_after_corroboration`
- closed-loop disposition: `eligible_for_review_note_persistence`
- safety flags prevent authoring/publication/claim insertion
- caveat is required, so it is a caveat-only cluster candidate rather than unrestricted clustering material

Skipped item preserved as excluded:

- source review ID: `source_review_12c73455aa1816e5df8c`
- downstream manifest decision: `source_context_unclear`
- automated disposition: `source_context_unclear`
- not described as human-only required action

## Final manifest summary

```json
{
  "caveat_only_cluster_candidate_count": 1,
  "eligible_for_clustering_count": 0,
  "excluded_items_count": 1,
  "skipped_items_count": 0,
  "downstream_manifest_decision_counts": {
    "caveat_only_cluster_candidate": 1,
    "source_context_unclear": 1
  },
  "closed_loop_disposition_counts": {
    "eligible_for_review_note_persistence": 1,
    "source_context_unclear": 1
  }
}
```

## DB/source_notes delta

The Run 17 script opened SQLite read-only with `PRAGMA query_only=ON` and performed no writes.

Final counts:

- `source_notes`: 365 → 365
- `source_support_rereview_draft`: 1 → 1
- `claims`: 181 → 181
- `editorial_reviews`: 10 → 10

No source/claim/editorial statuses changed.

## Tests

Added `tests/test_audit_persisted_rereview_notes.py` covering:

- reads Run 16 report and persisted source_notes row
- exactly one `source_support_rereview_draft` note is audited
- eligible note becomes `eligible_for_clustering` or `caveat_only_cluster_candidate`
- `source_context_unclear` item remains excluded
- missing persisted note fails closed
- malformed persisted note JSON fails closed
- missing safety flags fail closed
- `author_allowed=true` fails closed
- `publication_approved=true` fails closed
- `claim_inserted=true` fails closed
- `editorial_review_inserted=true` fails closed
- `source_registry_promoted=true` fails closed
- contradiction / `do_not_use` note is excluded
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

- `7 passed in 2.35s`

Full suite result:

- `89 passed in 22.16s`

## Verification

Commands run:

```bash
git status --short
.venv/bin/python -m pytest -q tests/test_audit_persisted_rereview_notes.py
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

Final protected diff stat was empty for:

- `data/source_registry.json`
- `docs/book`
- `docs/entities`
- `docs/research/claims.md`
- `data/schema.sql`
- `scripts/daily_book_worker.py`

Raw/.var/log git status check showed no tracked/untracked changes in those paths beyond the already intended persisted DB state.

## Safety confirmations

Confirmed unchanged / not performed:

- no DB writes during Run 17 audit
- no source_notes writes during Run 17 audit
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

## Recommendation for Run 18

Run 18 may perform clustering only over Run 17 manifest items marked `eligible_for_clustering` or `caveat_only_cluster_candidate`. It should remain report-first and should not create claims, narrative packets, chapter prose, author approval, or publication approval by default.
