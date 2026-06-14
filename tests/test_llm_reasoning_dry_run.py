import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_dry_run(*args):
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "llm_reasoning_dry_run.py"), *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )


def test_llm_reasoning_dry_run_no_llm_writes_markdown_and_json(tmp_path):
    result = run_dry_run(
        "--run-id",
        "test-llm-dry-run",
        "--limit",
        "3",
        "--output-dir",
        str(tmp_path),
        "--no-llm",
    )

    assert result.returncode == 0, result.stderr + result.stdout
    md_path = tmp_path / "test-llm-dry-run-llm-reasoning-dry-run.md"
    json_path = tmp_path / "test-llm-dry-run-llm-reasoning-dry-run.json"
    assert md_path.exists()
    assert json_path.exists()

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["mode"] == "dry_run_advisory_only"
    assert payload["llm_used"] is False
    assert payload["db_modified"] is False
    assert payload["chapters_modified"] is False
    assert payload["statuses_modified"] is False
    assert payload["daily_worker_modified"] is False
    assert payload["commit_allowlist_modified"] is False
    assert set(payload["sample_counts"]) >= {"sources", "claims", "entities"}
    assert isinstance(payload["source_findings"], list)
    assert isinstance(payload["claim_findings"], list)

    md = md_path.read_text(encoding="utf-8")
    assert "Executive summary" in md
    assert "Safety assessment" in md
    assert "advisory" in md.lower()


def test_llm_reasoning_dry_run_does_not_write_docs_book_or_db(tmp_path):
    book_files = sorted((ROOT / "docs" / "book").glob("*.md"))
    before_book = {p.relative_to(ROOT): p.read_bytes() for p in book_files}
    db_path = ROOT / ".var" / "book.sqlite"
    before_db = db_path.read_bytes() if db_path.exists() else None

    result = run_dry_run(
        "--run-id",
        "test-llm-dry-run-safety",
        "--limit",
        "2",
        "--output-dir",
        str(tmp_path),
        "--no-llm",
    )

    assert result.returncode == 0, result.stderr + result.stdout
    after_book = {p.relative_to(ROOT): p.read_bytes() for p in book_files}
    assert after_book == before_book
    after_db = db_path.read_bytes() if db_path.exists() else None
    assert after_db == before_db


def test_llm_reasoning_dry_run_fail_if_high_reasoning_model_required_without_llm(tmp_path):
    result = run_dry_run(
        "--run-id",
        "test-llm-dry-run-fail-safe",
        "--limit",
        "1",
        "--output-dir",
        str(tmp_path),
        "--no-llm",
        "--fail-if-no-high-reasoning-model",
    )

    assert result.returncode != 0
    assert not (tmp_path / "test-llm-dry-run-fail-safe-llm-reasoning-dry-run.json").exists()
