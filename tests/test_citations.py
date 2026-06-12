import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_script(name, *args):
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / name), *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )


def test_source_registry_exports_known_source_metadata():
    result = run_script("export_source_registry.py")
    assert result.returncode == 0, result.stderr + result.stdout
    path = ROOT / "data" / "source_registry.json"
    assert path.exists()
    payload = json.loads(path.read_text())
    records = {r["source_id"]: r for r in payload["records"]}
    for source_id in [
        "src_384bcc1123ee303676b1",
        "src_80c8c50e6406c7e7fc95",
        "src_e0864997d036665b77f9",
        "src_3eb174da3717ef674f19",
    ]:
        assert source_id in records
        rec = records[source_id]
        assert rec["title"]
        assert rec["canonical_url"] or rec["original_url"] or rec["archive_path"]
        assert rec["quality_score"]
        assert rec["source_type"]


def test_citation_resolver_turns_internal_tokens_into_numbered_references(tmp_path):
    run_script("export_source_registry.py")
    book_dir = tmp_path / "book"
    book_dir.mkdir()
    page = book_dir / "chapter.md"
    page.write_text(
        "# Chapter\n\nLoop engineering claim {{cite:src_384bcc1123ee303676b1}} and `src_80c8c50e6406c7e7fc95`.\n",
        encoding="utf-8",
    )
    result = run_script("resolve_book_citations.py", "--book-dir", str(book_dir))
    assert result.returncode == 0, result.stderr + result.stdout
    text = page.read_text(encoding="utf-8")
    assert "{{cite:" not in text
    assert "src_" not in text
    prose = text.split("## References", 1)[0]
    assert "[1]" in prose and "[2]" in prose
    assert "## References" in text


def test_resolver_blocks_unpublishable_origin_without_emitting_raw_ids(tmp_path):
    run_script("export_source_registry.py")
    book_dir = tmp_path / "book"
    book_dir.mkdir()
    page = book_dir / "chapter.md"
    # This known claim currently resolves to a source requiring human review.
    page.write_text("# Chapter\n\nSensitive claim {{cite:claim_1e6da5e353cab67ed16c}}.\n", encoding="utf-8")
    result = run_script("resolve_book_citations.py", "--book-dir", str(book_dir))
    assert result.returncode == 2
    text = page.read_text(encoding="utf-8")
    assert "claim_" not in text
    assert "src_" not in text
    assert "[unresolved citation]" not in text
    assert "source origin metadata not publishable" in result.stdout


def test_publication_gate_blocks_raw_ids_in_book_prose(tmp_path):
    book_dir = tmp_path / "book"
    book_dir.mkdir()
    (book_dir / "bad.md").write_text("# Bad\n\nRaw src_384bcc1123ee303676b1 in prose.\n", encoding="utf-8")
    result = run_script("verify_book_citations.py", "--book-dir", str(book_dir))
    assert result.returncode == 2
    assert "raw_id_hits" in result.stdout

    (book_dir / "bad.md").write_text("# Good\n\nResolved statement [1].\n\n## References\n\n[1] Source.\n", encoding="utf-8")
    result = run_script("verify_book_citations.py", "--book-dir", str(book_dir))
    assert result.returncode == 0, result.stderr + result.stdout
