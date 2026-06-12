# Author readiness audit — 20260612-1255 UTC

## Summary

The site is now publication-safe, but the generated chapters are intentionally conservative. The current book pages mostly say that no publishable chapter update is recommended because the eligible claim table is dominated by weak LinkedIn/search-result or human-review material. A proper narrative book requires promoting existing canonical sources into supported claims, then drafting chapters from those claims with numbered citations.

## Preface

- File: `docs/book/preface.md`
- Current status: **not-ready because too thin**
- Word count: 153
- Reader-facing citations: 0
- Can improve using existing registry sources: yes
- New research required: probably
- Missing source types needed: stable thesis and chapter evidence map.
- Strongest publishable sources currently available:
  - `src_2931d4430c4d9716fe8f` — GitHub - conorbronsdon/avoid-ai-writing: Skill that audits and rewrites content to remove AI writing patterns. Use it with your favorite agents including Claude Code, OpenClaw, and Hermes. · GitHub; github.com; quality `A`; type `web`; URL: https://github.com/conorbronsdon/avoid-ai-writing
  - `src_40b2cf3bcc17ee3a1a13` — r/GrapheneOS on Reddit: Je viens d'obtenir un Google Pixel 9 pro XL; www.reddit.com; quality `A`; type `web`; URL: https://www.reddit.com/r/GrapheneOS/comments/1u20n5e/just_got_a_google_pixel_9_pro_xl/?tl=fr
  - `src_45d026189270d1762fad` — hermes-agent — Hermes Agent Core & Official | Hermes Atlas; hermesatlas.com; quality `A`; type `web`; URL: https://hermesatlas.com/projects/NousResearch/hermes-agent
  - `src_5de659c63abf9db0dff3` — Run Nemotron 3 Ultra free in Hermes Agent | Hermes Agent; hermes-agent.nousresearch.com; quality `A`; type `web`; URL: https://hermes-agent.nousresearch.com/docs/guides/run-nemotron-3-ultra-free
  - `src_8408c6be5aaeee529e47` — GitHub - NousResearch/hermes-agent: The agent that grows with you · GitHub; www.google.com; quality `A`; type `web`; URL: https://www.google.com/goto?url=CAESZAHuR6pNXgeGMwUIOcy41wHF8HvrFBiJJ-tIysSkNPdU3K6pONT7xshWFfMorAlVGnDAg2wzArl3EsP8LeHytq5xUUhPDUqpYDvNEQ-akGfMvqk1Ix6T-eT27cO95Ei53u2f4eE%3D
- Recommended next action: Write the preface after at least chapters 1, 2, and 4 have supported claim sets.

## 1. The Agent Loop

- File: `docs/book/01-the-agent-loop.md`
- Current status: **not-ready because too thin**
- Word count: 152
- Reader-facing citations: 0
- Can improve using existing registry sources: yes
- New research required: yes
- Missing source types needed: foundational papers/docs and explicit claim records tied to loop mechanics.
- Strongest publishable sources currently available:
  - `src_384bcc1123ee303676b1` — Loop Engineering Playbook. Where loops live, how to run your first… | by Cobus Greyling | Jun, 2026 | Medium; cobusgreyling.medium.com; quality `B`; type `web`; URL: https://cobusgreyling.medium.com/loop-engineering-playbook-4460e01e88d8
  - `src_3eb174da3717ef674f19` — Loop Engineering Explained Visually - by The Cloud Girl; priyankavergadia.substack.com; quality `B`; type `web`; URL: https://priyankavergadia.substack.com/p/agent-loop-and-fleet-explained-visually
  - `src_4cc70181e0ffcb4cb300` — Designing Loops - A Practitioner's Short Field Guide; interestingengineering.substack.com; quality `B`; type `web`; URL: https://interestingengineering.substack.com/p/designing-loops-a-practitioners-short
  - `src_5cc15e3db44d8eabf9b0` — Loop Engineering Playbook. Where loops live, how to run your first… | by Cobus Greyling | Jun, 2026 | Medium; cobusgreyling.medium.com; quality `B`; type `web`; URL: https://cobusgreyling.medium.com/loop-engineering-playbook-4460e01e88d8
  - `src_7387e00f4d0e7dbf7fee` — Loop Engineering Playbook; cobusgreyling.substack.com; quality `B`; type `web`; URL: https://cobusgreyling.substack.com/p/loop-engineering-playbook
