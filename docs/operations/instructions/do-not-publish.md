# Do-Not-Publish Instruction

The system must be willing to block publication.

Publishing nothing is better than publishing unsupported, unsafe, generic, or misleading content.

## Block chapter publication if

- claims table is empty
- entities table is empty after sources were captured
- source IDs are missing
- claims have no statuses
- source quality is not scored
- Editor review did not run
- Author output lacks source/claim mapping
- Author output is generic or mostly filler
- chapter contains unsupported factual claims
- chapter contradicts existing claims without explanation
- chapter overstates weak evidence
- LinkedIn/social media material is treated as strong proof
- privacy review failed
- unsafe files are staged
- raw captures are staged unintentionally
- MkDocs strict build fails
- generated pages contain placeholder-only content without explanation
- capture appears blocked, polluted, or login-broken
- trend discovery is dominated by structural/platform noise

## Allowed publication during blocked state

If chapter publication is blocked, the system may still publish:

- safe status reports
- source index updates
- rejected trend lists
- quality warnings
- operational notes
- editor reports
- “no chapter update” notes

## Required blocked-state output

When publication is blocked, produce:

1. Block reason.
2. Affected files.
3. Failed checks.
4. Whether data was collected.
5. Whether data was usable.
6. What was safely updated, if anything.
7. Required next action.
8. Whether human review is required.

## Human-review triggers

Escalate to human review for:

- credential issues
- LinkedIn checkpoint/MFA/CAPTCHA
- privacy uncertainty
- legal/copyright uncertainty
- raw data cleanup from Git history
- destructive cleanup
- trend promotion with weak evidence
- major chapter restructure
- contradiction involving important book claims

## Final rule

Do not let automation create authority.

The book earns authority through review, evidence, and restraint.
