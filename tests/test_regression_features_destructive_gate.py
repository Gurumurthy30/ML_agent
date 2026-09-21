import os
import pytest
from unittest.mock import MagicMock, patch
from state import build_initial_state
from agents.features_agent import features_agent, FeatureStepDecision
from graph import route_after_features


def test_features_destructive_action_triggers_approval_in_non_guided_mode(tmp_path):
    # Setup test datasets
    raw_path = str(tmp_path / "raw.csv")
    with open(raw_path, "w") as f:
        f.write("a,b,target\n1,2,0\n3,4,1\n")

    transformed_path = str(tmp_path / "transformed.parquet")
    # Dropped column 'b' (destructive change)
    import pandas as pd
    pd.DataFrame({"a": [1, 3], "target": [0, 1]}).to_parquet(transformed_path)

    state = build_initial_state(dataset_path=raw_path, mode="full_pipeline", guided_mode=False)
    state["task_type"] = "classification"
    state["target_column"] = "target"
    state["profile"] = {"features": [{"name": "a"}, {"name": "b"}, {"name": "target"}]}

    # Mock decide_next_step to return a destructive step, then stop
    step_decisions = [
        FeatureStepDecision(
            decision="continue",
            task_spec="Drop column b",
            reasoning="Column b is unneeded",
            destructive_self_assessment=True,
        ),
        FeatureStepDecision(
            decision="stop",
            reasoning="Done",
            destructive_self_assessment=False,
        )
    ]

    mock_coder_result = {
        "success": True,
        "code": "df = df.drop(columns=['b'])",
        "stdout": "Dropped b",
        "output_path": transformed_path,
        "attempts": 1,
    }

    with patch("agents.features_agent.invoke_structured_robust", side_effect=step_decisions), \
         patch("agents.features_agent.coder_agent", return_value=mock_coder_result):
        result = features_agent(state)

    # In non-guided mode, destructive action MUST set requires_human_approval and feature_plan
    assert result.get("requires_human_approval") is True, "Destructive action did not set requires_human_approval=True"
    assert result.get("approval_reason") == "destructive_action", f"Expected destructive_action, got {result.get('approval_reason')}"
    assert result.get("feature_plan") is not None, "feature_plan was not set"

    # Verify graph routing in non-guided mode
    merged_state = {**state, **result}
    assert route_after_features(merged_state) == "human_approval", "route_after_features did not route to human_approval"
