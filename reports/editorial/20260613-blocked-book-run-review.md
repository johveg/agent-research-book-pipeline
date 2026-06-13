# Blocked daily book run review — citation-pipeline-test-20260612

Reviewed: 2026-06-13T07:55:00Z

## Gate decision

Publication remains **blocked**. The source/claim-mapping failure has been fixed in generated Author output, but the Editor gate still requires human review because some source material has privacy/publication uncertainty and some trend evidence is weak.

Final block reason from `scripts/editorial_pipeline_report.py`:

- `privacy review requires human review for some sources`

Safe updates allowed: reports, rejected trend lists, quality warnings, operational/editor notes, and source-index updates. Chapter publication remains blocked until human review or stronger evidence clears the Editor gate.

## Pipeline changes made

- `scripts/editorial_pipeline_report.py`
  - Treats LinkedIn/social/search-result evidence as **discovery signal only**, with `publication_decision=do_not_use` unless independently supported by stronger non-social sources.
  - Expands structural/platform trend filters to reject boilerplate such as `linkedin`, `profile`, `company`, `jobs`, `hiring`, `followers`, `follow`, `feed`, `post`, `hashtag`, `search`, `results`, and related URL/platform fragments.
  - Tightens chapter-gate parsing so Source/claim mapping is checked in the `Source/claim mapping` section rather than by raw internal IDs exposed in public pages.
- `scripts/discover_trends.py`
  - Filters structural/platform tokens and URL fragments before trend promotion.
  - Requires repeated meaningful evidence across at least two source files for multi-word trend candidates.
  - Emits rejected trends with reasons.
- `scripts/synthesize_chapters.py`
  - Generates explicit per-bullet Source/claim mapping without exposing raw internal claim/source IDs on public book pages.
  - Adds Editor notes clarifying that LinkedIn/social material is discovery-only unless independently confirmed.
- `scripts/book_role_report.py`
  - Uses the available `mkdocs` executable for strict builds instead of requiring `python -m mkdocs` in the script interpreter environment.
- `scripts/daily_book_worker.py`
  - When status is blocked, commits only safe reports/data/tooling paths and does **not** stage `docs/book` chapter prose.

## Affected chapter claim-like bullets

### book/05-context-memory-architecture.md

- Mapped: “Loop engineering is best treated here as designing the harness around an agent: triggers, goals, context, tools, checks, state, reports, retries, and escalation.” — supported; source tokens `[1] [2] [3]`.
- Caveated/mapped: “The present source set supports only a cautious connection between agent loops and context or memory architecture; stronger technical treatment needs better primary sources.” — weakly supported; source tokens `[4] [5]`.

### book/03-openclaw.md

- Mapped: “OpenClaw is represented in the existing source registry by its public GitHub repository, whose captured title describes it as a personal AI assistant for multiple operating systems and platforms.” — supported; source tokens `[1] [2]`.
- Caveated/mapped: “The current OpenClaw material is sufficient for cautious repository identification, but not enough for strong comparison claims or claims about adoption.” — weakly supported; source tokens `[1]`.

### book/04-loop-engineering.md

- Mapped: “Loop engineering is best treated here as designing the harness around an agent: triggers, goals, context, tools, checks, state, reports, retries, and escalation.” — supported; source tokens `[1] [2] [3]`.
- Caveated/mapped: “Several June 2026 public articles describe a shift from prompt engineering toward loop engineering, but the book should present that as an emerging discourse rather than a settled industry transition.” — weakly supported; source tokens `[1] [4] [3] [5]`.

### book/06-operating-loops.md

- Mapped: “Loop engineering is best treated here as designing the harness around an agent: triggers, goals, context, tools, checks, state, reports, retries, and escalation.” — supported; source tokens `[1] [2] [3]`.
- Mapped: “OpenClaw is represented in the existing source registry by its public GitHub repository, whose captured title describes it as a personal AI assistant for multiple operating systems and platforms.” — supported; source tokens `[4] [5]`.
- Mapped: “A useful loop-engineering chapter can therefore focus on loop boundaries, observability, evaluation, and safe handoff instead of claiming that prompts have disappeared.” — supported; source tokens `[6] [3]`.
- Mapped: “An agentic loop can be framed as a repeated AI-agent cycle with a trigger, a goal, actions, feedback, and verification rather than as a single prompt-response exchange.” — supported; source tokens `[6] [3]`.
- Caveated/mapped: “Several June 2026 public articles describe a shift from prompt engineering toward loop engineering, but the book should present that as an emerging discourse rather than a settled industry transition.” — weakly supported; source tokens `[1] [6] [3] [7]`.
- Caveated/mapped: “Current loop-engineering commentary often contrasts one-off prompting with systems that repeatedly plan, execute, evaluate, and adjust work.” — weakly supported; source tokens `[1] [2] [3]`.
- Caveated/mapped: “For production use, the available loop-engineering material points toward operational concerns: checks, monitoring, repeated execution, and explicit boundaries around autonomous work.” — weakly supported; source tokens `[1] [3] [7]`.
- Caveated/mapped: “The present source set supports only a cautious connection between agent loops and context or memory architecture; stronger technical treatment needs better primary sources.” — weakly supported; source tokens `[8] [9]`.

