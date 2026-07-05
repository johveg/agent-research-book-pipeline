import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "catalogue_linkedin_intake.py"


def test_catalogue_linkedin_intake_appends_sanitized_relevance_entry(tmp_path):
    catalogue = tmp_path / "catalogue.jsonl"
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--catalogue",
            str(catalogue),
            "--url",
            "https://www.linkedin.com/posts/example_activity-123",
            "--title",
            "Agent observability with Telegram ops",
            "--text",
            "Hermes style autonomous agents need monitoring, tool traces, and gateway alerts.",
            "--archive-dir",
            "data/posts/example",
            "--hermione-relevance",
            "Relevant to Hermione's ops feedback loop.",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    payload = json.loads(result.stdout)
    assert payload["ok"] is True

    lines = catalogue.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["source_platform"] == "linkedin"
    assert entry["input_url"].startswith("https://www.linkedin.com/posts/example")
    assert "observability-for-agents" in entry["book_relevance"]["candidate_chapters"]
    assert entry["hermione_relevance"]["score"] > 0
    assert entry["archive_dir"] == "data/posts/example"
    assert entry["book_relevance"]["evidence_strength"] == "discovery-only"
    joined = json.dumps(entry)
    assert "TELEGRAM_BOT_TOKEN" not in joined
    assert "AAE0" not in joined


def test_catalogue_linkedin_intake_uses_metadata_comments_and_media(tmp_path):
    archive = tmp_path / "post"
    archive.mkdir()
    metadata = archive / "metadata.json"
    metadata.write_text(
        json.dumps(
            {
                "input_url": "https://www.linkedin.com/feed/update/urn:li:activity:123",
                "canonical_url": "https://www.linkedin.com/posts/example_activity-123",
                "post": {"headline": "MCP tool integration", "article_body": "MCP connectors for AI agents."},
                "author": {"name": "Example Author"},
                "comments": {"count_visible_in_guest_html": 2},
                "media": [{"type": "image", "local_path": "media/image-1.jpg"}],
            }
        ),
        encoding="utf-8",
    )
    catalogue = tmp_path / "catalogue.jsonl"
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--catalogue", str(catalogue), "--metadata", str(metadata)],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    entry = json.loads(catalogue.read_text(encoding="utf-8"))
    assert entry["author"] == "Example Author"
    assert entry["archive_dir"] == str(archive)
    assert entry["visible_comment_summary"] == "2 guest-visible comment(s)."
    assert entry["media_summary"] == "1 media item(s) visible in archived metadata"
    assert "mcp-tools" in entry["book_relevance"]["candidate_chapters"]
