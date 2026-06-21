import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_SCRIPT = ROOT / "scripts" / "book_manuscript_contract.py"
PACKET_SCRIPT = ROOT / "scripts" / "book_manuscript_input_packet.py"
PUBLISHER_SCRIPT = ROOT / "scripts" / "book_manuscript_publisher.py"


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_contract_defines_chapter_roles_and_first_queue_item():
    mod = load(CONTRACT_SCRIPT, "book_manuscript_contract")
    contract = mod.build_contract()
    assert contract["contract_name"] == "book_manuscript_production_contract"
    assert contract["global_publication_mode"] == "guarded_one_chapter_at_a_time"
    assert contract["hard_safety_flags"]["publication_approved"] is False
    assert "introduction" in contract["chapters"]
    assert contract["chapters"]["introduction"]["target_path"] == "docs/book/introduction.md"
    queue = mod.build_queue(contract)
    assert queue["queue"][0]["chapter_id"] == "introduction"
    assert queue["queue"][0]["mode"] == "guarded_publish_canary"


def test_input_packet_for_introduction_has_no_publication_flags_and_no_raw_ids(tmp_path):
    mod = load(PACKET_SCRIPT, "book_manuscript_input_packet")
    contract = {
        "chapters": {"introduction": {"target_path": "docs/book/introduction.md", "role": "front_matter_chapter", "required_sections": ["thesis", "scope", "contribution", "limitations"]}},
        "hard_safety_flags": mod.FALSE_FLAGS,
        "forbidden_reader_facing_phrases": ["Current evidence status", "Source/claim mapping"],
    }
    inventory = {"pages": [{"path": "docs/book/01-the-agent-loop.md", "title": "Agent Loop", "recommended_academic_role": "tool_case_chapter", "missing_methodology_support": True}]}
    structure = "# Structure\n\nIntroduction, Methodology, Case chapters."
    packet = mod.build_packet("introduction", contract, inventory, structure)
    assert packet["ok"] is True
    assert packet["chapter_id"] == "introduction"
    assert packet["target_path"] == "docs/book/introduction.md"
    assert packet["publication_safety_flags"] == mod.FALSE_FLAGS
    reader_text = json.dumps({k: v for k, v in packet.items() if k not in {"publication_safety_flags", "safety_flags", "citation_policy", "forbidden_reader_facing_phrases"}}, sort_keys=True).lower()
    assert "claim_" not in reader_text
    assert "source_" not in reader_text
    assert "current evidence status" not in reader_text


def test_publisher_writes_only_target_chapter_after_all_gates_pass(tmp_path):
    mod = load(PUBLISHER_SCRIPT, "book_manuscript_publisher")
    root = tmp_path
    target = root / "docs" / "book" / "introduction.md"
    other = root / "docs" / "book" / "01-the-agent-loop.md"
    target.parent.mkdir(parents=True)
    other.write_text("# Existing\n\nKeep me.\n", encoding="utf-8")
    draft = root / "draft.md"
    draft.write_text("# Introduction\n\nThis chapter argues that governable agent loops require sustained academic/professional treatment. [1]\n\n## Scope and Limitations\n\nThe evidence is limited and should be read cautiously.\n\n## References\n[1] Existing internal source context.\n", encoding="utf-8")
    packet = {"chapter_id": "introduction", "target_path": "docs/book/introduction.md", "publication_safety_flags": mod.FALSE_FLAGS, "safety_flags": mod.FALSE_FLAGS}
    quality = {"manuscript_quality_passed": True, "publication_candidate": True, "docs_book_update_allowed": True, "failed_checks": []}
    evidence = {"evidence_safety_passed": True, "publication_candidate": True, "failed_checks": []}
    report = mod.publish(root=root, packet=packet, draft_md=draft, quality_gate=quality, evidence_gate=evidence)
    assert report["ok"] is True
    assert target.exists()
    assert other.read_text(encoding="utf-8") == "# Existing\n\nKeep me.\n"
    assert "governable agent loops" in target.read_text(encoding="utf-8")


