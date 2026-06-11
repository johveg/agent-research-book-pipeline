# 1. The Agent Loop

The central thesis of this book is that useful AI agents are not just prompts. They are loops: systems that repeatedly gather context, act through tools, verify outputs, save state, and report back to people.

## The basic loop

1. Define the goal.
2. Gather current context from files, web, databases, sessions, or messages.
3. Act through tools or scripts.
4. Verify the result with explicit checks.
5. Save durable state outside the model.
6. Report the result to a human channel.
7. Retry safe failures and escalate unsafe or ambiguous ones.

## Evidence in this project

The book loop itself has already processed 371 source records and maintains 1106 entity records and 55 claim records. Its daily collector, status poller, watchdog, database, vector index, Git commits, and GitHub Pages publication are all examples of the loop pattern described here.

## Cross-links

- [Hermes](02-hermes.md)
- [OpenClaw](03-openclaw.md)
- [Loop Engineering](04-loop-engineering.md)
- [Context and Memory Architecture](05-context-memory-architecture.md)
- [Operating Loops in Production](06-operating-loops.md)

Last generated from harvest: 2026-06-11T21:23:21Z.
