import json
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "capture_visual_daily.py"


def init_db(db_path: Path):
    schema = (ROOT / "data" / "schema.sql").read_text()
    with sqlite3.connect(db_path) as con:
        con.executescript(schema)


def run_visual(tmp_path: Path, *args: str, env_extra: dict[str, str] | None = None):
    raw = tmp_path / "raw"
    db = tmp_path / "book.sqlite"
    init_db(db)
    out = tmp_path / "visual.json"
    env = {
        "TEREFO_RAW_DIR": str(raw),
        "TEREFO_DB_PATH": str(db),
        "TEREFO_PIXELSHOT_BIN": str(tmp_path / "pixelshot"),
    }
    if env_extra:
        env.update(env_extra)
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--run-id", "visual-test", "--json-out", str(out), *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        env={**env, **dict(PYTHONPATH=str(ROOT / "scripts"))},
    )
    payload = json.loads(out.read_text()) if out.exists() else None
    return proc, payload, raw, db


def test_disabled_visual_capture_is_report_only_and_writes_no_visual_artifacts(tmp_path):
    proc, payload, raw, db = run_visual(tmp_path, "--url", "https://example.com", "--disabled")

    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert payload["status"] == "disabled"
    assert payload["visual_capture_enabled"] is False
    assert payload["items"] == []
    assert not (raw / "visual").exists()
    with sqlite3.connect(db) as con:
        assert con.execute("select count(*) from sources").fetchone()[0] == 0


def test_visual_capture_uses_pixelshot_and_registers_supplemental_source(tmp_path):
    pixelshot = tmp_path / "pixelshot"
    pixelshot.write_text(
        "#!/usr/bin/env python3\n"
        "import pathlib, sys\n"
        "out = pathlib.Path(sys.argv[sys.argv.index('--output') + 1])\n"
        "out.mkdir(parents=True, exist_ok=True)\n"
        "(out / 'tile-000.png').write_bytes(b'PNGDATA')\n"
    )
    pixelshot.chmod(0o755)

    proc, payload, raw, db = run_visual(
        tmp_path,
        "--url",
        "https://example.com/diagram",
        "--query",
        "visual agent diagram",
        "--enabled",
        "--max-urls",
        "1",
    )

    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert payload["status"] == "ok"
    assert payload["visual_capture_enabled"] is True
    assert payload["items"][0]["status"] == "ok"
    assert payload["items"][0]["source_type"] == "visual_web"
    assert payload["items"][0]["tile_count"] == 1
    assert payload["items"][0]["book_usage"]["eligible"] is False
    assert payload["items"][0]["book_usage"]["usage"] == "supplemental_visual_evidence_only"
    assert payload["items"][0]["book_usage"]["required_before_publication"] == [
        "human_or_vision_model_description",
        "source_support_review",
        "citation_mapping",
        "public_proof_gate",
    ]
    assert payload["items"][0]["provenance"]["original_url"] == "https://example.com/diagram"
    assert payload["items"][0]["provenance"]["originating_query"] == "visual agent diagram"
    assert payload["items"][0]["license_review"]["required"] is True
    tile = raw / payload["items"][0]["tiles"][0]
    assert tile.read_bytes() == b"PNGDATA"
    meta = raw / "visual" / "visual-test" / "example-com-diagram" / "visual-metadata.json"
    meta_payload = json.loads(meta.read_text())
    assert meta_payload["visibility"] == "supplemental_visual_evidence"
    assert meta_payload["book_usage"]["eligible"] is False
    assert meta_payload["provenance"]["capture_tool"] == "pixelshot"
    with sqlite3.connect(db) as con:
        row = con.execute("select source_type, url, query, archived_path, visibility from sources").fetchone()
    assert row == (
        "visual_web",
        "https://example.com/diagram",
        "visual agent diagram",
        "visual/visual-test/example-com-diagram/visual-metadata.json",
        "supplemental_visual_evidence",
    )


def test_visual_capture_degrades_to_report_when_pixelshot_missing(tmp_path):
    proc, payload, raw, db = run_visual(
        tmp_path,
        "--url",
        "https://example.com/table",
        "--enabled",
        env_extra={"TEREFO_PIXELSHOT_BIN": str(tmp_path / "does-not-exist")},
    )

    assert proc.returncode == 2
    assert payload["status"] == "pixelshot_missing"
    assert payload["items"] == []
    assert not (raw / "visual").exists()
    with sqlite3.connect(db) as con:
        assert con.execute("select count(*) from sources").fetchone()[0] == 0
