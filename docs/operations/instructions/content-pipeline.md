# Editorial Content Pipeline Instruction

Every research-to-book update must follow this pipeline.

Do not skip steps unless explicitly approved.

## Pipeline

1. Capture sources.
2. Store source metadata.
3. Sanitize source material.
4. Extract source notes.
5. Extract candidate entities.
6. Extract candidate claims.
7. Score source quality.
8. Detect duplicates and repeated signals.
9. Detect contradictions.
10. Curate findings.
11. Editor reviews claims and trends.
12. Author writes from approved/caveated claims.
13. Editor reviews Author output.
14. Book role publishes approved content.
15. Verify build and research quality.
16. Commit/push only safe curated artifacts.

## Hard rule

The Author must not write directly from raw captured material.

The Author must write from:

- approved claims
- source notes
- entity summaries
- chapter briefs
- editor instructions
- style sheet

## Failure handling

If any of the following are true, do not publish new chapter content:

- sources were captured but no entities were extracted
- sources were captured but no claims were extracted
- claims have no source IDs
- claim statuses are missing
- source quality is not scored
- Editor review did not run
- Author output lacks claim/source mapping
- chapter content is generic filler
- MkDocs build fails
- unsafe files are staged
- LinkedIn capture appears blocked, polluted, or session-broken

In such cases, publish only a status report or no update.

## Workflow insertion map

1. Entity extraction: implemented in `scripts/extract_entities.py`, inserted after capture in `scripts/daily_book_worker.py`.
2. Claim extraction: implemented in `scripts/extract_claims.py`, inserted after entity extraction.
3. Source quality scoring: implemented in `scripts/editorial_pipeline_report.py`, inserted before Author synthesis.
4. Claim review/status assignment: implemented in `scripts/editorial_pipeline_report.py`, inserted before Author synthesis.
5. Chapter brief handling: implemented in `scripts/synthesize_chapters.py` and `scripts/book_role_report.py`.
6. Author writing from approved claims: implemented in `scripts/synthesize_chapters.py`, but daily runs skip this unless explicitly allowed.
7. Editor review of chapter diffs: **planned** as durable explicit human/editor approval; v1 blocks and reports through editorial/book gates instead of faking approval.
8. Book role publication: implemented in `scripts/book_role_report.py` and `mkdocs build --strict`.
9. Research quality verification: implemented in `scripts/verify_editorial_ingestion.py` and `scripts/verify_editorial_roles.py`.

## TODO

- Add durable Editor approval records for material chapter diffs.
- Add explicit human approval metadata for major chapter restructure.
- Add richer contradiction/correction workflow.

## Required run output

Each run must produce:

1. Run ID.
2. Source counts.
3. Entity counts.
4. Claim counts.
5. Source quality distribution.
6. New candidate trends.
7. Claims promoted.
8. Claims rejected.
9. Chapter sections updated.
10. Editor warnings.
11. Book build status.
12. Git commit hash, if committed.
13. Final status: success, partial, blocked, or failed.

## Final rule

The pipeline is successful only if it improves either:

- the evidence base,
- the editorial understanding,
- the book structure,
- or the published book.

A run that collects data but does not improve any of those is a partial success, not a complete book update.