- Recommended next action: Promote foundational ReAct/agent-loop/tool-use sources and write from the loop model rather than trend snippets.

## 2. Hermes

- File: `docs/book/02-hermes.md`
- Current status: **not-ready because too thin**
- Word count: 154
- Reader-facing citations: 0
- Can improve using existing registry sources: yes
- New research required: yes
- Missing source types needed: official product/docs sources and stable release/source-code evidence.
- Strongest publishable sources currently available:
  - `src_45d026189270d1762fad` — hermes-agent — Hermes Agent Core & Official | Hermes Atlas; hermesatlas.com; quality `A`; type `web`; URL: https://hermesatlas.com/projects/NousResearch/hermes-agent
  - `src_5de659c63abf9db0dff3` — Run Nemotron 3 Ultra free in Hermes Agent | Hermes Agent; hermes-agent.nousresearch.com; quality `A`; type `web`; URL: https://hermes-agent.nousresearch.com/docs/guides/run-nemotron-3-ultra-free
  - `src_8408c6be5aaeee529e47` — GitHub - NousResearch/hermes-agent: The agent that grows with you · GitHub; www.google.com; quality `A`; type `web`; URL: https://www.google.com/goto?url=CAESZAHuR6pNXgeGMwUIOcy41wHF8HvrFBiJJ-tIysSkNPdU3K6pONT7xshWFfMorAlVGnDAg2wzArl3EsP8LeHytq5xUUhPDUqpYDvNEQ-akGfMvqk1Ix6T-eT27cO95Ei53u2f4eE%3D
  - `src_8d4f3b9531fe6368478b` — GitHub - NousResearch/hermes-agent: The agent that grows with you · GitHub; github.com; quality `A`; type `web`; URL: https://github.com/nousresearch/hermes-agent
  - `src_946462d4856d38e27d2c` — hermes-agent/README.md at main · NousResearch/hermes-agent; github.com; quality `A`; type `web`; URL: https://github.com/NousResearch/hermes-agent/blob/main/README.md
- Recommended next action: Capture/promote official Hermes docs, release notes, repository README/issues, and Nous-authored material before writing.

## 3. OpenClaw

- File: `docs/book/03-openclaw.md`
- Current status: **not-ready because too thin**
- Word count: 146
- Reader-facing citations: 0
- Can improve using existing registry sources: yes
- New research required: yes
- Missing source types needed: official OpenClaw sources and non-social comparative evidence.
- Strongest publishable sources currently available:
  - `src_2931d4430c4d9716fe8f` — GitHub - conorbronsdon/avoid-ai-writing: Skill that audits and rewrites content to remove AI writing patterns. Use it with your favorite agents including Claude Code, OpenClaw, and Hermes. · GitHub; github.com; quality `A`; type `web`; URL: https://github.com/conorbronsdon/avoid-ai-writing
  - `src_40b2cf3bcc17ee3a1a13` — r/GrapheneOS on Reddit: Je viens d'obtenir un Google Pixel 9 pro XL; www.reddit.com; quality `A`; type `web`; URL: https://www.reddit.com/r/GrapheneOS/comments/1u20n5e/just_got_a_google_pixel_9_pro_xl/?tl=fr
  - `src_89933e373b741e71c5c6` — GitHub - nesquena/hermes-webui: Hermes WebUI: The best way to use Hermes Agent from the web or from your phone! · GitHub; github.com; quality `A`; type `web`; URL: https://github.com/nesquena/hermes-webui
  - `src_b364e090655731640be0` — GitHub - openclaw/openclaw: Your own personal AI assistant. Any OS. Any Platform. The lobster way. 🦞; github.com; quality `A`; type `web`; URL: https://github.com/openclaw/openclaw
  - `src_c6b80c86cd5637ddd0b8` — Designing a New Personal AI Agent From Scratch, Not OpenClaw, Not Hermes: Fermix | by Sujeeth Shetty | Jun, 2026 | GoPenAI; blog.gopenai.com; quality `A`; type `web`; URL: https://blog.gopenai.com/designing-a-new-personal-ai-agent-from-scratch-not-openclaw-not-hermes-fermix-eae401a52e6f?gi=fc115768ff4e
