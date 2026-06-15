# Academic book structure plan

Generated: 2026-06-15T19:47:56Z

- run_id: `run48`
- report_only: `True`
- docs_book_restructured: `False`

## Recommended future structure

### Front matter

- Title page
- Preface
- Reader guide
- Contribution summary

### Part I Foundations

- Introduction
- Literature and Context
- Conceptual Framework
- Methodology

### Part II Core Concepts

- Closed-loop production
- Evidence boundaries
- Machine review and safety gates
- Academic prose quality contract

### Part III Tools and Case Material

- Hermes as automation infrastructure
- OpenClaw case material
- Terefo Heal Reboa pipeline case
- Tooling patterns and limits

### Part IV Production Operations

- Daily operation model
- Publication validation
- Monitoring and rollback
- Operational caveats

### Back Matter

- Glossary
- Source-quality schema
- Claim-status schema
- Bibliography
- Appendix: evidence ledger and internal reports

## Migration principles

- Move claim/source ledger material out of chapter prose and into appendices or internal reports.
- Give the book a clear thesis, contribution, methodology, literature/context chapter, and conceptual framework before expanding case chapters.
- Use evidence as cited support for sustained paragraphs, not as raw status bullets.
- Keep machine/editor workflow notes out of reader-facing pages.
- Do not restructure docs/book until a later explicitly tested restructuring run.

## Recommendation

Run a report-only manuscript inventory that classifies existing docs/book pages against this structure before any rewrite.
