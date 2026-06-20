# Run 60 closed-loop all-chapter public proof

- run_id: `run60`
- component: `closed_loop_manuscript_public_proof`
- all_chapter_public_proof_gate_wired: `True`
- autonomous_closed_loop_iteration_coverage: `True`
- daily_worker_preflight_ok: `True`
- all_chapter_public_proof_executed: `True`
- all_chapter_public_proof_ok: `False`
- total_chapters: `8`
- passed_chapters: `['agent_loop']`
- failed_chapters: `['context_memory', 'hermes', 'introduction', 'loop_engineering', 'methodology', 'openclaw', 'operating_loops']`
- missing_chapters: `['methodology']`
- policy: `Run all-chapter public proof in the autonomous closed-loop iteration/addition gate; any evidence-led or missing chapter fails closed before publication/commit.`
- fallback_channel_used: `False`
- weak_local_fallback_used: `False`
- generated_at_utc_iso: `2026-06-20T20:13:07.774647+00:00`
