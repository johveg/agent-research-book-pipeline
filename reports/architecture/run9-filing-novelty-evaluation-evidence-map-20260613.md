# Run 9 filing/novelty evaluation evidence map — 20260613

## Scope

Run 9 implemented a report-only filing and novelty evaluation for the downstream-eligible complete source-card → semantic-object chains from the Run 8 editor review packet.

Run 9 did **not** insert claims, promote claims, promote sources, write editorial reviews, create narrative packets, write chapter prose, wire the daily worker, approve author use, or approve publication.

## Files changed

Added:

- `scripts/llm_evaluate_filing_novelty.py`
- `tests/test_llm_evaluate_filing_novelty.py`
- `reports/editorial/citation-pipeline-test-20260612-filing-novelty-evaluation-run9.json`
- `reports/editorial/citation-pipeline-test-20260612-filing-novelty-evaluation-run9.md`
- `reports/architecture/run9-filing-novelty-evaluation-evidence-map-20260613.md`

No production files outside the report-only script/test/report surfaces were intentionally modified in Run 9.

## Files intentionally not changed

Protected surfaces intentionally not changed:

- `docs/book/`
- raw captures
- `.var/book.sqlite`
- source statuses
- claim statuses
- editorial statuses
- publication decisions
- chapter status
- `claims` table
- `editorial_reviews` table
- `scripts/daily_book_worker.py`
- commit allowlist
- `data/schema.sql`
- narrative packet outputs
- publishable chapter prose

## Current git status before/after

Preflight status showed existing untracked Run 1–8 reports/scripts/tests plus new Run 9 work. Branch/commit:

- branch: `main`
- short HEAD: `b103efb`

Final status after verification/restoration still shows untracked report-only run artifacts and scripts/tests, including Run 9:

- `?? scripts/llm_evaluate_filing_novelty.py`
- `?? tests/test_llm_evaluate_filing_novelty.py`
- `?? reports/editorial/citation-pipeline-test-20260612-filing-novelty-evaluation-run9.json`
- `?? reports/editorial/citation-pipeline-test-20260612-filing-novelty-evaluation-run9.md`
- `?? reports/architecture/run9-filing-novelty-evaluation-evidence-map-20260613.md`

No protected tracked files remained modified after restoring generated docs/source-registry artifacts.

## Input reports used

Primary input:

- `reports/editorial/citation-pipeline-test-20260612-editor-review-packet-run8.json`

Available context/provenance reports from prior runs:

- `reports/editorial/citation-pipeline-test-20260612-quality-gate-run7-full.json`
- `reports/editorial/citation-pipeline-test-20260612-source-card-drafts-high-reasoning-run7.json`
- `reports/editorial/citation-pipeline-test-20260612-semantic-object-drafts-high-reasoning-run7.json`
- `reports/editorial/citation-pipeline-test-20260612-reasoning-candidate-selection.json`

Run 5 evidence map remains unreliable/miswritten and was not used as source of truth.

## Editor packet items available

From Run 8 editor packet:

- packet items available: `14`
- downstream-eligible packet items available: `5`
- packet items evaluated by Run 9 default/live run: `5`

Run 9 default selection used only downstream-eligible packet items.

## Provider/model/bridge used

Live filing/novelty evaluation used the Hermes high-reasoning bridge:

- provider: `copilot`
- model: `gpt-5.5`
- bridge: `hermes_cli`
- bridge script: `scripts/hermes_high_reasoning_json.py`
- `llm_used=true`
- `reasoning_status=high_reasoning_used`

No weak/local fallback was used. The script fail-closes on invalid JSON and unapproved provider fallback.

## Filing decision counts

Live GPT-5.5 Run 9 report:

```json
{
  "needs_corroboration": 2,
  "new_caveat_candidate": 3
}
```

## Novelty decision counts

Live GPT-5.5 Run 9 report:

```json
{
  "novel": 1,
  "partially_novel": 4
}
```

## Next-stage recommendation counts

Live GPT-5.5 Run 9 report:

```json
{
  "needs_source_review": 5
}
```

Additional top-level counts:

- eligible-for-filing-later count: `0`
- needs-corroboration count: `2`
- duplicate count: `0`
- do-not-use count: `0`

## Existing claims/source-notes comparison method

Run 9 opened `.var/book.sqlite` in read-only/query-only mode and read existing repo/database material only:

- existing `claims`
- existing `source_notes`
- existing `sources` metadata

Comparison method:

1. Sanitize and truncate packet semantic-object text and existing database text.
2. Build compact read-only context from claims/source notes/source metadata.
3. For no-LLM mode, use token-overlap structural matching to identify likely existing claim/source overlap.
4. For live mode, send only compact/sanitized packet items and compact/sanitized existing repo/database context to GPT-5.5 through the Hermes CLI strict-JSON bridge.
5. Validate GPT-5.5 JSON against allowed filing, novelty, and next-stage vocabularies.
6. Merge advisory GPT-5.5 decisions with immutable provenance and safety flags.

