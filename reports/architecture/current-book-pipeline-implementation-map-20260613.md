# Current book pipeline implementation map

Generated: 2026-06-13

Scope: inspection-only architecture map for the Terefo Heal Reboa book pipeline. This report maps the current flow from raw capture to published MkDocs docs before adding any LLM reasoning layer.

## 1. Current pipeline sequence

The main orchestrator is `scripts/daily_book_worker.py`.

1. Initialize local runtime database and run state
   - `scripts/daily_book_worker.py`
   - `scripts/research_common.py`
   - `data/schema.sql`
   - Runtime DB: `.var/book.sqlite`
   - Runtime state/logs: `logs/runs/`

2. Raw capture
   - Public web capture: `scripts/capture_web_daily.py`
     - Uses Brave Search.
     - Fetches public result URLs.
     - Writes sanitized Markdown/JSON under `raw/web/<run_id>/<query>/`.
     - Inserts source rows into SQLite through `research_common.upsert_source()`.
   - LinkedIn capture: `scripts/capture_linkedin_daily.py`
     - Connects to existing CDP browser.
     - Opens LinkedIn search result pages only.
     - Scrolls until stable plateau.
     - Writes sanitized visible-result Markdown/JSON under `raw/linkedin/<run_id>/<query>/`.
     - Inserts source rows into SQLite through `research_common.upsert_source()`.
     - Does not intentionally close the persistent browser session beyond closing the CDP connection.

3. Source registry / SQLite writes
   - DB initialization and shared writes: `scripts/research_common.py`
     - `init_db()` executes `data/schema.sql`.
     - `connect_db()` opens `.var/book.sqlite`.
     - `upsert_source()` inserts into `sources` with `INSERT OR IGNORE`.
   - Source registry export: `scripts/export_source_registry.py`
   - Registry internals: `scripts/citation_common.py`
     - `export_source_registry()` reads SQLite `sources` and writes `data/source_registry.json`.
     - Registry declares authority: SQLite `sources` table exported by `scripts/export_source_registry.py`.

4. Entity extraction
   - `scripts/extract_entities.py`
   - Shared heuristics in `scripts/editorial_common.py`
   - Reads recent `sources`, builds entity candidates from `source_text()`, writes:
     - `entities`
     - `entity_sources`
   - Public entity pages are written by `scripts/update_entity_pages.py`.

5. Claim extraction
   - `scripts/extract_claims.py`
   - Shared heuristics in `scripts/editorial_common.py`
   - Reads recent `sources`, extracts conservative candidate sentences, writes:
     - `claims`
     - `claim_sources`
   - Public claims page is written by `scripts/update_claims_page.py`.

6. Trend discovery
   - `scripts/discover_trends.py`
   - Reads captured Markdown from `raw/web/<run_id>/` and `raw/linkedin/<run_id>/`.
   - Filters stop words and structural/platform terms.
   - Writes:
     - `reports/discovery/<run_id>-trend-discovery.md`
     - `reports/discovery/<run_id>-trend-discovery.json`
     - SQLite `trend_terms`
   - Editorial trend decisions are later applied by `scripts/editorial_pipeline_report.py::trend_decisions()`.

7. Editorial scoring and review
   - `scripts/editorial_pipeline_report.py`
   - Main responsibilities:
     - source quality scoring: `source_quality()` and `score_sources()`
     - duplicate/repeated-signal detection: `detect_duplicates()`
     - claim review/status assignment: `review_claims()`
     - contradiction heuristics: `detect_contradictions()`
     - trend accept/reject/monitor decisions: `trend_decisions()`
     - chapter update gate: `chapter_update_gate()`
     - blocked-state output and publication recommendation
   - Writes editorial report under `reports/editorial/` and updates SQLite:
     - `sources.quality_score`, `quality_notes`, `summary`, `relevant_entities`, `extracted_candidate_claims`, `duplicate_status`, `privacy_publication_status`, `publication_notes`
     - `claims.status`, `claim_type`, `source_quality`, `contradiction_status`, `publication_decision`, `editor_notes`, `reviewed_at`
     - `source_notes`
     - `editorial_reviews`

