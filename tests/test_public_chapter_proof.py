import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "public_chapter_proof.py"


def load_module():
    spec = importlib.util.spec_from_file_location("public_chapter_proof", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_public_page_evidence_ledger_fails():
    mod = load_module()
    html_text = """
    <h1>1. The Agent Loop</h1>
    <h2>Current Evidence Status</h2>
    <ul><li>status supported, quality A</li></ul>
    <h2>Source/claim mapping</h2>
    <p>Bullet 1 maps to supported claim; source tokens [1].</p>
    """
    result = mod.evaluate_public_chapter_text(html_text, expected_title="1. The Agent Loop")
    assert result["ok"] is False
    assert "evidence_ledger_language_present" in result["failed_checks"]
    assert result["public_page_booklike"] is False


def test_public_page_booklike_chapter_passes():
    mod = load_module()
    text = """
    # 1. The Agent Loop

    The central argument of this chapter is that agent loops are governable engineering systems, not isolated prompt-response exchanges. The evidence is limited and should be read cautiously because the available sources support an emerging professional vocabulary rather than field-wide consensus. [1]

    ## From Prompt to Loop

    Prompting remains important, but a loop also needs context, action, verification, state, reporting, retry, and escalation. The claim does not establish industry consensus; it narrows attention to the operational pattern that surrounds model outputs. [2]

    ## Verification, State, and Escalation

    Verification gives the loop an accountable boundary, state records what has happened, and escalation defines what the system does when confidence is low. Together these controls make the loop inspectable rather than merely repetitive. [3]

    ## Evidence Limits

    Evidence limits matter because practitioner discourse can be useful without becoming settled academic consensus. The chapter therefore treats loop engineering as a careful analytical frame and avoids stronger claims about universal adoption. [1] [2] [3]

    ## References
    [1] Ref.
    [2] Ref.
    [3] Ref.
    """
    result = mod.evaluate_public_chapter_text(text, expected_title="1. The Agent Loop")
    assert result["ok"] is True
    assert result["public_page_booklike"] is True
    assert result["failed_checks"] == []


def test_cli_writes_json_and_fails_closed_on_bad_page(tmp_path):
    html = tmp_path / "bad.html"
    html.write_text("# 1. The Agent Loop\n\n## Current evidence status\n\n- status supported, quality A\n\n## Source/claim mapping\nBullet 1 maps to supported claim.", encoding="utf-8")
    out = tmp_path / "out.json"
    proc = subprocess.run([
        sys.executable,
        str(SCRIPT),
        "--input-file", str(html),
        "--expected-title", "1. The Agent Loop",
        "--output-json", str(out),
    ], text=True, capture_output=True)
    assert proc.returncode == 2
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["ok"] is False
    assert data["source"] == str(html)
