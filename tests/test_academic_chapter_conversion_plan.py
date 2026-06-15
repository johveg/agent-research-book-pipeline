import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "academic_chapter_conversion_plan.py"


def load_module():
    spec = importlib.util.spec_from_file_location("academic_chapter_conversion_plan", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def write_inputs(tmp_path: Path):
    inv = tmp_path / "reports" / "inventory.json"
    inv.parent.mkdir(parents=True)
    inv.write_text(
        json.dumps(
            {
                "run_id": "run49",
                "page_count": 3,
                "pages": [
                    {
                        "path": "docs/book/preface.md",
                        "title": "Preface",
                        "recommended_academic_role": "front_matter",
                        "apparent_current_role": "preface_or_reader_guide",
                        "academic_maturity_level": 3,
                        "rewrite_priority": 4,
                        "recommended_next_action": "keep and revise scope",
                        "appendix_only_recommended": False,
                        "reports_only_recommended": False,
                    },
                    {
                        "path": "docs/book/01-the-agent-loop.md",
                        "title": "Agent Loop",
                        "recommended_academic_role": "core_concept_chapter",
                        "apparent_current_role": "academic_chapter_candidate",
                        "academic_maturity_level": 4,
                        "rewrite_priority": 2,
                        "recommended_next_action": "strengthen literature and definitions",
                        "appendix_only_recommended": False,
                        "reports_only_recommended": False,
                    },
                    {
                        "path": "docs/book/open-questions.md",
                        "title": "Open Questions",
                        "recommended_academic_role": "research_agenda",
                        "apparent_current_role": "open_questions_or_research_agenda",
                        "academic_maturity_level": 2,
                        "rewrite_priority": 1,
                        "recommended_next_action": "move to reports-only planning until synthesized",
                        "appendix_only_recommended": False,
                        "reports_only_recommended": True,
                    },
                ],
                "summary_counts": {
                    "missing_literature_support": 2,
                    "missing_methodology_support": 1,
                    "missing_conceptual_framework": 1,
                    "appendix_candidate": 0,
                    "reports_only": 1,
                },
            }
        ),
        encoding="utf-8",
    )
    contract = tmp_path / "config" / "academic_book_quality_contract.json"
    contract.parent.mkdir(parents=True)
    contract.write_text(json.dumps({"name": "contract"}), encoding="utf-8")
    structure = tmp_path / "book" / "academic_structure_plan.md"
    structure.parent.mkdir(parents=True)
    structure.write_text("# Structure\n", encoding="utf-8")
    return inv, contract, structure


def test_conversion_plan_maps_pages_and_recommends_run50(tmp_path):
    module = load_module()
    inv, contract, structure = write_inputs(tmp_path)
    plan = module.build_conversion_plan(inv, contract, structure, run_id="run49")
    assert plan["disposition"] == "rewrite_plan_created"
    assert plan["safety_flags"]["publication_approved"] is False
    assert plan["do_not_rewrite_yet"] is True
    assert plan["candidate_run50_scope"].startswith("Draft Introduction")
    assert plan["recommended_next_run"] == "Run 50 — Draft Introduction, thesis, scope, contribution, and limitations as report-only manuscript prose."
    assert "docs/book/open-questions.md" in plan["pages_to_keep_as_reports_only"]
    assert "introduction" in plan["missing_front_matter"]


def test_conversion_plan_cli_writes_reports_without_book_mutation(tmp_path):
    inv, contract, structure = write_inputs(tmp_path)
    out_json = tmp_path / "reports" / "plan.json"
    out_md = tmp_path / "reports" / "plan.md"
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--inventory",
            str(inv),
            "--quality-contract",
            str(contract),
            "--structure-plan",
            str(structure),
            "--output-json",
            str(out_json),
            "--output-md",
            str(out_md),
        ],
        text=True,
        capture_output=True,
    )
    assert proc.returncode == 0, proc.stderr
    data = json.loads(out_json.read_text(encoding="utf-8"))
    assert data["disposition"] == "rewrite_plan_created"
    assert data["docs_book_modified"] is False
    assert out_md.exists()


def test_conversion_plan_fails_closed_on_missing_inventory(tmp_path):
    module = load_module()
    _inv, contract, structure = write_inputs(tmp_path)
    plan = module.build_conversion_plan(tmp_path / "missing.json", contract, structure, run_id="bad")
    assert plan["disposition"] == "academic_inventory_failed_closed"
    assert plan["safety_flags"]["eligible_for_publication"] is False
