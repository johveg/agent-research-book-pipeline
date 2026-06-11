import sqlite3
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


def test_extract_entities_populates_entities_from_existing_sources():
    result = run_script("extract_entities.py", "--limit", "50")
    assert result.returncode == 0, result.stderr + result.stdout
    con = sqlite3.connect(ROOT / ".var" / "book.sqlite")
    count = con.execute("select count(*) from entities").fetchone()[0]
    assert count > 0
    generic = {"hashtag", "urn", "https", "query", "search", "result", "captured", "linkedin", "post", "visible"}
    names = {r[0].lower() for r in con.execute("select canonical_name from entities")}
    assert not (generic & names)


def test_extract_claims_populates_candidate_claims_with_sources():
    result = run_script("extract_claims.py", "--limit", "50")
    assert result.returncode == 0, result.stderr + result.stdout
    con = sqlite3.connect(ROOT / ".var" / "book.sqlite")
    count = con.execute("select count(*) from claims").fetchone()[0]
    assert count > 0
    missing_sources = con.execute(
        "select count(*) from claims c where not exists (select 1 from claim_sources cs where cs.claim_id = c.id)"
    ).fetchone()[0]
    assert missing_sources == 0
    statuses = {r[0] for r in con.execute("select distinct status from claims")}
    assert "candidate" in statuses


def test_generated_editorial_pages_are_populated():
    for script in ["update_entity_pages.py", "update_claims_page.py", "synthesize_chapters.py"]:
        result = run_script(script, "--run-id", "test-editorial")
        assert result.returncode == 0, result.stderr + result.stdout
    entity_index = ROOT / "docs" / "entities" / "index.md"
    claims_page = ROOT / "docs" / "research" / "claims.md"
    assert entity_index.exists()
    assert "Source count" in entity_index.read_text()
    assert "Candidate claims" in claims_page.read_text()
    assert len(claims_page.read_text().splitlines()) > 10


def test_verify_editorial_ingestion_passes_after_pipeline():
    result = run_script("verify_editorial_ingestion.py")
    assert result.returncode == 0, result.stderr + result.stdout
