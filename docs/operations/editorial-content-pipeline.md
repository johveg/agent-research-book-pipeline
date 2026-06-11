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