8. Chapter synthesis
   - `scripts/synthesize_chapters.py`
   - Called only by `scripts/daily_book_worker.py` when all earlier editorial gates are not blocked and `--allow-chapter-updates` is present.
   - Validates:
     - chapter briefs under `docs/chapter-briefs/`
     - style sheet `docs/operations/author-style-sheet.md`
   - Reads only Author-usable claims:
     - `supported`
     - `weakly_supported`
     - `promoted_to_chapter`
   - Excludes social-only / human-review source origins unless a stronger publishable source is linked.
   - Writes `docs/book/*.md` evidence-status sections with structured citation tokens like `{{cite:src_...}}`.

9. Citation verification and resolution
   - `scripts/resolve_book_citations.py`
   - `scripts/verify_book_citations.py`
   - Shared logic: `scripts/citation_common.py`
   - `resolve_book_citations.py` converts internal `{{cite:src_...}}`, backticked IDs, and legacy raw IDs into reader-facing numbered citations and references.
   - It blocks unresolved or non-publishable source origins while removing raw IDs from public prose.
   - `verify_book_citations.py` gates public book pages against:
     - raw `src_...` / `claim_...` IDs
     - `{{cite:...}}` tokens
     - `[unresolved citation]` markers

10. Book role verification and MkDocs build
   - `scripts/book_role_report.py`
   - Runs `mkdocs build --strict`.
   - Checks navigation, page placement, link/report reachability, citation safety, unsafe staged paths, raw tracked paths, and acceptance criteria.
   - Writes/prints a Book role report payload.
   - The orchestrator treats nonzero Book gate as blocked publication.

11. Research quality verification
   - `scripts/verify_editorial_ingestion.py`
   - `scripts/verify_editorial_roles.py`
   - `scripts/verify_book_workspace.py`
   - Check DB/content consistency, role instruction presence, and workspace safety.

12. Vector DB refresh
   - `scripts/build_vector_db.py`
   - Builds local ChromaDB at `vector_db/` and writes public manifest `data/chroma_manifest.json`.
   - Current index inputs include `docs/`, `raw/web`, `raw/linkedin`, and `reports/discovery` Markdown.
   - `vector_db/` itself is ignored and must not be committed.

13. Commit/push allowlist
   - `scripts/daily_book_worker.py` selects explicit `safe_paths`.
   - `scripts/research_common.py::git_commit_push()` stages only those paths, checks for unsafe names, commits, and pushes.

## 2. Scripts touched by each stage

- Raw capture:
  - `scripts/capture_web_daily.py`
  - `scripts/capture_linkedin_daily.py`
  - `scripts/research_common.py`

- Source registry / SQLite writes:
  - `scripts/research_common.py`
  - `scripts/init_db.py`
  - `data/schema.sql`
  - `scripts/export_source_registry.py`
  - `scripts/citation_common.py`

- Entity extraction:
  - `scripts/extract_entities.py`
  - `scripts/editorial_common.py`
  - `scripts/update_entity_pages.py`

- Claim extraction:
  - `scripts/extract_claims.py`
  - `scripts/editorial_common.py`
  - `scripts/update_claims_page.py`

- Trend discovery:
  - `scripts/discover_trends.py`
  - `scripts/editorial_pipeline_report.py`
  - `scripts/update_book_pages.py`

- Editorial scoring / Curator / Editor gate:
  - `scripts/editorial_pipeline_report.py`
  - `scripts/editorial_common.py`
  - role docs under `docs/operations/` and `docs/operations/instructions/`

- Chapter synthesis / Author role:
  - `scripts/synthesize_chapters.py`
  - `docs/chapter-briefs/*.md`
  - `docs/operations/author-style-sheet.md`

