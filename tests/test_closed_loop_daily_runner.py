import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import closed_loop_daily_runner as runner  # noqa: E402
import protected_mutation_guard as guard  # noqa: E402


ALL_CAPABILITIES = {
    "supports_skip_capture": True,
    "supports_skip_entity_extraction": True,
    "supports_skip_claim_extraction": True,
    "supports_skip_docs_entities_update": True,
    "supports_skip_docs_claims_update": True,
    "supports_skip_source_registry_export": True,
    "supports_skip_run_table_update": True,
    "supports_skip_vector": True,
    "supports_no_commit": True,
    "supports_no_push": True,
    "supports_no_docs_book_update_without_gate": True,
    "supports_preflight_only": True,
    "preflight_only_no_write": True,
    "capability_probe_no_write": True,
    "human_in_loop_dependency_added": False,
    "author_allowed": False,
    "publication_approved": False,
    "eligible_for_claim_insertion": False,
    "eligible_for_authoring": False,
    "eligible_for_publication": False,
    "chapter_update_allowed": False,
}


def make_worker(path: Path, capabilities: dict | None = None, probe_rc: int = 0, preflight_rc: int = 0):
    payload = ALL_CAPABILITIES if capabilities is None else capabilities
    path.write_text(
        "#!/usr/bin/env python3\n"
        "import json, sys\n"
        f"CAPS = {json.dumps(payload, sort_keys=True)!r}\n"
        f"PROBE_RC = {probe_rc}\n"
        f"PREFLIGHT_RC = {preflight_rc}\n"
        "if '--print-capabilities-json' in sys.argv:\n"
        "    print(CAPS)\n"
        "    raise SystemExit(PROBE_RC)\n"
        "print(json.dumps({'argv': sys.argv[1:], 'preflight_only': '--preflight-only' in sys.argv}, sort_keys=True))\n"
        "raise SystemExit(PREFLIGHT_RC)\n",
        encoding="utf-8",
    )
    path.chmod(0o755)


def make_mutation_guard(path: Path, ok: bool = True):
    path.write_text(
        "#!/usr/bin/env python3\n"
        "import json, sys, pathlib\n"
        "args = sys.argv[1:]\n"
        "if args[0] == 'snapshot':\n"
        "    out = pathlib.Path(args[args.index('--output') + 1])\n"
        "    out.parent.mkdir(parents=True, exist_ok=True)\n"
        "    out.write_text(json.dumps({'snapshot': str(out), 'db': {'counts': {'source_notes': 445, 'claims': 218, 'editorial_reviews': 10}, 'hashes': {}}, 'path_hashes': {}}))\n"
        "    print(json.dumps({'ok': True, 'output': str(out)}))\n"
        "    raise SystemExit(0)\n"
        "if args[0] == 'compare':\n"
        "    out = pathlib.Path(args[args.index('--output') + 1])\n"
        "    report = {\n"
        f"      'ok': {str(ok)}, 'profile': 'preflight_only_daily_runner', 'failed_checks': [] if {str(ok)} else ['forced_failure'],\n"
        "      'unexpected_changed_paths': [] if " + str(ok) + " else ['.var/book.sqlite'],\n"
        "      'db_delta': {}, 'status_hash_delta': {},\n"
        "      'protected_path_delta': {'data/source_registry.json': False, 'raw': False, 'docs/book': False, 'docs/entities': False, 'docs/research/claims.md': False, 'data/schema.sql': False, 'scripts/daily_book_worker.py': False, '.var/book.sqlite': False},\n"
        "      'docs_book_changed': False, 'docs_entities_changed': False, 'docs_claims_changed': False, 'source_registry_changed': False, 'raw_changed': False, 'schema_changed': False, 'daily_worker_changed': False, 'human_in_loop_dependency_added': False}\n"
        "    out.parent.mkdir(parents=True, exist_ok=True)\n"
        "    out.write_text(json.dumps(report, sort_keys=True))\n"
        "    print(json.dumps({'ok': report['ok'], 'output_json': str(out)}))\n"
        "    raise SystemExit(0 if report['ok'] else 2)\n",
        encoding="utf-8",
    )
    path.chmod(0o755)


