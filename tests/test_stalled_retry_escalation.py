"""
Tests for stalled-retry escalation (Section 2.2).

Verifies that the supervisor escalates to human_approval (and logs
stalled_retry_escalation) when a tier-1 retry is about to be issued but
metric_history shows no improvement between the first attempt and now.

Uses metric_history[-1] == metric_history[-2] as the stall signal,
consistent with how supervisor._validate_and_override_decision is implemented.
"""
import pytest
from unittest.mock import patch, MagicMock


def _state(
    *,
    run_id="test_run",
    retry_tier=1,
    retry_counts=None,
    last_verdict="reject",
    metric_history=None,
    iteration=5,
):
    return {
        "run_id": run_id,
        "dataset_fingerprint": "abc123",
        "mode": "full_pipeline",
        "guided_mode": False,
        "dataset_path": "fake.csv",
        "profile": {"rows": 100, "columns": 5},
        "eda_findings": {"narrative": "test"},
        "feature_set": {"steps": ["impute"]},
        "candidate_models": [{"model_family": "RandomForest", "cv_score": 0.72}],
        "metric_history": metric_history or [],
        "best_metric": max(metric_history) if metric_history else None,
        "last_verdict": last_verdict,
        "retry_tier": retry_tier,
        "retry_counts": retry_counts or {},
        "judge_feedback": "Model accuracy is not good enough",
        "requires_human_approval": False,
        "approval_reason": None,
        "approval_status": None,
        "feature_plan": None,
        "task_instructions": "",
        "supervisor_reasoning": "",
        "next_agent": None,
        "target_column": "target",
        "task_type": "classification",
        "iteration": iteration,
        "messages": [],
        "report": "",
        "artifact_path": "",
        "run_memory": [],
        "transformed_dataset_path": None,
    }


# ---------------------------------------------------------------------------
# Test 1: Identical scores → stall → escalate
# ---------------------------------------------------------------------------

def test_stall_detected_when_scores_identical():
    """
    retry_counts[1] == 1 (first retry already happened) + metric_history[-1] == metric_history[-2]
    → must escalate to human_approval instead of routing to modeler.
    """
    from agents.supervisor import SupervisorDecision, graph_node_supervisor

    llm_decision = SupervisorDecision(
        next_agent="modeler",
        retry_tier=1,
        reasoning="Try SVM",
        task_instructions="Use SVC with RBF kernel",
        requires_human_approval=False,
    )

    # Identical last two scores — clear stall signal
    state = _state(
        retry_tier=1,
        retry_counts={1: 1},
        metric_history=[0.72, 0.72],
    )

    with patch("agents.supervisor.invoke_structured_robust", return_value=llm_decision), \
         patch("agents.supervisor.log_event") as mock_log:

        result = graph_node_supervisor(state)

    assert result["next_agent"] == "human_approval", (
        f"Expected escalation to human_approval on stall, got {result['next_agent']}"
    )
    log_calls = [call.args for call in mock_log.call_args_list]
    stall_logged = any(
        len(c) >= 3 and c[2] == "stalled_retry_escalation"
        for c in log_calls
    )
    assert stall_logged, "stalled_retry_escalation event was not logged"


# ---------------------------------------------------------------------------
# Test 2: Different scores → no stall → routing proceeds
# ---------------------------------------------------------------------------

def test_no_stall_when_scores_improved():
    """
    When the first retry actually improved the score, no stall should be detected
    and the second retry should proceed (if under cap).
    """
    from agents.supervisor import SupervisorDecision, graph_node_supervisor

    llm_decision = SupervisorDecision(
        next_agent="modeler",
        retry_tier=1,
        reasoning="Score improved, try once more",
        task_instructions="Use GradientBoosting",
        requires_human_approval=False,
    )

    # Different scores — improvement detected
    state = _state(
        retry_tier=1,
        retry_counts={1: 1},
        metric_history=[0.70, 0.75],  # improved!
    )

    with patch("agents.supervisor.invoke_structured_robust", return_value=llm_decision), \
         patch("agents.supervisor.log_event") as mock_log:

        result = graph_node_supervisor(state)

    # Should NOT escalate on improvement
    assert result["next_agent"] == "modeler", (
        f"Should not escalate when metric improved (0.70 → 0.75), got {result['next_agent']}"
    )
    log_calls = [call.args for call in mock_log.call_args_list]
    stall_logged = any(
        len(c) >= 3 and c[2] == "stalled_retry_escalation"
        for c in log_calls
    )
    assert not stall_logged, "stalled_retry_escalation should not be logged when improvement occurred"


# ---------------------------------------------------------------------------
# Test 3: First retry (count==0) — stall check should not fire yet
# ---------------------------------------------------------------------------

def test_stall_check_not_fired_on_first_retry():
    """
    Stall detection only fires when count==1 (about to do 2nd retry).
    On the very first retry (count==0), stall check must not trigger even if
    metric_history has a repeated value (there might just be one score).
    """
    from agents.supervisor import SupervisorDecision, graph_node_supervisor

    llm_decision = SupervisorDecision(
        next_agent="modeler",
        retry_tier=1,
        reasoning="First retry — try alternative",
        task_instructions="Use XGBoost",
        requires_human_approval=False,
    )

    state = _state(
        retry_tier=1,
        retry_counts={1: 0},  # first retry (0 prior attempts)
        metric_history=[0.72],  # only one score so far
    )

    with patch("agents.supervisor.invoke_structured_robust", return_value=llm_decision), \
         patch("agents.supervisor.log_event"):

        result = graph_node_supervisor(state)

    assert result["next_agent"] == "modeler", (
        f"First retry (count=0) should not trigger stall detection, got {result['next_agent']}"
    )


# ---------------------------------------------------------------------------
# Test 4: Short history (< 2 entries) — stall check gracefully skipped
# ---------------------------------------------------------------------------

def test_stall_check_graceful_with_short_history():
    """Stall check requires at least 2 entries in metric_history. With only 1, must not error."""
    from agents.supervisor import SupervisorDecision, graph_node_supervisor

    llm_decision = SupervisorDecision(
        next_agent="modeler",
        retry_tier=1,
        reasoning="Try alternative",
        task_instructions="Use ExtraTreesClassifier",
        requires_human_approval=False,
    )

    state = _state(
        retry_tier=1,
        retry_counts={1: 1},
        metric_history=[0.72],  # only 1 entry — stall check should be skipped
    )

    with patch("agents.supervisor.invoke_structured_robust", return_value=llm_decision), \
         patch("agents.supervisor.log_event"):

        result = graph_node_supervisor(state)

    # Should not raise, and should route to modeler (stall not triggered)
    assert result["next_agent"] == "modeler"
