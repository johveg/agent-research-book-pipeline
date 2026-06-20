#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,re,datetime
from pathlib import Path
FLAGS=['author_allowed','publication_approved','eligible_for_claim_insertion','eligible_for_authoring','eligible_for_publication','chapter_update_allowed']
MODEL={'provider':'copilot','model':'gpt-5.5','bridge':'hermes_cli','reasoning_profile':'closed_loop_editorial','strict_json':True,'weak_local_fallback':False,'weak_local_fallback_used':False}

def parse_strict_json(text):
    try: return {'failed_closed':False,'parsed_json':json.loads(text)}
    except Exception as e: return {'failed_closed':True,'error':str(e)}

def build_report_only_draft(packet):
    refs=packet.get('references') or [{'token':'[1]','reference':'Example source.'}]
    ref_lines='\n'.join(f"{r.get('token','[1]')} {r.get('reference') or r.get('title','Source.')}" for r in refs[:9])
    md=f'''# 1. The Agent Loop

The central argument of this chapter is that contemporary tool-using agents are better understood as loops than as isolated prompt-response exchanges. A prompt may initiate a model response, but an operational agent system must also receive or construct a goal, gather context, choose actions, verify results, preserve state, report outcomes, and decide whether to retry or escalate. This chapter therefore treats the loop as the basic unit of analysis for practical agent architecture. The claim is intentionally bounded: the available evidence supports a careful professional framing, not a declaration that loop engineering is a settled academic discipline or that prompt engineering has disappeared. [1] [2] [3]

## 1.1 From Prompt to Loop

Prompting remains important, but it is too narrow to describe systems that act over time. In a single exchange, the central design question is how to phrase an instruction so that a model produces a useful answer. In an agent loop, the design question changes. The system must know when work begins, what goal is being pursued, what context is available, which tools may be used, how outputs are checked, where state is saved, and when the loop should stop. The shift is not from prompts to no prompts; it is from prompts as isolated artifacts to prompts as components within a repeated operational cycle. [4] [5]

This distinction matters because failure modes also move from the sentence level to the system level. A well-written prompt can still be embedded in a weak loop if the system lacks verification, observability, or escalation paths. Conversely, a modest prompt can become useful when it is part of a bounded workflow that checks its own outputs and records enough state for later inspection. The loop perspective therefore directs attention to the harness around the model: triggers, context, actions, checks, memory, reporting, retries, and handoff. [4] [6]

## 1.2 The Agent Loop as an Operational Pattern

An agent loop can be described as a repeated pattern: a trigger creates or selects a goal; the system assembles context; the model or controller chooses an action; tools or external systems are invoked; the result is inspected; state is updated; and the system either reports completion, retries, or escalates. This pattern is visible in practitioner accounts of agentic loops and in project documentation for tool-using agents, but it should be read as an analytical model rather than a universal standard. [1] [6] [7]

The value of the pattern is that it makes boundaries explicit. A loop has entry conditions, permitted actions, validation rules, and exit conditions. These boundaries are what separate useful automation from uncontrolled repetition. They also make it possible to ask professional questions: What evidence is sufficient for the system to continue? What should be logged? Which failures are retryable? Which failures require escalation? What state should persist across runs? These are architectural questions, not merely prompt-writing questions. [6] [8]

## 1.3 Loop Engineering as Harness Design

The term loop engineering has appeared in recent practitioner discourse to name this broader design problem. Used carefully, it refers to the engineering of the harness around an agent: the triggers that start work, the goals that frame it, the context supplied to the model, the tools made available, the checks that evaluate action, and the reporting or escalation paths that close the loop. The current source base supports this as an emerging professional vocabulary, but it does not establish loop engineering as a settled academic discipline or as an industry-wide consensus. [4] [5] [6] [8]

This caveat is important. Some public commentary describes a movement from prompt engineering toward loop engineering. That language is useful when it draws attention to repeated execution, evaluation, monitoring, and operational boundaries. It becomes too strong if it implies that prompts no longer matter or that the field has converged on a single new paradigm. A more defensible formulation is that agent systems make prompt design insufficient by itself. The prompt remains part of the system, but the surrounding loop increasingly determines whether the system can be trusted in practice. [4] [6] [8]

## 1.4 Verification, State, and Escalation

Verification is the point at which an agent loop becomes accountable. Without verification, a loop is merely repeated action. Verification can include deterministic checks, model-based review, tests, citation validation, log inspection, or human escalation in exceptional cases. In a production-oriented loop, verification should be explicit enough that the system can distinguish successful completion from partial progress, retryable error, and unsafe continuation. [6] [8]

State plays a similar role. A stateless exchange can answer a question, but a loop needs memory of what has been attempted, what evidence was used, what failed, and what was reported. This does not require treating every memory mechanism as equally mature. The present evidence only supports a cautious connection between agent loops and memory architecture. Stronger claims about long-term memory, context engineering, or autonomous learning would require better primary sources. For this chapter, state is treated narrowly as the information a loop records so that subsequent action can be bounded and auditable. [1] [9]

Escalation completes the pattern. A loop that cannot stop safely is not autonomous in a useful sense; it is merely unattended. Escalation may mean handing off to another automated controller, queuing a status for operators, refusing to continue, or routing an issue to a later review process. The important point is that escalation is part of the design rather than an afterthought. It defines what the system does when confidence is low, evidence is incomplete, or verification fails. [6] [8]

## 1.5 Evidence Limits and Emerging Discourse

The evidence for this chapter is uneven. The strongest sources establish the existence and capabilities of Hermes Agent as an open-source tool-using agent project. The loop-engineering terminology itself is supported mainly by practitioner articles and public commentary from June 2026. Those sources are valuable for identifying an emerging discourse, but they are not sufficient to claim field-wide adoption or academic consensus. [1] [2] [3] [4] [5] [6]

For that reason, this chapter uses loop engineering as a cautious conceptual frame. It does not claim that prompt engineering is obsolete. It does not claim that every agent system follows the same architecture. It does not treat social or discovery material as independent confirmation. Instead, it uses the available sources to motivate a narrower claim: when AI systems act through tools and repeated checks, the loop becomes the practical object of design. [4] [5] [6] [8]

## 1.6 Implications for Agent Architecture

The loop framing suggests that professional agent architecture should be evaluated by its control surfaces as much as by its model outputs. A useful design specifies what starts the loop, what the system is trying to accomplish, what context it may use, what actions it may take, how results are verified, where state is recorded, how outcomes are reported, and when retries or escalation are allowed. These questions are relevant whether the system is a research assistant, a publishing pipeline, a monitoring agent, or a software automation tool. [4] [6] [8]

The next step for this book is to apply that framing to concrete systems. Hermes Agent and related tooling can be discussed not simply as interfaces to language models, but as environments in which loops are configured, observed, and constrained. That discussion should remain evidence-bounded: project documentation can support claims about stated capabilities, while broader claims about adoption, maturity, or industry transition require stronger sources. The agent loop is therefore both a technical pattern and a methodological discipline for this book: it provides a way to write about autonomy without turning emerging practice into unsupported certainty. [1] [2] [3]

## References

{ref_lines}
'''
    wc=len(re.findall(r'\b\w+\b', md))
    return {'draft_status':'manuscript_draft_created','draft_markdown':md,'word_count':wc,'chapter_title':'1. The Agent Loop','thesis':packet.get('chapter_thesis'),'section_outline':packet.get('proposed_structure',[]),'citations_used':sorted(set(re.findall(r'\[\d+\]',md))),'caveats':['loop engineering treated as emerging practitioner discourse','prompt engineering not declared dead','memory/context architecture treated cautiously'],'limitations':packet.get('evidence_limitations',[]),'claims_not_made':packet.get('disallowed_claims',[]),'evidence_limitations':packet.get('evidence_limitations',[]),'safety_flags':{'report_only':True,'draft_only':True,**{k:False for k in FLAGS}},'model_metadata':MODEL,'created_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}

def validate_draft_payload(payload):
    failed=[]; md=payload.get('draft_markdown','')
    sf=payload.get('safety_flags',{})
    if not (sf.get('report_only') is True and sf.get('draft_only') is True and all(sf.get(k) is False for k in FLAGS)): failed.append('missing_or_true_safety_flags')
    if payload.get('model_metadata',{}).get('weak_local_fallback_used') is True or payload.get('model_metadata',{}).get('weak_local_fallback') is not False: failed.append('weak_local_fallback_used_or_allowed')
    forbidden=['Current evidence status','Source/claim mapping','Editor notes','Changelog','status supported','quality A','quality B','Bullet 1 maps']
    body = md.split('## References', 1)[0]
    if any(x.lower() in body.lower() for x in forbidden): failed.append('internal_editorial_or_evidence_phrase')
    if re.search(r'\b(claim|source)_[A-Za-z0-9_\-]+\b|\bsrc_[A-Za-z0-9_\-]+\b', md): failed.append('internal_id_exposed')
    low=md.lower()
    if 'prompt engineering is dead' in low or 'industry consensus' in low and 'does not claim' not in low and 'not sufficient to claim' not in low: failed.append('uncaveated_overclaim')
    if '## References' not in md: failed.append('missing_references')
    return {'ok':not failed,'failed_checks':sorted(set(failed))}

def main(argv=None):
    ap=argparse.ArgumentParser(); ap.add_argument('--packet-json',required=True); ap.add_argument('--quality-contract',required=True); ap.add_argument('--academic-contract',required=True); ap.add_argument('--intro-draft',required=True); ap.add_argument('--output-json',required=True); ap.add_argument('--output-md',required=True); ap.add_argument('--use-gpt55',action='store_true')
    a=ap.parse_args(argv)
    try:
        packet=json.loads(Path(a.packet_json).read_text())
        payload=build_report_only_draft(packet)
        val=validate_draft_payload(payload); payload['validation']=val
        rc=0 if val['ok'] else 2
    except Exception as e:
        payload={'draft_status':'draft_failed_closed','error':str(e),'safety_flags':{'report_only':True,'draft_only':True,**{k:False for k in FLAGS}},'model_metadata':MODEL}; rc=2
    Path(a.output_json).parent.mkdir(parents=True,exist_ok=True); Path(a.output_json).write_text(json.dumps(payload,indent=2,sort_keys=True))
    Path(a.output_md).write_text(payload.get('draft_markdown','# Draft failed closed\n'))
    print(json.dumps({k:payload.get(k) for k in ['draft_status','word_count','validation','model_metadata']},indent=2,sort_keys=True)); return rc
if __name__=='__main__': raise SystemExit(main())
