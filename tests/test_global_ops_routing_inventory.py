import json
from pathlib import Path

from scripts.global_ops_routing_inventory import classify_emitter, build_inventory, inventory_schema_version


def test_telegram_marius_flagged_as_non_ops_default_dm():
    item = classify_emitter(
        component="sample",
        repo_or_profile="test",
        path="x",
        text="send status to telegram:Marius by default",
        current_target="telegram:Marius",
    )
    assert item["should_route_to_ops"] is True
    assert item["sends_to_dm"] is True
    assert item["sends_to_default"] is True
    assert item["uses_fallback"] is True
    assert item["risk"] == "high"
    assert item["recommended_action"] == "replace_non_ops_target_with_AL-Hermoine-OPS_or_queue"


def test_al_hermoine_ops_required_and_compliant_when_present():
    item = classify_emitter(
        component="sample",
        repo_or_profile="test",
        path="x",
        text="target_channel: AL-Hermoine-OPS emitted_at_unix_s fallback_channel_used: false",
        current_target="AL-Hermoine-OPS",
        alias_resolvable=True,
    )
    assert item["current_target"] == "AL-Hermoine-OPS"
    assert item["target_channel_metadata"] is True
    assert item["uses_fallback"] is False
    assert item["severity"] == "info"


def test_fallback_routes_and_missing_metadata_are_flagged():
    item = classify_emitter(
        component="fallback",
        repo_or_profile="test",
        path="x",
        text="fallback_channel_used true send_message telegram",
        current_target="telegram",
    )
    assert item["uses_fallback"] is True
    assert item["sends_to_default"] is True
    assert item["target_channel_metadata"] is False
    assert item["status_timestamp_metadata_present"] is False
    assert item["risk"] == "high"


def test_inventory_output_schema_is_stable(tmp_path):
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    (repo / "scripts" / "send_ops_status.py").write_text("target_channel='AL-Hermoine-OPS'\nemitted_at_unix_s=1\n")
    inv = build_inventory(
        roots={"terefo": repo},
        cron_paths=[],
        alias_resolvable=False,
    )
    assert inv["schema_version"] == inventory_schema_version()
    assert "emitters" in inv
    assert inv["required_ops_channel"] == "AL-Hermoine-OPS"
    assert inv["emitters"][0]["component"]
    required = {
        "component", "repo_or_profile", "path", "job_id", "job_name", "current_target",
        "current_target_resolvable", "target_channel_metadata", "uses_fallback", "fallback_target",
        "sends_to_dm", "sends_to_default", "should_route_to_ops", "can_patch_safely",
        "required_patch", "status_timestamp_metadata_present", "severity", "risk", "recommended_action",
    }
    assert required.issubset(inv["emitters"][0])