- Recommended next action: Do fresh research for official OpenClaw repository/docs and reliable comparisons; block current social/comparison snippets.

## 4. Loop Engineering

- File: `docs/book/04-loop-engineering.md`
- Current status: **not-ready because too thin**
- Word count: 149
- Reader-facing citations: 0
- Can improve using existing registry sources: yes
- New research required: probably
- Missing source types needed: primary/technical sources and editor-approved claim records; current raw claims are mostly weak social/search snippets.
- Strongest publishable sources currently available:
  - `src_80c8c50e6406c7e7fc95` — Agentic Loops: From ReAct to Loop Engineering (2026 Guide); datasciencedojo.com; quality `B`; type `web`; URL: https://datasciencedojo.com/blog/agentic-loops-explained-from-react-to-loop-engineering-2026-guide/
  - `src_384bcc1123ee303676b1` — Loop Engineering Playbook. Where loops live, how to run your first… | by Cobus Greyling | Jun, 2026 | Medium; cobusgreyling.medium.com; quality `B`; type `web`; URL: https://cobusgreyling.medium.com/loop-engineering-playbook-4460e01e88d8
  - `src_3eb174da3717ef674f19` — Loop Engineering Explained Visually - by The Cloud Girl; priyankavergadia.substack.com; quality `B`; type `web`; URL: https://priyankavergadia.substack.com/p/agent-loop-and-fleet-explained-visually
  - `src_5cc15e3db44d8eabf9b0` — Loop Engineering Playbook. Where loops live, how to run your first… | by Cobus Greyling | Jun, 2026 | Medium; cobusgreyling.medium.com; quality `B`; type `web`; URL: https://cobusgreyling.medium.com/loop-engineering-playbook-4460e01e88d8
  - `src_7387e00f4d0e7dbf7fee` — Loop Engineering Playbook; cobusgreyling.substack.com; quality `B`; type `web`; URL: https://cobusgreyling.substack.com/p/loop-engineering-playbook
- Recommended next action: Promote the existing B-quality canonical loop-engineering articles into supported/caveated claims, then draft a real narrative chapter.

## 5. Context and Memory Architecture

- File: `docs/book/05-context-memory-architecture.md`
- Current status: **not-ready because too thin**
- Word count: 154
- Reader-facing citations: 0
- Can improve using existing registry sources: yes
- New research required: yes
- Missing source types needed: technical docs/papers and concrete implementation sources.
- Strongest publishable sources currently available:
  - `src_bebe03beb8a33c199ce8` — How to Set Up GBrain: A Simple Tutorial for AI Agent Memory; www.teknoding.com; quality `B`; type `web`; URL: https://www.teknoding.com/2026/06/how-to-set-up-gbrain-simple-tutorial.html
  - `src_2931d4430c4d9716fe8f` — GitHub - conorbronsdon/avoid-ai-writing: Skill that audits and rewrites content to remove AI writing patterns. Use it with your favorite agents including Claude Code, OpenClaw, and Hermes. · GitHub; github.com; quality `A`; type `web`; URL: https://github.com/conorbronsdon/avoid-ai-writing
  - `src_40b2cf3bcc17ee3a1a13` — r/GrapheneOS on Reddit: Je viens d'obtenir un Google Pixel 9 pro XL; www.reddit.com; quality `A`; type `web`; URL: https://www.reddit.com/r/GrapheneOS/comments/1u20n5e/just_got_a_google_pixel_9_pro_xl/?tl=fr
  - `src_45d026189270d1762fad` — hermes-agent — Hermes Agent Core & Official | Hermes Atlas; hermesatlas.com; quality `A`; type `web`; URL: https://hermesatlas.com/projects/NousResearch/hermes-agent
  - `src_5de659c63abf9db0dff3` — Run Nemotron 3 Ultra free in Hermes Agent | Hermes Agent; hermes-agent.nousresearch.com; quality `A`; type `web`; URL: https://hermes-agent.nousresearch.com/docs/guides/run-nemotron-3-ultra-free
