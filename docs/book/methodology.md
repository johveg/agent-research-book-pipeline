# Methodology

The central argument of this methodology chapter is that an autonomous book pipeline must separate evidence collection, claim evaluation, drafting, and publication into distinct layers. The system may collect material automatically, but it should not treat collected material as publishable prose. It may draft chapters automatically, but it should not treat a draft as approved. It may detect that new information belongs in the book, but it should still decide whether that information revises an existing chapter or warrants a new guarded chapter. This separation is what allows the loop to move quickly without turning speed into uncontrolled publication. [1]

The method is intentionally conservative. It assumes that agentic systems can help collect, classify, rewrite, and verify information, but that every step needs a visible gate. Evidence sources are recorded for traceability. Claims are shaped into manuscript prose only after they are bounded by scope, caveats, and references. Public chapters are checked for reader-facing form so that internal ledgers, source maps, and editorial status labels do not become the book itself. The pipeline therefore treats autonomy as an operating procedure rather than as permission to skip judgment. [1] [2]

## From Prompt to Loop

A methodology for agent-loop research cannot be limited to prompt design. The relevant object is the recurring workflow: collection, extraction, review, drafting, proof, publication, monitoring, and recovery. Each stage changes the status of the material. A source capture is not a claim. A claim is not a chapter. A draft is not a publication. A publication is not final if later evidence requires revision. The loop has to preserve those distinctions because the same text can be useful evidence in one layer and inappropriate reader-facing prose in another. [1]

This methodology therefore uses gates rather than trust in fluency. A model may produce fluent prose that is unsupported, or a source ledger may be accurate but unreadable. The production loop should reject both failure modes. The desired output is not merely correct data and not merely polished language. It is evidence-bounded manuscript prose: writing that develops an argument, cites support, names limitations, and avoids overstating what the current source base can show. [1] [2]

## Operational Pattern

The first stage is evidence intake. Sources are collected from configured searches, repositories, documentation, reports, and operational traces. Social or discovery material can identify leads, but it is not treated as independent confirmation unless stronger evidence supports the same claim. The second stage is processing: entities, claims, trends, and candidate chapter updates are extracted into internal artifacts where uncertainty can be preserved. These artifacts are for operators and later verification, not for direct publication as chapter prose. [1]

The third stage is chapter decision. After information has been collected and processed, the system asks whether it belongs in an existing chapter. If it does, the correct action is a fluent rewrite or refactor of that chapter so that the new material changes the argument naturally. Append-only stuffing is not acceptable because it produces a visible seam between old prose and new evidence. If the information does not fit an existing chapter, the system creates a guarded new-chapter queue item rather than directly writing a new public page. [1] [2]

The fourth stage is gated publication. A candidate chapter must pass manuscript quality checks, evidence-safety checks, citation checks, public chapter proof, workspace verification, build verification, mutation guards, and secret scans before it can be committed and pushed. The whole-book proof then checks whether every configured chapter still reads as manuscript prose rather than as an evidence ledger. This is what allows the loop to fail closed honestly. A failed proof is not a system crash; it is a safe refusal to claim that the book is ready. [1]

## Verification and Failure

Verification is distributed throughout the method. The system verifies that the worktree is clean enough to interpret, that generated reports are not confused with intended source changes, that each chapter has the required manuscript signals, that citations are present, that forbidden evidence-led phrases are absent, and that only intended files changed. These checks slow the loop down in the short term, but they make faster autonomous operation possible later because the system can distinguish safe completion from unsafe partial progress. [1] [2]

Failure is also part of the method. If the whole-book proof fails because older chapters still read like ledgers, the loop should fail closed and report the failing chapters. If a model produces invalid JSON or a publication packet does not meet the academic quality gate, the system should refuse mutation. If generated documentation or entity pages drift during verification, those changes should be restored unless they are intentionally part of the run. The methodology therefore treats fail-closed outcomes as evidence of control, not as embarrassing exceptions. [1]

## Limitations

The evidence boundaries of this methodology are the same limits that shape the rest of the manuscript. Local operational reports can prove that a workflow ran, failed, or recovered in this repository. They cannot prove that a broader field has adopted the same method. Project documentation can support claims about stated capabilities, but not claims about independent performance. Discovery material can suggest topics, but not confirm them. The manuscript therefore presents its own pipeline as a case and a method, not as universal proof. [1] [2]

These limits are especially important for autonomous chapter creation. A new chapter should appear only when processed information has no good existing home and the queue can describe its scope, target path, evidence status, and required gates. Even then, the chapter should not be treated as public until the publisher and proof gates approve it. The method is fast because it is explicit: every run either advances the manuscript through visible gates or records exactly why it stopped. That audit trail is part of the method rather than an administrative afterthought. [1] [2] [3]
## References

[1] [Approved research lane](book/open-questions.md).
[2] [Research loop evidence process](book/source-registry.md).
[3] [Guarded publication policy](book/methodology.md).
