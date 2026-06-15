# Run 49 evidence map — Academic manuscript inventory

- run_id: `run49`
- title: `Academic manuscript inventory and chapter conversion plan`
- disposition: `academic_inventory_completed`
- page_count_classified: `8`
- deterministic_inventory: `reports/editorial/run49-academic-manuscript-inventory.json`
- GPT-5.5 inventory: `reports/editorial/run49-academic-manuscript-inventory-gpt55.json`
- conversion_plan: `reports/editorial/run49-chapter-conversion-plan.json`
- mutation_guard: `reports/editorial/run49-protected-mutation-guard.json`
- docs/book_modified: `False`
- DB logical delta: `{}`
- source_registry/raw/schema/daily_worker changed: `False/False/False/False`

## Classification evidence

- maturity distribution: `{'2': 3, '3': 3, '4': 2}`
- evidence stub count: `0`
- claim ledger/source mapping count: `0`
- appendix candidate count: `1`
- reports-only candidate count: `0`
- missing literature support count: `0`
- missing methodology support count: `8`
- missing conceptual framework count: `4`
- GPT-5.5 used: `True`
- GPT-5.5 review status counts: `{'completed': 2, 'failed_closed': 6}`

## Top rewrite priorities

- priority `3` — `docs/book/04-loop-engineering.md` → `core_concept_chapter`: add methodology support; define conceptual framework and terms
- priority `3` — `docs/book/preface.md` → `front_matter`: add methodology support
- priority `4` — `docs/book/01-the-agent-loop.md` → `tool_case_chapter`: add methodology support
- priority `4` — `docs/book/02-hermes.md` → `tool_case_chapter`: add methodology support; define conceptual framework and terms
- priority `4` — `docs/book/03-openclaw.md` → `tool_case_chapter`: add methodology support; define conceptual framework and terms
- priority `4` — `docs/book/05-context-memory-architecture.md` → `tool_case_chapter`: add methodology support
- priority `4` — `docs/book/06-operating-loops.md` → `tool_case_chapter`: add methodology support
- priority `4` — `docs/book/open-questions.md` → `research_agenda`: route to appendix/back matter before any public chapter use; add methodology support; define conceptual framework and terms


## Recommended next run

Run 50 — Draft Introduction, thesis, scope, contribution, and limitations as report-only manuscript prose.

## Safety conclusion

Run 49 is report-only. It does not rewrite `docs/book`, does not promote claims, does not insert claims, does not update source/claim/editorial statuses, and does not modify the production scheduler.
