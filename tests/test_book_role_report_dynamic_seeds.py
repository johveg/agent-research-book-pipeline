import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "book_role_report.py"
sys.path.insert(0, str(ROOT / "scripts"))


def load_module():
    spec = importlib.util.spec_from_file_location("book_role_report", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_dynamic_approved_seed_chapter_paths_are_loaded_from_topic_config(tmp_path):
    cfg = tmp_path / "chapter_discovery_topics.json"
    cfg.write_text(json.dumps({
        "approved_subjects": [
            {"status": "approved", "target_path": "docs/book/agent-runtime-security.md"},
            {"status": "monitor_only", "target_path": "docs/book/not-public.md"},
            {"status": "approved", "target_path": "docs/entities/not-book.md"},
        ]
    }), encoding="utf-8")
    mod = load_module()

    assert mod.dynamic_seed_book_paths(cfg) == {"book/agent-runtime-security.md"}


def test_seed_author_acceptance_does_not_require_internal_editor_sections():
    mod = load_module()
    text = """
# Agent Runtime Security

The central argument of this chapter is cautious and booklike, with evidence limits and a weak-signal caveat for LinkedIn/social discovery. [1]

## References

[1] Ref.
"""

    result = mod.author_acceptance_for_chapter("book/agent-runtime-security.md", text, {"book/agent-runtime-security.md"})

    assert result["structure_follows_brief"] is True
    assert result["source_claim_mapping_included"] is True
    assert result["editor_notes_included"] is True
    assert result["changelog_included"] is True
    assert result["approved_seed_chapter"] is True
