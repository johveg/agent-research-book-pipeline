# Run 2 source-card drafts evidence map — 20260704

## Files changed

- `scripts/llm_source_cards.py`: new source-card draft generator. Reads SQLite read-only, uses sanitized source text helper, writes reports only.
- `tests/test_llm_source_cards.py`: tests no-LLM output, source-card schema, safety booleans, DB/status/book/protected-file immutability, wording limits, and fail-safe behavior.
- `/tmp/pytest-of-root/pytest-649/test_source_cards_high_reasoni0/test-source-cards-hr-source-card-drafts-high-reasoning.md`: generated Markdown source-card report.
- `/tmp/pytest-of-root/pytest-649/test_source_cards_high_reasoni0/test-source-cards-hr-source-card-drafts-high-reasoning.json`: generated JSON source-card report.
- `reports/architecture/run5-high-reasoning-bridge-evidence-map-20260704.md`: Run 2 evidence map.

## Files intentionally not changed

- `docs/book/`: not changed by the source-card script.
- `scripts/daily_book_worker.py`: not changed; no daily-worker integration.
- `data/schema.sql`: not changed; no schema migration.
- Commit allowlist: not changed.
- Raw capture paths: not changed.
- `.var/book.sqlite`: opened read-only; not modified by this script.

## Current working tree status

Initial Run 2 status included untracked Run 1 files. Final status should be captured after verification in the human report. The script itself does not stage, commit, or overwrite unrelated files.

## Commands run

Record exact targeted/full verification results after final verification. The source-card invocation that produced this map should be listed there.

## Evidence from source-card output

- Sample size: 2 sources
- LLM used: True
- Confidence level: `high`
- Source-card shape valid: yes; generated cards include required hashes, metadata, candidate fields, risk flags, and advisory-only booleans.
- More source richness than Run 1: yes; Run 2 creates per-source structured drafts rather than only general source findings.
- Suitable for later semantic extraction: likely, after editor review and persistence safety checks.
- `source_notes` sufficiency: likely sufficient for Run 3 draft persistence; defer dedicated table.

## Risks / limitations

- No-LLM source cards are structural and low-confidence.
- Real LLM prompts may produce unstable JSON unless schema-validated.
- Sanitized source text may still include too much wording if max-summary limits are raised.
- source_notes is generic and may be too limited for long-term source-card lifecycle/versioning.
- A dedicated source_cards table may still be needed after persistence review.
- Social/private-adjacent sources must remain discovery-only or needs-review until corroborated.
- Vector DB chunks are not source authority and are not used by this script.
- No-LLM output is structural/low-confidence only.
- Prompt/output instability remains for future real-LLM mode.
- Source wording leakage risk is controlled with short max-summary limits but should stay tested.
- Source-text safety depends on existing `editorial_common.source_text()` behavior.

## Recommendation for Run 3

Persist reviewed source-card drafts to `source_notes` with a disabled-by-default/report-first path. Do not add a dedicated `source_cards` table until source_notes persistence proves insufficient. Do not implement semantic extraction, narrative packets, or chapter writing yet.
