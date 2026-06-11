# Source Quality Instruction

Every source should be classified before it is used to support claims or chapter text.

## Source quality scale

Use this scale:

- A = primary source, official documentation, direct artifact, original paper, official release, standards document, or authoritative first-party material.
- B = credible technical article, project documentation, serious analysis, reputable publication, or well-supported independent explanation.
- C = named expert commentary, practitioner analysis, conference talk, podcast, or serious blog post.
- D = social post, anecdote, casual commentary, repost, weak signal, or unverified claim.
- E = duplicate, unclear, SEO-like, spammy, low-quality, platform boilerplate, scraped noise, or irrelevant material.

## Source use rules

A sources may support factual claims.

B sources may support factual claims when specific and credible.

C sources may support interpretation or context, preferably with caveats.

D sources may support weak-signal analysis only.

E sources should usually be rejected.

## Required source fields

Each source should have:

- source ID
- URL
- title
- author or organization if available
- date if available
- capture date
- source type
- quality score
- summary
- relevant entities
- extracted candidate claims
- duplicate status
- privacy/publication status
- notes

## Duplicate handling

If several sources repeat the same underlying material, treat them as duplicates or repetitions.

Do not count repeated LinkedIn posts as independent confirmation unless they clearly provide independent evidence.

## Source rejection

Reject or ignore sources that are:

- empty
- boilerplate
- inaccessible
- login-wall artifacts
- search result noise
- duplicate without added value
- SEO pages without useful content
- generic AI-generated material
- privacy-sensitive
- unsafe to publish

## Source quality output

For each run, produce:

1. Number of A sources.
2. Number of B sources.
3. Number of C sources.
4. Number of D sources.
5. Number of E sources.
6. Rejected source count.
7. Duplicate source count.
8. Sources needing human review.
9. Best new sources.
10. Weakest/noisiest sources.

## Final rule

Volume is not evidence.

Quality and independence matter more than count.
