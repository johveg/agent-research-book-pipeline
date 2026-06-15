#!/usr/bin/env python3
"""File-based event ledger for closed-loop daily runner attempts.

Run 41 intentionally uses JSONL rather than SQLite so event logging can be
introduced without schema changes or runtime DB mutation.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LEDGER = ROOT / "logs" / "closed_loop" / "events.jsonl"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _resolve(path: str | Path) -> Path:
    p = Path(path)
    return p if p.is_absolute() else ROOT / p


def compute_idempotency_key(run_id: str, mode: str, disposition: str, stage: str, command_contract_hash: str) -> str:
    payload = {
        "run_id": run_id,
        "mode": mode,
        "disposition": disposition,
        "stage": stage,
        "command_contract_hash": command_contract_hash,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def load_events(ledger_path: str | Path = DEFAULT_LEDGER) -> list[dict[str, Any]]:
    path = _resolve(ledger_path)
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            events.append(json.loads(line))
    return events


def append_event(
    ledger_path: str | Path,
    *,
    run_id: str,
    attempt_id: str,
    event_type: str,
    mode: str,
    disposition: str,
    status: str,
    payload: dict[str, Any] | None = None,
    command_contract_hash: str = "",
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    key = idempotency_key or compute_idempotency_key(run_id, mode, disposition, event_type, command_contract_hash)
    event = {
        "event_id": str(uuid.uuid4()),
        "timestamp": utc_now(),
        "run_id": run_id,
        "attempt_id": attempt_id,
        "event_type": event_type,
        "idempotency_key": key,
        "mode": mode,
        "disposition": disposition,
        "status": status,
        "payload": payload or {},
        "human_in_loop_dependency_added": False,
    }
    path = _resolve(ledger_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, sort_keys=True) + "\n")
    return event


def detect_duplicate_event(
    events: list[dict[str, Any]],
    *,
    run_id: str,
    attempt_id: str,
    idempotency_key: str,
    completed_only: bool = False,
) -> dict[str, Any] | None:
    for event in events:
        if event.get("run_id") != run_id:
            continue
        if event.get("attempt_id") != attempt_id:
            continue
        if event.get("idempotency_key") != idempotency_key:
            continue
        if completed_only and event.get("event_type") not in {"attempt_completed", "duplicate_suppressed"}:
            continue
        return event
    return None


def _record(
    ledger_path: str | Path,
    run_id: str,
    attempt_id: str,
    mode: str,
    disposition: str,
    command_contract_hash: str,
    event_type: str,
    status: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return append_event(
        ledger_path,
        run_id=run_id,
        attempt_id=attempt_id,
        event_type=event_type,
        mode=mode,
        disposition=disposition,
        status=status,
        payload=payload,
        command_contract_hash=command_contract_hash,
    )


def record_attempt_started(**kwargs) -> dict[str, Any]:
    return _record(kwargs.pop("ledger_path"), kwargs.pop("run_id"), kwargs.pop("attempt_id"), kwargs.pop("mode"), kwargs.pop("disposition"), kwargs.pop("command_contract_hash"), "attempt_started", "started", kwargs.pop("payload", {}))


def record_capability_probe(*, ok: bool, **kwargs) -> dict[str, Any]:
    return _record(kwargs.pop("ledger_path"), kwargs.pop("run_id"), kwargs.pop("attempt_id"), kwargs.pop("mode"), kwargs.pop("disposition"), kwargs.pop("command_contract_hash"), "capability_probe_passed" if ok else "capability_probe_failed", "passed" if ok else "failed", kwargs.pop("payload", {}))


def record_mutation_guard_before(**kwargs) -> dict[str, Any]:
    return _record(kwargs.pop("ledger_path"), kwargs.pop("run_id"), kwargs.pop("attempt_id"), kwargs.pop("mode"), kwargs.pop("disposition"), kwargs.pop("command_contract_hash"), "mutation_guard_before_snapshot", "completed", kwargs.pop("payload", {}))


def record_worker_preflight_execution(*, status: str, **kwargs) -> dict[str, Any]:
    event_type = {
        "started": "worker_preflight_execution_started",
        "completed": "worker_preflight_execution_completed",
        "failed": "worker_preflight_execution_failed",
    }.get(status, "worker_preflight_execution_failed")
    return _record(kwargs.pop("ledger_path"), kwargs.pop("run_id"), kwargs.pop("attempt_id"), kwargs.pop("mode"), kwargs.pop("disposition"), kwargs.pop("command_contract_hash"), event_type, status, kwargs.pop("payload", {}))


def record_mutation_guard_after(**kwargs) -> dict[str, Any]:
    return _record(kwargs.pop("ledger_path"), kwargs.pop("run_id"), kwargs.pop("attempt_id"), kwargs.pop("mode"), kwargs.pop("disposition"), kwargs.pop("command_contract_hash"), "mutation_guard_after_snapshot", "completed", kwargs.pop("payload", {}))


def record_mutation_guard_result(*, ok: bool, **kwargs) -> dict[str, Any]:
    return _record(kwargs.pop("ledger_path"), kwargs.pop("run_id"), kwargs.pop("attempt_id"), kwargs.pop("mode"), kwargs.pop("disposition"), kwargs.pop("command_contract_hash"), "mutation_guard_compare_passed" if ok else "mutation_guard_compare_failed", "passed" if ok else "failed", kwargs.pop("payload", {}))


def record_attempt_completed(**kwargs) -> dict[str, Any]:
    return _record(kwargs.pop("ledger_path"), kwargs.pop("run_id"), kwargs.pop("attempt_id"), kwargs.pop("mode"), kwargs.pop("disposition"), kwargs.pop("command_contract_hash"), "attempt_completed", "completed", kwargs.pop("payload", {}))


def record_attempt_failed(**kwargs) -> dict[str, Any]:
    return _record(kwargs.pop("ledger_path"), kwargs.pop("run_id"), kwargs.pop("attempt_id"), kwargs.pop("mode"), kwargs.pop("disposition"), kwargs.pop("command_contract_hash"), "attempt_failed", "failed", kwargs.pop("payload", {}))


def write_event_ledger_report(ledger_path: str | Path, output_md: str | Path) -> dict[str, Any]:
    events = load_events(ledger_path)
    counts = Counter(event.get("event_type", "unknown") for event in events)
    summary = {
        "ledger_path": str(_resolve(ledger_path)),
        "event_count": len(events),
        "event_types": dict(sorted(counts.items())),
        "human_in_loop_dependency_added": any(event.get("human_in_loop_dependency_added") is True for event in events),
    }
    out = _resolve(output_md)
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Closed-loop event ledger report",
        "",
        f"- Ledger path: `{summary['ledger_path']}`",
        f"- Event count: `{summary['event_count']}`",
        f"- human_in_loop_dependency_added: `{summary['human_in_loop_dependency_added']}`",
        "",
        "## Event types",
        "",
    ]
    lines.extend(f"- `{event_type}`: `{count}`" for event_type, count in summary["event_types"].items())
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return summary
