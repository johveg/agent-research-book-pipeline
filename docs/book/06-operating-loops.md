# 6. Operating Loops in Production

Production loops need manifests, verification, state files, safe retries, non-destructive watchdogs, and human escalation boundaries.

## Current evidence status

The following points are synthesized only from claim records whose status allows Author use:

- Loop engineering is best treated here as designing the harness around an agent: triggers, goals, context, tools, checks, state, reports, retries, and escalation. [1] [2] [3] (status `supported`, moderate evidence)
- OpenClaw is represented in the existing source registry by its public GitHub repository, whose captured title describes it as a personal AI assistant for multiple operating systems and platforms. [4] [5] (status `supported`, moderate evidence)
- A useful loop-engineering chapter can therefore focus on loop boundaries, observability, evaluation, and safe handoff instead of claiming that prompts have disappeared. [6] [3] (status `supported`, moderate evidence)
- An agentic loop can be framed as a repeated AI-agent cycle with a trigger, a goal, actions, feedback, and verification rather than as a single prompt-response exchange. [6] [3] (status `supported`, moderate evidence)
- Current evidence suggests: Several June 2026 public articles describe a shift from prompt engineering toward loop engineering, but the book should present that as an emerging discourse rather than a settled industry transition. [1] [6] [3] [7] (status `weakly_supported`, moderate evidence)
- Current evidence suggests: Current loop-engineering commentary often contrasts one-off prompting with systems that repeatedly plan, execute, evaluate, and adjust work. [1] [2] [3] (status `weakly_supported`, moderate evidence)
- Current evidence suggests: For production use, the available loop-engineering material points toward operational concerns: checks, monitoring, repeated execution, and explicit boundaries around autonomous work. [1] [3] [7] (status `weakly_supported`, moderate evidence)
- Current evidence suggests: The present source set supports only a cautious connection between agent loops and context or memory architecture; stronger technical treatment needs better primary sources. [8] [9] (status `weakly_supported`, weak evidence)

## Source/claim mapping

Every factual bullet above is generated with structured citation tokens and must resolve to numbered references before publication. If any token cannot resolve to canonical source metadata, the chapter remains in not-ready status.

## Editor notes

Generated Author output requires Editor approval before publication as narrative prose. Weak claims remain explicitly caveated.

## Changelog

- 2026-06-12T13:27:24Z: conservative evidence-status regeneration for run context.

## Editorial policy

Last generated: 2026-06-12T13:27:24Z. This chapter is not synthesized directly from raw LinkedIn/web captures; it only uses claim records from `docs/research/claims.md`.

## References

[1] “Loop Engineering Playbook. Where loops live, how to run your first… | by Cobus Greyling | Jun, 2026 | Medium”, cobusgreyling.medium.com, 2026-06-11T17:33:36Z, https://cobusgreyling.medium.com/loop-engineering-playbook-4460e01e88d8, quality B.
[2] “Loop Engineering Playbook”, cobusgreyling.substack.com, 2026-06-11T17:33:36Z, https://cobusgreyling.substack.com/p/loop-engineering-playbook, quality B.
[3] “Agentic Loops: From ReAct to Loop Engineering (2026 Guide)”, datasciencedojo.com, 2026-06-11T17:33:28Z, https://datasciencedojo.com/blog/agentic-loops-explained-from-react-to-loop-engineering-2026-guide/, quality B.
[4] “GitHub - openclaw/openclaw: Your own personal AI assistant. Any OS. Any Platform. The lobster way. 🦞”, github.com, 2026-06-11T17:33:21Z, https://github.com/openclaw/openclaw, quality A.
[5] “GitHub - openclaw/openclaw: Your own personal AI assistant. Any OS. Any Platform. The lobster way. 🦞”, github.com, 2026-06-12T01:10:27Z, https://github.com/openclaw/openclaw, quality A.
[6] “Loop Engineering Explained Visually - by The Cloud Girl”, priyankavergadia.substack.com, 2026-06-11T17:33:28Z, https://priyankavergadia.substack.com/p/agent-loop-and-fleet-explained-visually, quality B.
[7] “From Prompt Engineering to Loop Engineering: Why the Agent Era Demands a New Security Paradigm | by Filip Verloy | Jun, 2026 | Medium”, medium.com, 2026-06-11T17:33:28Z, https://medium.com/@filipv_74515/from-prompt-engineering-to-loop-engineering-why-the-agent-era-demands-a-new-security-paradigm-816385040e3d, quality B.
[8] “hermes-agent — Hermes Agent Core & Official | Hermes Atlas”, hermesatlas.com, 2026-06-11T17:33:13Z, https://hermesatlas.com/projects/NousResearch/hermes-agent, quality A.
[9] “How to Set Up GBrain: A Simple Tutorial for AI Agent Memory”, www.teknoding.com, 2026-06-11T17:33:21Z, https://www.teknoding.com/2026/06/how-to-set-up-gbrain-simple-tutorial.html, quality B.
