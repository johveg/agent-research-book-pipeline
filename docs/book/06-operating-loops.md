# 6. Operating Loops in Production

A production agent loop is not just an agent that keeps running. It is a controlled workflow with explicit inputs, permissions, state, checks, reports, and stopping rules.

This chapter applies the book’s core editorial lesson to operations: automation must be useful enough to run, but restrained enough to block itself.

## The problem

Once an agent loop touches real systems, failure changes shape. The problem is no longer only whether the model produced a good sentence. The loop may collect weak sources, update files, send messages, commit changes, or publish a site. A small error can be repeated every day until it looks normal.

That is why production loops need evidence gates, privacy checks, build verification, and human escalation. A loop that cannot stop should not publish.

## The concept

A production loop needs at least these controls:

- **Manifest**: what the loop is allowed to do.
- **Input boundary**: which sources and files it may read.
- **Action boundary**: which tools it may call and which writes are allowed.
- **State file or database**: what it records between runs.
- **Verification**: tests, builds, schema checks, and report checks.
- **Publication gate**: the step that decides whether output can be made public.
- **Escalation rule**: the conditions that require human review.

In a living research book, those controls map directly to editorial roles. The Curator separates signal from noise. The Editor checks claims, quality, privacy, and contradictions. The Author writes only from approved or caveated material. The Book role verifies structure and publication safety.

## What the evidence shows

The stored source base supports the idea that agent work is moving toward repeated workflows and designed loops, but much of the public language remains early and uneven (`src_384bcc1123ee303676b1`, `src_80c8c50e6406c7e7fc95`, `src_e0864997d036665b77f9`). Social/search-result claims that agents can find work, execute, evaluate, and repeat without constant supervision are weak and must be caveated (`claim_5fe426bc9f841da6446c`, `claim_2311b109d80f8a43b0ec`).

The operational lesson is more reliable than the hype: if a loop can repeat, it needs controls that repeat with it.

## What this means in practice

A production loop should produce different kinds of output depending on evidence quality:

- If evidence is strong and reviewed, it may support chapter movement.
- If evidence is weak but useful, it may support a status report or open question.
- If capture is blocked, polluted, or login-broken, it should publish only a safe operational note.
- If privacy or credential uncertainty appears, it should escalate and stop publication.
- If the build fails, it should not publish the book.

This is why “no chapter update” is a valid production result. Publishing nothing can be the correct output of a healthy loop.

## Risks and limits

Production loops can hide bad judgment behind clean automation. A script can exit zero while producing a poor research state. A report can be syntactically valid while overstating weak evidence. A generated chapter can be readable while lacking source/claim mapping.

The do-not-publish rule exists to counter that failure mode. The final authority should come from evidence and review, not from the fact that automation ran.

## Source notes

- Technical loop-engineering context: `src_384bcc1123ee303676b1`, `src_80c8c50e6406c7e7fc95`, `src_e0864997d036665b77f9`, `src_3eb174da3717ef674f19`.
- Weak claims about autonomous repeat-and-evaluate loops: `claim_5fe426bc9f841da6446c`, `claim_2311b109d80f8a43b0ec`, `claim_65d6fb05d553a471fdf3`.
- Operational publication rules: `docs/operations/instructions/do-not-publish.md`, `docs/operations/instructions/acceptance-criteria.md`, `docs/operations/instructions/content-pipeline.md`.

## Source/claim mapping

- Claim that production loops require manifests, verification, state, safe retries, and escalation: supported by the project’s operational instruction set and by loop-engineering sources `src_384bcc1123ee303676b1`, `src_80c8c50e6406c7e7fc95`.
- Claim that claims about unattended repeat/evaluate behavior are weak and require caveats: `claim_5fe426bc9f841da6446c`, `claim_2311b109d80f8a43b0ec`.
- Claim that blocked publication can still publish safe reports: `docs/operations/instructions/do-not-publish.md`.

## Weak claims used

- Claims about agents repeating without constant supervision are used only to motivate operational questions, not to claim that such operation is generally safe.

## Unsupported claims removed or avoided

- No claim is made that production agent loops are safe by default.
- No claim is made that a clean script exit proves a good research state.
- No claim is made that automation should override editorial vetoes.

## Editor notes

This chapter now turns weak loop claims into an operational safety argument and keeps publication restraint central.

## Changelog

- Replaced generated weak-claim bullets with production-focused prose.
- Added explicit production controls and do-not-publish behavior.
- Added source/claim mapping, weak-claim caveats, editor notes, and changelog.