- Citation verification:
  - `scripts/citation_common.py`
  - `scripts/resolve_book_citations.py`
  - `scripts/verify_book_citations.py`
  - `data/source_registry.json`

- Book role verification and MkDocs build:
  - `scripts/book_role_report.py`
  - `mkdocs.yml`
  - `docs/**`

- Commit/push allowlist:
  - `scripts/daily_book_worker.py`
  - `scripts/research_common.py`
  - `.gitignore`
  - `.github/workflows/pages.yml`

## 3. Current SQLite schema and relevant tables

Authoritative schema file: `data/schema.sql`.

Runtime database inspected: `.var/book.sqlite`.

Relevant tables:

- `runs`
  - run metadata: `id`, `started_at`, `ended_at`, `status`, `mode`, `summary_path`, `error`

- `sources`
  - source registry base table
  - key fields: `id`, `source_type`, `query`, `url`, `title`, `publisher`, `author`, `published_at`, `captured_at`, `archived_path`, `content_hash`, `reliability_tier`, `quality_score`, `quality_notes`, `summary`, `relevant_entities`, `extracted_candidate_claims`, `duplicate_status`, `privacy_publication_status`, `publication_notes`, `visibility`, `run_id`
  - unique constraint: `(url, content_hash)`

- `entities`
  - extracted entities: `id`, `type`, `name`, `canonical_name`, `summary`, `confidence`, first/last/updated timestamps

- `claims`
  - extracted candidate/editorial claims: `id`, `claim_text`, `claim_type`, `subject_entity_id`, `confidence`, `status`, first/last timestamps, `current_best_understanding`, `evidence_strength`, `source_count`, `source_quality`, `contradiction_status`, `publication_decision`, `editor_notes`, `reviewed_at`, `updated_at`

- `entity_sources`
  - many-to-many entity/source links: `entity_id`, `source_id`, `mention_count`, timestamps, `sample`

- `claim_sources`
  - many-to-many claim/source links: `claim_id`, `source_id`, `quote`, `support_type`

- `relationships`
  - currently present for future entity relationships: `subject_entity_id`, `relationship_type`, `object_entity_id`, confidence/timestamps/status

- `trend_terms`
  - trend candidates and decisions: `id`, `term`, `term_type`, `count`, timestamps, `status`, `evidence_path`, `run_id`

- `artifacts`
  - artifact registry: `id`, `run_id`, `artifact_type`, `path`, `created_at`, `status`

- `source_notes`
  - editorial source notes generated by `editorial_pipeline_report.py`

- `editorial_reviews`
  - editorial gate/review records generated by `editorial_pipeline_report.py`

Runtime observation: the live `.var/book.sqlite` contains the same relevant tables, plus columns added defensively by `ensure_pipeline_schema()` if an older DB exists. One runtime difference observed is that `claims.status` default in the existing DB is `observed`, while `data/schema.sql` currently defines the default as `candidate`; this appears to be a legacy runtime DB artifact rather than the current schema file.

## 4. Where chapter updates are gated by `--allow-chapter-updates`

Primary gate: `scripts/daily_book_worker.py`.

- CLI flag is declared at lines around `ap.add_argument("--allow-chapter-updates", action="store_true", ...)`.
- Flow:
  - If `editorial.get("final_status") == "blocked"`, `scripts/synthesize_chapters.py` is skipped.
  - Else if `not args.allow_chapter_updates`, `scripts/synthesize_chapters.py` is skipped with the message that daily runs collect/classify/extract/propose only.
  - Else, `scripts/synthesize_chapters.py --run-id <run_id>` runs.

Secondary gates:

- `scripts/editorial_pipeline_report.py`
  - Blocks chapter publication for missing entities, missing claims, missing source IDs, unscored sources, unsafe staged files, failed MkDocs, blocked LinkedIn capture, trend noise domination, privacy review, and failed acceptance criteria.
  - `chapter_update_gate()` validates existing/generated chapter sections for mapping, citations, hype language, social proof caveats, and filler.

