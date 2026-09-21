import pytest
from unittest.mock import MagicMock, patch
from state import build_initial_state
from agents.supervisor import graph_node_supervisor, SupervisorDecision


def test_supervisor_handles_adaptive_escalate():
    state = build_initial_state(dataset_path="test.csv", mode="full_pipeline")
    state["profile"] = {"features": []}
    state["eda_findings"] = {"summary": "done"}
    state["feature_set"] = {"steps": []}
    state["candidate_models"] = [{"model_family": "rf", "cv_score": 0.8}]
    state["retry_tier"] = 1
    state["last_verdict"] = "reject"

    mock_rec = {
        "action": "escalate",
        "next_agent": "features",
        "tier": 2,
        "reason": "Plateau detected: advancing from Tier 1 to Tier 2",
    }

    dummy_decision = SupervisorDecision(
        next_agent="profiler",
        reasoning="fallback",
        task_instructions="fallback",
    )

    with patch("agents.adaptive_controller.adaptive_controller.evaluate_next_action", return_value=mock_rec), \
         patch("agents.supervisor.invoke_structured_robust", return_value=dummy_decision) as mock_llm:
        res = graph_node_supervisor(state)

    assert res["next_agent"] == "features"
    assert res["retry_tier"] == 2
    assert res["requires_human_approval"] is False
    assert "Plateau detected" in res["supervisor_reasoning"]
    # LLM should not have been called because adaptive controller handled the routing
    mock_llm.assert_not_called()


def test_supervisor_handles_adaptive_human_approval():
    state = build_initial_state(dataset_path="test.csv", mode="full_pipeline")
    state["profile"] = {"features": []}
    state["retry_tier"] = 2

    mock_rec = {
        "action": "human_approval",
        "reason": "Repeated stall detected: manual intervention required",
    }

    dummy_decision = SupervisorDecision(
        next_agent="profiler",
        reasoning="fallback",
        task_instructions="fallback",
    )

    with patch("agents.adaptive_controller.adaptive_controller.evaluate_next_action", return_value=mock_rec), \
         patch("agents.supervisor.invoke_structured_robust", return_value=dummy_decision) as mock_llm:
        res = graph_node_supervisor(state)

    assert res["next_agent"] == "human_approval"
    assert res["requires_human_approval"] is True
    assert res["approval_reason"] == "stalled"
    mock_llm.assert_not_called()
