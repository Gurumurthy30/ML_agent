import pytest
from tools.tracer import record_event
from agents.reporter_agent import _build_monitoring_summary


def test_build_monitoring_summary_uses_tracer_and_groups_by_parent():
    run_id = "test_reporter_aggregation_run"

    # Record events via tracer with parent_agent
    record_event(
        run_id=run_id,
        agent="features_agent",
        event_type="step_end",
        duration_sec=1.5,
    )
    record_event(
        run_id=run_id,
        agent="coder_agent",
        event_type="coder_attempt",
        parent_agent="features_agent",
        parent_iteration=1,
        duration_ms=500,
    )
    record_event(
        run_id=run_id,
        agent="modeler_agent",
        event_type="attempt_result",
        model_name="RandomForest",
        cv_score=0.85,
        parent_agent="modeler_agent",
        duration_ms=1200,
    )
    record_event(
        run_id=run_id,
        agent="coder_agent",
        event_type="step_error",
        error="IndexError: out of bounds",
        parent_agent="modeler_agent",
    )

    summary = _build_monitoring_summary(run_id)

    # 1. Must have calls to tracer aggregation results (attempts and errors)
    assert "attempts" in summary, "summary must include structured tracer attempts"
    assert "attempts_by_parent" in summary, "summary must group attempts by parent_agent"
    assert "errors_by_parent" in summary, "summary must group errors by parent_agent"

    # 2. Verify parent nesting in steps_per_agent
    steps = summary["steps_per_agent"]
    assert "features_agent/coder_agent" in steps or "features_agent" in summary["attempts_by_parent"]

    # 3. Verify error signature aggregation from tracer
    assert len(summary["errors"]) > 0
    assert any("error_signature" in err for err in summary["errors"])
