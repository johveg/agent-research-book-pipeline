# 1. The Agent Loop

The central pattern is a closed loop: goal, context, action, verification, saved state, report, retry, and escalation.

## Current evidence status

The following points are synthesized only from claim records whose status allows Author use:

- Hermes Agent is a Nous Research open-source agent project presented as an agent that grows with the user and supports tool-using automation workflows. [1] [2] [3] (status `supported`, strong evidence)
- Loop engineering is best treated here as designing the harness around an agent: triggers, goals, context, tools, checks, state, reports, retries, and escalation. [4] [5] [6] (status `supported`, moderate evidence)
- A useful loop-engineering chapter can therefore focus on loop boundaries, observability, evaluation, and safe handoff instead of claiming that prompts have disappeared. [7] [6] (status `supported`, moderate evidence)
- An agentic loop can be framed as a repeated AI-agent cycle with a trigger, a goal, actions, feedback, and verification rather than as a single prompt-response exchange. [7] [6] (status `supported`, moderate evidence)
- Current evidence suggests: Several June 2026 public articles describe a shift from prompt engineering toward loop engineering, but the book should present that as an emerging discourse rather than a settled industry transition. [4] [7] [6] [8] (status `weakly_supported`, moderate evidence)
- Current evidence suggests: Current loop-engineering commentary often contrasts one-off prompting with systems that repeatedly plan, execute, evaluate, and adjust work. [4] [5] [6] (status `weakly_supported`, moderate evidence)
- Current evidence suggests: For production use, the available loop-engineering material points toward operational concerns: checks, monitoring, repeated execution, and explicit boundaries around autonomous work. [4] [6] [8] (status `weakly_supported`, moderate evidence)
- Current evidence suggests: The present source set supports only a cautious connection between agent loops and context or memory architecture; stronger technical treatment needs better primary sources. [1] [9] (status `weakly_supported`, weak evidence)

## Source/claim mapping

Every factual bullet above is generated from an Author-usable claim record and structured citation tokens. The public page does not expose internal claim/source IDs; traceability remains in the local source registry and editorial database.

- Bullet 1 maps to supported claim: “Hermes Agent is a Nous Research open-source agent project presented as an agent that grows with the user and supports tool-using automation workflows.”; source tokens: [1] [2] [3].
- Bullet 2 maps to supported claim: “Loop engineering is best treated here as designing the harness around an agent: triggers, goals, context, tools, checks, state, reports, retries, and escalation.”; source tokens: [4] [5] [6].
- Bullet 3 maps to supported claim: “A useful loop-engineering chapter can therefore focus on loop boundaries, observability, evaluation, and safe handoff instead of claiming that prompts have disappeared.”; source tokens: [7] [6].
- Bullet 4 maps to supported claim: “An agentic loop can be framed as a repeated AI-agent cycle with a trigger, a goal, actions, feedback, and verification rather than as a single prompt-response exchange.”; source tokens: [7] [6].
- Bullet 5 maps to caveated weak claim: “Several June 2026 public articles describe a shift from prompt engineering toward loop engineering, but the book should present that as an emerging discourse rather than a settled industry transition.”; source tokens: [4] [7] [6] [8].
- Bullet 6 maps to caveated weak claim: “Current loop-engineering commentary often contrasts one-off prompting with systems that repeatedly plan, execute, evaluate, and adjust work.”; source tokens: [4] [5] [6].
- Bullet 7 maps to caveated weak claim: “For production use, the available loop-engineering material points toward operational concerns: checks, monitoring, repeated execution, and explicit boundaries around autonomous work.”; source tokens: [4] [6] [8].
- Bullet 8 maps to caveated weak claim: “The present source set supports only a cautious connection between agent loops and context or memory architecture; stronger technical treatment needs better primary sources.”; source tokens: [1] [9].

## Editor notes

Generated Author output requires Editor approval before publication as narrative prose. Weak claims remain explicitly caveated. LinkedIn/social captures are discovery signals only and are not treated as independent confirmation unless stronger non-social sources support the same claim.

## Changelog

- 2026-06-26T21:23:29Z: conservative evidence-status regeneration for run context.

## Editorial policy

Last generated: 2026-06-26T21:23:29Z. This chapter is not synthesized directly from raw LinkedIn/social/web captures; it only uses claim records from `docs/research/claims.md`, and social material remains discovery signal only.

## References

[1] “hermes-agent — Hermes Agent Core & Official | Hermes Atlas”, hermesatlas.com, 2026-06-11T17:33:13Z, https://hermesatlas.com/projects/NousResearch/hermes-agent, quality A.
[2] “GitHub - NousResearch/hermes-agent: The agent that grows with you · GitHub”, github.com, 2026-06-12T01:10:01Z, https://github.com/nousresearch/hermes-agent, quality A.
[3] “hermes-agent/README.md at main · NousResearch/hermes-agent”, github.com, 2026-06-11T17:33:13Z, https://github.com/NousResearch/hermes-agent/blob/main/README.md, quality A.
[4] “Loop Engineering Playbook. Where loops live, how to run your first… | by Cobus Greyling | Jun, 2026 | Medium”, cobusgreyling.medium.com, 2026-06-11T17:33:36Z, https://cobusgreyling.medium.com/loop-engineering-playbook-4460e01e88d8, quality B.
[5] “Loop Engineering Playbook”, cobusgreyling.substack.com, 2026-06-11T17:33:36Z, https://cobusgreyling.substack.com/p/loop-engineering-playbook, quality B.
[6] “Agentic Loops: From ReAct to Loop Engineering (2026 Guide)”, datasciencedojo.com, 2026-06-11T17:33:28Z, https://datasciencedojo.com/blog/agentic-loops-explained-from-react-to-loop-engineering-2026-guide/, quality B.
[7] “Loop Engineering Explained Visually - by The Cloud Girl”, priyankavergadia.substack.com, 2026-06-11T17:33:28Z, https://priyankavergadia.substack.com/p/agent-loop-and-fleet-explained-visually, quality B.
[8] “From Prompt Engineering to Loop Engineering: Why the Agent Era Demands a New Security Paradigm | by Filip Verloy | Jun, 2026 | Medium”, medium.com, 2026-06-11T17:33:28Z, https://medium.com/@filipv_74515/from-prompt-engineering-to-loop-engineering-why-the-agent-era-demands-a-new-security-paradigm-816385040e3d, quality B.
[9] “How to Set Up GBrain: A Simple Tutorial for AI Agent Memory”, www.teknoding.com, 2026-06-11T17:33:21Z, https://www.teknoding.com/2026/06/how-to-set-up-gbrain-simple-tutorial.html, quality B.
