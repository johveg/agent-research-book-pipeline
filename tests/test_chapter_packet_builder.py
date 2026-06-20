import json, subprocess, sys
from pathlib import Path
from scripts.chapter_packet_builder import build_packet
ROOT=Path(__file__).resolve().parents[1]

def test_packet_contains_required_fields_and_false_flags(tmp_path):
    chapter=tmp_path/'evidence-led.md'
    chapter.write_text('# 1. The Agent Loop\n\n## Current evidence status\n\n- status supported claim.\n\n## Source/claim mapping\n\nBullet 1 maps to supported claim.\n\n## References\n[1] Example.\n')
    packet=build_packet(chapter, ROOT/'docs/research/claims.md', ROOT/'data/source_registry.json', ROOT/'config/manuscript_quality_contract.json')
    for key in ['chapter_slug','current_title','proposed_title','current_problem','chapter_thesis','allowed_claims','caveated_claims','traceability_map','publication_safety_flags']:
        assert key in packet
    assert packet['current_problem']=='evidence_led_needs_manuscript_conversion'
    assert all(v is False for k,v in packet['publication_safety_flags'].items() if k!='report_only_packet')
    assert packet['publication_safety_flags']['report_only_packet'] is True

def test_traceability_report_only_and_missing_inputs_fail_closed(tmp_path):
    outj=tmp_path/'packet.json'; outm=tmp_path/'packet.md'
    proc=subprocess.run([sys.executable, str(ROOT/'scripts/chapter_packet_builder.py'), '--chapter', str(tmp_path/'missing.md'), '--claims', str(ROOT/'docs/research/claims.md'), '--source-registry', str(ROOT/'data/source_registry.json'), '--quality-contract', str(ROOT/'config/manuscript_quality_contract.json'), '--output-json', str(outj), '--output-md', str(outm)], text=True)
    assert proc.returncode==2
    data=json.loads(outj.read_text())
    assert data['failed_closed'] is True
    assert data['publication_safety_flags']['chapter_update_allowed'] is False
