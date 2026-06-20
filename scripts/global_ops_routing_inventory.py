#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
from pathlib import Path
from typing import Any

REQUIRED_OPS_CHANNEL = "AL-Hermoine-OPS"
NON_OPS_TARGETS = {"telegram:marius", "marius", "telegram", "origin", "home", "default", "local", "all"}
DEFAULT_PATHS = {
    "terefo": Path("/home/hermoine/terefohealreboa"),
    "loop_engineering": Path("/home/hermoine/loop-engineering-24h"),
    "openclaw_web_watch": Path("/home/hermoine/openclaw-hermes-web-watch"),
    "linkedin_watch": Path("/home/hermoine/linkedin-24h-watch"),
    "default_profile": Path("/root/.hermes"),
    "ops_bot_profile": Path("/root/.hermes/profiles/ops-bot"),
}
SCAN_FILES = [
    "scripts/send_ops_status.py",
    "scripts/status_message_contract.py",
    "scripts/ops_delivery_outbox.py",
    "scripts/ops_delivery_controller.py",
    "scripts/production_daily_monitor.py",
    "scripts/closed_loop_production_scheduler.py",
    "scripts/production_daily_self_heal.py",
    "scripts/run_production_daily_cron.sh",
    "scripts/daily_web_search_capture.sh",
    "scripts/daily_linkedin_capture.sh",
    "scripts/update_vector_db.sh",
    "config.yaml",
]
TARGET_RE = re.compile(r"(AL-Hermoine-OPS|telegram:Marius|telegram:[A-Za-z0-9_.#:@-]+|deliver\s*[:=]\s*['\"]?([^'\"\n,}]+)|target_channel\s*[:=]\s*['\"]?([^'\"\n,}]+))")


def inventory_schema_version() -> str:
    return "run57.global_ops_routing_inventory.v1"


def _detect_target(text: str, explicit: str | None = None) -> str | None:
    if explicit:
        return explicit
    if "telegram:Marius" in text or "Marius" in text:
        return "telegram:Marius"
    m = TARGET_RE.search(text)
    if m:
        return next((g for g in m.groups() if g and not g.startswith("deliver") and not g.startswith("target_channel")), None) or m.group(0)
    if REQUIRED_OPS_CHANNEL in text:
        return REQUIRED_OPS_CHANNEL
    return None


def classify_emitter(component: str, repo_or_profile: str, path: str, text: str, current_target: str | None = None, job_id: str | None = None, job_name: str | None = None, alias_resolvable: bool = False) -> dict[str, Any]:
    target = _detect_target(text, current_target)
    target_norm = (target or "").strip().lower()
    target_channel_metadata = "target_channel" in text or REQUIRED_OPS_CHANNEL in text
    timestamp_present = any(k in text for k in ["emitted_at_unix_s", "emitted_at_unix_ms", "emitted_at_utc_iso", "emitted_at_oslo_iso"])
    explicit_fallback_true = bool(re.search(r"fallback_channel_used\W*(true|1)|fallback_(target|channel)\s*[:=]\s*['\"]?(telegram:Marius|Marius|telegram|default|home|origin)", text, re.I))
    generic_fallback = bool(re.search(r"\b(default|home)\s+(channel|target|delivery)|telegram:Marius", text, re.I))
    uses_fallback = explicit_fallback_true or generic_fallback or target_norm in NON_OPS_TARGETS
    sends_to_dm = "marius" in target_norm
    sends_to_default = target_norm in {"telegram", "origin", "home", "default", "all"} or sends_to_dm
    should_route = any(k in (component + " " + path + " " + text).lower() for k in ["ops", "status", "monitor", "production", "telegram", "cron", "capture", "loop", "openclaw", "linkedin"])
    compliant_target = target == REQUIRED_OPS_CHANNEL
    current_resolvable = bool(compliant_target and alias_resolvable)
    required_patch = None
    risk = "low"
    severity = "info"
    recommended = "no_action"
    if should_route and not compliant_target:
        required_patch = "replace_non_ops_target_with_AL-Hermoine-OPS_or_queue"
        recommended = required_patch
        risk = "high" if (uses_fallback or sends_to_dm or sends_to_default) else "medium"
        severity = "error" if risk == "high" else "warning"
    elif compliant_target and not alias_resolvable:
        required_patch = "queue_until_AL-Hermoine-OPS_resolves"
        recommended = required_patch
        risk = "medium"
        severity = "warning"
    if should_route and (not target_channel_metadata or not timestamp_present):
        if not required_patch:
            required_patch = "add_target_channel_and_timestamp_metadata"
            recommended = required_patch
        risk = "high" if uses_fallback else max(risk, "medium", key=["low","medium","high"].index)
        severity = "warning" if severity == "info" else severity
    return {
        "component": component,
        "repo_or_profile": repo_or_profile,
        "path": path,
        "job_id": job_id,
        "job_name": job_name,
        "current_target": target,
        "current_target_resolvable": current_resolvable,
        "target_channel_metadata": target_channel_metadata,
        "uses_fallback": uses_fallback,
        "fallback_target": "telegram:Marius" if "marius" in text.lower() else (target if uses_fallback and target != REQUIRED_OPS_CHANNEL else None),
        "sends_to_dm": sends_to_dm,
        "sends_to_default": sends_to_default,
        "should_route_to_ops": should_route,
        "can_patch_safely": path.endswith((".py", ".sh", ".json")) and should_route,
        "required_patch": required_patch,
        "status_timestamp_metadata_present": timestamp_present,
        "severity": severity,
        "risk": risk,
        "recommended_action": recommended,
    }


