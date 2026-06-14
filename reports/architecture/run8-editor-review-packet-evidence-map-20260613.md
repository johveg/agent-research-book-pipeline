# Run 8 editor review packet evidence map — 20260613

## Scope

Run 8 created a report-only human/editor review packet for the passed Run 7 high-reasoning chains.

Before packet generation, Run 8 reran the corrected GPT-5.5 quality gate with `--limit 30` so all Run 7 semantic objects were reviewed.

Run 8 is not publication approval, author approval, chapter writing, claim insertion, narrative packet creation, or daily-worker wiring.

## Files changed

Implementation/tests:

- `scripts/llm_build_editor_review_packet.py`
  - New deterministic, no-LLM, report-only packet builder.
  - Reads candidate-selection, source-card, semantic-object, and full quality-gate JSON reports.
  - Builds complete source-card -> semantic-object -> quality-review packet items.
  - Normalizes all packet outputs to `author_allowed=false`, `publication_approved=false`, `advisory_only=true`.
- `tests/test_llm_build_editor_review_packet.py`
  - New TDD tests for report writing, linkage requirements, provenance/hashes, approval safety, no DB writes, docs/book immutability, and status immutability.
- `scripts/llm_quality_gate.py`
  - Small output-path/safety refinement so `--report-suffix run7-full` writes quality-gate outputs to `*-quality-gate-run7-full.*` and does not overwrite an existing evidence map placeholder.

Reports created:

- `reports/editorial/citation-pipeline-test-20260612-quality-gate-run7-full.json`
- `reports/editorial/citation-pipeline-test-20260612-quality-gate-run7-full.md`
- `reports/editorial/citation-pipeline-test-20260612-editor-review-packet-run8.json`
- `reports/editorial/citation-pipeline-test-20260612-editor-review-packet-run8.md`
- `reports/architecture/run8-editor-review-packet-evidence-map-20260613.md`

## Files intentionally not changed

- `docs/book/`: not changed in final state.
- Raw captures: not modified.
- `.var/book.sqlite`: not modified by default.
- Source/claim/editorial statuses and publication/chapter decisions: not modified.
- `scripts/daily_book_worker.py`: not modified.
- Commit allowlist: not modified.
- `data/schema.sql`: not modified.
- Existing `claims` table: no inserts.
- Narrative packets: not created.
- Publishable chapter prose: not generated.
- Vector DB chunks: not used as source authority.
- Secrets/tokens/OAuth/cookies/API keys: not printed.
- Long source excerpts: not written.
- `reports/architecture/run5-high-reasoning-bridge-evidence-map-20260613.md`: not used as source of truth and not overwritten.

## Current git status before/after

Preflight:

- Branch: `main`
- HEAD: `b103efb`
- Working tree already contained untracked Run 1–7 scripts/tests/reports from the staged pipeline work.
- No tracked protected file modifications were present before Run 8.

During verification, MkDocs/generated-doc checks dirtied generated artifacts under `data/source_registry.json`, `docs/book/`, `docs/entities/`, and `docs/research/claims.md`. These were restored:

```bash
git restore data/source_registry.json docs/book docs/entities docs/research/claims.md
rm -f docs/entities/boris-cherny.md
```

Final status contains only untracked staged pipeline scripts/tests/reports; no tracked protected docs/book/schema/worker/status files are modified.

## Input reports used

- `reports/editorial/citation-pipeline-test-20260612-reasoning-candidate-selection.json`
- `reports/editorial/citation-pipeline-test-20260612-source-card-drafts-high-reasoning-run7.json`
- `reports/editorial/citation-pipeline-test-20260612-semantic-object-drafts-high-reasoning-run7.json`
- `reports/editorial/citation-pipeline-test-20260612-quality-gate-run7.json`
- Full rerun generated and then used:
  - `reports/editorial/citation-pipeline-test-20260612-quality-gate-run7-full.json`

## Full quality-gate rerun result

Command:

```bash
python3 scripts/llm_quality_gate.py \
  --run-id citation-pipeline-test-20260612 \
  --limit 30 \
  --output-dir reports/editorial \
  --require-high-reasoning \
  --source-card-report reports/editorial/citation-pipeline-test-20260612-source-card-drafts-high-reasoning-run7.json \
  --semantic-object-report reports/editorial/citation-pipeline-test-20260612-semantic-object-drafts-high-reasoning-run7.json \
  --report-suffix run7-full
```

Result:

- `llm_used=true`
- `provider=copilot`
- `model=gpt-5.5`
- `bridge=hermes_cli`
- `reasoning_status=high_reasoning_used`
- `db_modified=false`

## Source cards reviewed

- Source cards available: `5`
- Source cards reviewed in full gate: `5`

## Semantic objects reviewed

- Semantic objects available: `14`
- Semantic objects reviewed in full gate: `14`

This resolves the Run 7 limitation where only `10` semantic objects were reviewed.

## Pass/warn/fail counts

Full quality-gate rerun counts:

```json
{
  "pass": 6,
  "warn": 13,
  "fail": 0
}
```

Compatibility counts:

```json
{
  "ready_for_editor_review": 6,
  "needs_revision": 13,
  "blocked": 0
}
```

Downstream eligible count from the full quality gate:

- `6`

Note: this includes both source-card and semantic-object review items.

