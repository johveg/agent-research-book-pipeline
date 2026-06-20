#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,re,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
FLAGS=['author_allowed','publication_approved','eligible_for_claim_insertion','eligible_for_authoring','eligible_for_publication','chapter_update_allowed']

def _refs_from_chapter(text):
    refs=[]
    ref_section = text.split('## References', 1)[-1] if '## References' in text else text
    pattern = re.compile(r'\[(\d+)\]\s+(.*?)(?=\s+\[\d+\]\s+|\Z)', re.S)
    for m in pattern.finditer(ref_section.strip()):
        reference = ' '.join(m.group(2).split())
        reference = re.sub(r',\s*quality\s+[A-Z]\.?', '.', reference)
        refs.append({'token':f'[{m.group(1)}]','reference':reference})
    return refs

def _claim_lines(claims_path):
    if not Path(claims_path).exists(): return []
    out=[]
    for line in Path(claims_path).read_text(errors='ignore').splitlines():
        if line.strip().startswith('- ') and len(line.strip())>40:
            out.append(line.strip()[2:])
    return out[:12]

def build_packet(chapter, claims, source_registry, quality_contract):
    for p in [chapter, claims, source_registry, quality_contract]:
        if not Path(p).exists(): raise FileNotFoundError(str(p))
    text=Path(chapter).read_text(); title=text.splitlines()[0].lstrip('# ').strip() if text.splitlines() else 'Untitled'
    refs=_refs_from_chapter(text); claim_lines=_claim_lines(claims)
    evidence_led=bool(re.search(r'Current evidence status|Source/claim mapping|Bullet \d+ maps|status `?(supported|weakly_supported)', text, re.I))
    allowed=[l for l in claim_lines if 'weakly_supported' not in l.lower()][:8]
    caveated=[l for l in claim_lines if 'weakly_supported' in l.lower() or 'limited' in l.lower()][:8]
    flags={'report_only_packet':True, **{k:False for k in FLAGS}}
    return {
        'chapter_slug':Path(chapter).stem,
        'current_title':title,
        'proposed_title':'1. The Agent Loop',
        'current_problem':'evidence_led_needs_manuscript_conversion' if evidence_led else 'prose_led_review_needed',
        'chapter_purpose':'Explain the agent loop as an operational pattern for tool-using AI systems while cautiously situating loop engineering as emerging practitioner discourse.',
        'chapter_thesis':'The agent loop, rather than the isolated prompt, is the useful unit for analyzing systems that act, verify, remember, report, retry, and escalate.',
        'target_reader':'Technically literate practitioners and researchers',
        'key_terms_to_define':['agent loop','loop engineering','goal','context','tool use','verification','state','reporting','retry','escalation'],
        'allowed_claims':allowed or ['Hermes Agent is a Nous Research open-source agent project supporting tool-using automation workflows.','An agentic loop can be framed as a repeated cycle with trigger, goal, action, feedback, and verification.'],
        'caveated_claims':caveated or ['Loop engineering is emerging practitioner discourse and should not be presented as settled academic consensus.','The connection between agent loops and memory architecture requires cautious treatment.'],
        'disallowed_claims':['Prompt engineering is dead.','Loop engineering is a settled academic discipline.','There is industry consensus on a transition from prompts to loops.','LinkedIn/social captures independently confirm claims.'],
        'evidence_summary':'Existing chapter has usable claims and references, but it exposes the evidence ledger instead of synthesizing prose.',
        'evidence_limitations':['Sources are partly practitioner articles from June 2026.','Weak claims require caveats.','Social captures are discovery signals only.'],
        'source_quality_summary':'References include A-quality project sources and B-quality practitioner sources; quality labels are report-only and must not appear in public prose.',
        'source_types_used':['project documentation','GitHub repository','practitioner articles','tutorial/discourse sources'],
        'claims_requiring_caveat':['loop engineering as field transition','memory/context architecture connection','production implications beyond available material'],
        'claims_requiring_more_sources':['academic grounding for loop engineering','stronger primary sources on memory/context architecture'],
        'proposed_structure':['1.1 From Prompt to Loop','1.2 The Agent Loop as an Operational Pattern','1.3 Loop Engineering as Harness Design','1.4 Verification, State, and Escalation','1.5 Evidence Limits and Emerging Discourse','1.6 Implications for Agent Architecture'],
        'prohibited_phrases':json.loads(Path(quality_contract).read_text()).get('forbidden_reader_facing_phrases',[]),
        'traceability_map':{'references':refs,'chapter_hash':hashlib.sha256(text.encode()).hexdigest(),'claim_source':'docs/research/claims.md'},
        'references':refs,
        'publication_safety_flags':flags,
    }

def fail(error): return {'failed_closed':True,'error':error,'publication_safety_flags':{'report_only_packet':True, **{k:False for k in FLAGS}}}

def main(argv=None):
    ap=argparse.ArgumentParser();
    for arg in ['chapter','claims','source-registry','quality-contract','output-json','output-md']: ap.add_argument('--'+arg, required=True)
    a=ap.parse_args(argv)
    try:
        packet=build_packet(a.chapter,a.claims,a.source_registry,a.quality_contract); rc=0
    except Exception as e:
        packet=fail(str(e)); rc=2
    Path(a.output_json).parent.mkdir(parents=True,exist_ok=True); Path(a.output_json).write_text(json.dumps(packet,indent=2,sort_keys=True))
    Path(a.output_md).write_text('# Chapter packet: Agent Loop\n\n```json\n'+json.dumps(packet,indent=2,sort_keys=True)+'\n```\n')
    print(json.dumps(packet,indent=2,sort_keys=True)); return rc
if __name__=='__main__': raise SystemExit(main())
