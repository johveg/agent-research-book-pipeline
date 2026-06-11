# 5. Context and Memory Architecture

Agent loops depend on context. A loop that cannot remember what it did, what it learned, or what it must avoid will keep repeating work and may publish stale or unsafe conclusions. A loop that remembers too much, or remembers the wrong things, can also create privacy and authority problems.

This chapter treats memory as an operating design problem, not as a magic feature.

## The problem

A human can notice when a source is weak, when a task was already done, or when a repeated claim is only social noise. An agent loop needs explicit structures for the same discipline: source records, claim records, entity summaries, editorial reviews, role boundaries, and publication gates.

The stored material includes claims and sources around agent memory, Hermes usage, and OpenClaw/Hermes comparisons. Much of that material is weak social/search-result evidence, so it is useful for identifying questions but not for proving broad technical conclusions (`claim_5b23137f3adf9f377009`, `claim_b21a2d3bdc8f81b12220`).

## The concept

A useful memory architecture separates several kinds of state:

- **Source memory**: what was captured, when, from where, and with what quality score.
- **Claim memory**: what the system believes may be true, with status, source IDs, and caveats.
- **Entity memory**: stable summaries of people, projects, tools, and organizations.
- **Workflow memory**: what jobs ran, what failed, and what is pending.
- **Publication memory**: what was approved, rejected, blocked, or escalated.

Mixing these together creates risk. A raw capture is not a claim. A claim is not a chapter fact. A chapter fact is not publishable until it has passed review.

## What the evidence shows

The stored sources support a general pattern: agent systems are being discussed alongside memory, workflow, and tool-use concerns. Stronger sources describe projects or documentation; weaker sources describe public reactions or fragments.

The reliable editorial conclusion is narrow: memory is necessary for durable agent work, but memory must be governed. The source base does not justify broad claims that any particular agent-memory approach is complete, safe, or generally adopted.

## What this means in practice

For this living research book, context and memory architecture should do three things.

First, it should prevent repeated collection from becoming repeated publication. Daily capture can add sources and weak signals, but it should not automatically rewrite chapters.

Second, it should preserve traceability. If a paragraph states a factual point, the reader should be able to see which source or claim ID supports it.

Third, it should protect the human and the project. Credentials, raw browser state, private logs, and unnecessary personal data are not book material. They should not be staged, published, or summarized into narrative prose.

## Risks and limits

Memory can make weak evidence look stronger than it is. A weak claim seen ten times in similar social posts is still weak if all ten posts are repeating the same idea without independent support. The Curator function must separate repeated signals from stronger evidence.

Memory can also preserve mistakes. That is why claims need statuses, contradictions need review, and publication must remain blockable.

## Source notes

- Hermes project/documentation context for operational agent work: `src_946462d4856d38e27d2c`, `src_5de659c63abf9db0dff3`, `src_45d026189270d1762fad`.
- OpenClaw project context: `src_b364e090655731640be0`.
- Weak memory-related public signals: `claim_5b23137f3adf9f377009`, `claim_b21a2d3bdc8f81b12220`.

## Source/claim mapping

- Claim that durable agent work needs explicit source, claim, entity, workflow, and publication state: supported by the project workflow implemented in this repository and by the Hermes/project context sources `src_946462d4856d38e27d2c`, `src_5de659c63abf9db0dff3`.
- Claim that public memory-related mentions are weak signals only: `claim_5b23137f3adf9f377009`, `claim_b21a2d3bdc8f81b12220`.
- Claim that raw captures must not become chapter facts directly: operational rules in `docs/operations/instructions/content-pipeline.md`, `docs/operations/instructions/acceptance-criteria.md`, and `docs/operations/instructions/do-not-publish.md`.

## Weak claims used

- Social/search-result claims about specific memory tools or agent-memory reactions are used only as prompts for further review.

## Unsupported claims removed or avoided

- No claim is made that a specific memory implementation is best.
- No claim is made that repeated mentions prove adoption.
- No claim is made that memory makes autonomous work safe by itself.

## Editor notes

This chapter now explains the architecture needed by the book workflow itself and avoids unsupported claims about external memory systems.

## Changelog

- Replaced placeholder-style text with a conservative chapter.
- Added source/claim mapping, weak-claim caveats, editor notes, and changelog.
