from pathlib import Path
import importlib.util
import sys

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "verify_book_workspace.py"
sys.path.insert(0, str(ROOT / "scripts"))


def load_module():
    spec = importlib.util.spec_from_file_location("verify_book_workspace", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_secret_named_run_reports_are_not_treated_as_secret_material():
    mod = load_module()
    assert mod.is_unsafe_tracked_path("reports/editorial/run58-secrets-scan.json") is False
    assert mod.is_unsafe_tracked_path("reports/editorial/run59-secrets-scan.md") is False


def test_real_secret_and_credential_paths_remain_blocked():
    mod = load_module()
    assert mod.is_unsafe_tracked_path("config/prod-token.txt") is True
    assert mod.is_unsafe_tracked_path(".var/browser/profile.json") is True
    assert mod.is_unsafe_tracked_path("private/cookie-jar.txt") is True
    assert mod.is_unsafe_tracked_path("ops/credential-store.json") is True