def base_args(tmp_path: Path, worker: Path, guard_script: Path, extra=None):
    args = [
        "--run-id", "citation-pipeline-test-20260612",
        "--mode", "preflight_only",
        "--disposition", "safe_reports_only",
        "--daily-worker", str(worker),
        "--state-machine-config", str(tmp_path / "state.json"),
        "--transition-engine", str(tmp_path / "transition.py"),
        "--mutation-guard", str(guard_script),
        "--event-ledger", str(tmp_path / "logs" / "events.jsonl"),
        "--before-snapshot", str(tmp_path / "before.json"),
        "--after-snapshot", str(tmp_path / "after.json"),
        "--mutation-guard-report", str(tmp_path / "reports" / "mutation.json"),
        "--output-json", str(tmp_path / "reports" / "runner.json"),
        "--output-md", str(tmp_path / "reports" / "runner.md"),
        "--telegram-status", str(tmp_path / "reports" / "telegram.md"),
    ]
    if extra:
        args += extra
    return args


def read_report(tmp_path: Path):
    return json.loads((tmp_path / "reports" / "runner.json").read_text())


def test_probes_daily_worker_capabilities(tmp_path):
    worker = tmp_path / "worker.py"
    guard_script = tmp_path / "guard.py"
    make_worker(worker)
    make_mutation_guard(guard_script)

    rc = runner.main(base_args(tmp_path, worker, guard_script, ["--execute-preflight-only"]))

    assert rc == 0
    report = read_report(tmp_path)
    assert report["daily_worker_capability_probe"]["ok"] is True
    assert report["missing_capabilities"] == []
    assert report["supported_capabilities"]


def test_fails_closed_if_capability_probe_fails(tmp_path):
    worker = tmp_path / "worker.py"
    guard_script = tmp_path / "guard.py"
    make_worker(worker, probe_rc=3)
    make_mutation_guard(guard_script)

    rc = runner.main(base_args(tmp_path, worker, guard_script, ["--execute-preflight-only"]))

    assert rc == 2
    report = read_report(tmp_path)
    assert report["execution_allowed"] is False
    assert report["execution_performed"] is False
    assert report["final_disposition"] == "attempt_failed"


def test_fails_closed_if_required_no_write_capability_is_missing(tmp_path):
    worker = tmp_path / "worker.py"
    guard_script = tmp_path / "guard.py"
    caps = dict(ALL_CAPABILITIES)
    caps["supports_skip_claim_extraction"] = False
    make_worker(worker, capabilities=caps)
    make_mutation_guard(guard_script)

    rc = runner.main(base_args(tmp_path, worker, guard_script, ["--execute-preflight-only"]))

    assert rc == 2
    report = read_report(tmp_path)
    assert "supports_skip_claim_extraction" in report["missing_capabilities"]
    assert report["execution_allowed"] is False


def test_requires_supports_preflight_only_true(tmp_path):
    worker = tmp_path / "worker.py"
    guard_script = tmp_path / "guard.py"
    caps = dict(ALL_CAPABILITIES)
    caps["supports_preflight_only"] = False
    make_worker(worker, capabilities=caps)
    make_mutation_guard(guard_script)

    rc = runner.main(base_args(tmp_path, worker, guard_script, ["--execute-preflight-only"]))

    assert rc == 2
    assert "supports_preflight_only" in read_report(tmp_path)["missing_capabilities"]


def test_execution_allowed_true_only_for_preflight_mode_with_execute_flag(tmp_path):
    worker = tmp_path / "worker.py"
    guard_script = tmp_path / "guard.py"
    make_worker(worker)
    make_mutation_guard(guard_script)

    assert runner.main(base_args(tmp_path, worker, guard_script, ["--execute-preflight-only"])) == 0
    assert read_report(tmp_path)["execution_allowed"] is True

    args = base_args(tmp_path, worker, guard_script, ["--execute-preflight-only"])
    args[args.index("--mode") + 1] = "report_only"
    assert runner.main(args) == 2
    assert read_report(tmp_path)["execution_allowed"] is False

    args = base_args(tmp_path, worker, guard_script, ["--execute-preflight-only"])
    args[args.index("--mode") + 1] = "publish"
    assert runner.main(args) == 2
    assert read_report(tmp_path)["execution_allowed"] is False


def test_execution_allowed_false_for_report_only_without_explicit_execute_flag(tmp_path):
    worker = tmp_path / "worker.py"
    guard_script = tmp_path / "guard.py"
    make_worker(worker)
    make_mutation_guard(guard_script)

    rc = runner.main(base_args(tmp_path, worker, guard_script))

    assert rc == 2
    assert read_report(tmp_path)["execution_allowed"] is False


