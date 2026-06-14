# Run 6 quality gate evidence map — 20260613

## Scope

Run 6 implemented a report-only reviewer-quality gate over the Run 5 GPT-5.5 high-reasoning draft reports.

Inputs reviewed:

- `reports/editorial/citation-pipeline-test-20260612-source-card-drafts-high-reasoning.json`
- `reports/editorial/citation-pipeline-test-20260612-semantic-object-drafts-high-reasoning.json`

Run 6 did **not** implement persistence, filing/novelty evaluation, claim clustering, narrative packets, chapter authoring, daily-worker wiring, schema changes, or commit/push allowlist changes.

## Files changed

- `scripts/llm_quality_gate.py`: new report-only quality gate script. It reads existing high-reasoning JSON reports, validates they are `llm_used=true` and `reasoning_status=high_reasoning_used`, checks source-card and semantic-object schema/linkage/safety metadata, and writes advisory Markdown/JSON reports.
- `tests/test_llm_quality_gate.py`: new Run 6 tests covering report-only safety, high-reasoning fail-closed behavior, schema/linkage issue detection, DB/status/protected-file immutability, and output schema.
- `reports/editorial/citation-pipeline-test-20260612-quality-gate.md`: generated Run 6 Markdown quality-gate report.
- `reports/editorial/citation-pipeline-test-20260612-quality-gate.json`: generated Run 6 machine-readable quality-gate report.
- `reports/architecture/run6-quality-gate-evidence-map-20260613.md`: this evidence map.

## Files intentionally not changed

- `docs/book/`: restored after verification-generated changes; no final tracked changes.
- `docs/entities/`: restored after verification-generated changes; no final tracked changes.
- `docs/research/claims.md`: restored after verification-generated changes; no final tracked changes.
- `data/source_registry.json`: restored after verification-generated changes; no final tracked changes.
- `scripts/daily_book_worker.py`: not changed.
- `data/schema.sql`: not changed.
- Commit/push allowlist logic: not changed.
- `.var/book.sqlite`: not modified by the Run 6 quality-gate script.
- Raw paths: not read or modified by Run 6.
- `vector_db/`: not used as source authority.

## Run 6 command

```bash
python3 scripts/llm_quality_gate.py \
  --run-id citation-pipeline-test-20260612 \
  --source-card-report reports/editorial/citation-pipeline-test-20260612-source-card-drafts-high-reasoning.json \
  --semantic-object-report reports/editorial/citation-pipeline-test-20260612-semantic-object-drafts-high-reasoning.json \
  --output-dir reports/editorial \
  --allow-blocking-output
```

Result:

- Exit code: `0`
- Source cards reviewed: `3`
- Semantic objects reviewed: `3`
- Quality-gate LLM used: `false`
- Input source-card report: `llm_used=true`, `reasoning_status=high_reasoning_used`, `provider=copilot`, `model=gpt-5.5`
- Input semantic-object report: `llm_used=true`, `reasoning_status=high_reasoning_used`, `provider=copilot`, `model=gpt-5.5`
- DB modified: `false`
- Raw/vector authority used: `false`

## Quality-gate result

```json
{
  "blocked": 0,
  "needs_revision": 6,
  "ready_for_editor_review": 0
}
```

Additional counts:

- Blocking issue count: `0`
- Revision issue count: `6`
- Ready-for-editor-review count: `0`
- Recommended next stage: `revise_high_reasoning_drafts`

Interpretation:

- The Run 5 reports are valid high-reasoning inputs and did not fail the quality gate on schema or safety linkage in a blocking way.
- All six reviewed items still need revision before downstream work because the underlying source cards/semantic objects are marked `recommended_use=do_not_use` and/or `evidence_strength=reject`; source cards also carry privacy/human-review requirements.
- This is not a publication approval and not approval for claim clustering, narrative packets, filing/novelty evaluation, chapter synthesis, or daily-worker wiring.

## Main review issues

Source-card reviews flagged:

- `recommended_use is do_not_use; keep blocked from downstream use`
- `evidence_strength is reject; not suitable for filing/novelty work`
- `privacy/publication status requires human review`
- two of three source cards had no linked semantic object in the Run 5 semantic report because the semantic run reviewed only three persisted source-card notes and all three semantic objects linked to one card.

