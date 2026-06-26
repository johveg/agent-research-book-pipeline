# Operations Runbook

Use Hermes cron jobs to start the daily worker, poll status, and run a non-destructive watchdog. Do not kill the persistent LinkedIn browser unless explicitly authorized.

## Editorial role system

The published editorial instructions live under [Roles](roles.md) and [Operations / Instructions](instructions/master-editorial-system.md).

## Conservative daily workflow

Daily runs are for collection and preparation, not automatic chapter rewriting.

1. Capture web and LinkedIn source metadata.
2. Run entity extraction with `scripts/extract_entities.py`.
3. Run claim extraction with `scripts/extract_claims.py`.
4. Run source quality scoring and claim review with `scripts/editorial_pipeline_report.py`.
5. Update safe source/entity/claim/report pages.
6. Skip Author chapter synthesis unless weekly curation or explicit Editor approval allows `--allow-chapter-updates`.
7. Run `scripts/book_role_report.py` for publication safety.
8. Run research quality verification.

## Workflow insertion map

- Entity extraction: implemented in `scripts/extract_entities.py`, inserted after capture in `scripts/daily_book_worker.py`.
- Claim extraction: implemented in `scripts/extract_claims.py`, inserted after entity extraction.
- Source quality scoring: implemented in `scripts/editorial_pipeline_report.py`, inserted before Author synthesis.
- Claim review/status assignment: implemented in `scripts/editorial_pipeline_report.py`, inserted before Author synthesis.
- Chapter brief handling: implemented in `scripts/synthesize_chapters.py` and `scripts/book_role_report.py`.
- Author writing from approved claims: implemented in `scripts/synthesize_chapters.py`, but skipped by default in daily runs.
- Editor review of chapter diffs: planned; v1 blocks/reports through editorial/book gates and requires human/editor approval for material movement.
- Book role publication: implemented in `scripts/book_role_report.py` and strict MkDocs build.
- Research quality verification: implemented in `scripts/verify_editorial_ingestion.py` and `scripts/verify_editorial_roles.py`.

## Weekly workflow

Run `scripts/weekly_curation_report.py` to decide whether anything should move in the book. Weekly curation reviews sources, entities, claims, trends, contradictions, weak/noisy signals, chapter impact, required human decisions, and next week’s watchlist.

## Verification commands

```bash
cd /home/hermoine/agent-research-book-pipeline
/home/hermoine/agent-research-linkedin-source/.venv/bin/python3 scripts/verify_book_workspace.py
/home/hermoine/agent-research-linkedin-source/.venv/bin/python3 scripts/verify_editorial_roles.py
. .venv/bin/activate
python -m mkdocs build --strict
```

## Do-not-publish rule

If editorial gates fail, publish only safe reports/source indexes/operational notes. Do not publish new chapter content until the blocked-state output identifies the reason, affected files, failed checks, data usability, safe updates, required next action, and human-review requirement.
