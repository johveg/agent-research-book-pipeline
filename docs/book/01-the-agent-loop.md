# 1. The Agent Loop

An agent loop is a managed cycle of work. A human or system gives an agent a goal; the agent gathers context, chooses an action, uses tools, checks the result, records state, reports what happened, and either stops, retries, or escalates.

That cycle matters more than any single prompt. A prompt is an instruction. A loop is an operating pattern.

## The problem

The stored source base repeatedly points to the same practical tension: people want agents to do longer-running work, but longer-running work creates new risks. A one-off answer can be inspected after the fact. A loop can change files, send messages, schedule jobs, collect data, and publish reports. That makes verification, state, and escalation part of the system design.

The current evidence is strongest where it comes from project artifacts and technical articles. It is weakest where it comes from social/search-result fragments. This chapter therefore treats social claims about “everyone talking about loop engineering” as attention signals only (`claim_1e6da5e353cab67ed16c`, `claim_78b5de70d95c32a72222`).

## The concept

A useful loop has at least seven parts:

1. **Goal**: what the agent is trying to accomplish.
2. **Context**: source material, files, memory, tools, constraints, and prior state.
3. **Action**: the tool call, code edit, search, extraction, report, or message.
4. **Verification**: checks that prove whether the action worked.
5. **State**: what is saved so the next step does not start blind.
6. **Decision**: continue, retry, stop, or escalate.
7. **Report**: a human-readable explanation of what changed and what remains uncertain.

This is why a living research book needs an editorial loop rather than just a collector. Collection expands the source base. The editorial loop decides whether that source base is coherent, traceable, safe, and useful.

## What the evidence shows

The stored sources show an emerging vocabulary around loops, agent workflows, memory, and tool-using agents. Technical articles describe loop engineering as a move from manual prompt-by-prompt operation toward designed workflows (`src_384bcc1123ee303676b1`, `src_80c8c50e6406c7e7fc95`, `src_e0864997d036665b77f9`). Social/search-result captures echo that theme, but they are weak evidence and are not used here as proof of adoption (`claim_99a44d43b86eaa5907ba`, `claim_ddcb28eb301b363c351a`).

The reliable takeaway is not that a new industry category has already formed. The reliable takeaway is narrower: agent work is being discussed less as isolated prompting and more as systems of repeated action, evaluation, and recovery.

## What this means in practice

A practical agent loop should make failure visible. If the agent cannot verify an action, it should not pretend success. If the source base is too weak, it should publish a status report rather than a chapter update. If a step touches privacy, credentials, destructive cleanup, or unclear legal material, it should escalate to a human.

For this book, that means:

- daily jobs may collect, classify, and report;
- editorial gates decide whether evidence is strong enough for chapter movement;
- Author output must include source/claim mapping;
- Book-role publication must block unsafe or unsupported content.

## Risks and limits

Loops can create authority by repetition. A daily job that repeatedly publishes weak claims can make them look more solid than they are. That is why repeated social posts are not independent confirmation, and why the book separates source indexes, editor reports, and narrative chapters.

The risk is not only technical failure. It is editorial drift: a pile of plausible paragraphs with no review trail.

## Source notes

- Technical context for loop engineering and agent loops: `src_384bcc1123ee303676b1`, `src_80c8c50e6406c7e7fc95`, `src_e0864997d036665b77f9`.
- Weak social/search-result signals about the term: `claim_1e6da5e353cab67ed16c`, `claim_78b5de70d95c32a72222`, `claim_99a44d43b86eaa5907ba`, `claim_ddcb28eb301b363c351a`.

## Source/claim mapping

- Claim that loop discussions are shifting attention from one-off prompts toward designed workflows: `src_384bcc1123ee303676b1`, `src_80c8c50e6406c7e7fc95`, `src_e0864997d036665b77f9`, with weak signal support from `claim_99a44d43b86eaa5907ba`.
- Claim that social attention exists but is not proof of maturity: `claim_1e6da5e353cab67ed16c`, `claim_78b5de70d95c32a72222`.

## Weak claims used

- Social claims about “everyone” discussing loop engineering are used only as weak signals of attention.

## Unsupported claims removed or avoided

- No claim is made that loop engineering has replaced prompt engineering as an industry fact.
- No claim is made that autonomous loops are safe without verification.

## Editor notes

This chapter is now explanatory rather than a dump of weak claims. It preserves the evidence trail and keeps weak social material in a caveated role.

## Changelog

- Replaced generated weak-claim bullets with chapter prose.
- Added source notes, source/claim mapping, weak-claim caveats, editor notes, and changelog.
