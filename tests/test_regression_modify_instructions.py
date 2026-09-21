"""
Regression tests for P0: Verify operator 'modify' instructions reach the Features agent.

Verifies end-to-end:
1. `human_approval_node` extracts and persists `modifications` in `state["modifications"]`
   and `state["feature_plan"]["modifications"]`.
2. `features_agent`'s `decide_next_step` extracts `modifications` and injects it into both
   the structured `context["human_modifications"]` and the `system_prompt` directive.
3. When `features_agent` finishes, `modifications` is cleanly reset to None.
4. The API endpoint `POST /runs/{id}/resume` accepts `modifications` and correctly builds the
   LangGraph `Command(resume=...)` payload.
"""
import json
import time
import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from api.main import app
from graph import human_approval_node, route_after_human_approval
from agents.features_agent import features_agent, FeatureStepDecision
from tools.tracer import register_run, update_run_status
from state import build_initial_state


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_human_approval_node_persists_modifications(monkeypatch, tmp_path):
    """
    Test that human_approval_node extracts `modifications` from the resume payload,
    persists it into state and feature_plan, and routes to 'features'.
    """
    run_id = f"test_mod_persist_{int(time.time()*1000)}"
    register_run(run_id, dataset_path="dummy.csv")

    state = {
        "run_id": run_id,
        "requires_human_approval": True,
        "approval_reason": "destructive_action",
        "feature_plan": {
            "description": "Drop columns with missing values",
            "proposed_output_path": str(tmp_path / "feat.parquet"),
        },
    }

    # Simulate operator submitting modify decision with explicit instructions
    operator_instructions = "Do not drop column 'age' or 'fare'; impute with median instead."
    monkeypatch.setattr(
        "graph.interrupt",
        lambda x: {"approval_status": "modify", "modifications": operator_instructions},
    )

    update = human_approval_node(state)

    assert update["approval_status"] == "modify"
    assert update["requires_human_approval"] is False
    assert update["modifications"] == operator_instructions
    assert update["feature_plan"]["modifications"] == operator_instructions
    assert "transformed_dataset_path" not in update

    # Verify downstream routing sends to features
    state.update(update)
    assert route_after_human_approval(state) == "features"


def test_features_agent_decide_next_step_receives_modifications(monkeypatch, tmp_path):
    """
    Test that features_agent's decide_next_step actually reads the `modifications`
    text from state and factors it into both the structured context and system prompt.
    """
    # Create sample dataset
    data_file = tmp_path / "sample.csv"
    data_file.write_text("age,fare,survived\n22,7.25,0\n38,71.28,1\n")

    run_id = f"test_feat_mod_{int(time.time()*1000)}"
    register_run(run_id, dataset_path=str(data_file))

    state = build_initial_state(dataset_path=str(data_file), run_id=run_id)
    operator_text = "Keep column 'age' and impute using median. Do NOT drop it."
    state["modifications"] = operator_text
    state["feature_plan"] = {"description": "Previous dropped age", "modifications": operator_text}

    captured_calls = []

    def mock_invoke_structured_robust(llm, schema, messages, **kwargs):
        captured_calls.append(messages)
        # Return stop decision so the loop finishes immediately after 1 decision
        return FeatureStepDecision(
            decision="stop",
            reasoning="Adhered to human instructions and halted.",
            destructive_self_assessment=False,
        )

    monkeypatch.setattr("agents.features_agent.invoke_structured_robust", mock_invoke_structured_robust)

    update = features_agent(state)

    # 1. Assert decide_next_step was called
    assert len(captured_calls) >= 1
    messages = captured_calls[0]
    sys_msg = messages[0].content
    user_msg = messages[1].content

    # 2. Assert the modification text is in the system prompt directive
    assert operator_text in sys_msg
    assert "Human operator reviewed the previous feature proposal and requested modifications" in sys_msg

    # 3. Assert the modification text is in the user context JSON
    assert "human_modifications" in user_msg
    assert operator_text in user_msg

    # 4. Assert modifications is reset to None in the returned state update
    assert update.get("modifications") is None


def test_api_resume_endpoint_passes_modifications(client, monkeypatch):
    """
    Test that POST /runs/{id}/resume properly forwards modifications to Command(resume=...).
    """
    run_id = f"test_api_resume_mod_{int(time.time()*1000)}"
    register_run(run_id, dataset_path="dummy.csv")
    update_run_status(run_id, status="paused", stop_reason="human_approval_required")

    captured_stream_input = []

    def mock_run_graph(stream_input, run_id):
        captured_stream_input.append(stream_input)

    monkeypatch.setattr("api.main._run_graph_in_background", mock_run_graph)

    operator_note = "Scale numeric variables with RobustScaler instead of StandardScaler"
    res = client.post(
        f"/runs/{run_id}/resume",
        json={"approval_status": "modify", "modifications": operator_note},
    )

    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "resumed"
    assert data["decision"] == "modify"

    assert len(captured_stream_input) == 1
    cmd = captured_stream_input[0]
    assert cmd.resume == {"approval_status": "modify", "modifications": operator_note}