Run 9 did not use vector DB chunks as source authority and did not run external web searches.

## Evaluation items

Live GPT-5.5 evaluated five downstream-eligible items:

- `filing_eval_c39f3be4e7bef7f0dabe` / `editor_packet_b7dc9103943b3b345e15` → `needs_corroboration`, `partially_novel`, `needs_source_review`
- `filing_eval_5a84c224eb58bf625f42` / `editor_packet_23c4afb16f0732af29df` → `new_caveat_candidate`, `partially_novel`, `needs_source_review`
- `filing_eval_b82d67d436357d41bf72` / `editor_packet_48e56de78fce06dde725` → `needs_corroboration`, `partially_novel`, `needs_source_review`
- `filing_eval_bd562e909f80e16a2bb3` / `editor_packet_13a17d293dd6140c91ae` → `new_caveat_candidate`, `novel`, `needs_source_review`
- `filing_eval_224fd1bd260b4222fdfc` / `editor_packet_9ec385327deb68b949a6` → `new_caveat_candidate`, `partially_novel`, `needs_source_review`

All items preserve:

- source ID
- source-card ID
- semantic-object ID
- quality-review ID
- packet-item ID
- input hash
- output hash
- `author_allowed=false`
- `publication_approved=false`
- `advisory_only=true`

## DB safety

Before and after Run 9 DB/status snapshot:

```json
{
  "sources_count": 945,
  "claims_count": 146,
  "editorial_reviews_count": 10,
  "source_notes_count": 282,
  "source_card_draft_count": 10,
  "semantic_object_draft_count": 32,
  "sources_status_hash": "bde40f350904114e864f418a59b9eb8636ae6dc598d5a73d8422ef280cb446ba",
  "claims_status_hash": "2c2829622ff2988c13bc3c3f89c71dccd6139c1ec8ee06e28dc2f5e218d8df1c",
  "editorial_reviews_hash": "ed4c9b3e8704af05cdd641320bece13b8c57a9762d4a8449f6af10314585d087"
}
```

DB safety result:

- DB changed by default: `no`
- DB write scope: `none`
- claims inserted: `0`
- editorial reviews inserted: `0`
- source_notes count before/after: `282 / 282`
- sources status hash before/after: unchanged
- claims status hash before/after: unchanged
- editorial reviews hash before/after: unchanged

## Chapter safety

MkDocs/verification generated docs artifacts during verification. They were restored with:

```bash
git restore data/source_registry.json docs/book docs/entities docs/research/claims.md
rm -f docs/entities/boris-cherny.md
```

Final chapter safety:

- `docs/book/` changed: `no`
- chapters modified: `false`
- long source excerpts written: `false`
- raw/private material written: `false`

## Verification results

Targeted tests:

```bash
.venv/bin/python -m pytest -q tests/test_llm_evaluate_filing_novelty.py
```

Result:

- `4 passed in 0.64s`

Full suite:

```bash
.venv/bin/python -m pytest -q
```

Result:

- `42 passed in 9.38s`

Workspace/editorial/citation/MkDocs verification:

```bash
python3 scripts/verify_book_workspace.py
python3 scripts/verify_editorial_roles.py
python3 scripts/verify_book_citations.py
.venv/bin/python -m mkdocs build --strict
```

Results:

- workspace verifier: `status=ok`
- editorial roles verifier: `status=ok`
- citation verifier: `status=ok`
- MkDocs strict: exit `0`; docs built successfully, with the existing MkDocs Material warning

## Risks and limitations

- Run 9 is advisory and report-only.
- GPT-5.5 filing/novelty decisions are not human/editor decisions.
- `new_caveat_candidate` and `needs_corroboration` do not mean the statements are true.
- `needs_source_review` means none of the five downstream-eligible chains should proceed directly to narrative packets.
- Novelty was evaluated only against existing repo/database material, not external web sources.
- No corroboration research was performed in Run 9.
- No claims were inserted or promoted.
- No author/publication approval was granted.

## Recommendation for Run 10

Recommended Run 10:

- run a **report-only source review/corroboration pass** for the five evaluated items before any narrative packet candidate generation.

Rationale:

- live GPT-5.5 recommended `needs_source_review` for all `5` evaluated items
- two items explicitly need corroboration
- three items are caveat candidates, which require careful source/context review before downstream use
- no item was marked `eligible_for_filing_later`

Run 10 should remain report-only unless the user explicitly opts into persistence. It should not insert claims, modify statuses, approve author use, approve publication, or create chapter prose.