- `scripts/synthesize_chapters.py`
  - Restricts Author use to claims with status `supported`, `weakly_supported`, or `promoted_to_chapter`.
  - Requires publishable non-social origin evidence in its claim query.

- `scripts/book_role_report.py`
  - Blocks publication if chapter pages expose raw IDs, unresolved citations, unsafe staged files, tracked raw captures, or MkDocs strict build failures.

## 5. Unsafe path exclusions and publish/commit safety gates

`.gitignore` excludes:

- Python/runtime:
  - `__pycache__/`, `*.py[cod]`, `.venv/`, `.env`, `.env.*`, `.pytest_cache/`, `.mypy_cache/`
  - Exception: `!.env.example`

- Local credentials/browser/session state:
  - `.var/`
  - `**/browser-profile/`
  - `**/*cookies*`
  - `**/*token*`
  - `**/*secret*`
  - `**/*credential*`

- Runtime logs and worker state:
  - `logs/runs/*.log`
  - `logs/runs/*.json`
  - `logs/runs/state/*.state`
  - `logs/runs/state/latest.state`
  - `logs/runs/*.pid`

- Raw/private captures:
  - `raw/`
  - Exception: `!raw/.gitkeep`

- Local databases and vector stores:
  - `*.sqlite`, `*.sqlite3`, `*.db`
  - `vector_db/`

- Build output:
  - `site/`

Commit/push allowlist in `scripts/daily_book_worker.py`:

- Always allowed when committing pipeline output:
  - `reports`
  - `data/search_config.json`
  - `data/schema.sql`
  - `data/chroma_manifest.json`
  - `data/source_registry.json`
  - `.github`
  - `mkdocs.yml`
  - `README.md`
  - `.gitignore`
  - `.env.example`
  - `scripts`
  - `tests`
  - `docs/research`
  - `docs/entities`
  - `docs/reports`
  - `docs/operations`
- `docs/book` is appended only when final status is not `blocked`.
- The code comment explicitly says: never stage `docs/book` chapter prose while the Editor gate is blocked.

Additional unsafe checks:

- `scripts/research_common.py::git_commit_push()` refuses to commit if current git status includes path fragments:
  - `.env`, `cookie`, `token`, `secret`, `credential`, `.var/`, `browser-profile`

- `scripts/editorial_pipeline_report.py::git_unsafe_staged()` blocks staged paths matching:
  - `raw`, `logs`, `.var`, `vector_db`, `site`, `.env`, cookies/tokens/secrets/sessions/browser/profile, or DB sidecar extensions `.sqlite`, `.db`, `.wal`, `.shm`
  - exception: `raw/.gitkeep`

- `scripts/book_role_report.py` uses a similar `UNSAFE_PATTERNS` regex and also checks `git ls-files raw`, allowing only `raw/.gitkeep`.

- `scripts/verify_editorial_ingestion.py` blocks staged raw additions except deletions and `raw/.gitkeep`; it warns if raw captures are already tracked.

- `scripts/verify_book_workspace.py` scans tracked files for forbidden fragments: `.env`, `cookie`, `token`, `secret`, `credential`, `.var/browser`, `browser-profile`, with `.env.example` allowed.

## 6. Current safety gates

Current gates before public chapter publication:

- Raw material isolation:
  - raw captures stay under ignored `raw/`.
  - runtime DB and logs stay under ignored `.var/` and `logs/runs/`.

- Editorial gate:
  - `scripts/editorial_pipeline_report.py` blocks publication when extraction/scoring/review requirements are not met.
  - LinkedIn/social sources are scored as weak discovery signals, not independent confirmation.

- Author gate:
  - chapter synthesis is skipped by default.
  - `--allow-chapter-updates` is required in addition to a non-blocked editorial status.
  - Author can only write from approved/caveated claim records, not raw captures.

- Citation gate:
  - public pages must not expose raw `src_...`/`claim_...` IDs or unresolved citation tokens.
  - non-publishable source origins block resolution.

