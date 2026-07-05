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

    (book_dir / "bad.md").write_text("# Good\n\nResolved statement [1].\n\n## References\n\n[1] [Source](https://example.com/source).\n", encoding="utf-8")
    result = run_script("verify_book_citations.py", "--book-dir", str(book_dir))
    assert result.returncode == 0, result.stderr + result.stdout


def test_publication_gate_blocks_citation_reference_mismatch(tmp_path):
    book_dir = tmp_path / "book"
    book_dir.mkdir()
    bad = book_dir / "bad-mismatch.md"
    bad.write_text(
        "# Bad mismatch\n\n"
        "This claim cites [1] and [2].\n\n"
        "## References\n\n"
        "[1] Source one.\n",
        encoding="utf-8",
    )
    result = run_script("verify_book_citations.py", "--book-dir", str(book_dir))
    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["status"] == "blocked"
    assert payload["citation_reference_mismatch_hits"]
    hit = payload["citation_reference_mismatch_hits"][0]
    assert hit["missing_reference_numbers"] == [2]


def test_citation_resolver_formats_references_as_hyperlinks(tmp_path):
    book_dir = tmp_path / "book"
    book_dir.mkdir()
    page = book_dir / "chapter.md"
    page.write_text(
        "# Chapter\n\nClaim {{cite:src_aaaaaaaaaaaaaaaaaaaa}} and {{cite:src_bbbbbbbbbbbbbbbbbbbb}}.\n",
        encoding="utf-8",
    )

    registry = {
        "schema_version": 1,
        "generated_at": "2026-07-05T00:00:00Z",
        "authority": "test",
        "records": [
            {
                "source_id": "src_aaaaaaaaaaaaaaaaaaaa",
                "title": "Hermes agent docs",
                "publisher": "Hermes Atlas",
                "canonical_url": "https://hermesatlas.com/projects/NousResearch/hermes-agent",
                "original_url": "https://hermesatlas.com/projects/NousResearch/hermes-agent",
                "source_type": "web",
                "privacy_publication_status": "public",
            },
            {
                "source_id": "src_bbbbbbbbbbbbbbbbbbbb",
                "title": "Hermes README",
                "publisher": "GitHub",
                "canonical_url": "https://github.com/NousResearch/hermes-agent",
                "original_url": "https://github.com/NousResearch/hermes-agent",
                "source_type": "web",
                "privacy_publication_status": "public",
            },
        ],
    }
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(json.dumps(registry), encoding="utf-8")

    result = run_script("resolve_book_citations.py", "--book-dir", str(book_dir), "--registry", str(registry_path))
    assert result.returncode == 0, result.stderr + result.stdout
    text = page.read_text(encoding="utf-8")
    assert "[1] [Hermes Atlas](https://hermesatlas.com/projects/NousResearch/hermes-agent)\n\n" in text
    assert "2026-" not in text


def test_citation_resolver_normalizes_legacy_reference_lines(tmp_path):
    book_dir = tmp_path / "book"
    book_dir.mkdir()
    page = book_dir / "chapter.md"
    page.write_text(
        "# Chapter\n\nSupported point [1].\n\n## References\n\n"
        "[1] \"Hermes\", hermesatlas.com, 2026-06-11T17:33:13Z, https://hermesatlas.com/projects/NousResearch/hermes-agent.\n",
        encoding="utf-8",
    )

    result = run_script("resolve_book_citations.py", "--book-dir", str(book_dir))
    assert result.returncode == 0, result.stderr + result.stdout
    text = page.read_text(encoding="utf-8")
    assert "[1] [Hermes](https://hermesatlas.com/projects/NousResearch/hermes-agent)" in text
    assert "2026-06-11T17:33:13Z" not in text


def test_citation_resolver_adds_blank_lines_between_existing_reference_entries(tmp_path):
    book_dir = tmp_path / "book"
    book_dir.mkdir()
    page = book_dir / "chapter.md"
    page.write_text(
        "# Chapter\n\nSupported point [1] [2].\n\n## References\n\n"
        "[1] [Source one](https://example.com/one).\n"
        "[2] [Source two](https://example.com/two).\n",
        encoding="utf-8",
    )

    result = run_script("resolve_book_citations.py", "--book-dir", str(book_dir))
    assert result.returncode == 0, result.stderr + result.stdout
    text = page.read_text(encoding="utf-8")
    assert "[1] [Source one](https://example.com/one).\n\n[2] [Source two](https://example.com/two)." in text


def test_publication_gate_blocks_missing_blank_line_between_references(tmp_path):
    book_dir = tmp_path / "book"
    book_dir.mkdir()
    (book_dir / "cramped.md").write_text(
        "# Cramped\n\nSupported point [1] [2].\n\n## References\n\n"
        "[1] [Source one](https://example.com/one).\n"
        "[2] [Source two](https://example.com/two).\n",
        encoding="utf-8",
    )
    result = run_script("verify_book_citations.py", "--book-dir", str(book_dir))
    assert result.returncode == 2
    payload = json.loads(result.stdout)
    failures = payload["legacy_reference_style_hits"][0]["style_failures"]
    assert "missing_blank_line_after_reference" in failures


def test_publication_gate_blocks_legacy_metadata_reference_style(tmp_path):
    book_dir = tmp_path / "book"
    book_dir.mkdir()
    (book_dir / "legacy.md").write_text(
        "# Legacy\n\nSupported point [1].\n\n## References\n\n"
        "[1] \"Hermes\", hermesatlas.com, 2026-06-11T17:33:13Z, https://hermesatlas.com/projects/NousResearch/hermes-agent, quality A.\n",
        encoding="utf-8",
    )
    result = run_script("verify_book_citations.py", "--book-dir", str(book_dir))
    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["status"] == "blocked"
    assert payload["legacy_reference_style_hits"]
    failures = payload["legacy_reference_style_hits"][0]["style_failures"]
    assert "missing_markdown_hyperlink" in failures
    assert "contains_timestamp" in failures
    assert "contains_quality_label" in failures


def test_publication_gate_blocks_orphan_and_duplicate_references(tmp_path):
    book_dir = tmp_path / "book"
    book_dir.mkdir()
    bad = book_dir / "bad-refs.md"
    bad.write_text(
        "# Bad refs\n\n"
        "This claim cites [1].\n\n"
        "## References\n\n"
        "[1] Source one.\n"
        "[1] Duplicate source one.\n"
        "[2] Orphan source two.\n",
        encoding="utf-8",
    )
    result = run_script("verify_book_citations.py", "--book-dir", str(book_dir))
    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["status"] == "blocked"
    assert payload["citation_reference_mismatch_hits"]
    hit = payload["citation_reference_mismatch_hits"][0]
    assert hit["duplicate_reference_numbers"] == [1]
    assert hit["orphan_reference_numbers"] == [2]
