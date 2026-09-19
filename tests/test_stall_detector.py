"""
Unit tests for the new stall-detection, state-fingerprinting, and stopping-criterion logic.
"""
import pytest
from unittest.mock import patch, MagicMock

from config import METRIC_IMPROVEMENT_EPSILON, LOOP_SAFETY_CEILING
from state import build_initial_state
from agents.supervisor import (
    compute_agent_fingerprint,
    SupervisorDecision,
    graph_node_supervisor,
    _determine_fallback_next_agent,
    _validate_and_override_decision,
)


def _base_state(**overrides):
    s = build_initial_state("fake.csv")
    s["profile"] = {"rows": 100, "columns": 5}
    s["eda_findings"] = {"narrative": "test"}
    s["feature_set"] = {"steps": ["scale"]}
    s.update(overrides)
    return s


# ---------------------------------------------------------------------------
# Test 1: State fingerprinting determinism and sensitivity
# ---------------------------------------------------------------------------

def test_fingerprint_deterministic():
    state1 = _base_state(
        candidate_models=[{"model_family": "RandomForest", "cv_score": 0.81}],
        judge_feedback="Improve precision",
    )
    state2 = _base_state(
        candidate_models=[{"model_family": "RandomForest", "cv_score": 0.81}],
        judge_feedback="Improve precision",
    )
    fp1 = compute_agent_fingerprint("modeler", state1)
    fp2 = compute_agent_fingerprint("modeler", state2)
    assert fp1 == fp2, "Identical states must yield identical fingerprints"


def test_fingerprint_changes_on_state_change():
    state1 = _base_state(
        candidate_models=[{"model_family": "RandomForest", "cv_score": 0.81}],
        judge_feedback="Feedback A",
    )
    state2 = _base_state(
        candidate_models=[{"model_family": "XGBoost", "cv_score": 0.84}],
        judge_feedback="Feedback B",
    )
    fp1 = compute_agent_fingerprint("modeler", state1)
    fp2 = compute_agent_fingerprint("modeler", state2)
    assert fp1 != fp2, "Different states must produce different fingerprints"


# ---------------------------------------------------------------------------
# Test 2: Supervisor post-retry routing routes Modeler retry to Judge
# ---------------------------------------------------------------------------

def test_post_retry_modeler_routes_to_judge():
    """
    When modeler finishes a retry attempt, supervisor MUST route to judge
    to evaluate the new models rather than looping back to modeler.
    """
    state = _base_state(
        last_verdict="reject",
        retry_tier=1,
        retry_counts={1: 1},
        last_executed_agent="modeler",
        candidate_models=[{"model_family": "RandomForest", "cv_score": 0.80}],
    )
    decision = _determine_fallback_next_agent(state)
    assert decision.next_agent == "judge", (
        f"Expected routing to 'judge' after modeler retry, got '{decision.next_agent}'"
    )


def test_post_retry_features_routes_to_modeler():
    """
    When features finishes a tier-2 retry, supervisor MUST route to modeler
    to train on the new feature representation.
    """
    state = _base_state(
        last_verdict="reject",
        retry_tier=2,
        retry_counts={2: 1},
        last_executed_agent="features",
        feature_set={"steps": ["standardize", "pca"]},
    )
    decision = _determine_fallback_next_agent(state)
    assert decision.next_agent == "modeler", (
        f"Expected routing to 'modeler' after tier-2 features retry, got '{decision.next_agent}'"
    )


# ---------------------------------------------------------------------------
# Test 3: Stall detection with epsilon threshold (metric delta < epsilon)
# ---------------------------------------------------------------------------

def test_stall_detected_when_delta_below_epsilon():
    """
    When the score change between retries is smaller than METRIC_IMPROVEMENT_EPSILON,
    supervisor must flag a stall and escalate to human_approval.
    """
    # delta is 0.0002, smaller than default epsilon 0.001
    tiny_delta_scores = [0.8100, 0.8102]
    assert abs(tiny_delta_scores[1] - tiny_delta_scores[0]) < METRIC_IMPROVEMENT_EPSILON

    state = _base_state(
        last_verdict="reject",
        retry_tier=1,
        retry_counts={1: 1},
        metric_history=tiny_delta_scores,
    )
    decision = SupervisorDecision(
        next_agent="modeler",
        retry_tier=1,
        reasoning="Try another model",
        task_instructions="Train GradientBoosting",
    )

    with patch("agents.supervisor.log_event") as mock_log:
        result = _validate_and_override_decision(decision, state, MagicMock(), "run_test")

    assert result.next_agent == "human_approval"
    assert result.approval_reason == "stalled"
    logged_events = [c.args[2] for c in mock_log.call_args_list if len(c.args) >= 3]
    assert "stalled_retry_escalation" in logged_events


# ---------------------------------------------------------------------------
# Test 4: Stall detection with identical state fingerprint
# ---------------------------------------------------------------------------

def test_stall_detected_when_fingerprint_is_identical():
    """
    If the state fingerprint before retry matches the previous fingerprint,
    supervisor must escalate on identical state stall.
    """
    state = _base_state(
        last_verdict="reject",
        retry_tier=1,
        retry_counts={1: 1},
        metric_history=[0.75, 0.80],  # scores differed earlier
    )
    # Record fingerprint in state as if previous attempt had this exact state
    fp = compute_agent_fingerprint("modeler", state)
    state["agent_fingerprints"] = {"modeler": fp}

    decision = SupervisorDecision(
        next_agent="modeler",
        retry_tier=1,
        reasoning="Try again",
        task_instructions="Train model",
    )

    with patch("agents.supervisor.log_event") as mock_log:
        result = _validate_and_override_decision(decision, state, MagicMock(), "run_test")

    assert result.next_agent == "human_approval"
    assert result.approval_reason == "stalled"
    logged_events = [c.args[2] for c in mock_log.call_args_list if len(c.args) >= 3]
    assert "stalled_retry_escalation" in logged_events


# ---------------------------------------------------------------------------
# Test 5: Stop reasons surfaced in supervisor output
# ---------------------------------------------------------------------------

def test_stop_reason_converged_on_reporter():
    state = _base_state(
        profile={"rows": 10},
        eda_findings={"findings": "ok"},
        feature_set={"steps": ["scale"]},
        candidate_models=[{"model_family": "LR", "cv_score": 0.85}],
        last_verdict="accept",
    )
    with patch("agents.supervisor.invoke_structured_robust", return_value=SupervisorDecision(
        next_agent="reporter",
        reasoning="Judge accepted model",
        task_instructions="Compile report",
    )):
        res = graph_node_supervisor(state)

    assert res["next_agent"] == "reporter"
    assert res["stop_reason"] == "converged"


def test_stop_reason_safety_ceiling_on_global_limit():
    from config import GLOBAL_ITER_CEILING
    state = _base_state(iteration=GLOBAL_ITER_CEILING + 5)
    res = graph_node_supervisor(state)
    assert res["next_agent"] == "human_approval"
    assert res["stop_reason"] == "hit_safety_ceiling"
    assert res["approval_reason"] == "global_iteration_ceiling"
