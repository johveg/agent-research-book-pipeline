# Terefo Heal Reboa Reference Provenance Summary

Date: 2026-06-12

## Summary

The current Terefo Heal Reboa site/book is not handling references correctly yet.

Local book path inspected:

`/home/hermoine/terefohealreboa`

Current problem:

- Book chapters expose internal IDs directly, for example `src_384bcc1123ee303676b1`.
- Those IDs are useful internally, but they are not reader-facing citations.
- The vector database is being treated too much like a source authority.
- The vector database is not a source authority; it is only a retrieval/index layer.

## Correct citation model

### 1. Inline citations in prose

Current style:

> The stored material describes loop engineering as a move from manually prompting an agent step by step toward designing the loop that prompts, checks, and routes the agent’s work (`src_384bcc1123ee303676b1`, `src_80c8c50e6406c7e7fc95`, `src_e0864997d036665b77f9`).

Better style:

> The stored material describes loop engineering as a move from manually prompting an agent step by step toward designing the loop that prompts, checks, and routes the agent’s work [1][2][3].

Then the page should include a References section:

[1] Cobus Greyling, “Loop Engineering Playbook. Where loops live, how to run your first…”, Medium, captured 2026-06-11. Source record: `src_384bcc1123ee303676b1`.

[2] Data Science Dojo, “Agentic Loops: From ReAct to Loop Engineering (2026 Guide)”, datasciencedojo.com, captured 2026-06-11. Source record: `src_80c8c50e6406c7e7fc95`.

[3] Linas Substack, “Loop Engineering: Design AI Loops That Ship While You Sleep”, captured 2026-06-11. Source record: `src_e0864997d036665b77f9`.

Preferably each reference links to a canonical source database page or anchor, not only to the raw external URL.

### 2. The source database must be the authority, not Chroma/vector DB

The correct provenance chain should be:

```text
Raw capture
→ archived source file
→ canonical source registry
→ extracted chunks
→ vector DB
→ cited book text
```

The vector DB should never be the final citation. It can say “this chunk came from source_id X”, but then the citation system must resolve X through the source registry.

Bad:

- “Reference: Chroma chunk abc123”
- “Reference: vector result src_384…”

Good:

- “Reference: Cobus Greyling, Medium article, original URL, archive path, capture date, quality score, source id.”

## Existing metadata found

There is already partial source metadata that can be reused.

Relevant existing file:

`/home/hermoine/terefohealreboa/docs/research/sources.md`

Also present in generated editorial and weekly reports.

Examples:

### `src_384bcc1123ee303676b1`

- Title: “Loop Engineering Playbook. Where loops live, how to run your first…”
- URL: `https://cobusgreyling.medium.com/loop-engineering-playbook-4460e01e88d8`
- Publisher: `cobusgreyling.medium.com`
- Source type: `web`
- Quality score: `B`

### `src_80c8c50e6406c7e7fc95`

- Title: “Agentic Loops: From ReAct to Loop Engineering (2026 Guide)”
- URL: `https://datasciencedojo.com/blog/agentic-loops-explained-from-react-to-loop-engineering-2026-guide/`
- Publisher: `datasciencedojo.com`
- Source type: `web`
- Quality score: `B`

### `src_e0864997d036665b77f9`

- Title: “Loop Engineering: Design AI Loops That Ship While You Sleep”
- URL: `https://linas.substack.com/p/loop-engineering-complete-guide`
- Publisher: `linas.substack.com`
- Source type: `web`
- Quality score: `B`

### `src_3eb174da3717ef674f19`

- Title: “Loop Engineering Explained Visually - by The Cloud Girl”
- URL: `https://priyankavergadia.substack.com/p/agent-loop-and-fleet-explained-visually`
- Publisher: `priyankavergadia.substack.com`
- Source type: `web`
- Quality score: `B`

Conclusion: the source data exists; the publication layer is not using it properly.

## Recommended system change

Implement this as a citation resolver and publication gate.

### A. Canonical source registry

Create or normalize one of these:

`data/source_registry.json`

or:

`docs/research/source-database.md`

Each source record should include:

- `source_id`
- `title`
- `author`
- `publisher`
- `canonical_url`
- `original_url`
- `archive_path`
- `raw_capture_path`
- `source_type`
- `captured_at`
- `published_at`
- `quality_score`
- `privacy_publication_status`
- `duplicate_status`
- `run_id`
- `search_query`
- `content_hash`
- `extraction_method`

### B. Citation resolver

A script should scan `docs/book/*.md` for:

- `src_...`
- `claim_...`

Then it should:

- assign numbered citations by order of first appearance;
- replace raw IDs with `[1]`, `[2]`, etc.;
- append a References section;
- resolve each reference against the source registry;
- for `claim_...`, resolve claim → supporting source(s) before citing.

### C. Origin backtracking

If a vector result only knows `source_id`, it must resolve:

```text
source_id
→ source registry
→ archive path
→ original/raw capture metadata
→ URL/publisher/title/date
```

If that fails, the book should mark it as:

> Unresolved source origin — not publishable as citation.

### D. Publication gate

The build should fail if:

- raw `src_...` appears in `docs/book/*.md`;
- raw `claim_...` appears in prose without source resolution;
- a citation has no source registry entry;
- a citation points only to vector DB metadata;
- a source has `privacy_publication_status: human_review` but is published as normal evidence;
- weak LinkedIn/search-result material is used as strong support.

## Core principle

The vector DB is allowed to answer:

> Which stored chunks are relevant?

It is not allowed to answer:

> What is the source?

The source database answers that.

The book should cite human-readable source records, while the internal IDs remain traceability handles behind the scenes.

## Recommendation

Fix the pipeline first, then regenerate the chapters. Otherwise manual prose patches will be overwritten and the cron/book loop may reintroduce raw `src_...` IDs later.
