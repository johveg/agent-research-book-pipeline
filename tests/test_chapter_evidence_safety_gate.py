import json, subprocess, sys
from pathlib import Path
from scripts.chapter_evidence_safety_gate import evaluate_evidence_safety
ROOT=Path(__file__).resolve().parents[1]

def packet():
    return {'allowed_claims':['Agents can be framed as loops.'], 'caveated_claims':['Loop engineering is emerging discourse.'], 'references':[{'token':'[1]','title':'Source A'},{'token':'[2]','title':'Source B'}]}

def test_evidence_safety_passes_caveated_cited_text():
    text='# X\n\nAgents can be framed as loops, while loop engineering should be treated as emerging discourse rather than settled consensus. [1] [2]\n\n## References\n[1] Source A.\n[2] Source B.'
    res=evaluate_evidence_safety(packet(), text)
    assert res['evidence_safety_passed'] is True

def test_invented_citation_and_internal_ids_fail():
    text='# X\n\nclaim_abc source_xyz says industry consensus. [99]\n\n## References\n[1] Source A.'
    res=evaluate_evidence_safety(packet(), text)
    assert res['evidence_safety_passed'] is False
    assert 'internal_id_exposed' in res['failed_checks']

def test_cli_missing_fails_closed(tmp_path):
    proc=subprocess.run([sys.executable, str(ROOT/'scripts/chapter_evidence_safety_gate.py'), '--packet-json', str(tmp_path/'missing.json'), '--draft-md', str(tmp_path/'missing.md'), '--source-registry', str(ROOT/'data/source_registry.json'), '--claims', str(ROOT/'docs/research/claims.md'), '--output-json', str(tmp_path/'out.json'), '--output-md', str(tmp_path/'out.md')])
    assert proc.returncode==2
    assert json.loads((tmp_path/'out.json').read_text())['evidence_safety_passed'] is False
