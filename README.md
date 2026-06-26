# Terefo Heal Reboa

A living, source-backed research book about **Hermes**, **OpenClaw**, **loop engineer**, and **loop engineering**.

The project is designed as a Hermes-operated research loop:

1. collect public web-search results and authenticated LinkedIn search-result pages;
2. archive sanitized source evidence and metadata;
3. store sources, claims, entities, relationships, and trend terms in SQLite;
4. update Markdown book chapters and research pages;
5. prepare a local vector database for semantic search;
6. publish the book via GitHub Pages;
7. report daily status to Telegram through Hermes cron jobs;
8. self-monitor without touching credentials or browser sessions destructively.

## Public site

GitHub Pages is configured through `.github/workflows/pages.yml` using MkDocs Material.

## Local workspace

Expected local path:

```text
/home/hermoine/agent-research-book-pipeline
```

## Operating principle

This repo should contain **public/sanitized research artifacts and book content**. Runtime state, credentials, browser profiles, raw authenticated HTML, local SQLite DB files, and vector DB binaries stay local and are ignored by git.
