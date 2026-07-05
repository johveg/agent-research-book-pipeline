# Run 1 LLM reasoning dry-run evidence map — 20260704

## Files changed

- `scripts/llm_reasoning_dry_run.py`: new dry-run advisory report generator; reads SQLite in read-only mode and writes Markdown/JSON reports only.
- `tests/test_llm_reasoning_dry_run.py`: tests no-LLM execution, report outputs, safety booleans, and no docs/book or DB writes.
- `/tmp/pytest-of-root/pytest-649/test_llm_reasoning_dry_run_doe0/test-llm-dry-run-safety-llm-reasoning-dry-run.md`: generated advisory Markdown report.
- `/tmp/pytest-of-root/pytest-649/test_llm_reasoning_dry_run_doe0/test-llm-dry-run-safety-llm-reasoning-dry-run.json`: generated advisory JSON report.
- `reports/architecture/run1-llm-reasoning-dry-run-evidence-map-20260704.md`: implementation/evidence map for Run 1 evaluation.

## Files intentionally not changed

- `docs/book/`: not changed by this script.
- `scripts/daily_book_worker.py`: not changed; no daily-worker wiring in Run 1.
- `data/schema.sql`: not changed; no DB migration in Run 1.
- Commit allowlist: not changed.
- Raw capture paths: not changed.
- `.var/book.sqlite`: opened read-only; not modified by this script.

## Current working tree status

Capture final `git status --short` in the final human report after all verification commands complete. This script itself does not stage or commit files.

## Commands run

Record final command results after verification. The dry-run invocation that produced this map should be listed there.

## Evidence from dry-run output

- Source sample size: 2
- Claim sample size: 2
- Entity count inspected: 4365
- LLM used: False
- Confidence level: `low_draft_structural`
- Useful advisory reasoning produced: yes, as deterministic structural/draft analysis in no-LLM mode; high-reasoning LLM output should be evaluated separately if configured.
- Source richness captured better than current sentence extraction: partially; the report surfaces source-card/semantic-extraction candidates but does not yet create durable cards.
- Next step direction: source cards using existing `source_notes` first, while deferring new schema until the card shape is proven.

## Risks / limitations

- No-LLM mode is structural and low-confidence by design.
- LLM output may be unstable unless constrained by schema validation.
- Sanitized source text can still contain too much source wording if max-length guards are loosened.
- Vector DB chunks must remain non-authoritative context only.
- Model availability is not assumed; `--no-llm` produces low-confidence draft-only output.
- Prompt/output instability remains a risk for future real-LLM mode and should be constrained by JSON schema validation.
- Reports deliberately truncate source wording to reduce risk of copying too much raw source text.

## Recommendation for Run 2

Proceed to source cards using the existing `source_notes` table first. Do not add chapter packets, modify `docs/book/`, or promote claims/sources until source-card shape, privacy guards, and tests are stable.
