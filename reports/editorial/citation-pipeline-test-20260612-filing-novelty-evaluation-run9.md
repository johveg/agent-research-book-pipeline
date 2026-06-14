# Filing and novelty evaluation: citation-pipeline-test-20260612

## Executive summary

- editor_packet_report: `reports/editorial/citation-pipeline-test-20260612-editor-review-packet-run8.json`
- editor_packet_items_available: `14`
- downstream_eligible_items_available: `5`
- items_evaluated: `5`
- provider: `copilot`
- model: `gpt-5.5`
- bridge: `hermes_cli`
- reasoning_status: `high_reasoning_used`
- Filing decision counts: `{'needs_corroboration': 2, 'new_caveat_candidate': 3}`
- Novelty decision counts: `{'partially_novel': 4, 'novel': 1}`
- Next-stage recommendation counts: `{'needs_source_review': 5}`
- Safety: report-only; no DB/status/chapter/schema/worker/allowlist changes; not author-approved; not publication-approved.

## Filing/novelty table

| packet item id | source id | semantic object id | semantic object type | chapter target | filing decision | novelty decision | next stage | matched existing claim/source ids | confidence | blockers |
|---|---|---|---|---|---|---|---|---|---|---|
| editor_packet_b7dc9103943b3b345e15 | [internal-id] | semantic_object_draft_425a074033ba640ec639 | trend_signal | 02-hermes, 03-openclaw | needs_corroboration | partially_novel | needs_source_review | [internal-id], [internal-id] | low | Only metadata-level evidence is described.; No direct source excerpt confirming interface… |
| editor_packet_23c4afb16f0732af29df | [internal-id] | semantic_object_draft_0aed99a302b307d6fdd3 | counterpoint | 02-hermes, 03-openclaw | new_caveat_candidate | partially_novel | needs_source_review | [internal-id], [internal-id], [internal-id] | medium | Absence-based assessment requires source-card review. |
| editor_packet_48e56de78fce06dde725 | [internal-id] | semantic_object_draft_5df8116fc7dc2d06b2e7 | factual_claim | 02-hermes, 03-openclaw | needs_corroboration | partially_novel | needs_source_review | [internal-id], [internal-id], [internal-id] | low | The claim is explicitly framed as weak.; No integration or architecture evidence is provi… |
| editor_packet_13a17d293dd6140c91ae | [internal-id] | semantic_object_draft_5558303e45f77723657a | factual_claim | 02-hermes, 03-openclaw | new_caveat_candidate | novel | needs_source_review | [internal-id], [internal-id] | medium | Source type must be verified before filing.; Could be misclassified without inspecting th… |
| editor_packet_9ec385327deb68b949a6 | [internal-id] | semantic_object_draft_18e5d778bd54802d41b3 | counterpoint | 02-hermes, 03-openclaw | new_caveat_candidate | partially_novel | needs_source_review | [internal-id] | medium | No method or validation evidence is described.; Integration details are absent from the p… |

## Per-item filing evaluation

### filing_eval_c39f3be4e7bef7f0dabe

- Provenance: packet `editor_packet_b7dc9103943b3b345e15`, source `src_6d7b6d80cda4e784877d`, card `source_card_draft_src_6d7b6d80cda4e784877d`, object `semantic_object_draft_425a074033ba640ec639`, quality review `semantic_object_draft_425a074033ba640ec639`
- Semantic object: The project metadata suggests a web or phone interface for using Hermes Agent.
- Filing decision: `needs_corroboration`
- Novelty decision: `partially_novel`
- Next stage: `needs_source_review`
- Similarity rationale: Existing material supports OpenClaw/Hermes as agent projects, but not the specific web or phone interface inference.
- Corroboration needed: `True`
- Corroboration questions: What exact metadata field suggests a web or phone interface?, Does an official source or repository file confirm a web or phone interface?, Is the interface for Hermes Agent itself or only for adjacent tooling?
- Required editor decisions: Decide whether interface metadata is relevant enough to preserve as a trend signal.
- Risk flags: weak_metadata_inference, possible_overreading_of_project_metadata
- Explicit safety: not author-approved, not publication-approved, advisory-only.

### filing_eval_5a84c224eb58bf625f42

- Provenance: packet `editor_packet_23c4afb16f0732af29df`, source `src_6d7b6d80cda4e784877d`, card `source_card_draft_src_6d7b6d80cda4e784877d`, object `semantic_object_draft_0aed99a302b307d6fdd3`, quality review `semantic_object_draft_0aed99a302b307d6fdd3`
- Semantic object: The card does not verify project maturity, feature completeness, code quality, or maintenance status.
- Filing decision: `new_caveat_candidate`
- Novelty decision: `partially_novel`
- Next stage: `needs_source_review`
- Similarity rationale: This aligns with existing caution that official docs/repo material are safer than social summaries, but adds a specific limitation about maturity and maintenance not being verified.
- Corroboration needed: `True`
- Corroboration questions: Does the source card contain any direct evidence about maturity, feature completeness, code quality, or maintenance?, Are there official repository indicators such as releases, commits, issues, or documentation that could corroborate maturity claims?
- Required editor decisions: Decide whether to file this as a reusable caveat for weak project-metadata cards.
- Risk flags: absence_of_evidence, publication_safety_caveat
- Explicit safety: not author-approved, not publication-approved, advisory-only.

### filing_eval_b82d67d436357d41bf72

