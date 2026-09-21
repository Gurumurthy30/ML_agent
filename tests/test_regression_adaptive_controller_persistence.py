"""
Regression test for 0c: Adaptive controller multi-process state persistence.
Verifies that TriedIdeasRegistry, ErrorSignatureDeduplicator, and SafetyEnvelope
state persists in SQLite so distinct worker process instances share state.
"""
import time
import pytest
from agents.adaptive_controller import (
    TriedIdeasRegistry,
    ErrorSignatureDeduplicator,
    SafetyEnvelope,
)


def test_tried_ideas_registry_cross_process_persistence():
    run_id = f"test_run_ideas_{int(time.time()*1000)}"
    worker_1 = TriedIdeasRegistry()
    worker_2 = TriedIdeasRegistry()

    # Worker 1 records an idea
    worker_1.record_idea(
        run_id=run_id,
        phase="features",
        tier=1,
        idea_summary="Target encoding on categorical columns with smoothing",
        details={"columns": ["cat1", "cat2"]},
    )

    # Worker 2 (separate instance, empty memory cache) checks is_tried
    tried, reason = worker_2.is_tried(
        run_id=run_id,
        phase="features",
        idea_summary="Target encoding on categorical columns with smoothing",
    )
    assert tried is True
    assert "Identical idea already tested at tier 1" in (reason or "")

    # Worker 2 retrieves summaries
    summaries = worker_2.get_tried_summaries(run_id=run_id, phase="features")
    assert len(summaries) == 1
    assert "Target encoding" in summaries[0]


def test_error_signature_deduplicator_cross_process_persistence():
    run_id = f"test_run_errs_{int(time.time()*1000)}"
    worker_1 = ErrorSignatureDeduplicator()
    worker_2 = ErrorSignatureDeduplicator()

    err_msg = "KeyError: 'target_col' not found at line 42 in /tmp/test.py"

    # Worker 1 records first error
    sig1, is_repeat1 = worker_1.record_error(run_id, "KeyError", err_msg)
    assert is_repeat1 is False
    assert worker_1.should_force_escalate(run_id, max_consecutive=2) is False

    # Worker 2 records second identical error (from a different request/worker)
    sig2, is_repeat2 = worker_2.record_error(run_id, "KeyError", err_msg)
    assert sig1 == sig2
    assert is_repeat2 is True
    assert worker_2.should_force_escalate(run_id, max_consecutive=2) is True


def test_safety_envelope_cross_process_persistence():
    run_id = f"test_run_safety_{int(time.time()*1000)}"
    worker_1 = SafetyEnvelope(max_wall_time_s=2)
    worker_2 = SafetyEnvelope(max_wall_time_s=2)

    # Worker 1 starts the run
    worker_1.start_run(run_id)

    # Worker 2 immediately checks: should be safe
    status, _ = worker_2.check_envelope(run_id, current_iteration=1)
    assert status == "safe"

    # Wait for time limit to exceed
    time.sleep(2.1)

    # Worker 2 checks envelope after timeout: should be exhausted
    status, reason = worker_2.check_envelope(run_id, current_iteration=2)
    assert status == "exhausted"
    assert "Wall-clock safety limit reached" in reason
