# Manuscript Style Guide

## Purpose

This guide separates Terefo Heal Reboa's evidence machinery from its reader-facing manuscript. Evidence reports, claims, source registries, and editorial pipeline notes remain essential, but public chapters must read as academic/professional prose rather than as evidence ledgers.

## Target tone

The book uses an academic/professional tone: careful, precise, evidence-bounded, and useful to technically literate practitioners and researchers. It should avoid hype, product marketing, unsupported field-wide claims, and declarations that an emerging practice is settled.

## Audience

The primary audience is technically literate practitioners, researchers, and engineering leaders trying to understand agent systems, closed-loop automation, and the operational consequences of tool-using AI.

## Chapter anatomy

Reader-facing chapters should include:

1. A clear title.
2. An opening thesis paragraph that states the chapter's argument.
3. Conceptual framing and definitions.
4. Analytical sections that synthesize sources rather than list them.
5. Integrated citations in normal prose.
6. Explicit limitations where evidence is weak or practitioner-led.
7. A conclusion or transition to the next chapter.
8. References.

## Citation use

Citations should support claims in prose. They should not appear as raw source-token ledgers, claim maps, or quality-status dumps. Citation tokens such as `[1]` are allowed; internal claim IDs, source IDs, and source-quality labels are not reader-facing chapter prose.

## Weak evidence

Weak or emerging evidence must be expressed with caveats such as "emerging practitioner discourse", "the available sources suggest", "limited evidence", or "does not establish consensus". Weak claims must not be phrased as settled academic conclusions, industry consensus, or proof of broad adoption.

## Established concepts vs emerging discourse

Established project facts may be stated when supported by primary project documentation. Emerging practitioner terms such as "loop engineering" should be framed as useful vocabulary in current discourse, not as settled academic discipline unless stronger sources support that claim.

## Avoiding overclaiming

Do not claim that prompt engineering is dead. Do not claim that loop engineering has replaced prompt engineering. Do not claim industry-wide adoption, field consensus, or mature academic status without strong evidence.

## Evidence mapping location

Evidence mapping belongs in:

- `reports/editorial/`
- `reports/manuscript/`
- `docs/research/`
- `docs/appendices/`
- local source registry and editorial database

It does not belong in the main public chapter body.

## Never in public prose

Reader-facing chapter prose must not include: "Current evidence status", "Source/claim mapping", "Bullet X maps to", status labels such as `supported` or `weakly_supported`, source-quality labels such as quality A/B, editor notes, changelogs, editorial policy boilerplate, claim records, source tokens, or internal pipeline commentary.

## Preserving traceability

Traceability is preserved by generating chapter packets and evidence maps alongside the manuscript. The manuscript cites sources normally; the reports retain the claim/source mapping needed for auditability.
