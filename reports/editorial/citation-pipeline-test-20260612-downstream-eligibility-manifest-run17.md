# Run 17 downstream eligibility manifest — citation-pipeline-test-20260612

## Summary

- Report-only: `True`
- Persisted notes audited: `1`
- Eligible for clustering: `0`
- Caveat-only cluster candidates: `1`
- Excluded items: `1`
- Source notes changed: `False`

## Manifest items

- `manifest_2901cc01a0bc7a2252b35183` / note `note_a30056d3f19faa7deb0c9dbc`
  - source_review_id: `source_review_5baf68d86960f91b97ac`
  - decision: `caveat_only_cluster_candidate`
  - caveat_required: `True`
  - support/corroboration/evidence: `partially_supported` / `partially_corroborated` / `eligible_for_filing_later_after_corroboration`

## Excluded items

- source_review_id: `source_review_12c73455aa1816e5df8c`
  - decision: `source_context_unclear`
  - disposition: `source_context_unclear`

## Safety

This manifest does not insert claims or editorial reviews, does not update source/claim/editorial statuses, does not change source_registry/raw captures/docs/book/schema/daily worker, and does not approve authoring or publication.

## Recommendation for Run 18

Run 18 may perform clustering over only the Run 17 manifest items marked `eligible_for_clustering` or `caveat_only_cluster_candidate`. It should remain report-first, not create claims or narrative packets by default, and should preserve author/publication approval flags as false.
