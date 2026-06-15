# Run 44 status — guarded book publication canary

Generated: 2026-06-15T12:29:00Z

## Run

- title: Aggressive guarded book publication canary with evidence expansion and daily publish fallback
- run id: `citation-pipeline-test-20260612`
- repository: `/home/hermoine/terefohealreboa`
- success: yes
- publication status: `live_gpt55_completed`
- publication decision: `substantive_canary_applied`

## Model gate

- GPT-5.5 used: true
- provider/model/profile: `copilot` / `gpt-5.5` / `closed_loop_editorial`
- bridge: `hermes_cli`
- strict JSON required: true
- weak/local fallback refused: true

## Evidence expansion

- status: `expanded_existing_evidence`
- candidates considered: 10
- Run 43 packets consumed: 1
- Run 43 ready packets: 0
- existing evidence only: yes
- external web collection: no
- new raw collection: no

## Publish packets

- publish packet count: 1
- substantive approved count: 1
- machine-approved count: 1
- caveat-only count: 0
- no-safe-promotion / safe-reports count: 0
- disposition counts: `{"publish_packet_machine_approved": 1}`

## Publication result

- docs/book applied: true
- publication applied: true
- publication type: substantive canary
- daily status fallback applied: false
- target file: `docs/book/06-operating-loops.md`
- docs/book files changed: `docs/book/06-operating-loops.md`
- guarded publisher status: `substantive_publication_applied`
- changed files from publisher: `docs/book/06-operating-loops.md`

## Verification

- focused Run 44 suite: `40 passed`
- full pytest: `280 passed in 128.19s`
- workspace verifier: ok
- editorial-role verifier: ok
- citation verifier: ok, no raw id hits and no unresolved hits
- MkDocs strict: ok
- git diff --check: ok
- secrets scan: `SECRETS_SCAN_OK changed_text_files=21`
- forbidden dependency term scan: ok
- full verification result: ok

## Mutation guard

- profile: `docs_book_write`
- result: `ok=true`
- DB delta: `{}`
- current DB counts: `{"claims": 218, "editorial_reviews": 10, "source_notes": 445}`
- protected path deltas: `{ ".var/book.sqlite": true, "data/schema.sql": false, "data/source_registry.json": false, "docs/book": true, "docs/entities": false, "docs/research/claims.md": false, "raw": false, "scripts/daily_book_worker.py": false }`
- source registry changed: false
- raw changed: false
- schema changed: false
- daily worker changed: false
- docs/entities changed: false
- docs/research/claims.md changed: false
- SQLite logical DB delta: none
- SQLite physical hash drift: allowed only without logical delta under `docs_book_write`

## Reports created

- `reports/editorial/citation-pipeline-test-20260612-publication-orchestrator-run44.json`
- `reports/editorial/citation-pipeline-test-20260612-publication-orchestrator-run44.md`
- `reports/editorial/citation-pipeline-test-20260612-evidence-expansion-run44.json`
- `reports/editorial/citation-pipeline-test-20260612-evidence-expansion-run44.md`
- `reports/editorial/citation-pipeline-test-20260612-publish-packets-run44.json`
- `reports/editorial/citation-pipeline-test-20260612-publish-packets-run44.md`
- `reports/editorial/citation-pipeline-test-20260612-book-patch-preview-run44.json`
- `reports/editorial/citation-pipeline-test-20260612-book-patch-preview-run44.md`
- `reports/editorial/citation-pipeline-test-20260612-guarded-book-publication-run44.json`
- `reports/editorial/citation-pipeline-test-20260612-guarded-book-publication-run44.md`
- `reports/editorial/citation-pipeline-test-20260612-mutation-guard-run44.json`
- `reports/editorial/citation-pipeline-test-20260612-mutation-guard-run44.md`
- `reports/architecture/run44-guarded-book-publication-evidence-map-20260614.md`
- `reports/telegram/run44-status.md`

## Commit / push

- implementation/status commit: pending at status-write time
- push result: pending at status-write time
- final git status: pending at status-write time

## Run 45 recommendation

Enable the daily production scheduler behind the same fail-closed gates:

- `closed_loop_runtime.json`
- production scheduler command
- daily raw collection enabled
- evidence promotion enabled
- author/editor/red-team enabled
- guarded book publication enabled
- Telegram status enabled
- commit/push enabled only after gates
- GPT-5.5 final production red-team
- no routine manual dependency

## Blockers

None at status-write time. Run 44 cleaned unintended generated artifacts from full verification and retained only the guarded docs/book canary plus Run 44 control-plane/report changes.
