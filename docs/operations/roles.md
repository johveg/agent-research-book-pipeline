# Book / Author / Editor Roles

This project uses three practical roles. They can be executed by one Hermes coordinator or split across agents later.

## Book role

Maintains the published structure:

- chapter order
- navigation
- entity pages
- source and claim pages
- GitHub Pages build health

The book role does not invent facts. It only promotes source-backed material.

## Author role

Turns verified research into readable prose:

- explains Hermes, OpenClaw, loop engineering, context architecture, and memory architecture;
- writes in book form rather than daily-news form;
- adds citations or source notes where claims are specific;
- marks weak signals as unresolved instead of overstating them.

## Editor role

Protects quality and safety:

- checks whether a claim is backed by a source;
- rejects private/sensitive personal data;
- prevents raw authenticated HTML, cookies, tokens, browser profiles, `.env`, and runtime DB files from being published;
- reviews trend candidates before adding new recurring searches;
- keeps contradiction/history instead of silently overwriting facts.

## Current daily loop

1. Web search: Hermes/OpenClaw/loop-engineering queries through Brave Search.
2. LinkedIn search: read-only authenticated search-result page capture through existing CDP browser.
3. Trend discovery: candidate words/phrases from daily captures.
4. Book update: generated source/trend pages plus curated chapter structure.
5. Vector update: local ChromaDB over sanitized Markdown.
6. Commit/push: sanitized artifacts only.
7. Report: Telegram via Hermes cron.