- Recommended next action: Add/promo technical sources on context windows, memory systems, RAG, agent memory, and persistence architectures.

## 6. Operating Loops in Production

- File: `docs/book/06-operating-loops.md`
- Current status: **not-ready because too thin**
- Word count: 152
- Reader-facing citations: 0
- Can improve using existing registry sources: yes
- New research required: yes
- Missing source types needed: operations-grade sources, case studies, and safety/evaluation references.
- Strongest publishable sources currently available:
  - `src_2931d4430c4d9716fe8f` — GitHub - conorbronsdon/avoid-ai-writing: Skill that audits and rewrites content to remove AI writing patterns. Use it with your favorite agents including Claude Code, OpenClaw, and Hermes. · GitHub; github.com; quality `A`; type `web`; URL: https://github.com/conorbronsdon/avoid-ai-writing
  - `src_40b2cf3bcc17ee3a1a13` — r/GrapheneOS on Reddit: Je viens d'obtenir un Google Pixel 9 pro XL; www.reddit.com; quality `A`; type `web`; URL: https://www.reddit.com/r/GrapheneOS/comments/1u20n5e/just_got_a_google_pixel_9_pro_xl/?tl=fr
  - `src_45d026189270d1762fad` — hermes-agent — Hermes Agent Core & Official | Hermes Atlas; hermesatlas.com; quality `A`; type `web`; URL: https://hermesatlas.com/projects/NousResearch/hermes-agent
  - `src_5de659c63abf9db0dff3` — Run Nemotron 3 Ultra free in Hermes Agent | Hermes Agent; hermes-agent.nousresearch.com; quality `A`; type `web`; URL: https://hermes-agent.nousresearch.com/docs/guides/run-nemotron-3-ultra-free
  - `src_8408c6be5aaeee529e47` — GitHub - NousResearch/hermes-agent: The agent that grows with you · GitHub; www.google.com; quality `A`; type `web`; URL: https://www.google.com/goto?url=CAESZAHuR6pNXgeGMwUIOcy41wHF8HvrFBiJJ-tIysSkNPdU3K6pONT7xshWFfMorAlVGnDAg2wzArl3EsP8LeHytq5xUUhPDUqpYDvNEQ-akGfMvqk1Ix6T-eT27cO95Ei53u2f4eE%3D
- Recommended next action: Research production operations: guardrails, evals, observability, runbooks, CI/CD, escalation and governance for agent loops.

## Open Questions