def test_publisher_can_rewrite_operating_loops_as_guarded_manuscript_chapter(tmp_path):
    mod = load(PUBLISHER_SCRIPT, "book_manuscript_publisher")
    root = tmp_path
    target = root / "docs" / "book" / "06-operating-loops.md"
    other = root / "docs" / "book" / "02-hermes.md"
    target.parent.mkdir(parents=True)
    target.write_text("# 6. Operating Loops in Production\n\n## Current evidence status\n\n- status supported, quality A\n", encoding="utf-8")
    other.write_text("# Existing\n\nKeep me.\n", encoding="utf-8")
    draft = root / "draft.md"
    draft.write_text("# 6. Operating Loops in Production\n\nThe central argument is that production loops need boundaries, verification, state, and escalation. The evidence is limited and should be read cautiously. [1]\n\n## References\n[1] Ref.\n", encoding="utf-8")
    packet = {"chapter_id": "operating_loops", "target_path": "docs/book/06-operating-loops.md", "publication_safety_flags": mod.FALSE_FLAGS, "safety_flags": mod.FALSE_FLAGS}
    quality = {"manuscript_quality_passed": True, "publication_candidate": True, "docs_book_update_allowed": True, "failed_checks": []}
    evidence = {"evidence_safety_passed": True, "publication_candidate": True, "failed_checks": []}
    report = mod.publish(root=root, packet=packet, draft_md=draft, quality_gate=quality, evidence_gate=evidence)
    assert report["ok"] is True
    assert report["published_path"] == "docs/book/06-operating-loops.md"
    assert "Current evidence status" not in target.read_text(encoding="utf-8")
    assert other.read_text(encoding="utf-8") == "# Existing\n\nKeep me.\n"


def test_publisher_refuses_failed_gate_or_wrong_target(tmp_path):
    mod = load(PUBLISHER_SCRIPT, "book_manuscript_publisher")
    root = tmp_path
    draft = root / "draft.md"
    draft.write_text("# Draft\n\nThis chapter argues cautiously. [1]\n\n## References\n[1] Ref.\n", encoding="utf-8")
    packet = {"chapter_id": "introduction", "target_path": "docs/book/02-hermes.md", "publication_safety_flags": mod.FALSE_FLAGS, "safety_flags": mod.FALSE_FLAGS}
    quality = {"manuscript_quality_passed": True, "publication_candidate": True, "docs_book_update_allowed": True}
    evidence = {"evidence_safety_passed": True, "publication_candidate": True}
    report = mod.publish(root=root, packet=packet, draft_md=draft, quality_gate=quality, evidence_gate=evidence)
    assert report["ok"] is False
    assert "target_not_allowed_for_run58" in report["failed_checks"]
    packet["target_path"] = "docs/book/introduction.md"
    quality["manuscript_quality_passed"] = False
    report = mod.publish(root=root, packet=packet, draft_md=draft, quality_gate=quality, evidence_gate=evidence)
    assert report["ok"] is False
    assert "manuscript_quality_gate_failed" in report["failed_checks"]


def test_cli_can_publish_to_temp_book(tmp_path):
    root = tmp_path
    (root / "docs" / "book").mkdir(parents=True)
    draft = root / "draft.md"
    packet = root / "packet.json"
    quality = root / "quality.json"
    evidence = root / "evidence.json"
    outj = root / "out.json"
    outm = root / "out.md"
    draft.write_text("# Introduction\n\nThis chapter argues that agent loops should be handled as governable systems. [1]\n\n## Limitations\n\nThe evidence is limited and cautious.\n\n## References\n[1] Ref.\n", encoding="utf-8")
    flags = {"author_allowed": False, "publication_approved": False, "eligible_for_claim_insertion": False, "eligible_for_authoring": False, "eligible_for_publication": False, "chapter_update_allowed": False}
    packet.write_text(json.dumps({"chapter_id": "introduction", "target_path": "docs/book/introduction.md", "publication_safety_flags": flags, "safety_flags": flags}), encoding="utf-8")
    quality.write_text(json.dumps({"manuscript_quality_passed": True, "publication_candidate": True, "docs_book_update_allowed": True}), encoding="utf-8")
    evidence.write_text(json.dumps({"evidence_safety_passed": True, "publication_candidate": True}), encoding="utf-8")
    proc = subprocess.run([sys.executable, str(PUBLISHER_SCRIPT), "--root", str(root), "--packet-json", str(packet), "--draft-md", str(draft), "--quality-gate", str(quality), "--evidence-gate", str(evidence), "--output-json", str(outj), "--output-md", str(outm)], text=True, capture_output=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert (root / "docs" / "book" / "introduction.md").exists()
    assert json.loads(outj.read_text(encoding="utf-8"))["published_path"] == "docs/book/introduction.md"