- Book role gate:
  - MkDocs strict build must pass.
  - new pages must be linked or under accepted docs sections.
  - unsafe staged/tracked paths block publication.

- Commit gate:
  - only explicit allowlisted paths are staged.
  - `docs/book` is excluded when final status is blocked.
  - unsafe path fragments cause `git_commit_push()` to refuse committing.

## 7. Safest extension points for an LLM reasoning layer

Recommended extension points, from safest to riskiest:

1. Add an LLM-assisted `source_notes` enrichment step after capture but before claim extraction.
   - Input: sanitized source metadata/text via `editorial_common.source_text()`.
   - Output: structured notes into `source_notes` and/or extra fields in `sources.summary`.
   - Safety: no chapter writes; no publication effect unless later gates approve.

2. Add an LLM-assisted candidate-claim proposal step before `review_claims()`.
   - Input: sanitized source text and existing entity/source records.
   - Output: candidate claims with source IDs and quotes only.
   - Must preserve default `status='candidate'` or `needs_review`; never auto-promote to `supported`.

3. Add an LLM-assisted contradiction / duplicate / clustering step inside or adjacent to `editorial_pipeline_report.py`.
   - Input: claim/source tables.
   - Output: review annotations, contradiction candidates, duplicate clusters.
   - Keep publication decision human/editor-gated.

4. Add an LLM-assisted trend explanation step after `discover_trends.py` but before trend promotion.
   - Input: candidate trend terms and evidence paths.
   - Output: rationale for monitor/reject, not recurring search mutations by default.

5. Add an LLM-assisted chapter-brief recommender.
   - Input: approved/caveated claims, source notes, entity summaries, existing chapter briefs.
   - Output: proposed changes under `reports/` or `docs/research/`, not direct `docs/book` edits.

Avoid first:

- Direct LLM writes to `docs/book/*.md`.
- LLM updates to claim `status='supported'` or `promoted_to_chapter` without explicit editor approval.
- LLM access to raw authenticated LinkedIn HTML beyond sanitized visible-result Markdown.
- LLM-assisted commit path expansion.

## 8. Recommended first implementation step

First implement a dry-run LLM reasoning layer as a new script that writes reports only:

- Proposed script: `scripts/llm_reasoning_dry_run.py`
- Inputs:
  - SQLite `sources`, `source_notes`, `entities`, `claims`, `claim_sources`
  - sanitized source text through `editorial_common.source_text()`
- Outputs only:
  - `reports/architecture/` or `reports/editorial/<run_id>-llm-reasoning-dry-run.md/json`
- No DB writes in the first version, or DB writes only to a new review/proposal table after a schema review.
- No chapter writes.
- No source status promotion.
- No commit allowlist expansion.
- Must be invoked before `editorial_pipeline_report.py` or in parallel as advisory context.

This creates a measurable reasoning layer while preserving every existing hard safety gate.

## 9. Verification run during this inspection

Commands run from `/home/hermoine/terefohealreboa`:

```bash
python3 --version
# Python 3.11.15

.venv/bin/python -m pytest -q
# 8 passed in 2.71s

/home/hermoine/linkedin-24h-watch/.venv/bin/python3 scripts/verify_book_workspace.py
# status: ok; errors: []; warnings: []

/home/hermoine/linkedin-24h-watch/.venv/bin/python3 scripts/verify_editorial_roles.py
# status: ok; errors: []; warnings: []

python3 scripts/verify_book_citations.py
# status: ok; raw_id_hits: []; unresolved_hits: []

.venv/bin/python -m mkdocs build --strict
# exit 0; documentation built successfully
```

MkDocs emitted non-fatal informational output about many generated entity pages existing outside `nav`, then completed successfully.

Note: the test suite exercises generation scripts and caused local working-tree changes to generated docs/research/entity artifacts. After verification, after-only generated entity/research changes were restored. Pre-existing working-tree changes that were present before this inspection were left untouched. This report is the only intentional new file from this inspection.