def _read(path: Path) -> str:
    try:
        if path.exists() and path.is_file() and path.stat().st_size < 2_000_000:
            return path.read_text(errors="ignore")
    except Exception:
        return ""
    return ""


def _jobs_from_json(path: Path) -> list[dict[str, Any]]:
    try:
        data = json.loads(path.read_text())
    except Exception:
        return []
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return data.get("jobs", []) if isinstance(data.get("jobs"), list) else [data]
    return []


def build_inventory(roots: dict[str, Path] | None = None, cron_paths: list[Path] | None = None, alias_resolvable: bool = False) -> dict[str, Any]:
    roots = roots or DEFAULT_PATHS
    cron_paths = cron_paths or [Path("/root/.hermes/cron/jobs.json"), Path("/root/.hermes/profiles/ops-bot/cron/jobs.json")]
    emitters: list[dict[str, Any]] = []
    for name, root in roots.items():
        if not root.exists():
            continue
        for rel in SCAN_FILES:
            p = root / rel
            text = _read(p)
            if text:
                emitters.append(classify_emitter(Path(rel).stem, name, str(p), text, alias_resolvable=alias_resolvable))
        # limited broader discovery for status wrappers
        for p in list(root.glob("scripts/*status*.py"))[:20] + list(root.glob("scripts/*telegram*.sh"))[:20] + list(root.glob("*.sh"))[:20]:
            text = _read(p)
            if text and str(p) not in {e["path"] for e in emitters}:
                emitters.append(classify_emitter(p.stem, name, str(p), text, alias_resolvable=alias_resolvable))
    for cp in cron_paths:
        for job in _jobs_from_json(cp):
            blob = json.dumps(job, ensure_ascii=False)
            if not any(k in blob.lower() for k in ["terefo", "openclaw", "linkedin", "loop", "ops", "status", "monitor", "production"]):
                continue
            emitters.append(classify_emitter(
                "hermes_cron_job", str(cp.parent), str(cp), blob,
                current_target=job.get("deliver") or job.get("target") or job.get("delivery"),
                job_id=job.get("id") or job.get("job_id"), job_name=job.get("name") or job.get("title"), alias_resolvable=alias_resolvable,
            ))
    noncompliant = [e for e in emitters if e["should_route_to_ops"] and (e["current_target"] != REQUIRED_OPS_CHANNEL or e["uses_fallback"] or not e["target_channel_metadata"])]
    return {
        "schema_version": inventory_schema_version(),
        "run_id": "run57",
        "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "required_ops_channel": REQUIRED_OPS_CHANNEL,
        "alias_resolvable": alias_resolvable,
        "emitters": emitters,
        "summary": {"emitter_count": len(emitters), "noncompliant_count": len(noncompliant), "high_risk_count": sum(1 for e in emitters if e["risk"] == "high")},
    }


def write_reports(inv: dict[str, Any], json_path: Path, md_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(inv, indent=2, sort_keys=True))
    lines = ["# Run 57 global OPS routing inventory", "", f"- required_ops_channel: `{REQUIRED_OPS_CHANNEL}`", f"- emitters: `{inv['summary']['emitter_count']}`", f"- noncompliant: `{inv['summary']['noncompliant_count']}`", "", "```json", json.dumps(inv, indent=2, sort_keys=True), "```", ""]
    md_path.write_text("\n".join(lines))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--alias-resolvable", action="store_true")
    ap.add_argument("--output-json", default="reports/editorial/run57-global-ops-routing-inventory.json")
    ap.add_argument("--output-md", default="reports/editorial/run57-global-ops-routing-inventory.md")
    args = ap.parse_args()
    inv = build_inventory(alias_resolvable=args.alias_resolvable)
    write_reports(inv, Path(args.output_json), Path(args.output_md))
    print(json.dumps(inv, indent=2, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