## Editor packet generation result

Command:

```bash
python3 scripts/llm_build_editor_review_packet.py \
  --run-id citation-pipeline-test-20260612 \
  --output-dir reports/editorial \
  --candidate-selection-report reports/editorial/citation-pipeline-test-20260612-reasoning-candidate-selection.json \
  --source-card-report reports/editorial/citation-pipeline-test-20260612-source-card-drafts-high-reasoning-run7.json \
  --semantic-object-report reports/editorial/citation-pipeline-test-20260612-semantic-object-drafts-high-reasoning-run7.json \
  --quality-gate-report reports/editorial/citation-pipeline-test-20260612-quality-gate-run7-full.json \
  --report-suffix run8
```

Result:

- JSON: `reports/editorial/citation-pipeline-test-20260612-editor-review-packet-run8.json`
- Markdown: `reports/editorial/citation-pipeline-test-20260612-editor-review-packet-run8.md`
- Packet items total: `14`
- Packet pass items: `5`
- Packet warn items: `9`
- Packet fail items: `0`
- Complete chains total: `14`
- Downstream eligible packet items: `5`
- `author_allowed=false`
- `publication_approved=false`
- `advisory_only=true`
- `db_modified=false`

## Complete chains included

Complete chains included in packet: `14`

Downstream-eligible/pass chains: `5`

- `source_card_draft_src_6d7b6d80cda4e784877d` -> `semantic_object_draft_425a074033ba640ec639`
- `source_card_draft_src_6d7b6d80cda4e784877d` -> `semantic_object_draft_0aed99a302b307d6fdd3`
- `source_card_draft_src_6d7b6d80cda4e784877d` -> `semantic_object_draft_5df8116fc7dc2d06b2e7`
- `source_card_draft_src_6d7b6d80cda4e784877d` -> `semantic_object_draft_5558303e45f77723657a`
- `source_card_draft_src_6d7b6d80cda4e784877d` -> `semantic_object_draft_18e5d778bd54802d41b3`

The other `9` complete chains are included as `warn` / revision-needed editor context, not as downstream-eligible items.

## Downstream eligible count

- Full quality gate downstream eligible count: `6` review items total
- Editor packet downstream eligible count: `5` complete source-card -> semantic-object chains

The difference is because the quality-gate count includes one passing source-card review plus five passing semantic-object reviews; the editor packet counts complete semantic-object chains.

## DB safety

DB changed by default: **no**

Pre/post DB and status snapshot:

```json
{
  "claims_count": 146,
  "claims_status_hash": "2c2829622ff2988c13bc3c3f89c71dccd6139c1ec8ee06e28dc2f5e218d8df1c",
  "editorial_reviews_count": 10,
  "editorial_reviews_hash": "ed4c9b3e8704af05cdd641320bece13b8c57a9762d4a8449f6af10314585d087",
  "semantic_object_draft_count": 32,
  "source_card_draft_count": 10,
  "source_notes_count": 282,
  "sources_count": 945,
  "sources_status_hash": "bde40f350904114e864f418a59b9eb8636ae6dc598d5a73d8422ef280cb446ba"
}
```

These match the Run 7 baseline/pre-Run 8 snapshot.

## Chapter safety

- `docs/book/` changed by final state: **no**
- Generated docs artifacts from verification were restored.
- No chapter prose generated.

## Verification results

Targeted:

```bash
.venv/bin/python -m pytest -q tests/test_llm_build_editor_review_packet.py
.venv/bin/python -m pytest -q tests/test_llm_quality_gate.py
```

Results:

- Editor packet tests: `2 passed in 0.21s`
- Quality gate tests: `6 passed in 0.74s`

Full checks:

```bash
.venv/bin/python -m pytest -q
python3 scripts/verify_book_workspace.py
python3 scripts/verify_editorial_roles.py
python3 scripts/verify_book_citations.py
.venv/bin/python -m mkdocs build --strict
```

Results:

- Full suite: `38 passed in 8.37s`
- Workspace verifier: `status=ok`, no errors/warnings
- Editorial roles verifier: `status=ok`, no errors/warnings
- Citation verifier: `status=ok`, no raw-id/unresolved hits
- MkDocs strict: exit `0`, documentation built successfully; upstream MkDocs Material warning only

## Risks / limitations

- The packet is advisory and report-only; it is not an approval workflow.
- Full quality-gate rerun is GPT-5.5 reviewer output and should be checked by a human editor.
- Five semantic-object chains passed only under the current source-card and quality-gate criteria; they still need human/source verification before filing or novelty evaluation.
- Nine complete chains are included as warn/revision-needed context and should not advance without fixes.
- No external re-fetch/corroboration was performed in Run 8.
- Existing source metadata remains the source basis; vector DB chunks were not used as source authority.

## Recommendation for Run 9

Recommendation: `proceed_to_filing_novelty_evaluation_for_packet_items` — but only for the `5` downstream-eligible packet chains, and still report-only by default.

Conditions for Run 9:

1. Use only packet items with `downstream_eligible=true`.
2. Do not insert claims by default.
3. Do not modify source/claim/editorial statuses by default.
4. Do not approve author use or publication.
5. Produce a filing/novelty evaluation report that separates provenance, novelty/filing assessment, required corroboration, and explicit blockers.
