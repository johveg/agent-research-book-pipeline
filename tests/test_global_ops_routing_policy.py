import json
from scripts.global_ops_routing_policy import classify_delivery, routing_fixed, load_policy


def test_all_ops_messages_require_al_hermoine_ops():
    policy = load_policy("config/global_ops_routing_policy.json")
    result = classify_delivery({"target_channel": "Other", "fallback_channel_used": False, "status_metadata": {"emitted_at_unix_s": 1}}, policy, alias_resolvable=True)
    assert result["classification"] == "failed_closed"
    assert "unresolved_target" in result["reasons"] or "wrong_target_channel" in result["reasons"]


def test_fallback_default_dm_is_hard_fail():
    policy = load_policy("config/global_ops_routing_policy.json")
    result = classify_delivery({"target_channel": "telegram:Marius", "fallback_channel_used": True, "status_metadata": {"emitted_at_unix_s": 1}}, policy, alias_resolvable=True)
    assert result["classification"] == "blocked_fallback"
    assert result["success"] is False


def test_unresolved_ops_requires_queue_not_fallback():
    policy = load_policy("config/global_ops_routing_policy.json")
    result = classify_delivery({"target_channel": "AL-Hermoine-OPS", "fallback_channel_used": False, "status_metadata": {"emitted_at_unix_s": 1}, "queued": True}, policy, alias_resolvable=False)
    assert result["classification"] == "queued"
    assert result["disposition"] == "ops_outbox_queued"


def test_success_requires_confirmed_live_delivery():
    policy = load_policy("config/global_ops_routing_policy.json")
    no_confirm = classify_delivery({"target_channel": "AL-Hermoine-OPS", "fallback_channel_used": False, "status_metadata": {"emitted_at_unix_s": 1}}, policy, alias_resolvable=True)
    assert no_confirm["classification"] == "failed_closed"
    ok = classify_delivery({"target_channel": "AL-Hermoine-OPS", "fallback_channel_used": False, "status_metadata": {"emitted_at_unix_s": 1}, "delivery_confirmation": {"message_id": "m1"}}, policy, alias_resolvable=True)
    assert ok["classification"] == "compliant"
    assert ok["success"] is True


def test_final_routing_fixed_requires_live_delivery():
    assert routing_fixed(alias_resolvable=True, live_delivery_confirmed=False) is False
    assert routing_fixed(alias_resolvable=True, live_delivery_confirmed=True) is True
