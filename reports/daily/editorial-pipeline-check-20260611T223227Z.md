# Daily research book run

- Run ID: `editorial-pipeline-check-20260611T223227Z`
- Started: 2026-06-11T22:32:27Z
- Finished: 2026-06-11T22:32:29Z
- Final status: `success`
- Book build status: `ok`
- Git commit hash: `not committed`

## Required run output

1. Run ID: `editorial-pipeline-check-20260611T223227Z`
2. Source counts: `{'linkedin_search_result': 338, 'web': 33}`
3. Entity counts: `1106`
4. Claim counts: `{'needs_review': 1, 'weakly_supported': 54}`
5. Source quality distribution: `{'A': 7, 'B': 9, 'C': 16, 'D': 338, 'E': 1}`
6. New candidate trends: `0`
7. Claims promoted: `0`
8. Claims rejected: `0`
9. Chapter sections updated: `[]`
10. Editor warnings: `[]`
11. Book build status: `ok`
12. Git commit hash, if committed: `not committed`
13. Final status: `success`

## Steps

- `capture_web_daily.py`: exit 0
- `capture_linkedin_daily.py`: exit 0
- `extract_entities.py`: exit 0
- `extract_claims.py`: exit 0
- `discover_trends.py`: exit 0
- `update_entity_pages.py`: exit 0
- `update_claims_page.py`: exit 0
- `editorial_pipeline_report.py`: exit 0
- `synthesize_chapters.py`: exit 0
- `update_book_pages.py`: exit 0
- `verify_editorial_ingestion.py`: exit 0
- `book_role_report.py`: exit 0
- `editorial_pipeline_report.py`: exit 0

## Publication recommendation

- `publish`

## Notes

LinkedIn/social media is treated as a discovery signal, not independent confirmation. The Author may write only from Editor-promoted or clearly caveated claim records, never directly from raw captures.
