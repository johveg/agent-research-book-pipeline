import json, subprocess, sys
from pathlib import Path
from scripts.manuscript_quality_gate import evaluate_manuscript
ROOT=Path(__file__).resolve().parents[1]

def test_quality_gate_passes_narrative_and_blocks_metadata():
    good='# 1. The Agent Loop\n\nThis chapter argues that agents are best understood as loops rather than isolated exchanges. The evidence is limited but useful. [1]\n\n## 1.1 From Prompt to Loop\n\nThe argument develops through definitions and synthesis across sources. It does not claim consensus. [1] [2]\n\n## 1.2 Limitations and Transition\n\nThe evidence remains practitioner-led, so the chapter uses cautious language.\n\n## References\n[1] A.\n[2] B.'
    res=evaluate_manuscript(good)
    assert res['manuscript_quality_passed'] is True
    bad='# X\n\n## Source/claim mapping\nBullet 1 maps to supported claim. quality A.'
    assert evaluate_manuscript(bad)['manuscript_quality_passed'] is False

def test_cli_outputs_fail_closed_for_missing_input(tmp_path):
    proc=subprocess.run([sys.executable, str(ROOT/'scripts/manuscript_quality_gate.py'), '--draft-md', str(tmp_path/'missing.md'), '--quality-contract', str(ROOT/'config/manuscript_quality_contract.json'), '--academic-contract', str(ROOT/'config/academic_book_quality_contract.json'), '--output-json', str(tmp_path/'out.json'), '--output-md', str(tmp_path/'out.md')])
    assert proc.returncode==2
    assert json.loads((tmp_path/'out.json').read_text())['publication_candidate'] is False
