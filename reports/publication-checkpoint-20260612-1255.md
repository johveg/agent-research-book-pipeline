# Publication checkpoint — 20260612-1255 UTC

## Current status

- Tests: PASS (`.venv/bin/python -m pytest -q` returned 0 in the checkpoint run; 8 tests passed)
- Citation gate: OK (`raw_id_hits=0`, `unresolved_hits=0`)
- Book role gate: APPROVED (`errors=0`)
- MkDocs strict: PASS (`mkdocs build --strict` exit 0)
- Source registry records: 587

## Commands run

```bash
git status --short
.venv/bin/python -m pytest -q
python3 scripts/verify_book_citations.py
.venv/bin/python scripts/book_role_report.py
mkdocs build --strict
```

Checkpoint command log: `logs/runs/checkpoint-20260612-1255.log`

## Git status summary at checkpoint

```text
M docs/book/01-the-agent-loop.md
 M docs/book/02-hermes.md
 M docs/book/03-openclaw.md
 M docs/book/04-loop-engineering.md
 M docs/book/05-context-memory-architecture.md
 M docs/book/06-operating-loops.md
 M docs/book/open-questions.md
 M docs/book/preface.md
 M docs/entities/addy-osmani-introduces-loop.md
 M docs/entities/agentic-ai.md
 M docs/entities/ai-agent.md
 M docs/entities/ai-agents.md
 M docs/entities/ai-assisted.md
 M docs/entities/ai-coding-agents.md
 M docs/entities/anthropic.md
 M docs/entities/autonomous-coding-agents.md
 M docs/entities/aws.md
 M docs/entities/bennett-black.md
 M docs/entities/bert.md
 M docs/entities/cfo.md
 M docs/entities/chief-ai-officer.md
 M docs/entities/claude-code.md
 M docs/entities/claude-fable.md
 M docs/entities/claude.md
 M docs/entities/companies.md
 M docs/entities/concepts.md
 M docs/entities/continual-learning.md
 M docs/entities/devesh-paragiri.md
 M docs/entities/enterprise-architecture.md
 M docs/entities/extension-chrome-guichet-unique.md
 M docs/entities/github.md
 M docs/entities/google.md
 M docs/entities/hermes-agent.md
 M docs/entities/hermes-atlas.md
 M docs/entities/hermes.md
 M docs/entities/high-performance-alternative.md
 M docs/entities/hirebox-human-resource.md
 M docs/entities/hivemind.md
 M docs/entities/index.md
 M docs/entities/interacting-with-coding-agents.md
 M docs/entities/know-hermes-agent.md
 M docs/entities/kyc.md
 M docs/entities/langgraph.md
 M docs/entities/llm-fine-tuning.md
 M docs/entities/llm.md
 M docs/entities/loop-engineer.md
 M docs/entities/loop-engineering.md
 M docs/entities/mcp.md
 M docs/entities/microsoft-mvp.md
 M docs/entities/microsoft.md
 M docs/entities/most-ai.md
 M docs/entities/nishanth-rao.md
 M docs/entities/nlp.md
 M docs/entities/nous-research.md
 M docs/entities/nvidia.md
 M docs/entities/openai.md
 M docs/entities/openclaw.md
 M docs/entities/outpost.md
 M docs/entities/peft.md
 M docs/entities/people.md
 M docs/entities/projects.md
 M docs/entities/prompting-ai-coding-agents.md
 M docs/entities/python.md
 M docs/entities/rag-pipelines.md
 M docs/entities/rag.md
 M docs/entities/remote-openclaw.md
 M docs/entities/seo.md
 M docs/entities/thenextgentechinsider-com.md
 M docs/entities/trained-my-hermes-agent.md
 M docs/entities/vibe-coding.md
 M docs/entities/xgboost.md
 M docs/entities/yoe.md
 M docs/entities/yoni-atteia.md
 M docs/research/claims.md
 M scripts/book_role_report.py
 M scripts/daily_book_worker.py
 M scripts/synthesize_chapters.py
 M scripts/update_entity_pages.py
 M tests/test_editorial_ingestion.py
?? data/source_registry.json
?? docs/entities/andrew-sauer.md
?? docs/entities/human-agency.md
?? docs/entities/mohamed-amin.md
?? reports/reference-provenance-summary-20260612.md
?? scripts/citation_common.py
?? scripts/export_source_registry.py
?? scripts/resolve_book_citations.py
?? scripts/verify_book_citations.py
?? tests/test_citations.py
```

## Source registry summary

- Registry path: `data/source_registry.json`
- Records: 587
- Publishable records by current resolver rule: 52
- Source types: {'linkedin_search_result': 534, 'web': 53}
- Quality scores: {'D': 534, 'C': 27, 'A': 12, 'B': 11, 'E': 3}
- Privacy statuses: {'human_review': 535, 'publishable_metadata_only': 49, 'reject': 3}

## Citation status

```json
{
  "status": "ok",
  "raw_id_hits": [],
  "unresolved_hits": []
}
```

## Book role status

- Publication: `approved`
- Errors: 0
- Warnings: 0
- Citation gate in Book report: `ok`
- Internal MkDocs return code in Book report: `0`

## MkDocs strict status

- Exit code: `0`
- Result: PASS

## Known non-blocking warnings

- MkDocs reports generated entity detail pages outside nav; strict build still exits 0.
- MkDocs Material emits upstream MkDocs 2.0 advisory; strict build still exits 0.

## Notes

This checkpoint does not weaken citation, source-origin, privacy, Book role, or MkDocs strict gates. The public book pages remain free of raw internal source IDs and unresolved citation markers.
