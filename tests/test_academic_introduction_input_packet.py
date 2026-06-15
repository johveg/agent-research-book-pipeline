import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "academic_introduction_input_packet.py"


def load_module():
    spec = importlib.util.spec_from_file_location("academic_introduction_input_packet", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def minimal_inputs(tmp_path: Path):
    contract = tmp_path / "contract.json"
    contract.write_text(json.dumps({
        "minimum_requirements_for_academic_chapter_prose": ["purpose", "thesis", "definitions", "limitations"],
        "hard_safety_flags": {
            "author_allowed": False,
            "publication_approved": False,
            "eligible_for_claim_insertion": False,
            "eligible_for_authoring": False,
            "eligible_for_publication": False,
            "chapter_update_allowed": False,
        },
    }), encoding="utf-8")
    structure = tmp_path / "structure.md"
    structure.write_text("# Structure\n\nIntroduction, methodology, conceptual framework.\n", encoding="utf-8")
    inv = tmp_path / "inventory.json"
    inv.write_text(json.dumps({
        "page_count": 2,
        "pages": [
            {"path": "docs/book/preface.md", "title": "Preface", "recommended_academic_role": "front_matter", "missing_methodology_support": True, "missing_conceptual_framework": True, "missing_literature_support": False},
            {"path": "docs/book/01.md", "title": "Agent loop", "recommended_academic_role": "core_concept_chapter", "missing_methodology_support": True, "missing_conceptual_framework": False, "missing_literature_support": True},
        ],
    }), encoding="utf-8")
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps({
        "recommended_next_run": "Run 50 — Draft Introduction, thesis, scope, contribution, and limitations as report-only manuscript prose.",
        "rewrite_priority_sequence": [{"path": "docs/book/01.md", "recommended_academic_role": "core_concept_chapter"}],
    }), encoding="utf-8")
    book = tmp_path / "docs" / "book"
    book.mkdir(parents=True)
    (book / "01.md").write_text("# Agent loop\n\nA practitioner note about loops.\n", encoding="utf-8")
    return contract, structure, inv, plan, book


def test_input_packet_required_fields_and_false_flags(tmp_path):
    mod = load_module()
    contract, structure, inv, plan, book = minimal_inputs(tmp_path)
    packet = mod.build_packet(contract, structure, inv, plan, book)
    for key in ["proposed_working_title", "proposed_audience", "proposed_thesis_candidates", "evidence_use_policy_summary", "do_not_say_list", "citation_evidence_constraints"]:
        assert packet.get(key)
    assert packet["publication_safety_flags"] == mod.FALSE_FLAGS
    assert packet["safety_flags"] == mod.FALSE_FLAGS
    assert packet["disposition"] == "report_only_manuscript_draft"
    text = json.dumps(packet).lower()
    assert "proves" not in text
    assert "established discipline" not in text


def test_missing_input_fails_closed(tmp_path):
    mod = load_module()
    contract, structure, inv, plan, book = minimal_inputs(tmp_path)
    missing = tmp_path / "missing.json"
    result = mod.build_packet(missing, structure, inv, plan, book)
    assert result["ok"] is False
    assert result["disposition"] == "introduction_draft_failed_closed"
    assert result["publication_safety_flags"] == mod.FALSE_FLAGS


def test_cli_writes_reports_only_and_does_not_touch_book(tmp_path):
    contract, structure, inv, plan, book = minimal_inputs(tmp_path)
    before = {p.name: p.read_text(encoding="utf-8") for p in book.glob("*.md")}
    out_json = tmp_path / "out.json"
    out_md = tmp_path / "out.md"
    proc = subprocess.run([
        sys.executable, str(SCRIPT),
        "--quality-contract", str(contract),
        "--structure-plan", str(structure),
        "--inventory", str(inv),
        "--conversion-plan", str(plan),
        "--book-dir", str(book),
        "--output-json", str(out_json),
        "--output-md", str(out_md),
    ], text=True, capture_output=True)
    assert proc.returncode == 0, proc.stderr
    assert out_json.exists() and out_md.exists()
    assert before == {p.name: p.read_text(encoding="utf-8") for p in book.glob("*.md")}
    data = json.loads(out_json.read_text(encoding="utf-8"))
    assert data["ok"] is True
    assert data["publication_safety_flags"] == data["safety_flags"]
