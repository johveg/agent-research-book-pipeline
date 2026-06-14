#!/usr/bin/env python3
"""Central model-profile loader for safety-critical reasoning/coding routes."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config" / "reasoning_models.json"

REQUIRED_FIELDS = {
    "provider": str,
    "model": str,
    "bridge": str,
    "reasoning_effort": str,
    "task_class": str,
    "allow_weak_fallback": bool,
    "allow_local_fallback": bool,
    "strict_json_required": bool,
}

ALLOWED_PROFILE_NAMES = {"editorial_reasoning", "coding_agent", "closed_loop_editorial"}
ALLOWED_REASONING_EFFORTS = {"low", "medium", "high"}
ALLOWED_BRIDGES = {"hermes_cli", "codex_cli"}
ALLOWED_DISPOSITIONS = {
    "auto_quarantine",
    "discovery_only",
    "needs_more_sources",
    "caveat_only",
    "exclude_from_pipeline",
    "contradiction_review_required",
    "safe_reports_only",
    "eligible_for_review_note_persistence",
    "blocked_for_publication_by_policy",
    "source_context_unclear",
}


class ModelProfileError(RuntimeError):
    """Fail-closed model-profile configuration error."""


def _resolve_config_path(config_path: str | Path | None = None) -> Path:
    if config_path is None:
        return DEFAULT_CONFIG
    p = Path(config_path)
    return p if p.is_absolute() else ROOT / p


def load_model_config(config_path: str | Path | None = None) -> dict[str, Any]:
    path = _resolve_config_path(config_path)
    if not path.exists():
        raise ModelProfileError(f"model profile config missing: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ModelProfileError(f"model profile config invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ModelProfileError("model profile config must be a JSON object")
    if not isinstance(data.get("profiles"), dict):
        raise ModelProfileError("model profile config missing profiles object")
    if not isinstance(data.get("defaults"), dict):
        raise ModelProfileError("model profile config missing defaults object")
    return data


def validate_model_profile(name: str, profile: dict[str, Any]) -> dict[str, Any]:
    if name not in ALLOWED_PROFILE_NAMES:
        raise ModelProfileError(f"invalid profile enum: {name}")
    if not isinstance(profile, dict):
        raise ModelProfileError(f"profile {name} must be object")
    for field, typ in REQUIRED_FIELDS.items():
        if field not in profile:
            raise ModelProfileError(f"profile {name} missing required field: {field}")
        if not isinstance(profile[field], typ) or (typ is str and not profile[field].strip()):
            raise ModelProfileError(f"profile {name} invalid field: {field}")
    if profile["reasoning_effort"] not in ALLOWED_REASONING_EFFORTS:
        raise ModelProfileError(f"profile {name} invalid reasoning_effort")
    if profile["bridge"] not in ALLOWED_BRIDGES:
        raise ModelProfileError(f"profile {name} invalid bridge")
    if profile["allow_weak_fallback"] is not False:
        raise ModelProfileError(f"profile {name} must disallow weak fallback")
    if profile["allow_local_fallback"] is not False:
        raise ModelProfileError(f"profile {name} must disallow local fallback")
    if name in {"editorial_reasoning", "closed_loop_editorial"} and profile["strict_json_required"] is not True:
        raise ModelProfileError(f"profile {name} must require strict JSON")
    if name == "closed_loop_editorial":
        dispositions = profile.get("allowed_dispositions")
        if not isinstance(dispositions, list) or not dispositions:
            raise ModelProfileError("closed_loop_editorial missing allowed_dispositions")
        unknown = set(dispositions) - ALLOWED_DISPOSITIONS
        if unknown:
            raise ModelProfileError(f"closed_loop_editorial invalid dispositions: {sorted(unknown)}")
    out = dict(profile)
    out["profile_name"] = name
    out["weak_local_fallback_refused"] = True
    return out


def load_model_profile(profile_name: str, config_path: str | Path | None = None) -> dict[str, Any]:
    data = load_model_config(config_path)
    profiles = data["profiles"]
    defaults = data["defaults"]
    name = defaults.get(profile_name, profile_name)
    if not isinstance(name, str) or name not in profiles:
        raise ModelProfileError(f"model profile missing: {profile_name}")
    return validate_model_profile(name, profiles[name])


def resolve_model_profile(
    profile_name: str | None,
    provider: str | None = None,
    model: str | None = None,
    config_path: str | Path | None = None,
) -> dict[str, Any]:
    """Resolve explicit CLI provider/model or a named profile.

    Missing config fails closed unless explicit provider and model are supplied.
    Explicit provider/model remain backward-compatible and override profile metadata.
    """
    if provider and model:
        return {
            "profile_name": "explicit_cli",
            "provider": provider,
            "model": model,
            "bridge": "hermes_cli",
            "reasoning_effort": "high",
            "task_class": profile_name or "explicit_cli",
            "allow_weak_fallback": False,
            "allow_local_fallback": False,
            "strict_json_required": True,
            "weak_local_fallback_refused": True,
        }
    if not profile_name:
        profile_name = "editorial_reasoning"
    return load_model_profile(profile_name, config_path=config_path)
