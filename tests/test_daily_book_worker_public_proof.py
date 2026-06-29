import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "scripts" / "daily_book_worker.py"
PROOF = ROOT / "scripts" / "public_chapter_proof.py"


def test_daily_worker_capability_advertises_all_chapter_public_proof_gate():
    proc = subprocess.run(
        [sys.executable, str(WORKER), "--print-capabilities-json"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    caps = json.loads(proc.stdout)
    assert caps["supports_all_chapter_public_proof_gate"] is True
    assert caps["all_chapter_public_proof_gate_blocks_evidence_led_pages"] is True


def test_preflight_runs_all_chapter_public_proof_without_mutating_book():
    proc = subprocess.run(
        [sys.executable, str(WORKER), "run60-preflight", "--preflight-only", "--run-all-chapter-public-proof"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    data = json.loads(proc.stdout)
    assert data["ok"] is True
    assert data["execution_performed"] is False
    assert data["all_chapter_public_proof_executed"] is True
    assert data["all_chapter_public_proof_report"].endswith("run60-preflight-all-chapters-public-proof.json")
    proof = json.loads((ROOT / data["all_chapter_public_proof_report"]).read_text())
    assert proof["source_kind"] == "all_local_book_chapters"
    assert proof["total_chapters"] >= 8
    assert "agent_loop" in proof["chapter_results"]
    assert "agent_loop" in set(proof["passed_chapters"]) | set(proof["failed_chapters"])
