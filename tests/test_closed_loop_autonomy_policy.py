import importlib.util
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def load(name):
    spec=importlib.util.spec_from_file_location(name, ROOT/'scripts'/f'{name}.py'); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
def test_unresolved_ops_alias_with_outbox_is_degraded_continue_allowed():
    m=load('closed_loop_autonomy_policy'); r=m.evaluate_policy({'ops_alias_resolved':False,'outbox_available':True,'ops_status_queued':True})
    assert r['continue_allowed'] is True and r['degraded_mode'] is True
    assert 'ops_alias_unresolved_but_status_queued' in r['degradation_reasons']
def test_unresolved_ops_alias_without_outbox_failed_closed():
    m=load('closed_loop_autonomy_policy'); r=m.evaluate_policy({'ops_alias_resolved':False,'outbox_available':False})
    assert r['continue_allowed'] is False
    assert 'ops_alias_unresolved_without_durable_outbox' in r['hard_stop_reasons']
def test_fallback_docs_book_secrets_are_hard_stops():
    m=load('closed_loop_autonomy_policy')
    for key in ['fallback_telegram_channel_used','docs_book_changed_without_publication_gate','secrets_detected']:
        r=m.evaluate_policy({key:True,'ops_alias_resolved':True})
        assert r['continue_allowed'] is False and key in r['hard_stop_reasons']
def test_methodology_report_only_allowed_in_degraded_but_publication_false_and_no_human_flags():
    m=load('closed_loop_autonomy_policy'); r=m.evaluate_policy({'ops_alias_resolved':False,'outbox_available':True,'ops_status_queued':True,'methodology_report_only':True})
    assert r['continue_allowed'] is True
    assert r['publication_allowed'] is False
    assert r['human_required'] is False and r['manual_action_required'] is False
    assert 'methodology_draft_report_only' in r['degradation_reasons']
