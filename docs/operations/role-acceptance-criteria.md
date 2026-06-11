# Role Acceptance Criteria

Each role must meet explicit acceptance criteria before its work is considered complete.

## Book role acceptance criteria

The Book role is complete only when:

- `mkdocs build --strict` passes
- navigation is valid
- new pages are linked
- report pages are reachable
- generated pages are inside the `docs/` tree
- no unsafe files are staged
- no credentials, cookies, tokens, raw browser state, or unsafe logs are committed
- publication status is reported
- failed checks are not hidden

## Author role acceptance criteria

The Author role is complete only when:

- prose is clear and readable
- chapter structure follows the brief
- every factual claim maps to claim/source IDs
- weak claims are caveated
- unsupported claims are removed
- no generic AI filler remains
- no hype language remains
- source/claim mapping is included
- editor notes are included
- changelog is included

## Editor role acceptance criteria

The Editor role is complete only when:

- claims are reviewed
- source quality is scored
- privacy risk is checked
- contradictions are checked
- duplicate/repeated signals are identified
- weak claims are caveated or rejected
- trends are accepted/rejected/monitored
- Author output is approved/rejected/revised
- publication recommendation is explicit

## Curator function acceptance criteria

The Curator function is complete only when:

- meaningful findings are separated from noise
- duplicates are identified
- weak signals are labeled
- strong signals are identified
- candidate claims are selected
- irrelevant material is rejected
- chapter impact is stated
- human-review items are listed

## Research quality acceptance criteria

The research update is acceptable only when:

- sources > 0 implies source notes exist
- sources > 0 implies entities are considered
- sources > 0 implies claims are considered
- claims have source IDs
- source quality is assigned
- unsupported claims are not promoted
- chapter updates have Editor approval
- reports accurately state what happened

## Final acceptance rule

A run is not successful merely because scripts exited with code 0.

A run is successful only if the resulting research state is coherent, traceable, safe, and useful.
