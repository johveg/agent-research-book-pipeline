# Open Questions

This page records unresolved questions that the current evidence base cannot yet answer safely. It is part of the book, not a backlog dump: an open question is published when restraint is more accurate than a forced conclusion.

## Why open questions matter

The source base contains a mix of official project material, technical articles, secondary commentary, social/search-result fragments, and noisy captures. Some material is useful because it points to a topic. Less material is strong enough to support a chapter fact.

Open questions prevent weak evidence from being laundered into authority.

## Current open questions

### 1. Is “loop engineering” becoming a stable discipline or only a temporary label?

The stored material shows active discussion around loop engineering in technical writing and public commentary (`src_384bcc1123ee303676b1`, `src_80c8c50e6406c7e7fc95`, `src_e0864997d036665b77f9`). It also includes weak claims that “everyone” is suddenly talking about it or that it has replaced prompt engineering (`claim_1e6da5e353cab67ed16c`, `claim_44553080825a09530959`).

The question remains open because attention is not the same as adoption, and repeated phrasing is not the same as independent evidence.

### 2. Which parts of loop engineering are genuinely new?

Loops, feedback, test runners, monitors, workflow engines, and escalation paths are not new. What may be new is the combination of those patterns with language-model agents that can interpret context, use tools, write code or prose, and recover from some failures.

The book should keep asking which claims describe a new practice and which claims relabel older automation patterns.

### 3. How should Hermes and OpenClaw be compared fairly?

The source base includes direct project evidence for Hermes and OpenClaw (`src_946462d4856d38e27d2c`, `src_b364e090655731640be0`) plus secondary comparison material (`src_8e7b3cdb70416086cc19`, `src_3910909dbbac56313a11`). It also contains weak public claims and reactions.

A fair comparison would need a stable evaluation frame: supported platforms, installation path, tool model, memory model, safety controls, scheduling, integrations, observability, and operational cost. The current book should not rank the projects until those criteria are reviewed against stronger sources.

### 4. What evidence is enough to move from source index to chapter claim?

The current workflow has claim statuses, source quality scoring, chapter briefs, editorial reports, and do-not-publish rules. The open question is how strict the promotion threshold should be for an emerging topic where many signals come from social platforms or early practitioner posts.

A conservative v1 answer is already in force: weak signals may explain why a topic is watched, but they should not become uncaveated chapter facts.

### 5. What makes a production agent loop safe enough to run unattended?

The book can describe necessary controls: manifests, state, verification, retry rules, privacy review, publication gates, and escalation. It cannot yet claim that these controls are sufficient for all production contexts.

More evidence is needed from real deployments, failure reports, security reviews, and operational postmortems.

## What should be collected next

- Primary documentation or repositories for loop-engineering tools and frameworks.
- Independent technical articles that define loop structure, failure handling, and verification.
- Case studies with concrete outcomes, not only claims of productivity.
- Security or privacy analyses of long-running agent loops.
- Clear examples of failed loops and how teams recovered.
- More reliable Hermes/OpenClaw comparison material using explicit criteria.

## What should not be promoted yet

- Social repetition as proof of adoption.
- “Prompt engineering is dead” as a factual conclusion.
- Claims that autonomous agents can safely run without human review.
- Claims that any one assistant framework is superior without a reviewed comparison method.
- Noisy trend terms dominated by platform boilerplate.

## Source notes

- Stronger loop-engineering sources: `src_384bcc1123ee303676b1`, `src_80c8c50e6406c7e7fc95`, `src_e0864997d036665b77f9`, `src_3eb174da3717ef674f19`.
- Weak attention claims: `claim_1e6da5e353cab67ed16c`, `claim_44553080825a09530959`, `claim_78b5de70d95c32a72222`.
- Hermes/OpenClaw project and comparison sources: `src_946462d4856d38e27d2c`, `src_b364e090655731640be0`, `src_8e7b3cdb70416086cc19`, `src_3910909dbbac56313a11`.

## Source/claim mapping

- Claim that loop engineering needs more evidence before being treated as settled: `src_384bcc1123ee303676b1`, `src_80c8c50e6406c7e7fc95`, plus weak attention claims `claim_1e6da5e353cab67ed16c`, `claim_44553080825a09530959`.
- Claim that Hermes/OpenClaw comparison remains open: `src_946462d4856d38e27d2c`, `src_b364e090655731640be0`, `src_8e7b3cdb70416086cc19`, `src_3910909dbbac56313a11`.
- Claim that production safety remains unresolved: operational rules in `docs/operations/instructions/do-not-publish.md` and `docs/operations/instructions/acceptance-criteria.md`.

## Weak claims used

- Weak social/search-result claims are used only to identify topics that need review.

## Unsupported claims removed or avoided

- No open question is answered by popularity alone.
- No weak signal is promoted to a settled chapter conclusion.
- No comparison claim is accepted without criteria.

## Editor notes

This page now functions as a controlled uncertainty register for the book. It keeps unresolved issues visible without turning them into unsupported claims.

## Changelog

- Replaced minimal weak-claim page with structured open questions.
- Added source/claim mapping, weak-claim caveats, editor notes, and changelog.
