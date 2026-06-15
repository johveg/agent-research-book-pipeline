# Academic book quality gate

Generated: 2026-06-15T19:38:36Z

- run_id: `run48`
- decision: `mixed_quality_gate_decisions`
- update_count: `3`
- blocked_evidence_stub_count: `1`
- academic_chapter_candidate_count: `1`
- appendix_only_count: `1`
- safe_reports_only_count: `1`
- gpt55_used: `False`

## Decision counts

- academic_book_update_allowed: 1
- appendix_only_allowed: 1
- blocked_evidence_stub_not_chapter_prose: 1

## Updates

- `run48_academic_candidate`: academic_chapter_update -> academic_book_update_allowed
- `run48_evidence_stub`: evidence_stub -> blocked_evidence_stub_not_chapter_prose
  - failed: `missing_definitions`
  - failed: `missing_evidence_grounded_paragraphs`
  - failed: `missing_explicit_chapter_purpose`
  - failed: `missing_limitations_caveats`
  - failed: `missing_sustained_argument`
  - failed: `raw_or_internal_id_in_main_prose`
  - failed: `status_labels_in_main_prose`
- `run48_appendix_candidate`: appendix_evidence_update -> appendix_only_allowed

## Safety

This gate is deterministic/report-only. It does not create human/editor approval, does not approve publication, and does not allow chapter mutation by itself.