- File: `docs/book/open-questions.md`
- Current status: **not-ready because too thin**
- Word count: 145
- Reader-facing citations: 0
- Can improve using existing registry sources: yes
- New research required: yes
- Missing source types needed: curated unanswered-question inventory and editor-approved risk framing.
- Strongest publishable sources currently available:
  - `src_2931d4430c4d9716fe8f` — GitHub - conorbronsdon/avoid-ai-writing: Skill that audits and rewrites content to remove AI writing patterns. Use it with your favorite agents including Claude Code, OpenClaw, and Hermes. · GitHub; github.com; quality `A`; type `web`; URL: https://github.com/conorbronsdon/avoid-ai-writing
  - `src_40b2cf3bcc17ee3a1a13` — r/GrapheneOS on Reddit: Je viens d'obtenir un Google Pixel 9 pro XL; www.reddit.com; quality `A`; type `web`; URL: https://www.reddit.com/r/GrapheneOS/comments/1u20n5e/just_got_a_google_pixel_9_pro_xl/?tl=fr
  - `src_45d026189270d1762fad` — hermes-agent — Hermes Agent Core & Official | Hermes Atlas; hermesatlas.com; quality `A`; type `web`; URL: https://hermesatlas.com/projects/NousResearch/hermes-agent
  - `src_5de659c63abf9db0dff3` — Run Nemotron 3 Ultra free in Hermes Agent | Hermes Agent; hermes-agent.nousresearch.com; quality `A`; type `web`; URL: https://hermes-agent.nousresearch.com/docs/guides/run-nemotron-3-ultra-free
  - `src_8408c6be5aaeee529e47` — GitHub - NousResearch/hermes-agent: The agent that grows with you · GitHub; www.google.com; quality `A`; type `web`; URL: https://www.google.com/goto?url=CAESZAHuR6pNXgeGMwUIOcy41wHF8HvrFBiJJ-tIysSkNPdU3K6pONT7xshWFfMorAlVGnDAg2wzArl3EsP8LeHytq5xUUhPDUqpYDvNEQ-akGfMvqk1Ix6T-eT27cO95Ei53u2f4eE%3D
- Recommended next action: Derive questions from blocked/weak claims plus source gaps, not as claims of fact.

# Source promotion recommendations

## 1. Chapters that can be improved now using existing publishable canonical sources

### Loop Engineering
- Why it matters: this is the strongest current evidence cluster and should become the first real narrative chapter.
- Chapter: `docs/book/04-loop-engineering.md`
- Evidence exists:
  - `src_80c8c50e6406c7e7fc95` — Agentic Loops: From ReAct to Loop Engineering (2026 Guide); quality `B`; status `publishable_metadata_only`
  - `src_384bcc1123ee303676b1` — Loop Engineering Playbook. Where loops live, how to run your first… | by Cobus Greyling | Jun, 2026 | Medium; quality `B`; status `publishable_metadata_only`
  - `src_3eb174da3717ef674f19` — Loop Engineering Explained Visually - by The Cloud Girl; quality `B`; status `publishable_metadata_only`
  - `src_5cc15e3db44d8eabf9b0` — Loop Engineering Playbook. Where loops live, how to run your first… | by Cobus Greyling | Jun, 2026 | Medium; quality `B`; status `publishable_metadata_only`
  - `src_7387e00f4d0e7dbf7fee` — Loop Engineering Playbook; quality `B`; status `publishable_metadata_only`
  - `src_916fb39c4634f0adc248` — From Prompt Engineering to Loop Engineering: Why the Agent Era Demands a New Security Paradigm | by Filip Verloy | Jun, 2026 | Medium; quality `B`; status `publishable_metadata_only`
- Missing: Editor-promoted claim records that summarize these sources without hype; ideally one or two primary/technical sources beyond commentary posts.
- Safe to publish now: safe as cited, caveated background after claim promotion; not safe as strong industry trend claims without better support.

## 2. Chapters that need better source promotion from already captured raw data

- `docs/book/04-loop-engineering.md`: promote B-quality article/web sources from the registry into supported/caveated claims.
- `docs/book/02-hermes.md`: inspect captured Hermes Agent/Nos Research sources and promote only official docs/repo/release material; leave social comparison snippets blocked.
- `docs/book/05-context-memory-architecture.md`: review captured RAG, memory architecture, and context references; promote technical sources only if they have canonical origin metadata.

## 3. Chapters that require new external research

- `docs/book/01-the-agent-loop.md`: needs foundational ReAct/tool-use/agent-loop papers or docs and concrete implementation examples.
- `docs/book/02-hermes.md`: needs official Hermes Agent documentation, repository, release notes, and implementation-level sources.
- `docs/book/03-openclaw.md`: needs official OpenClaw sources and reliable comparison material; current support is mostly social/search noise.
- `docs/book/06-operating-loops.md`: needs production operations sources: evals, observability, guardrails, incident handling, CI/CD, and governance.
- `docs/book/open-questions.md`: needs curated uncertainty/risk inventory from Editor-vetted gaps rather than social trend claims.

