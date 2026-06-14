# Run 14D — Closed-loop editorial gate correction and blocked-run control-flow guard

Created: 2026-06-14

## Objective

Prevent the daily book loop from mutating or committing `docs/book` chapter prose when the editorial gate is blocked, while keeping safe reports/indexes available and replacing human-only next actions with automated dispositions.

## Evidence inspected

- `scripts/daily_book_worker.py`
- `scripts/editorial_pipeline_report.py`
- `scripts/synthesize_chapters.py`
- `scripts/update_book_pages.py`
- `reports/daily/citation-pipeline-test-20260612.md`
- `logs/runs/citation-pipeline-test-20260612.log`
- Commit `723c124`

## Commit 723c124 finding

Commands run:

```bash
git show --stat --name-status 723c124
git show --name-only --pretty=fuller 723c124
git diff 723c124^ 723c124 -- docs/book
```

Result: `git diff 723c124^ 723c124 -- docs/book` returned no diff. Commit `723c124` did not include `docs/book` files.

Conclusion: the observed run mutated chapter files in the working tree and reported chapter updates while blocked, but the commit itself did not contain `docs/book` changes. This is a blocked-run chapter-mutation control breach, not a confirmed docs/book commit breach for `723c124`.

## Root cause

`daily_book_worker.py` skipped `synthesize_chapters.py` when the first editorial report was blocked, but still always ran:

- `resolve_book_citations.py`
- `update_book_pages.py`

It also generated the final editorial summary after those steps, so blocked reports could still list chapter sections as updated. Commit allowlisting excluded `docs/book` when blocked, but the worker did not fail closed if `docs/book` remained dirty after a blocked run.

`editorial_pipeline_report.py` also represented routine privacy uncertainty as `human_review_required` / “human review or stronger evidence”, which created a human-only dead end instead of a closed-loop automated disposition.

## Changes made

### `scripts/daily_book_worker.py`

- Added `chapter_publication_allowed(editorial, allow_chapter_updates)`.
- Added `docs_book_dirty_files()` fail-closed guard.
- Changed blocked/no-allow behavior to skip all chapter-publication mutation steps:
  - `synthesize_chapters.py`
  - `resolve_book_citations.py`
  - `update_book_pages.py`
- Ensured `--allow-chapter-updates` is necessary but not sufficient.
- Added summary publication decision model fields:
  - `data_collected`
  - `data_usable_for_reports`
  - `data_usable_for_chapter_update`
  - `chapter_update_allowed`
  - `chapter_update_status`
  - `chapter_sections_updated`
  - `chapter_update_skipped_reason`
  - `automated_disposition`
  - `publication_recommendation`
- Prevented blocked summaries from claiming chapter sections were updated.
- If final status is blocked and `docs/book` has dirty files, the worker does not commit and reports the dirty files.
- Blocked commit allowlist continues to exclude `docs/book` and now also excludes broad schema staging.

### `scripts/editorial_pipeline_report.py`

- Added closed-loop disposition vocabulary and helpers:
  - `automated_disposition_for_reason(...)`
  - `publication_decision_model(...)`
- Mapped routine uncertainty to automated dispositions:
  - privacy/human-review wording → `auto_quarantine`
  - weak evidence/trend promotion → `needs_more_sources`
  - social-only evidence → `discovery_only`
  - raw/unsafe/low-quality paths → `exclude_from_publication`
  - contradictions → `contradiction_requires_isolation`
- Replaced blocked-state human-only fields with automated disposition fields and optional escalation metadata.
- Preserved safe-report continuation through `safe_updates_allowed`.

### `tests/test_daily_book_worker_blocked_gate.py`

Added regression tests proving:

- blocked editorial gate skips `synthesize_chapters.py`
- blocked editorial gate skips `update_book_pages.py`
- blocked gate reports no chapter sections updated
- blocked gate can still produce safe reports/no-chapter notes
- `--allow-chapter-updates` absent skips chapter mutation even if the gate passes
- `--allow-chapter-updates` present is not sufficient when the gate is blocked
- blocked run with dirty `docs/book` refuses to commit
- summary uses `automated_disposition` rather than human-only action
- policy helper maps privacy/weak/social/raw risks to closed-loop dispositions

## Verification results

- `python3 -m py_compile scripts/daily_book_worker.py scripts/editorial_pipeline_report.py`: passed
- `.venv/bin/python -m pytest -q tests/test_daily_book_worker_blocked_gate.py`: `5 passed`
- `.venv/bin/python -m pytest -q`: `62 passed`
- `python3 scripts/verify_book_workspace.py`: status `ok`
- `python3 scripts/verify_editorial_roles.py`: status `ok`
- `python3 scripts/verify_book_citations.py`: status `ok`
- `.venv/bin/python -m mkdocs build --strict`: passed; MkDocs emitted existing nav informational messages and Material warning, no strict failure

## Protected artifact policy

This run intentionally changed only:

- `scripts/daily_book_worker.py`
- `scripts/editorial_pipeline_report.py`
- `tests/test_daily_book_worker_blocked_gate.py`
- `reports/architecture/run14d-closed-loop-editorial-gate-correction-evidence-map-20260614.md`

No intentional changes were made to:

- `docs/book`
- raw captures
- `data/schema.sql`
- claims/editorial review/source status tables
- narrative packet files

Existing dirty `docs/book` files from the prior blocked run were observed before the patch. They should be restored/cleaned in a separate corrective cleanup if not already intentionally preserved.

## Recommendation

Do not proceed to Run 15 until the workspace is clean of blocked-run `docs/book` drift. Since commit `723c124` did not include `docs/book`, no revert of that commit is required for chapter prose. A cleanup commit may still be appropriate if safe generated/report artifacts need to be normalized after restoring blocked chapter drift.