def test_executes_only_preflight_command_with_all_no_write_flags(tmp_path):
    worker = tmp_path / "worker.py"
    guard_script = tmp_path / "guard.py"
    make_worker(worker)
    make_mutation_guard(guard_script)

    assert runner.main(base_args(tmp_path, worker, guard_script, ["--execute-preflight-only"])) == 0
    command = read_report(tmp_path)["daily_worker_command"]

    assert command.count("--preflight-only") == 1
    for flag in [
        "--skip-capture",
        "--skip-entity-extraction",
        "--skip-claim-extraction",
        "--skip-docs-entities-update",
        "--skip-docs-claims-update",
        "--skip-source-registry-export",
        "--skip-run-table-update",
        "--skip-vector",
        "--no-commit",
    ]:
        assert flag in command


def test_mutation_guard_before_after_and_compare_are_invoked(tmp_path):
    worker = tmp_path / "worker.py"
    guard_script = tmp_path / "guard.py"
    make_worker(worker)
    make_mutation_guard(guard_script)

    assert runner.main(base_args(tmp_path, worker, guard_script, ["--execute-preflight-only"])) == 0

    assert (tmp_path / "before.json").exists()
    assert (tmp_path / "after.json").exists()
    assert (tmp_path / "reports" / "mutation.json").exists()
    report = read_report(tmp_path)
    assert report["mutation_guard_executed"] is True
    assert report["mutation_guard_ok"] is True


def test_mutation_guard_failure_marks_attempt_failed(tmp_path):
    worker = tmp_path / "worker.py"
    guard_script = tmp_path / "guard.py"
    make_worker(worker)
    make_mutation_guard(guard_script, ok=False)

    rc = runner.main(base_args(tmp_path, worker, guard_script, ["--execute-preflight-only"]))

    assert rc == 2
    report = read_report(tmp_path)
    assert report["mutation_guard_ok"] is False
    assert report["final_disposition"] == "attempt_failed"


def test_mutation_guard_success_marks_attempt_completed(tmp_path):
    worker = tmp_path / "worker.py"
    guard_script = tmp_path / "guard.py"
    make_worker(worker)
    make_mutation_guard(guard_script, ok=True)

    assert runner.main(base_args(tmp_path, worker, guard_script, ["--execute-preflight-only"])) == 0

    assert read_report(tmp_path)["final_disposition"] == "attempt_completed"


def test_report_includes_deltas_false_flags_commit_push_blocks_and_telegram_fallback(tmp_path):
    worker = tmp_path / "worker.py"
    guard_script = tmp_path / "guard.py"
    make_worker(worker)
    make_mutation_guard(guard_script)

    assert runner.main(base_args(tmp_path, worker, guard_script, ["--execute-preflight-only"])) == 0
    report = read_report(tmp_path)

    for key in ["db_delta", "protected_path_delta", "status_hash_delta"]:
        assert key in report
    for key in [
        "production_publish_enabled",
        "docs_book_update_enabled",
        "raw_collection_enabled",
        "metadata_write_enabled",
        "authoring_enabled",
        "publication_approved",
        "chapter_update_allowed",
        "human_in_loop_dependency_added",
        "runner_commit_allowed",
        "runner_push_allowed",
    ]:
        assert report[key] is False
    assert report["telegram_fallback_written"] is True
    assert Path(report["telegram_status_path"]).exists()
    assert report["runner_commit_block_reasons"]
    assert report["runner_push_block_reasons"]


def test_runner_does_not_modify_protected_runtime_paths(tmp_path):
    protected = {
        ".var/book.sqlite": b"sqlite-before",
        "data/source_registry.json": b"{}\n",
        "raw/source.txt": b"raw-before",
        "docs/book/chapter.md": b"book-before",
        "docs/entities/entity.md": b"entity-before",
        "docs/research/claims.md": b"claims-before",
        "data/schema.sql": b"schema-before",
    }
    for rel, content in protected.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    worker = tmp_path / "worker.py"
    guard_script = tmp_path / "guard.py"
    make_worker(worker)
    make_mutation_guard(guard_script)

    cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        rc = runner.main(base_args(tmp_path, worker, guard_script, ["--execute-preflight-only"]))
    finally:
        os.chdir(cwd)

    assert rc == 0
    for rel, content in protected.items():
        assert (tmp_path / rel).read_bytes() == content
