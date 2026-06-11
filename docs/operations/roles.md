# Book / Author / Editor Roles

This project uses three practical roles. They can be executed by one Hermes coordinator or split across agents later.

## Book role → keeps the book usable

The Book role should not write the argument. Its job is structural.

The Book role maintains:

- MkDocs navigation
- chapter files
- entity pages
- report indexes
- broken-link checks
- build validity
- consistent formatting
- approved public content only

The Book role is basically the publisher / production editor.

It should ask:

- Does the site build?
- Are pages in the right place?
- Are links valid?
- Are reports reachable?
- Are chapters consistently structured?
- Is the book navigable?

It should not decide whether a claim is true.

## Author role → turns approved evidence into readable argument

The Author role turns verified or explicitly approved research into readable prose:

- explains Hermes, OpenClaw, loop engineering, context architecture, and memory architecture;
- writes in book form rather than daily-news form;
- builds an argument from approved evidence rather than dumping raw captures;
- adds citations or source notes where claims are specific;
- marks weak signals as unresolved instead of overstating them.

The Author role should not promote weak or private material by itself. It writes from material the Editor has approved or clearly labeled as safe candidate evidence.

## Editor role → protects quality, truth, privacy, and coherence

The Editor role protects the integrity of the book:

- checks whether a claim is backed by a source;
- decides whether evidence is strong enough for narrative promotion;
- rejects private/sensitive personal data;
- prevents raw authenticated HTML, cookies, tokens, browser profiles, `.env`, and runtime DB files from being published;
- reviews trend candidates before adding new recurring searches;
- keeps contradiction/history instead of silently overwriting facts;
- preserves coherence across chapters so the book does not become a pile of disconnected daily notes.

## Current daily loop

1. Web search: Hermes/OpenClaw/loop-engineering queries through Brave Search.
2. LinkedIn search: read-only authenticated search-result page capture through existing CDP browser.
3. Trend discovery: candidate words/phrases from daily captures.
4. Book update: generated source/trend pages plus curated chapter structure.
5. Vector update: local ChromaDB over sanitized Markdown.
6. Commit/push: sanitized artifacts only.
7. Report: Telegram via Hermes cron.
