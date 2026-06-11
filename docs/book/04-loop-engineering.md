# 4. Loop Engineering

Loop engineering is an emerging term for designing the system around an agent’s repeated work: context gathering, action, verification, retry, repair, state, reporting, and escalation. It should be presented as an emerging concept, not as a settled industry standard.

## The problem

Prompt engineering focuses on getting a useful answer from a model. Agent work creates a different problem: how to make repeated model/tool actions useful over time without losing visibility or control.

A coding agent, research agent, or operations agent may need to do more than answer once. It may need to inspect files, change code, run tests, retry failed steps, collect sources, update reports, and stop when evidence is too weak. That is a loop-design problem.

## The concept

The stored material describes loop engineering as a move from manually prompting an agent step by step toward designing the loop that prompts, checks, and routes the agent’s work. Stronger support comes from technical explainers and practitioner articles (`src_384bcc1123ee303676b1`, `src_80c8c50e6406c7e7fc95`, `src_e0864997d036665b77f9`, `src_3eb174da3717ef674f19`).

The concept overlaps with older automation ideas: cron jobs, workflow engines, feedback loops, test runners, monitors, and human escalation. The useful question is not whether every part is new. The useful question is what changes when the worker inside the loop is a language-model agent that can interpret, plan, write, and use tools.

## What the evidence shows

The evidence supports a cautious description:

- There is active technical writing about agent loops and loop engineering (`src_80c8c50e6406c7e7fc95`, `src_384bcc1123ee303676b1`).
- Several sources frame the shift as moving beyond one-off prompting toward designed workflows (`src_e0864997d036665b77f9`, `src_3eb174da3717ef674f19`, `src_4f618fedc4cf90a6561e`).
- Social/search-result material shows attention and repetition around the term, but remains weak signal rather than proof of adoption (`claim_1e6da5e353cab67ed16c`, `claim_78b5de70d95c32a72222`, `claim_44553080825a09530959`).

The evidence does not yet show that loop engineering is a formal discipline with stable definitions, standards, or broad organizational maturity.

## How it differs from prompt engineering

Prompt engineering asks: “What instruction should I give the model now?”

Loop engineering asks:

- What context should the agent receive each cycle?
- What tools may it use?
- What proves the result worked?
- What state should persist?
- When should it retry?
- When should it stop?
- When should it ask a human?
- What should be published, and what should be withheld?

This difference is practical. A good prompt can still produce bad automation if the loop has no verification or escalation.

## What this means in practice

A loop should be observable and recoverable. It should produce logs or reports that a human can understand. It should distinguish between collecting data, interpreting it, writing prose, and publishing content. It should be able to block itself.

In this book’s workflow, that means daily collection can update source indexes and editor reports, but chapter prose should move only when evidence and review justify it. The do-not-publish rule is not a side constraint; it is part of the loop.

## Risks and limits

The phrase “loop engineering” may settle, change meaning, or fade. Some uses are careful; others are promotional. The book should track the term without depending on the term. The underlying operating problem remains: tool-using agents need designed feedback, state, verification, and escalation.

## Source notes

- Technical and practitioner sources: `src_384bcc1123ee303676b1`, `src_80c8c50e6406c7e7fc95`, `src_e0864997d036665b77f9`, `src_3eb174da3717ef674f19`, `src_4f618fedc4cf90a6561e`.
- Weak public-attention signals: `claim_1e6da5e353cab67ed16c`, `claim_78b5de70d95c32a72222`, `claim_44553080825a09530959`, `claim_99a44d43b86eaa5907ba`.

## Source/claim mapping

- Loop engineering as designed agent workflow rather than one-off prompting: `src_384bcc1123ee303676b1`, `src_80c8c50e6406c7e7fc95`, `src_e0864997d036665b77f9`, `src_3eb174da3717ef674f19`.
- Public attention around the term, caveated as weak signal: `claim_1e6da5e353cab67ed16c`, `claim_78b5de70d95c32a72222`, `claim_44553080825a09530959`.
- Need to avoid treating social repetition as adoption proof: source quality rules in `docs/operations/instructions/source-quality.md` and weak-source claims above.

## Weak claims used

- Claims that loop engineering is suddenly being discussed are used only as evidence of attention.
- Claims that it has “replaced” prompt engineering are treated as weak and overstated unless stronger evidence is added.

## Unsupported claims removed or avoided

- No claim is made that loop engineering is an industry standard.
- No claim is made that all organizations are adopting it.
- No claim is made that unattended agents are generally safe.

## Editor notes

This chapter follows the supplied brief for “What is Loop Engineering?” and uses the stored material conservatively.

## Changelog

- Replaced generated weak-claim list with a structured chapter.
- Added distinction between prompt engineering and loop engineering.
- Added explicit source/claim mapping, weak-claim caveats, editor notes, and changelog.
