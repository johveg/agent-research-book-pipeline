# Run 49 chapter conversion plan

- disposition: `rewrite_plan_created`
- do_not_rewrite_yet: `True`
- docs/book modified: `False`
- recommended next run: Run 50 — Draft Introduction, thesis, scope, contribution, and limitations as report-only manuscript prose.

## Recommended future book structure

- Front matter: Preface and reader guide
- Introduction: thesis, scope, contribution, limitations
- Literature and context: agent-loop and tool-ecosystem background
- Conceptual framework: definitions, taxonomy, and model of closed-loop agents
- Methodology: evidence collection, source quality, and validation approach
- Core chapters: agent loop, Hermes, OpenClaw, Loop Engineering, memory/context architecture, operating loops
- Governance and safety chapter: publication gates, mutation guards, and no-fallback controls
- Appendices: evidence/source inventories, open questions, glossary, bibliography

## Page mapping

- `docs/book/01-the-agent-loop.md` → `tool_case_chapter` / `main_manuscript_candidate` / priority `4`
- `docs/book/02-hermes.md` → `tool_case_chapter` / `main_manuscript_candidate` / priority `4`
- `docs/book/03-openclaw.md` → `tool_case_chapter` / `main_manuscript_candidate` / priority `4`
- `docs/book/04-loop-engineering.md` → `core_concept_chapter` / `main_manuscript_candidate` / priority `3`
- `docs/book/05-context-memory-architecture.md` → `tool_case_chapter` / `main_manuscript_candidate` / priority `4`
- `docs/book/06-operating-loops.md` → `tool_case_chapter` / `main_manuscript_candidate` / priority `4`
- `docs/book/open-questions.md` → `research_agenda` / `appendix` / priority `4`
- `docs/book/preface.md` → `front_matter` / `main_manuscript_candidate` / priority `3`

## Rewrite priority sequence

- priority `3` — `docs/book/04-loop-engineering.md`: add methodology support; define conceptual framework and terms
- priority `3` — `docs/book/preface.md`: add methodology support
- priority `4` — `docs/book/01-the-agent-loop.md`: add methodology support
- priority `4` — `docs/book/02-hermes.md`: add methodology support; define conceptual framework and terms
- priority `4` — `docs/book/03-openclaw.md`: add methodology support; define conceptual framework and terms
- priority `4` — `docs/book/05-context-memory-architecture.md`: add methodology support
- priority `4` — `docs/book/06-operating-loops.md`: add methodology support
- priority `4` — `docs/book/open-questions.md`: route to appendix/back matter before any public chapter use; add methodology support; define conceptual framework and terms

## Missing sections

- missing front matter: `['introduction']`
- missing methodology: `['methodology']`
- missing literature/context: `['literature_and_context']`
- missing conceptual framework: `['conceptual_framework']`
- missing glossary/bibliography: `['glossary', 'bibliography']`

## Safety note

Do not rewrite docs/book in Run 49; this plan is report-only and not publication approval.