## 4. Claims that should remain blocked

- Blocked claim records with linked sources but zero publishable source origins: 84
- Reason: only support is LinkedIn/search-result/human-review material or otherwise lacks publishable canonical origin metadata.
- Safe to publish: no, not as factual claims. They may be used only as internal trend signals or as prompts for new research.
- Examples:
  - `claim_00d0cc7024aaddd2adf4` — Some of the most ambitious early-stage startups are moving back to "loop engineer".; source types `linkedin_search_result`; qualities `D`
  - `claim_04498133bcb64f370816` — Typing prompts into an AI agent and reviewing what comes back is the new junior engineering.; source types `linkedin_search_result`; qualities `D`
  - `claim_08b20402ee60da372924` — Loop Engineering Emerges to Advance Autonomous AI Coding Agents 📌 Software development is undergoing a paradigm shift as developers move fro "loop engineering".; source types `linkedin_search_result`; qualities `D`
  - `claim_0c76b2d0770ff1442eeb` — "Designing Loops" - A Practioners Short Guide Anthropic's Boris Cherny "My job is to write Loops" 🔄 Prompt Engineering, Context Engineering "loop engineering".; source types `linkedin_search_result`; qualities `D`
  - `claim_115b4898cd95a01eed6c` — Instead of direct prompting, the focus is now on designing s "loop engineering".; source types `linkedin_search_result`; qualities `D`
  - `claim_18d2cb81ce2a907f0b84` — Enterprise Architecture is entering the Loop Engineering era.; source types `linkedin_search_result`; qualities `D`
  - `claim_195590e66b871a4a2388` — AI Industry Shifts Toward Loop Engineering and Agentic Development Architectures 📌 The AI landscape is pivoting from manual prompting to loo "loop engineering".; source types `linkedin_search_result`; qualities `D`
  - `claim_1e6da5e353cab67ed16c` — Everyone is suddenly talking about "loop engineering." The idea: stop prompting your coding agent one step at a time.; source types `linkedin_search_result`; qualities `D`
  - `claim_2311b109d80f8a43b0ec` — Loop engineering is all the hype now but have you actually looked into what kind of stuff the LLM does in those loops?.; source types `linkedin_search_result`; qualities `D`
  - `claim_301c456c255778bde504` — 🛠️ Nous Research has quietly solved one of the clunkiest parts of open-s "Hermes Agent".; source types `linkedin_search_result`; qualities `D`
  - `claim_35259524a830a49e0d38` — Anthropic Guardrails Limit Researcher Access to Fable 5 Capabilities 📌 Anthropic’s security guardrails are inadvertently stifling innovation "loop engineering".; source types `linkedin_search_result`; qualities `D`
  - `claim_3758bb6824db2606c9b9` — Feed post Stuart Inskip • 3rd+ Strategic Product Leader delivering 0-to-1 launches and roadmap ownership across consumer loyalty, omnichanne "loop engineering".; source types `linkedin_search_result`; qualities `D`

## Prioritized top actions

1. Promote the existing Loop Engineering canonical article cluster into supported/caveated claims and draft chapter 4 first.
2. Capture/promote official Hermes Agent sources before attempting chapter 2 narrative prose.
3. Research official OpenClaw sources and avoid publishing social comparison claims until canonical evidence exists.
4. Build a foundational agent-loop source pack: ReAct, tool use, reflection/verification, state/memory, escalation.
5. Build an operations source pack for production loops: evals, guardrails, observability, CI/CD, incident response, and governance.

## Recommended next Author prompt

> Using the current `data/source_registry.json`, promote publishable Loop Engineering sources into supported/caveated claims for chapter 4 only, then draft a conservative narrative replacement for `docs/book/04-loop-engineering.md` with numbered citations. Do not use LinkedIn/search-result/human-review material as citation authority. Run the citation resolver, citation gate, Book role gate, tests, and MkDocs strict build afterward.
