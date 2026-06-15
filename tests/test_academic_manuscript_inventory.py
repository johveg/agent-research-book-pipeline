import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "academic_manuscript_inventory.py"


def load_module():
    spec = importlib.util.spec_from_file_location("academic_manuscript_inventory", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def write_inputs(tmp_path: Path):
    book = tmp_path / "docs" / "book"
    book.mkdir(parents=True)
    (book / "chapter.md").write_text(
        "# Agent Loop\n\n"
        "This chapter argues that autonomous agent loops require explicit safety boundaries. "
        "The term agent loop means a repeated sense-plan-act-verify cycle.\n\n"
        "Prior work and literature on workflow automation provide context for this claim. "
        "Methodologically, this chapter compares operational traces and published descriptions.\n\n"
        "A limitation is that available evidence is uneven across tools.\n\n"
        "## Summary\n\nThe chapter summarizes the argument.\n",
        encoding="utf-8",
    )
    (book / "stub.md").write_text(
        "# Evidence Stub\n\n- `src_abc123` — support_status: pending\n- claim_id: clm_1\n",
        encoding="utf-8",
    )
    contract = tmp_path / "config" / "academic_book_quality_contract.json"
    contract.parent.mkdir(parents=True)
    contract.write_text(json.dumps({"version": "test", "name": "contract"}), encoding="utf-8")
    structure = tmp_path / "book" / "academic_structure_plan.md"
    structure.parent.mkdir(parents=True)
    structure.write_text("# Structure\n\n- Introduction\n- Methodology\n", encoding="utf-8")
    return book, contract, structure


def test_inventory_classifies_pages_and_preserves_hard_false_flags(tmp_path):
    module = load_module()
    book, contract, structure = write_inputs(tmp_path)
    report = module.build_inventory(book, contract, structure, run_id="testrun", use_gpt55_review=False)

    assert report["disposition"] == "academic_inventory_completed"
    assert report["page_count"] == 2
    assert report["safety_flags"] == {
        "author_allowed": False,
        "publication_approved": False,
        "eligible_for_claim_insertion": False,
        "eligible_for_authoring": False,
        "eligible_for_publication": False,
        "chapter_update_allowed": False,
    }
    by_path = {Path(p["path"]).name: p for p in report["pages"]}
    assert by_path["chapter.md"]["apparent_current_role"] == "academic_chapter_candidate"
    assert by_path["chapter.md"]["main_chapter_allowed"] is True
    assert by_path["stub.md"]["apparent_current_role"] in {"evidence_stub", "claim_ledger_or_source_mapping"}
    assert by_path["stub.md"]["reports_only_recommended"] is True
    assert by_path["stub.md"]["evidence_stub_risk"] is True


def test_inventory_cli_writes_json_and_markdown_without_touching_book(tmp_path):
    book, contract, structure = write_inputs(tmp_path)
    before = {p.name: p.read_text(encoding="utf-8") for p in book.glob("*.md")}
    out_json = tmp_path / "reports" / "inventory.json"
    out_md = tmp_path / "reports" / "inventory.md"
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--book-dir",
            str(book),
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
    assert data["page_count"] == 2
    assert out_md.exists()
    after = {p.name: p.read_text(encoding="utf-8") for p in book.glob("*.md")}
    assert after == before


def test_inventory_fails_closed_when_contract_or_book_missing(tmp_path):
    module = load_module()
    book, contract, structure = write_inputs(tmp_path)
    missing = tmp_path / "missing.json"
    report = module.build_inventory(book, missing, structure, run_id="bad", use_gpt55_review=False)
    assert report["disposition"] == "academic_inventory_failed_closed"
    assert report["page_count"] == 0
    assert report["safety_flags"]["publication_approved"] is False


def test_gpt55_invalid_json_and_missing_safety_flags_fail_closed(tmp_path, monkeypatch):
    module = load_module()
    book, contract, structure = write_inputs(tmp_path)

    monkeypatch.setattr(module, "call_gpt55_review", lambda *a, **k: "not json")
    report = module.build_inventory(book, contract, structure, run_id="gpt", use_gpt55_review=True)
    assert all(p["gpt55_review_status"] == "failed_closed" for p in report["pages"])
    assert report["weak_local_fallback_used"] is False

    monkeypatch.setattr(module, "call_gpt55_review", lambda *a, **k: json.dumps({"academic_maturity_level": 4}))
    report2 = module.build_inventory(book, contract, structure, run_id="gpt", use_gpt55_review=True)
    assert all(p["gpt55_review_status"] == "failed_closed" for p in report2["pages"])
    assert report2["safety_flags"]["chapter_update_allowed"] is False


def test_gpt55_review_refuses_weak_or_local_fallback(tmp_path, monkeypatch):
    module = load_module()
    book, contract, structure = write_inputs(tmp_path)
    monkeypatch.setenv("TEREFO_ALLOW_WEAK_LOCAL_FALLBACK", "1")
    report = module.build_inventory(book, contract, structure, run_id="gpt", use_gpt55_review=True)
    assert report["gpt55_review_status"] == "failed_closed"
    assert report["weak_local_fallback_used"] is False
    assert any("weak/local fallback" in e for e in report["errors"])