Semantic-object reviews flagged:

- `recommended_use is do_not_use; keep blocked from downstream use`
- `evidence_strength is reject; not suitable for filing/novelty work`

Positive signals:

- Source-card and semantic-object reports were produced by the Run 5 high-reasoning bridge.
- Stable hashes are present.
- Semantic objects preserve `author_allowed=false`, `publication_approved=false`, `advisory_only=true`, and `paraphrase_only=true`.
- The quality gate detected revision needs without writing DB or changing statuses.

## DB safety

Before/after snapshots around verification and quality-gate execution were identical.

Snapshot:

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

Safety conclusions:

- DB changed by Run 6 default/report-only quality gate: `no`
- `source_notes` count before/after: `282` → `282`
- `source_card_draft` count before/after: `10` → `10`
- `semantic_object_draft` count before/after: `32` → `32`
- Sources table status hash unchanged: yes
- Claims table status hash unchanged: yes
- Editorial reviews hash unchanged: yes

## Verification results

Commands run from `/home/hermoine/terefohealreboa`:

```bash
python3 -m py_compile scripts/llm_quality_gate.py
.venv/bin/python -m pytest -q tests/test_llm_quality_gate.py
.venv/bin/python -m pytest -q
python3 scripts/verify_book_workspace.py
python3 scripts/verify_editorial_roles.py
python3 scripts/verify_book_citations.py
.venv/bin/python -m mkdocs build --strict
python3 scripts/llm_quality_gate.py \
  --run-id citation-pipeline-test-20260612 \
  --source-card-report reports/editorial/citation-pipeline-test-20260612-source-card-drafts-high-reasoning.json \
  --semantic-object-report reports/editorial/citation-pipeline-test-20260612-semantic-object-drafts-high-reasoning.json \
  --output-dir reports/editorial
```

Results:

- Run 6 targeted tests: `3 passed in 0.38s` during full verification, then `3 passed in 0.31s` after final recommendation fix.
- Full test suite: `30 passed in 7.00s`.
- Workspace verifier: `status=ok`, no errors/warnings.
- Editorial roles verifier: `status=ok`, no errors/warnings.
- Citation verifier: `status=ok`, no raw-id/unresolved hits.
- MkDocs strict: exit `0`; Material/MkDocs 2.0 upstream warning only; docs built successfully.
- Quality gate command: exit `0` with `--allow-blocking-output` and exit `0` without it because no blocking issues were found.

## Generated artifact cleanup

The verification commands generated or modified tracked docs artifacts. These were restored after verification:

- `data/source_registry.json`
- `docs/book/`
- `docs/entities/`
- `docs/research/claims.md`

Removed generated untracked artifact:

- `docs/entities/boris-cherny.md`

Final tracked protected docs/schema/daily-worker changes: none.

## Current final git status summary

Final `git status --short` shows untracked Run 1–6 reports/scripts/tests only. No tracked `docs/book/`, `data/schema.sql`, `scripts/daily_book_worker.py`, or commit-allowlist changes remain.

New Run 6 untracked files:

- `scripts/llm_quality_gate.py`
- `tests/test_llm_quality_gate.py`
- `reports/editorial/citation-pipeline-test-20260612-quality-gate.md`
- `reports/editorial/citation-pipeline-test-20260612-quality-gate.json`
- `reports/architecture/run6-quality-gate-evidence-map-20260613.md`

## Recommendation for Run 7

Recommended Run 7: revise or expand the high-reasoning draft sample before any downstream persistence or book integration.

Concrete safe next step:

1. Re-run or tune Run 5 high-reasoning source-card/semantic-object generation on a more publication-suitable sample, or explicitly select candidate source-card drafts that are not `do_not_use`/`reject`/privacy-blocked.
2. Re-run Run 6 quality gate.
3. Require at least one source-card/semantic-object chain to pass `ready_for_editor_review` before moving to human editor packet creation.
4. Continue to block filing/novelty evaluation, claim clustering, narrative packets, chapter synthesis, and daily-worker wiring until the quality gate passes and human/editor criteria are explicit.
