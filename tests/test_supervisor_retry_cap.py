"""
Tests for supervisor retry cap enforcement (Bug 9 / Section 2.1).

Verifies that graph_node_supervisor ALWAYS overrides an LLM decision that would
exceed the per-tier retry cap (2 attempts), regardless of what the LLM returns.
Also verifies the stalled-retry escalation (Section 2.2).

These tests use mocking to avoid actual LLM calls — the key invariant being
tested is the deterministic code path, not the LLM's output.
"""
import os
import pytest
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# Helpers — minimal AgentState stubs
# ---------------------------------------------------------------------------

def _state(
    *,
    run_id="test_run",
    retry_tier=1,
    retry_counts=None,
    last_verdict="reject",
    metric_history=None,
    iteration=0,
    profile={"rows": 100, "columns": 5},
    eda_findings={"narrative": "test"},
    feature_set={"steps": ["impute"]},
    candidate_models=[{"model_family": "RandomForest", "cv_score": 0.72}],
):
    return {
        "run_id": run_id,
        "dataset_fingerprint": "abc123",
        "mode": "full_pipeline",
        "guided_mode": False,
        "dataset_path": "fake.csv",
        "profile": profile,
        "eda_findings": eda_findings,
        "feature_set": feature_set,
        "candidate_models": candidate_models,
        "metric_history": metric_history or [],
        "best_metric": None,
        "last_verdict": last_verdict,
        "retry_tier": retry_tier,
        "retry_counts": retry_counts or {},
        "judge_feedback": "Model accuracy too low",
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
# Test 1: Tier-1 cap enforced — LLM wants to re-route to modeler but count >= 2
# ---------------------------------------------------------------------------

def test_tier1_cap_overrides_llm_decision():
    """
    When retry_counts[1] >= 2, supervisor must escalate to human_approval
    regardless of what the LLM's structured output says.
    """
    from agents.supervisor import SupervisorDecision, graph_node_supervisor

    # LLM would return: route to modeler with tier-1
    llm_decision = SupervisorDecision(
        next_agent="modeler",
        retry_tier=1,
        reasoning="Try another model family",
        task_instructions="Use XGBoost",
        requires_human_approval=False,
    )

    state = _state(retry_tier=1, retry_counts={1: 2}, last_verdict="reject",
                   metric_history=[0.72, 0.73])

    with patch("agents.supervisor.invoke_structured_robust", return_value=llm_decision), \
         patch("agents.supervisor.log_event") as mock_log:

        result = graph_node_supervisor(state)

    assert result["next_agent"] == "human_approval", (
        f"Expected human_approval but got {result['next_agent']}. "
        "Supervisor must override LLM when tier-1 cap (2/2) is reached."
    )
    # Verify override was logged
    log_calls = [call.args for call in mock_log.call_args_list]
    override_logged = any(
        len(c) >= 3 and c[2] == "retry_cap_override"
        for c in log_calls
    )
    assert override_logged, "retry_cap_override event was not logged"


# ---------------------------------------------------------------------------
# Test 2: Tier-2 cap enforced
# ---------------------------------------------------------------------------

def test_tier2_cap_overrides_llm_decision():
    """Tier-2 retry cap (2/2) must also escalate regardless of LLM output."""
    from agents.supervisor import SupervisorDecision, graph_node_supervisor

    llm_decision = SupervisorDecision(
        next_agent="features",
        retry_tier=2,
        reasoning="Re-engineer features again",
        task_instructions="Try different encoding",
        requires_human_approval=False,
    )

    state = _state(retry_tier=2, retry_counts={2: 2}, last_verdict="reject",
                   metric_history=[0.72, 0.72])

    with patch("agents.supervisor.invoke_structured_robust", return_value=llm_decision), \
         patch("agents.supervisor.log_event") as mock_log:

        result = graph_node_supervisor(state)

    assert result["next_agent"] == "human_approval"
    log_calls = [call.args for call in mock_log.call_args_list]
    override_logged = any(
        len(c) >= 3 and c[2] == "retry_cap_override"
        for c in log_calls
    )
    assert override_logged, "retry_cap_override event was not logged for tier-2"


# ---------------------------------------------------------------------------
# Test 3: Under cap — LLM decision is respected
# ---------------------------------------------------------------------------

def test_under_cap_llm_decision_respected():
    """When retry_counts[1] == 1 (still under cap), LLM routing is used."""
    from agents.supervisor import SupervisorDecision, graph_node_supervisor

    llm_decision = SupervisorDecision(
        next_agent="modeler",
        retry_tier=1,
        reasoning="Try gradient boosting",
        task_instructions="Use GradientBoostingClassifier",
        requires_human_approval=False,
    )

    state = _state(retry_tier=1, retry_counts={1: 1}, last_verdict="reject",
                   metric_history=[0.70, 0.75])  # improved

    with patch("agents.supervisor.invoke_structured_robust", return_value=llm_decision), \
         patch("agents.supervisor.log_event"):

        result = graph_node_supervisor(state)

    assert result["next_agent"] == "modeler", (
        f"LLM's modeler routing should be respected when count=1 < cap=2, got {result['next_agent']}"
    )


# ---------------------------------------------------------------------------
# Test 4: Stalled-retry escalation
# ---------------------------------------------------------------------------

def test_stalled_retry_escalation_when_no_improvement():
    """
    When retry_counts[1] == 1 (about to do 2nd attempt) but metric_history
    shows the last two scores are identical, escalate early instead of burning
    the last attempt on a pointless repeat.
    """
    from agents.supervisor import SupervisorDecision, graph_node_supervisor

    llm_decision = SupervisorDecision(
        next_agent="modeler",
        retry_tier=1,
        reasoning="Try SVM",
        task_instructions="Use SVC",
        requires_human_approval=False,
    )

    # Identical last two scores — stall condition
    state = _state(retry_tier=1, retry_counts={1: 1}, last_verdict="reject",
                   metric_history=[0.72, 0.72])

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
# Test 5: No false positive — non-reject state is not affected by cap logic
# ---------------------------------------------------------------------------

def test_no_cap_enforcement_outside_reject_cycle():
    """Retry cap logic must not fire when last_verdict != 'reject'."""
    from agents.supervisor import SupervisorDecision, graph_node_supervisor

    llm_decision = SupervisorDecision(
        next_agent="judge",
        retry_tier=None,
        reasoning="Models ready, send to judge",
        task_instructions="Evaluate candidates",
        requires_human_approval=False,
    )

    state = _state(last_verdict=None, retry_tier=0, retry_counts={})

    with patch("agents.supervisor.invoke_structured_robust", return_value=llm_decision), \
         patch("agents.supervisor.log_event"):

        result = graph_node_supervisor(state)

    assert result["next_agent"] == "judge"