- Provenance: packet `editor_packet_48e56de78fce06dde725`, source `src_6d7b6d80cda4e784877d`, card `source_card_draft_src_6d7b6d80cda4e784877d`, object `semantic_object_draft_5df8116fc7dc2d06b2e7`, quality review `semantic_object_draft_5df8116fc7dc2d06b2e7`
- Semantic object: The metadata weakly shows agent-adjacent tooling that names OpenClaw and Hermes as relevant environments.
- Filing decision: `needs_corroboration`
- Novelty decision: `partially_novel`
- Next stage: `needs_source_review`
- Similarity rationale: Existing claims already connect OpenClaw and Hermes to agent-related material; this item adds only a weak metadata-based angle about adjacent tooling.
- Corroboration needed: `True`
- Corroboration questions: Which metadata fields explicitly name OpenClaw and Hermes?, Does the source establish actual integration, compatibility, or only keyword association?, Is this tooling official, third-party, or unrelated metadata noise?
- Required editor decisions: Decide whether this should be retained only as source-context metadata rather than a claim.
- Risk flags: weak_metadata_inference, keyword_association_risk
- Explicit safety: not author-approved, not publication-approved, advisory-only.

### filing_eval_bd562e909f80e16a2bb3

- Provenance: packet `editor_packet_13a17d293dd6140c91ae`, source `src_6d7b6d80cda4e784877d`, card `source_card_draft_src_6d7b6d80cda4e784877d`, object `semantic_object_draft_5558303e45f77723657a`, quality review `semantic_object_draft_5558303e45f77723657a`
- Semantic object: This item is framed as a writing-audit and rewrite skill, not as a primary source on agent architecture.
- Filing decision: `new_caveat_candidate`
- Novelty decision: `novel`
- Next stage: `needs_source_review`
- Similarity rationale: Existing claims discuss Hermes documentation and project positioning, but this specific source-classification caveat is not duplicated.
- Corroboration needed: `True`
- Corroboration questions: Does the source title, README, or metadata identify it as a writing-audit/rewrite skill?, Does the source contain any primary architectural documentation, or only audit/rewrite instructions?, Should it be classified as tooling evidence rather than architecture evidence?
- Required editor decisions: Decide final source classification before allowing any architecture-related use.
- Risk flags: source_type_uncertainty, architecture_evidence_risk
- Explicit safety: not author-approved, not publication-approved, advisory-only.

### filing_eval_224fd1bd260b4222fdfc

- Provenance: packet `editor_packet_9ec385327deb68b949a6`, source `src_6d7b6d80cda4e784877d`, card `source_card_draft_src_6d7b6d80cda4e784877d`, object `semantic_object_draft_18e5d778bd54802d41b3`, quality review `semantic_object_draft_18e5d778bd54802d41b3`
- Semantic object: The card does not show the skill's method, rules, accuracy, or integration details.
- Filing decision: `new_caveat_candidate`
- Novelty decision: `partially_novel`
- Next stage: `needs_source_review`
- Similarity rationale: This reinforces the existing preference for official documentation as safer authority, while adding a specific caveat about missing method, rules, accuracy, and integration details.
- Corroboration needed: `True`
- Corroboration questions: Does the source card include implementation details, rules, tests, evaluations, or integration instructions?, Can official docs or repository files verify the skill's method and integration points?, Is there any evidence of accuracy or reliability testing?
- Required editor decisions: Decide whether this caveat should block all claim use from the source until implementation evidence is reviewed.
- Risk flags: missing_method_detail, missing_validation_evidence, integration_uncertainty
- Explicit safety: not author-approved, not publication-approved, advisory-only.

## Cross-item synthesis

- Strongest new candidates: `[]`
- Likely duplicates: `[]`
- Items needing corroboration: `['filing_eval_c39f3be4e7bef7f0dabe', 'filing_eval_5a84c224eb58bf625f42', 'filing_eval_b82d67d436357d41bf72', 'filing_eval_bd562e909f80e16a2bb3', 'filing_eval_224fd1bd260b4222fdfc']`
- Chapter/topic distribution: `{'02-hermes': 5, '03-openclaw': 5}`
- Recurring blockers: `{'Only metadata-level evidence is described.': 1, 'No direct source excerpt confirming interface functionality.': 1, 'Absence-based assessment requires source-card review.': 1, 'The claim is explicitly framed as weak.': 1, 'No integration or architecture evidence is provided.': 1, 'Source type must be verified before filing.': 1, 'Could be misclassified without inspecting the underlying source.': 1, 'No method or validation evidence is described.': 1, 'Integration details are absent from the packet item.': 1}`
- Before narrative packets: Human/editor review plus corroboration or explicit acceptance of filing notes is required before narrative packet candidates.

## Safety assessment

- db_modified: `False`
- db_write_scope: `none`
- chapters_modified: `False`
- statuses_modified: `False`
- schema_modified: `False`
- daily_worker_modified: `False`
- commit_allowlist_modified: `False`
- raw_private_material_written: `False`
- long_source_excerpt_written: `False`
- claims_inserted: `0`
- editorial_reviews_inserted: `0`
- author_allowed: `False`
- publication_approved: `False`
- advisory_only: `True`
- external_web_search_used: `False`
- vector_db_authority_used: `False`

## Recommendation for Run 10

- Recommendation: `run_corroboration_research_for_items_needing_corroboration`
- Condition: keep report-only unless explicitly asked to persist
- Condition: do not insert claims or approve publication
- Condition: use human/editor review before narrative packets