### book/preface.md

- Mapped: “Hermes Agent is a Nous Research open-source agent project presented as an agent that grows with the user and supports tool-using automation workflows.” — supported; source tokens `[1] [2] [3]`.
- Mapped: “Loop engineering is best treated here as designing the harness around an agent: triggers, goals, context, tools, checks, state, reports, retries, and escalation.” — supported; source tokens `[4] [5] [6]`.
- Mapped: “An agentic loop can be framed as a repeated AI-agent cycle with a trigger, a goal, actions, feedback, and verification rather than as a single prompt-response exchange.” — supported; source tokens `[7] [6]`.
- Caveated/mapped: “The present source set supports only a cautious connection between agent loops and context or memory architecture; stronger technical treatment needs better primary sources.” — weakly supported; source tokens `[1] [8]`.

### book/01-the-agent-loop.md

- Mapped: “Hermes Agent is a Nous Research open-source agent project presented as an agent that grows with the user and supports tool-using automation workflows.” — supported; source tokens `[1] [2] [3]`.
- Mapped: “Loop engineering is best treated here as designing the harness around an agent: triggers, goals, context, tools, checks, state, reports, retries, and escalation.” — supported; source tokens `[4] [5] [6]`.
- Mapped: “A useful loop-engineering chapter can therefore focus on loop boundaries, observability, evaluation, and safe handoff instead of claiming that prompts have disappeared.” — supported; source tokens `[7] [6]`.
- Mapped: “An agentic loop can be framed as a repeated AI-agent cycle with a trigger, a goal, actions, feedback, and verification rather than as a single prompt-response exchange.” — supported; source tokens `[7] [6]`.
- Caveated/mapped: “Several June 2026 public articles describe a shift from prompt engineering toward loop engineering, but the book should present that as an emerging discourse rather than a settled industry transition.” — weakly supported; source tokens `[4] [7] [6] [8]`.
- Caveated/mapped: “Current loop-engineering commentary often contrasts one-off prompting with systems that repeatedly plan, execute, evaluate, and adjust work.” — weakly supported; source tokens `[4] [5] [6]`.
- Caveated/mapped: “For production use, the available loop-engineering material points toward operational concerns: checks, monitoring, repeated execution, and explicit boundaries around autonomous work.” — weakly supported; source tokens `[4] [6] [8]`.
- Caveated/mapped: “The present source set supports only a cautious connection between agent loops and context or memory architecture; stronger technical treatment needs better primary sources.” — weakly supported; source tokens `[1] [9]`.

### book/open-questions.md

- Removed/withheld from chapter prose: no factual bullets were published for this chapter update. The page remains a not-ready/open-question page because matching claims are not usable in prose.

### book/02-hermes.md

- Mapped: “Hermes Agent is a Nous Research open-source agent project presented as an agent that grows with the user and supports tool-using automation workflows.” — supported; source tokens `[1] [2] [3]`.
- Mapped: “The captured Hermes documentation includes concrete guides, which makes official docs and repository material safer citation authority than social summaries.” — supported; source tokens `[4] [3]`.

## Unsupported/social-only material

Current claim counts after the Editor pass:

- Supported claims: 6
- Weakly supported/caveated claims: 5
- Needs-review claims: 135
- Social/search-result discovery-only claims marked `do_not_use`: 133

These social/search-result claims were not used as independent confirmation and remain blocked from chapter prose.

## Verification

Commands run from `/home/hermoine/terefohealreboa`:

```bash
python3 -m py_compile scripts/editorial_pipeline_report.py scripts/discover_trends.py scripts/synthesize_chapters.py scripts/book_role_report.py scripts/daily_book_worker.py
python3 scripts/editorial_pipeline_report.py --run-id citation-pipeline-test-20260612 --book-build-status ok --json-out logs/runs/citation-pipeline-test-20260612-editorial-final-review-2.json
python3 scripts/verify_book_citations.py --json-out logs/runs/citation-pipeline-test-20260612-verify-citations-final-review-2.json
python3 scripts/book_role_report.py > logs/runs/citation-pipeline-test-20260612-book-role-final-review-2.json
mkdocs build --strict
```

Observed results:

- `py_compile=ok`
- Editorial pipeline report: exit `2`, final status `blocked`
- Citation verification: exit `0`, status `ok`, no raw ID hits, no unresolved hits
- Book role report: exit `0`, publication `approved`, no errors/warnings
- `mkdocs build --strict`: exit `0`, documentation built successfully

## Final status

The author/editor pipeline is stricter and more publishable: claim-like bullets are mapped or caveated, social material is discovery-only, trend noise is filtered more aggressively, and blocked runs no longer stage `docs/book` chapter prose. The publication gate remains **blocked** until privacy/human-review requirements are resolved.
