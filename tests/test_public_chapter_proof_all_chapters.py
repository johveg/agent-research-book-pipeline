import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "public_chapter_proof.py"


def test_all_local_book_chapters_report_every_configured_chapter(tmp_path):
    out = tmp_path / "all.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--all-local-book-chapters",
            "--contract-json",
            str(ROOT / "config" / "book_manuscript_production_contract.json"),
            "--repo-root",
            str(ROOT),
            "--output-json",
            str(out),
        ],
        text=True,
        capture_output=True,
    )
    assert out.exists(), proc.stderr
    data = json.loads(out.read_text())
    configured = set(json.loads((ROOT / "config" / "book_manuscript_production_contract.json").read_text())["chapters"])
    assert set(data["chapter_results"]) == configured
    assert data["total_chapters"] == len(configured)
    assert data["source_kind"] == "all_local_book_chapters"
    assert proc.returncode == (0 if data["ok"] else 2)


def test_all_chapter_gate_fails_when_any_configured_chapter_is_evidence_ledger(tmp_path):
    root = tmp_path / "repo"
    docs = root / "docs" / "book"
    docs.mkdir(parents=True)
    contract = tmp_path / "contract.json"
    contract.write_text(json.dumps({
        "chapters": {
            "good": {"target_path": "docs/book/good.md", "title": "Good"},
            "bad": {"target_path": "docs/book/bad.md", "title": "Bad"},
        }
    }))
    (docs / "good.md").write_text(
        "# Good\n\nThe central argument of this chapter establishes a booklike frame with evidence limits and references rather than a ledger. [1]\n\n"
        "A second sustained paragraph gives the reader context and explains why the chapter remains cautious about its claims while still using references. [2]\n\n"
        "A third sustained paragraph keeps the prose analytical, names evidence limits, and integrates references without internal source machinery. [3]\n\n"
        "A fourth sustained paragraph returns to the central argument and uses references to close the chapter's public-facing account. [1] [2] [3]\n\n## References\n[1] Ref.\n[2] Ref.\n[3] Ref.\n"
    )
    (docs / "bad.md").write_text("# Bad\n\n## Current Evidence Status\n\n- status supported, quality A\n\n## Source/claim mapping\nBullet 1 maps to supported claim. [1]\n")
    out = tmp_path / "all.json"
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--all-local-book-chapters", "--contract-json", str(contract), "--repo-root", str(root), "--output-json", str(out)],
        text=True,
        capture_output=True,
    )
    data = json.loads(out.read_text())
    assert proc.returncode == 2
    assert data["ok"] is False
    assert data["failed_chapters"] == ["bad"]
    assert "evidence_ledger_language_present" in data["chapter_results"]["bad"]["failed_checks"]
