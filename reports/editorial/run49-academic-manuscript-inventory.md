# Run run49 academic manuscript inventory

- disposition: `academic_inventory_completed`
- page_count: `8`
- GPT-5.5 used: `False`
- GPT-5.5 review status: `not_run`
- docs/book modified: `False`

## Summary counts

```json
{
  "academic_chapter_candidate": 1,
  "appendix_only_recommended": 1,
  "maturity_2": 3,
  "maturity_3": 3,
  "maturity_4": 2,
  "missing_conceptual_framework": 4,
  "missing_methodology_support": 8,
  "open_questions_or_research_agenda": 1,
  "preface_or_reader_guide": 1,
  "recommended_core_concept_chapter": 1,
  "recommended_front_matter": 1,
  "recommended_research_agenda": 1,
  "recommended_tool_case_chapter": 5,
  "tool_profile": 5
}
```

## Pages

### 1. The Agent Loop
- path: `docs/book/01-the-agent-loop.md`
- apparent_current_role: `tool_profile`
- recommended_academic_role: `tool_case_chapter`
- academic_maturity: `3 — practitioner guide draft`
- safe_handling: `rewrite_plan_created`
- rewrite_priority: `4`
- recommended_next_action: add methodology support

### 2. Hermes
- path: `docs/book/02-hermes.md`
- apparent_current_role: `tool_profile`
- recommended_academic_role: `tool_case_chapter`
- academic_maturity: `2 — research note / scaffold`
- safe_handling: `rewrite_plan_created`
- rewrite_priority: `4`
- recommended_next_action: add methodology support; define conceptual framework and terms

### 3. OpenClaw
- path: `docs/book/03-openclaw.md`
- apparent_current_role: `tool_profile`
- recommended_academic_role: `tool_case_chapter`
- academic_maturity: `2 — research note / scaffold`
- safe_handling: `rewrite_plan_created`
- rewrite_priority: `4`
- recommended_next_action: add methodology support; define conceptual framework and terms

### 4. Loop Engineering
- path: `docs/book/04-loop-engineering.md`
- apparent_current_role: `academic_chapter_candidate`
- recommended_academic_role: `core_concept_chapter`
- academic_maturity: `4 — academic/professional chapter draft`
- safe_handling: `manuscript_page_classified`
- rewrite_priority: `3`
- recommended_next_action: add methodology support; define conceptual framework and terms

### 5. Context and Memory Architecture
- path: `docs/book/05-context-memory-architecture.md`
- apparent_current_role: `tool_profile`
- recommended_academic_role: `tool_case_chapter`
- academic_maturity: `3 — practitioner guide draft`
- safe_handling: `rewrite_plan_created`
- rewrite_priority: `4`
- recommended_next_action: add methodology support

### 6. Operating Loops in Production
- path: `docs/book/06-operating-loops.md`
- apparent_current_role: `tool_profile`
- recommended_academic_role: `tool_case_chapter`
- academic_maturity: `3 — practitioner guide draft`
- safe_handling: `rewrite_plan_created`
- rewrite_priority: `4`
- recommended_next_action: add methodology support

### Open Questions
- path: `docs/book/open-questions.md`
- apparent_current_role: `open_questions_or_research_agenda`
- recommended_academic_role: `research_agenda`
- academic_maturity: `2 — research note / scaffold`
- safe_handling: `appendix_candidate`
- rewrite_priority: `4`
- recommended_next_action: route to appendix/back matter before any public chapter use; add methodology support; define conceptual framework and terms

### Preface
- path: `docs/book/preface.md`
- apparent_current_role: `preface_or_reader_guide`
- recommended_academic_role: `front_matter`
- academic_maturity: `4 — academic/professional chapter draft`
- safe_handling: `manuscript_page_classified`
- rewrite_priority: `3`
- recommended_next_action: add methodology support
