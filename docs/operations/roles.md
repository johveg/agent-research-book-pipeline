# Editorial Role System

This project is a living research book workflow, not only a collector/source index. The roles below keep collection, curation, editing, authoring, and publication separate.

## Instruction set

- [Master Editorial System](instructions/master-editorial-system.md)
- [Book Role](instructions/book-role.md)
- [Author Role](instructions/author-role.md)
- [Editor Role](instructions/editor-role.md)
- [Curator Function](instructions/curator-function.md)
- [Content Pipeline](instructions/content-pipeline.md)
- [Claim Status](instructions/claim-status.md)
- [Chapter Briefs](instructions/chapter-briefs.md)
- [Author Style Sheet](instructions/author-style-sheet.md)
- [Source Quality](instructions/source-quality.md)
- [Weekly Curation](instructions/weekly-curation.md)
- [Acceptance Criteria](instructions/acceptance-criteria.md)
- [Do Not Publish](instructions/do-not-publish.md)

## Role boundaries

### Collector

Captures and stores source metadata. The Collector does not decide what belongs in prose.

### Curator

Separates meaningful findings from noise, duplicates, weak signals, irrelevant material, and human-review items.

### Editor

Reviews claims, source quality, contradictions, privacy risk, duplicate/repeated signals, trends, and Author output. The Editor may block publication.

### Author

Writes only from approved/caveated claims, chapter briefs, source notes, entity summaries, editor instructions, and the style sheet. The Author does not write from raw captures.

### Book role

Maintains MkDocs structure, navigation, links, reports, strict build status, and publication safety. The Book role does not decide claim truth.

## Current conservative v1 implementation

- Entity extraction: implemented in `scripts/extract_entities.py`, called by `scripts/daily_book_worker.py`.
- Claim extraction: implemented in `scripts/extract_claims.py`, called by `scripts/daily_book_worker.py`.
- Source quality scoring: implemented in `scripts/editorial_pipeline_report.py`.
- Claim review/status assignment: implemented in `scripts/editorial_pipeline_report.py`.
- Chapter brief handling: implemented in `scripts/synthesize_chapters.py` and checked by `scripts/book_role_report.py`.
- Author writing from approved claims: implemented conservatively in `scripts/synthesize_chapters.py`; daily runs skip this unless explicitly allowed.
- Editor review of chapter diffs: **planned** as durable explicit human/editor approval; current v1 blocks and reports through `scripts/editorial_pipeline_report.py` and `scripts/book_role_report.py`.
- Book role publication: implemented in `scripts/book_role_report.py` plus `mkdocs build --strict`.
- Research quality verification: implemented in `scripts/verify_editorial_ingestion.py` and `scripts/verify_editorial_roles.py`.

## TODO

- Add durable Editor approval records for material chapter diffs.
- Add richer contradiction/correction workflow.
- Add a UI or report field for human decisions after weekly curation.
