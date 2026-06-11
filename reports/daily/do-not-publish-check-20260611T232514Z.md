# Daily research book run

- Run ID: `do-not-publish-check-20260611T232514Z`
- Started: 2026-06-11T23:25:14Z
- Finished: 2026-06-11T23:25:18Z
- Final status: `blocked`
- Book build status: `ok`
- Git commit hash: `not committed`

## Required run output

1. Run ID: `do-not-publish-check-20260611T232514Z`
2. Source counts: `{'linkedin_search_result': 338, 'web': 33}`
3. Entity counts: `1106`
4. Claim counts: `{'needs_review': 1, 'weakly_supported': 54}`
5. Source quality distribution: `{'A': 7, 'B': 9, 'C': 16, 'D': 338, 'E': 1}`
6. New candidate trends: `0`
7. Claims promoted: `0`
8. Claims rejected: `0`
9. Chapter sections updated: `['book/05-context-memory-architecture.md', 'book/03-openclaw.md', 'book/04-loop-engineering.md', 'book/06-operating-loops.md', 'book/preface.md', 'book/01-the-agent-loop.md', 'book/open-questions.md', 'book/02-hermes.md']`
10. Editor warnings: `[]`
11. Book build status: `ok`
12. Git commit hash, if committed: `not committed`
13. Final status: `blocked`

## Steps

- `capture_web_daily.py`: exit 0
- `capture_linkedin_daily.py`: exit 0
- `extract_entities.py`: exit 0
- `extract_claims.py`: exit 0
- `discover_trends.py`: exit 0
- `update_entity_pages.py`: exit 0
- `update_claims_page.py`: exit 0
- `editorial_pipeline_report.py`: exit 2
- `synthesize_chapters.py`: exit 0
- `update_book_pages.py`: exit 0
- `verify_editorial_ingestion.py`: exit 0
- `book_role_report.py`: exit 0
- `editorial_pipeline_report.py`: exit 2

## Publication recommendation

- `publish safe curated artifacts only`

## Blocked-state output

1. Block reason: `['Author output lacks source/claim mapping', 'book/05-context-memory-architecture.md may treat LinkedIn/social material as proof without caveat', 'book/03-openclaw.md may treat LinkedIn/social material as proof without caveat', 'book/04-loop-engineering.md may treat LinkedIn/social material as proof without caveat', 'book/06-operating-loops.md may treat LinkedIn/social material as proof without caveat', 'book/preface.md may treat LinkedIn/social material as proof without caveat', 'book/01-the-agent-loop.md may treat LinkedIn/social material as proof without caveat', 'book/02-hermes.md may treat LinkedIn/social material as proof without caveat', 'privacy review requires human review for some sources']`
2. Affected files: `['book/05-context-memory-architecture.md', 'book/03-openclaw.md', 'book/04-loop-engineering.md', 'book/06-operating-loops.md', 'book/preface.md', 'book/01-the-agent-loop.md', 'book/open-questions.md', 'book/02-hermes.md']`
3. Failed checks: `['book/05-context-memory-architecture.md may treat LinkedIn/social material as proof without caveat', 'book/03-openclaw.md may treat LinkedIn/social material as proof without caveat', 'book/04-loop-engineering.md may treat LinkedIn/social material as proof without caveat', 'book/06-operating-loops.md may treat LinkedIn/social material as proof without caveat', 'book/preface.md may treat LinkedIn/social material as proof without caveat', 'book/01-the-agent-loop.md may treat LinkedIn/social material as proof without caveat', 'book/02-hermes.md may treat LinkedIn/social material as proof without caveat', 'Author output lacks source/claim mapping', 'book/05-context-memory-architecture.md may treat LinkedIn/social material as proof without caveat', 'book/03-openclaw.md may treat LinkedIn/social material as proof without caveat', 'book/04-loop-engineering.md may treat LinkedIn/social material as proof without caveat', 'book/06-operating-loops.md may treat LinkedIn/social material as proof without caveat', 'book/preface.md may treat LinkedIn/social material as proof without caveat', 'book/01-the-agent-loop.md may treat LinkedIn/social material as proof without caveat', 'book/02-hermes.md may treat LinkedIn/social material as proof without caveat', 'privacy review requires human review for some sources']`
4. Data collected: `True`
5. Data usable: `True`
6. Safely updated: `['safe status reports', 'source index updates', 'rejected trend lists', 'quality warnings', 'operational notes', 'editor reports', 'no chapter update notes']`
7. Required next action: `human review or stronger evidence before chapter publication`
8. Human review required: `True`
9. Human review reasons: `['privacy uncertainty']`
- Blocked reasons:
  - book/05-context-memory-architecture.md may treat LinkedIn/social material as proof without caveat
  - book/03-openclaw.md may treat LinkedIn/social material as proof without caveat
  - book/04-loop-engineering.md may treat LinkedIn/social material as proof without caveat
  - book/06-operating-loops.md may treat LinkedIn/social material as proof without caveat
  - book/preface.md may treat LinkedIn/social material as proof without caveat
  - book/01-the-agent-loop.md may treat LinkedIn/social material as proof without caveat
  - book/02-hermes.md may treat LinkedIn/social material as proof without caveat
  - chapter publication blocked: Author output lacks source/claim mapping; book/05-context-memory-architecture.md may treat LinkedIn/social material as proof without caveat; book/03-openclaw.md may treat LinkedIn/social material as proof without caveat; book/04-loop-engineering.md may treat LinkedIn/social material as proof without caveat; book/06-operating-loops.md may treat LinkedIn/social material as proof without caveat; book/preface.md may treat LinkedIn/social material as proof without caveat; book/01-the-agent-loop.md may treat LinkedIn/social material as proof without caveat; book/02-hermes.md may treat LinkedIn/social material as proof without caveat; privacy review requires human review for some sources

## Notes

LinkedIn/social media is treated as a discovery signal, not independent confirmation. The Author may write only from Editor-promoted or clearly caveated claim records, never directly from raw captures.
