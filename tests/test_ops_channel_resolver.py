import json
from pathlib import Path

from scripts.ops_channel_resolver import (
    resolve_alias,
    sanitize_directory,
    sanitize_send_list,
    reject_ops_substitute,
    safe_add_alias,
)


def test_marius_dm_rejected_as_ops_substitute():
    assert reject_ops_substitute("telegram:Marius") == "rejected_non_ops_dm"
    assert reject_ops_substitute("Marius") == "rejected_non_ops_dm"


def test_unknown_alias_unresolved_without_fallback():
    directory = {"channels": [{"name": "Marius", "platform": "telegram", "chat_id": "123"}]}
    result = resolve_alias(directory, "AL-Hermoine-OPS")
    assert result["status"] == "ops_alias_unresolved"
    assert result["fallback_accepted"] is False
    assert result["fallback_channel_used"] is False


def test_safe_alias_accepted_only_when_known_non_dm():
    directory = {"channels": [{"name": "AL-Hermoine-OPS", "platform": "telegram", "kind": "group", "chat_id": "-100123"}]}
    result = resolve_alias(directory, "AL-Hermoine-OPS")
    assert result["status"] == "ops_alias_resolved"
    assert result["is_dm"] is False
    assert result["target_redacted"] == "[REDACTED]"


def test_no_secrets_emitted_by_sanitizer():
    directory = {"channels": [{"name": "AL-Hermoine-OPS", "chat_id": "-1001234567890", "bot_token": "123456789:***"}]}
    sanitized = json.dumps(sanitize_directory(directory))
    assert "-1001234567890" not in sanitized
    assert "abcdefghijklmnopqrstuvwxyz" not in sanitized
    assert "[REDACTED" in sanitized


def test_send_list_sanitizer_removes_bracketed_marius_target_suffix():
    sanitized = sanitize_send_list("telegram:\n  telegram:Marius  [123456]\n")
    assert "123456" not in sanitized
    assert "telegram:Marius [" not in sanitized
    assert "telegram:Marius (rejected_non_ops_dm)" in sanitized


def test_safe_add_alias_preserves_existing_and_refuses_fake_target(tmp_path):
    p = tmp_path / "channel_directory.json"
    p.write_text(json.dumps({"channels": [{"name": "Other", "platform": "telegram", "kind": "group", "chat_id": "-1001"}]}))
    missing = safe_add_alias(p, "AL-Hermoine-OPS", None)
    assert missing["status"] == "failed_closed_no_resolvable_ops_target"
    added = safe_add_alias(p, "AL-Hermoine-OPS", {"platform": "telegram", "kind": "group", "chat_id": "-1002"})
    assert added["status"] == "ops_alias_resolved"
    data = json.loads(p.read_text())
    assert len(data["channels"]) == 2


def test_ops_bot_home_alias_is_safe_private_delivery_contract():
    directory = {'channels': [{'name': 'AL-Hermoine-OPS', 'platform': 'telegram', 'kind': 'ops_bot_home', 'delivery_profile': 'ops-bot', 'delivery_target': 'telegram'}]}
    result = resolve_alias(directory, 'AL-Hermoine-OPS')
    assert result['status'] == 'ops_alias_resolved'
    assert result['delivery_profile'] == 'ops-bot'
    assert result['delivery_target'] == 'telegram'
    assert result['fallback_channel_used'] is False
