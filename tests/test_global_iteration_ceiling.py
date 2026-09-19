"""
Tests for the global iteration ceiling circuit breaker (Section 2.3).

Verifies that graph_node_supervisor short-circuits to human_approval (without
calling the LLM) when state["iteration"] >= PIPELINE_GLOBAL_ITER_CEILING.
"""
import os
import pytest
from unittest.mock import patch, MagicMock


def _state(*, run_id="test_run", iteration=0, **kwargs):
    base = {
        "run_id": run_id,
        "dataset_fingerprint": "abc123",
        "mode": "full_pipeline",
        "guided_mode": False,
        "dataset_path": "fake.csv",
        "profile": {"rows": 100, "columns": 5},
        "eda_findings": {"narrative": "test"},
        "feature_set": {"steps": ["impute"]},
        "candidate_models": [],
        "metric_history": [],
        "best_metric": None,
        "last_verdict": None,
        "retry_tier": 0,
        "retry_counts": {},
        "judge_feedback": None,
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
    base.update(kwargs)
    return base


# ---------------------------------------------------------------------------
# Test 1: Ceiling exactly met — should escalate
# ---------------------------------------------------------------------------

def test_ceiling_exactly_met_escalates(monkeypatch):
    """When state['iteration'] == ceiling, must escalate without calling LLM."""
    monkeypatch.setenv("PIPELINE_GLOBAL_ITER_CEILING", "10")

    # Need to reimport to pick up the new env var value
    import importlib
    import agents.supervisor as sup_module
    importlib.reload(sup_module)

    state = _state(iteration=10)
    mock_llm_call = MagicMock()

    with patch.object(sup_module, "invoke_structured_robust", mock_llm_call), \
         patch.object(sup_module, "log_event") as mock_log:

        result = sup_module.graph_node_supervisor(state)

    assert result["next_agent"] == "human_approval"
    assert result.get("approval_reason") == "global_iteration_ceiling"
    # LLM must NOT have been called
    mock_llm_call.assert_not_called()

    log_calls = [call.args for call in mock_log.call_args_list]
    ceiling_logged = any(
        len(c) >= 3 and c[2] == "global_iteration_ceiling"
        for c in log_calls
    )
    assert ceiling_logged, "global_iteration_ceiling event was not logged"


# ---------------------------------------------------------------------------
# Test 2: Ceiling exceeded — should also escalate
# ---------------------------------------------------------------------------

def test_ceiling_exceeded_escalates(monkeypatch):
    """When state['iteration'] > ceiling, must still escalate."""
    monkeypatch.setenv("PIPELINE_GLOBAL_ITER_CEILING", "10")

    import importlib
    import agents.supervisor as sup_module
    importlib.reload(sup_module)

    state = _state(iteration=50)

    with patch.object(sup_module, "invoke_structured_robust", MagicMock()) as mock_llm, \
         patch.object(sup_module, "log_event"):

        result = sup_module.graph_node_supervisor(state)

    assert result["next_agent"] == "human_approval"
    mock_llm.assert_not_called()


# ---------------------------------------------------------------------------
# Test 3: Under ceiling — should NOT trigger, normal routing proceeds
# ---------------------------------------------------------------------------

def test_under_ceiling_does_not_trigger(monkeypatch):
    """
    When state['iteration'] < ceiling, the ceiling check must not fire and
    normal LLM routing must proceed.
    """
    monkeypatch.setenv("PIPELINE_GLOBAL_ITER_CEILING", "200")

    import importlib
    import agents.supervisor as sup_module
    importlib.reload(sup_module)

    from agents.supervisor import SupervisorDecision
    llm_decision = SupervisorDecision(
        next_agent="modeler",
        reasoning="Features ready, proceed to modeling",
        task_instructions="Train baseline model",
        requires_human_approval=False,
    )

    state = _state(
        iteration=5,
        feature_set={"steps": ["impute"]},
        candidate_models=[],
    )

    with patch.object(sup_module, "invoke_structured_robust", return_value=llm_decision), \
         patch.object(sup_module, "log_event"):

        result = sup_module.graph_node_supervisor(state)

    assert result["next_agent"] == "modeler", (
        f"Ceiling should not fire at iteration=5 with ceiling=200, got {result['next_agent']}"
    )


# ---------------------------------------------------------------------------
# Test 4: Ceiling is generous — confirm default (200) doesn't cut normal runs
# ---------------------------------------------------------------------------

def test_default_ceiling_is_generous(monkeypatch):
    """
    Default ceiling of 200 should not fire for a normal 3-iteration Modeler run.
    The intent is that the circuit breaker is a last resort, not a productivity limiter.
    """
    monkeypatch.delenv("PIPELINE_GLOBAL_ITER_CEILING", raising=False)

    import importlib
    import agents.supervisor as sup_module
    importlib.reload(sup_module)

    from agents.supervisor import SupervisorDecision
    llm_decision = SupervisorDecision(
        next_agent="judge",
        reasoning="Models trained",
        task_instructions="Evaluate",
        requires_human_approval=False,
    )

    # 3 iterations — far below 200
    state = _state(
        iteration=3,
        candidate_models=[{"model_family": "RF", "cv_score": 0.8}],
    )

    with patch.object(sup_module, "invoke_structured_robust", return_value=llm_decision), \
         patch.object(sup_module, "log_event"):

        result = sup_module.graph_node_supervisor(state)

    assert result["next_agent"] != "human_approval", (
        f"Default ceiling (200) should not fire at iteration=3, but got human_approval"
    )
