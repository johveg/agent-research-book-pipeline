# Run 56 manuscript contract

```json
{
  "contract": {
    "allowed_evidence_machinery_locations": [
      "reports/editorial/",
      "reports/manuscript/",
      "docs/research/",
      "docs/appendices/",
      "local_source_registry",
      "editorial_database"
    ],
    "blocked_overclaims": [
      "prompt engineering is dead",
      "settled academic discipline",
      "industry consensus",
      "universal adoption",
      "proven industry transition"
    ],
    "caveat_terms": [
      "emerging",
      "limited",
      "cautious",
      "practitioner discourse",
      "does not establish",
      "not settled",
      "weak evidence"
    ],
    "contract_name": "manuscript_quality_contract",
    "forbidden_reader_facing_phrases": [
      "Current evidence status",
      "Source/claim mapping",
      "Bullet 1 maps to",
      "maps to supported claim",
      "status supported",
      "status weakly_supported",
      "quality A",
      "quality B",
      "Generated Author output",
      "Editor notes",
      "Changelog",
      "Editorial policy",
      "claim record",
      "source tokens"
    ],
    "hard_safety_flags": [
      "author_allowed",
      "publication_approved",
      "eligible_for_claim_insertion",
      "eligible_for_authoring",
      "eligible_for_publication",
      "chapter_update_allowed"
    ],
    "layers": {
      "evidence_layer": [
        "claims",
        "source_registry",
        "confidence_status",
        "citation_tokens",
        "editorial_notes",
        "internal_traceability",
        "source_claim_mapping"
      ],
      "manuscript_layer": [
        "argument_led_prose",
        "definitions",
        "synthesis_across_sources",
        "careful_citations",
        "limitations",
        "transitions",
        "reader_facing_structure",
        "no_exposed_internal_workflow_machinery"
      ]
    },
    "required_reader_facing_elements": [
      "chapter_title",
      "opening_thesis_paragraph",
      "conceptual_framing",
      "analytical_sections",
      "integrated_citations",
      "limitations_where_needed",
      "conclusion_or_transition",
      "references"
    ],
    "run_introduced": "run56",
    "version": 1
  },
  "contract_path": "config/manuscript_quality_contract.json",
  "created_at_utc": "2026-06-20T06:48:01.001348+00:00",
  "run_id": "run56",
  "safety_flags": {
    "author_allowed": false,
    "chapter_update_allowed": false,
    "eligible_for_authoring": false,
    "eligible_for_claim_insertion": false,
    "eligible_for_publication": false,
    "publication_approved": false
  },
  "status": "manuscript_contract_created",
  "style_guide_path": "docs/research/manuscript-style-guide.md",
  "summary": "Defines evidence layer vs manuscript layer and blocks internal evidence machinery from reader-facing prose."
}
```
