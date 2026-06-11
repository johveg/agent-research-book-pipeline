# Chapter Brief: 6. Operating Loops in Production

## Purpose

Describe how recurring agent loops should be operated safely with manifests, state, verification, watchdogs, and human escalation.

## Target reader

Intelligent operators, architects, engineers, builders, and technical leaders trying to understand emerging agent systems without hype.

## Main argument

The chapter should argue that production value depends less on a single smart run and more on transparent, recoverable operations. It should treat automation boundaries and failure handling as first-class design.

## Required concepts

- cron
- state files
- manifests
- status pollers
- watchdogs
- safe retries
- human review

## Required claims

Use technical pattern, risk, limitation, and example claims from supported operational evidence.

## Required examples

- Start-worker/status-poller pattern
- watchdog with manual-only boundaries
- safe artifact commit gate.

## Allowed source types

A/B sources may support factual claims. C sources may support interpretation if caveated. D social/search material may only support weak signals or examples when caveated. E sources must not support chapter facts.

## Excluded source types

Raw LinkedIn/web captures, private/session-visible material, credentials, cookies, logs, E-quality sources, and unsupported repeated social posts. D sources require caveats and cannot establish strong facts.

## Open questions

- Which claims have enough A/B support to move from weak signal to supported?
- What contradictions or limitations should remain visible?
- What evidence is missing before a stronger chapter argument can be published?

## What this chapter must not claim

Must not recommend autonomous repair for credentials, login/MFA, browser session corruption, or unknown unsafe failures.

## Desired tone

Clear, practical, grounded, analytical, readable, skeptical where appropriate, and lightly opinionated only when evidence supports it. Avoid hype and generic AI prose.

## Desired length

Medium chapter, approximately 1,200–2,500 words when evidence supports it.

## Related entities

- cron jobs
- watchdog
- Hermes Agent
- GitHub Pages

## Publication readiness criteria

- A chapter brief exists before Author work begins.
- Every factual claim maps to a claim ID and source IDs.
- Only supported, caveated weakly_supported, or promoted_to_chapter claims are used.
- The Editor has reviewed claims and chapter output against this brief.
- Weak evidence is visibly caveated.
- No raw captures or unsafe/private material are published.
- MkDocs strict build and Book role gate pass.
