#!/usr/bin/env python3
"""Safe Hermes CLI JSON bridge for high-reasoning calls.

This helper never prints secrets intentionally. It invokes Hermes through the
local CLI, parses stdout as strict JSON, and returns a normalized result object.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

try:
    from model_profiles import ModelProfileError, resolve_model_profile
except Exception:  # pragma: no cover - keeps helper usable if imported outside repo layout
    ModelProfileError = RuntimeError  # type: ignore
    resolve_model_profile = None  # type: ignore

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROVIDER = "copilot"
DEFAULT_MODEL = "gpt-5.5"
DEFAULT_COMMAND = "hermes"
DEFAULT_TIMEOUT = 180
DEFAULT_SOURCE_TAG = "tool"
DEFAULT_TOOLSET = "safe"
BRIDGE = "hermes_cli"

SECRET_PATTERNS = [
    re.compile(r"(?i)(authorization|bearer|token|api[_-]?key|oauth|cookie|credential)\s*[:=]\s*\S+"),
    re.compile(r"(sk-[A-Za-z0-9_-]+|github_pat_[A-Za-z0-9_]+|gh[opsu]_[A-Za-z0-9_]+)"),
]


class HighReasoningError(RuntimeError):
    def __init__(self, result: dict[str, Any]) -> None:
        super().__init__(str(result.get("error") or "high reasoning call failed"))
        self.result = result


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def redact(text: str) -> str:
    text = str(text or "")
    for pat in SECRET_PATTERNS:
        text = pat.sub(lambda m: (m.group(1) + "=[REDACTED]") if m.lastindex else "[REDACTED]", text)
    return text


def env_config(provider: str | None = None, model: str | None = None, timeout_seconds: int | None = None, profile: dict[str, Any] | None = None) -> dict[str, Any]:
    provider_value = provider or (profile or {}).get("provider") or os.environ.get("TEREFO_LLM_PROVIDER", DEFAULT_PROVIDER) or DEFAULT_PROVIDER
    model_value = model or (profile or {}).get("model") or os.environ.get("TEREFO_LLM_REASONING_MODEL", DEFAULT_MODEL) or DEFAULT_MODEL
    return {
        "bridge": (profile or {}).get("bridge") or os.environ.get("TEREFO_LLM_BRIDGE", BRIDGE) or BRIDGE,
        "command": os.environ.get("TEREFO_LLM_COMMAND", DEFAULT_COMMAND) or DEFAULT_COMMAND,
        "provider": provider_value,
        "model": model_value,
        "timeout_seconds": int(timeout_seconds or os.environ.get("TEREFO_LLM_TIMEOUT_SECONDS", DEFAULT_TIMEOUT) or DEFAULT_TIMEOUT),
        "source_tag": os.environ.get("TEREFO_LLM_SOURCE_TAG", DEFAULT_SOURCE_TAG) or DEFAULT_SOURCE_TAG,
        "toolset": os.environ.get("TEREFO_LLM_TOOLSETS", DEFAULT_TOOLSET) or DEFAULT_TOOLSET,
        "override_bridge_command": os.environ.get("TEREFO_HIGH_REASONING_BRIDGE_COMMAND", ""),
        "model_profile": (profile or {}).get("profile_name", "explicit_cli" if provider and model else ""),
        "strict_json_required": bool((profile or {}).get("strict_json_required", True)),
        "reasoning_effort": (profile or {}).get("reasoning_effort", "high"),
        "task_class": (profile or {}).get("task_class", "editorial_reasoning"),
    }


def command_shape(cfg: dict[str, Any]) -> list[str]:
    return [
        "timeout",
        str(cfg["timeout_seconds"]),
        cfg["command"],
        "chat",
        "-Q",
        "--provider",
        cfg["provider"],
        "-m",
        cfg["model"],
        "--source",
        cfg["source_tag"],
        "-t",
        cfg["toolset"],
        "-q",
        "<strict-json-prompt>",
    ]


def base_result(cfg: dict[str, Any], schema_name: str, prompt_hash: str = "") -> dict[str, Any]:
    return {
        "ok": False,
        "provider": cfg.get("provider") or "",
        "model": cfg.get("model") or "",
        "bridge": cfg.get("bridge") or BRIDGE,
        "schema_name": schema_name,
        "llm_used": False,
        "reasoning_status": "blocked_on_hermes_cli_or_provider",
        "parsed_json": {},
        "stdout_json_valid": False,
        "exit_code": None,
        "timed_out": False,
        "elapsed_seconds": 0.0,
        "error": "",
        "stderr_redacted": "",
        "stdout_hash": "",
        "command_shape": " ".join(shlex.quote(x) for x in command_shape(cfg)),
        "weak_local_fallback_refused": True,
        "model_profile": cfg.get("model_profile") or "",
        "strict_json_required": bool(cfg.get("strict_json_required", True)),
        "reasoning_effort": cfg.get("reasoning_effort", ""),
        "task_class": cfg.get("task_class", ""),
        "prompt_hash": prompt_hash,
        "generated_at": utc_now(),
    }


def validate_canary(obj: dict[str, Any]) -> None:
    if obj.get("ok") is not True:
        raise ValueError("canary ok must be true")
    if str(obj.get("model") or "") != DEFAULT_MODEL:
        raise ValueError("canary model mismatch")
    if obj.get("reasoning") != "available":
        raise ValueError("canary reasoning must be available")


def call_high_reasoning_json(
    prompt: str,
    schema_name: str,
    validator: Callable[[dict[str, Any]], None] | None = None,
    provider: str | None = None,
    model: str | None = None,
    timeout_seconds: int = DEFAULT_TIMEOUT,
    reasoning_profile: str | None = None,
) -> dict[str, Any]:
    profile = None
    if reasoning_profile:
        if resolve_model_profile is None:
            raise HighReasoningError({"error": "model_profile_loader_unavailable", "provider": provider or "", "model": model or "", "bridge": BRIDGE})
        try:
            profile = resolve_model_profile(reasoning_profile, provider=provider, model=model)
        except Exception as exc:
            raise HighReasoningError({"error": f"model_profile_error:{exc}", "provider": provider or "", "model": model or "", "bridge": BRIDGE}) from exc
    cfg = env_config(provider=provider, model=model, timeout_seconds=timeout_seconds, profile=profile)
    import hashlib
    result = base_result(cfg, schema_name, hashlib.sha256(prompt.encode("utf-8")).hexdigest())
    if not cfg["provider"] or not cfg["model"]:
        result["error"] = "provider_or_model_missing"
        raise HighReasoningError(result)
    if cfg["provider"] not in {"copilot"}:
        result["error"] = f"weak_or_unapproved_provider_refused:{cfg['provider']}"
        raise HighReasoningError(result)

    input_payload = {
        "prompt": prompt,
        "schema_name": schema_name,
        "provider": cfg["provider"],
        "model": cfg["model"],
        "strict_json_required": cfg["strict_json_required"],
        "model_profile": cfg.get("model_profile") or "",
    }
    if cfg["override_bridge_command"]:
        cmd = [cfg["override_bridge_command"]]
        stdin_text = json.dumps(input_payload, ensure_ascii=False)
        timeout = cfg["timeout_seconds"]
    else:
        cmd = [
            "timeout",
            str(cfg["timeout_seconds"]),
            cfg["command"],
            "chat",
            "-Q",
            "--provider",
            cfg["provider"],
            "-m",
            cfg["model"],
            "--source",
            cfg["source_tag"],
            "-t",
            cfg["toolset"],
            "-q",
            prompt,
        ]
        stdin_text = None
        timeout = cfg["timeout_seconds"] + 10

    start = time.monotonic()
    try:
        proc = subprocess.run(cmd, input=stdin_text, text=True, capture_output=True, timeout=timeout)
    except FileNotFoundError:
        result["error"] = "command_missing"
        raise HighReasoningError(result)
    except subprocess.TimeoutExpired as exc:
        result["timed_out"] = True
        result["exit_code"] = 124
        result["elapsed_seconds"] = round(time.monotonic() - start, 3)
        result["stderr_redacted"] = redact(exc.stderr or "")[:1000]
        result["error"] = "timeout"
        raise HighReasoningError(result)

    result["elapsed_seconds"] = round(time.monotonic() - start, 3)
    result["exit_code"] = proc.returncode
    result["stderr_redacted"] = redact(proc.stderr or "")[:1000]
    stdout = proc.stdout or ""
    result["stdout_hash"] = hashlib.sha256(stdout.encode("utf-8")).hexdigest()
    if proc.returncode == 124:
        result["timed_out"] = True
        result["error"] = "timeout"
        raise HighReasoningError(result)
    if proc.returncode != 0:
        result["error"] = f"nonzero_exit:{proc.returncode}"
        raise HighReasoningError(result)
    try:
        parsed = json.loads(stdout.strip())
    except Exception as exc:
        result["error"] = f"invalid_json:{type(exc).__name__}"
        result["stdout_preview_redacted"] = redact(stdout[:500])
        raise HighReasoningError(result)
    if not isinstance(parsed, dict):
        result["error"] = "invalid_json:not_object"
        raise HighReasoningError(result)
    if validator:
        try:
            validator(parsed)
        except Exception as exc:
            result["error"] = f"schema_mismatch:{exc}"
            result["parsed_json"] = parsed
            raise HighReasoningError(result)
    result.update({
        "ok": True,
        "llm_used": True,
        "reasoning_status": "high_reasoning_used",
        "parsed_json": parsed,
        "stdout_json_valid": True,
        "error": "",
    })
    return result


def canary_prompt(model: str = DEFAULT_MODEL) -> str:
    return f'Return JSON only: {{"ok": true, "model": "<model-name>", "reasoning": "available"}}. Use model "{model}". No markdown, no prose.'


def write_canary_reports(result: dict[str, Any], output_dir: Path, run_id: str, json_only: bool, markdown_only: bool) -> dict[str, str]:
    output_dir = output_dir if output_dir.is_absolute() else ROOT / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{run_id}-high-reasoning-canary.json"
    md_path = output_dir / f"{run_id}-high-reasoning-canary.md"
    outputs = {"json": str(json_path.relative_to(ROOT)) if json_path.is_relative_to(ROOT) else str(json_path), "markdown": str(md_path.relative_to(ROOT)) if md_path.is_relative_to(ROOT) else str(md_path)}
    report = dict(result)
    report["output_paths"] = outputs
    if not markdown_only:
        json_path.write_text(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    if not json_only:
        md = "\n".join([
            f"# High-reasoning canary: {run_id}",
            "",
            f"- Provider: `{report.get('provider')}`",
            f"- Model: `{report.get('model')}`",
            f"- Bridge: `{report.get('bridge')}`",
            f"- OK: {report.get('ok')}",
            f"- LLM used: {report.get('llm_used')}",
            f"- Reasoning status: `{report.get('reasoning_status')}`",
            f"- Exit code: {report.get('exit_code')}",
            f"- Timed out: {report.get('timed_out')}",
            f"- Weak/local fallback refused: {report.get('weak_local_fallback_refused')}",
            f"- Parsed JSON: `{json.dumps(report.get('parsed_json', {}), sort_keys=True)}`",
            f"- Error: `{report.get('error')}`",
            "",
        ])
        md_path.write_text(md, encoding="utf-8")
    return outputs


def parse_args(argv: list[str]) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Invoke Hermes high-reasoning provider and require strict JSON stdout.")
    ap.add_argument("--canary", action="store_true")
    ap.add_argument("--prompt", default="")
    ap.add_argument("--schema-name", default="generic")
    ap.add_argument("--provider", default=None)
    ap.add_argument("--model", default=None)
    ap.add_argument("--reasoning-profile", default="")
    ap.add_argument("--timeout-seconds", type=int, default=int(os.environ.get("TEREFO_LLM_TIMEOUT_SECONDS", DEFAULT_TIMEOUT)))
    ap.add_argument("--output-dir", default="reports/editorial")
    ap.add_argument("--run-id", default="latest")
    ap.add_argument("--json-only", action="store_true")
    ap.add_argument("--markdown-only", action="store_true")
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    prompt_model = args.model or ("gpt-5.5" if args.reasoning_profile else os.environ.get("TEREFO_LLM_REASONING_MODEL", DEFAULT_MODEL))
    prompt = canary_prompt(prompt_model) if args.canary else args.prompt
    validator = validate_canary if args.canary else None
    if not prompt:
        print(json.dumps({"ok": False, "error": "prompt_missing"}, sort_keys=True), file=sys.stdout)
        return 2
    try:
        result = call_high_reasoning_json(prompt, "canary" if args.canary else args.schema_name, validator, args.provider, args.model, args.timeout_seconds, args.reasoning_profile or None)
        if args.canary:
            outputs = write_canary_reports(result, Path(args.output_dir), args.run_id, args.json_only, args.markdown_only)
            result["output_paths"] = outputs
        print(json.dumps(result, sort_keys=True, ensure_ascii=False), file=sys.stdout)
        return 0
    except HighReasoningError as exc:
        result = exc.result
        if args.canary:
            try:
                outputs = write_canary_reports(result, Path(args.output_dir), args.run_id, args.json_only, args.markdown_only)
                result["output_paths"] = outputs
            except Exception:
                pass
        print(json.dumps(result, sort_keys=True, ensure_ascii=False), file=sys.stdout)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
