import os
import stat
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "git_push_with_hermes_key.sh"
KEY_PATH = "/root/.ssh/id_ed25519_github_hermione_hermes"


def test_push_helper_exists_and_references_expected_key_not_key_contents():
    assert SCRIPT.exists()
    text = SCRIPT.read_text()
    assert KEY_PATH in text
    assert "IdentitiesOnly=yes" in text
    assert "StrictHostKeyChecking=accept-new" in text
    assert "BEGIN OPENSSH" + " PRIVATE KEY" not in text
    assert "BEGIN RSA" + " PRIVATE KEY" not in text


def test_push_helper_check_key_only_exits_clearly():
    proc = subprocess.run([str(SCRIPT), "--check-key-only"], text=True, capture_output=True, cwd=ROOT)
    assert proc.returncode in {0, 2}
    combined = proc.stdout + proc.stderr
    assert "private key" not in combined.lower()
    assert "key" in combined.lower()


def test_push_helper_dry_run_does_not_push():
    proc = subprocess.run([str(SCRIPT), "--dry-run"], text=True, capture_output=True, cwd=ROOT)
    assert proc.returncode in {0, 2}
    combined = proc.stdout + proc.stderr
    assert "git push" in combined
    assert "BEGIN" not in combined
