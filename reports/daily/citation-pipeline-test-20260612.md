# Daily research book run

- Run ID: `citation-pipeline-test-20260612`
- Started: 2026-06-15T01:10:57Z
- Finished: 2026-06-15T01:33:52Z
- Final status: `blocked`
- Book build status: `ok`
- Git commit hash: `bf47c53`

## Required run output

1. Run ID: `citation-pipeline-test-20260612`
2. Source counts: `{'linkedin_search_result': 1487, 'web': 108}`
3. Entity counts: `3745`
4. Claim counts: `{'candidate': 96, 'needs_review': 111, 'supported': 6, 'weakly_supported': 5}`
5. Source quality distribution: `{'A': 25, 'B': 16, 'C': 63, 'D': 1487, 'E': 4}`
6. New candidate trends: `30`
7. Claims promoted: `0`
8. Claims rejected: `0`
9. Chapter sections updated: `[]`
10. Editor warnings: `[]`
11. Book build status: `ok`
12. Git commit hash, if committed: `bf47c53`
13. Final status: `blocked`

## Publication decision model

- data_collected: `True`
- data_usable_for_reports: `True`
- data_usable_for_chapter_update: `False`
- chapter_update_allowed: `False`
- chapter_update_status: `skipped`
- chapter_sections_updated: `[]`
- chapter_update_skipped_reason: `blocked_for_publication_by_policy`
- automated_disposition: `auto_quarantine`
- publication_recommendation: `do_not_publish_chapter_updates`

## Steps

- `capture_web_daily.py`: exit 0
- `capture_linkedin_daily.py`: exit 0
- `extract_entities.py`: exit 0
- `extract_claims.py`: exit 0
- `discover_trends.py`: exit 0
- `update_entity_pages.py`: exit 0
- `update_claims_page.py`: exit 0
- `export_source_registry.py`: exit 0
- `editorial_pipeline_report.py`: exit 2
- `synthesize_chapters.py`: exit 0
- `resolve_book_citations.py`: exit 0
- `update_book_pages.py`: exit 0
- `verify_editorial_ingestion.py`: exit 0
- `verify_book_citations.py`: exit 0
- `book_role_report.py`: exit 0
- `editorial_pipeline_report.py`: exit 2
- `build_vector_db.py`: exit 0

## Publication recommendation

- `do_not_publish_chapter_updates`

## Blocked-state output

1. Block reason: `['privacy review requires human review for some sources']`
2. Affected files: `['book/05-context-memory-architecture.md', 'book/03-openclaw.md', 'book/04-loop-engineering.md', 'book/06-operating-loops.md', 'book/preface.md', 'book/01-the-agent-loop.md', 'book/open-questions.md', 'book/02-hermes.md']`
3. Failed checks: `['privacy review requires human review for some sources']`
4. Data collected: `True`
5. Data usable: `True`
6. Safely updated: `['capture reports', 'source indexes', 'rejected trend lists', 'quality warnings', 'operational notes', 'editor reports', 'vector/index updates', 'no-chapter-update notes']`
7. Required next action: `auto_quarantine`
8. Automated disposition: `auto_quarantine`
9. Optional escalation: `True`
10. Optional escalation reasons: `['privacy uncertainty', 'trend promotion with weak evidence']`
- Blocked reasons:
  - chapter publication blocked: privacy review requires human review for some sources

## Notes

LinkedIn/social media is treated as a discovery signal, not independent confirmation. The Author may write only from Editor-promoted or clearly caveated claim records, never directly from raw captures.
