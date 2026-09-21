"""
Regression tests for Scoped Memory Architecture:
1. Profiler has NO memory (simple one-time dataset profiling, reads/writes zero memory).
2. Specialist Working Agents have strictly PRIVATE / SCORE memory:
   - Modeler tracks models, hyperparams, CV scores, and mistakes/blunders to avoid repeating them.
   - Coder tracks past execution failures/fixes to avoid repeating broken patterns.
   - EDA tracks its own analyses and statistical scores in isolation.
   - Features tracks its own transformations and scores in isolation.
3. Strict isolation between specialist agents: no cross-agent scratchpad contamination.
4. LangGraph reducer merge behavior for private_memories.
"""
import pytest
from unittest.mock import patch, MagicMock
from state import build_initial_state
from utils.scoped_memory import (
    merge_private_memories,
    format_modeler_scorecard,
    format_coder_private_history,
)
from agents.profiler_agent import profiler_agent
from agents.coder_agent import coder_agent
from agents.eda_agent import eda_agent
from agents.features_agent import features_agent
from agents.modeler_agent import modeler_agent


def test_profiler_has_no_memory(tmp_path):
    """Profiler must run once as a simple profiler with strictly NO memory access or output."""
    csv_file = tmp_path / "test.csv"
    csv_file.write_text("a,b,target\n1,2,0\n3,4,1\n")

    state = build_initial_state(str(csv_file))
    # Ensure initial state has no profiler private memory bucket
    assert "profiler" not in state["private_memories"]

    mock_json = '{"target_column": "target", "task_type": "classification", "recommended_metric": "accuracy", "data_quality_flags": []}'
    with patch("agents.profiler_agent.stream_text", return_value=mock_json):
        res = profiler_agent(state)

    # Output must NOT write to private_memories or read memory
    assert "private_memories" not in res
    assert "run_memory" not in res
    assert "profile" in res
    assert res["target_column"] == "target"


def test_modeler_private_score_memory_and_blunder_tracking():
    """
    Modeler must record candidate models, validation scores, and explicit blunder logs
    so it knows past attempts and does not repeat blunders ('blender mistakes').
    """
    history = [
        {"model_family": "RandomForest", "metric_name": "accuracy", "score": 0.82, "status": "success", "metric_delta": 0.0},
        {"model_family": "LinearRegression", "metric_name": "accuracy", "score": None, "status": "failed", "blunder_note": "Failed to converge: solver crashed on unscaled data"},
        {"model_family": "DecisionTree", "metric_name": "accuracy", "score": 0.75, "status": "stalled", "metric_delta": -0.07, "blunder_note": "Score degraded by 0.0700"},
    ]
    p_mem = {"modeler": history}

    scorecard = format_modeler_scorecard(p_mem, current_best=0.82)

    # Verify attempts, scores, and blunders are explicitly documented
    assert "RandomForest" in scorecard
    assert "accuracy=0.8200" in scorecard
    assert "RECORDED BLUNDERS / MISTAKES TO AVOID" in scorecard
    assert "Failed to converge" in scorecard
    assert "Score degraded" in scorecard
    assert "DO NOT repeat the above blunders" in scorecard


def test_modeler_agent_writes_private_score_memory_and_open_summary(tmp_path):
    """Verify modeler_agent execution produces private_memories['modeler'] and open_summary_memory['modeler']."""
    csv_file = tmp_path / "data.csv"
    csv_file.write_text("x,y\n1,0\n2,1\n")

    state = build_initial_state(str(csv_file))
    state["profile"] = {"recommended_metric": "accuracy", "data_quality_flags": []}
    state["task_type"] = "classification"

    mock_step_decision = MagicMock(decision="continue", task_spec="Train a baseline RandomForest", reasoning="test")
    mock_stop_decision = MagicMock(decision="stop", reasoning="finished")
    decisions = [mock_step_decision, mock_stop_decision]

    mock_coder_result = {
        "success": True,
        "code": "print('RESULT_JSON: {\"model_family\": \"RandomForest\", \"cv_score\": 0.85, \"metric\": \"accuracy\"}')",
        "stdout": "RESULT_JSON: {\"model_family\": \"RandomForest\", \"cv_score\": 0.85, \"metric\": \"accuracy\"}",
        "output_path": "model.joblib",
        "attempts": 1,
        "private_memory_entry": {
            "task_spec": "Train RandomForest", "success": True, "code": "...", "attempts": 1,
        },
    }

    with patch("agents.modeler_agent.invoke_structured_robust", side_effect=decisions), \
         patch("agents.modeler_agent.coder_agent", return_value=mock_coder_result):
        res = modeler_agent(state)

    assert "private_memories" in res
    assert "modeler" in res["private_memories"]
    assert len(res["private_memories"]["modeler"]) >= 1
    trial = res["private_memories"]["modeler"][0]
    assert trial["model_family"] == "RandomForest"
    assert trial["score"] == 0.85

    assert "coder" in res["private_memories"]
    assert len(res["private_memories"]["coder"]) >= 1

    assert "open_summary_memory" in res
    assert "modeler" in res["open_summary_memory"]
    assert "RandomForest" in res["open_summary_memory"]["modeler"]


def test_coder_private_error_history():
    """Coder must format and inject recent execution failures into system prompt context."""
    p_mem = {
        "coder": [
            {"task_spec": "plot data", "success": False, "stderr": "ImportError: No module named 'seaborn'"},
            {"task_spec": "calc stats", "success": True, "code": "print(1)"},
            {"task_spec": "write file", "success": False, "stderr": "FileNotFoundError: [Errno 2] No such file or directory: 'artifacts/out.json'"},
        ]
    }
    notes = format_coder_private_history(p_mem)
    assert "Avoid repeating recent execution mistakes" in notes
    assert "seaborn" in notes
    assert "FileNotFoundError" in notes


def test_specialist_private_memory_isolation():
    """Verify that specialist agents have strictly isolated private memories via the reducer."""
    initial = {"coder": [], "eda": [], "features": [], "modeler": []}

    # EDA update
    eda_update = {"eda": [{"analyses": ["correlation_matrix"], "iterations": 1}]}
    state_after_eda = merge_private_memories(initial, eda_update)
    assert len(state_after_eda["eda"]) == 1
    assert len(state_after_eda["features"]) == 0
    assert len(state_after_eda["modeler"]) == 0
    assert len(state_after_eda["coder"]) == 0

    # Features update
    features_update = {"features": [{"steps": ["impute_median"], "iterations": 1}]}
    state_after_features = merge_private_memories(state_after_eda, features_update)
    assert len(state_after_features["eda"]) == 1
    assert len(state_after_features["features"]) == 1
    assert len(state_after_features["modeler"]) == 0

    # Modeler update
    modeler_update = {"modeler": [{"model_family": "LightGBM", "score": 0.89}]}
    state_after_modeler = merge_private_memories(state_after_features, modeler_update)
    assert len(state_after_modeler["eda"]) == 1
    assert len(state_after_modeler["features"]) == 1
    assert len(state_after_modeler["modeler"]) == 1
    assert len(state_after_modeler["coder"]) == 0


def test_private_memory_bounding():
    """Verify private memories do not leak unbounded entries (capped at 50 per agent)."""
    initial = {"coder": [], "eda": [], "features": [], "modeler": []}
    large_update = {"modeler": [{"trial": i} for i in range(70)]}
    merged = merge_private_memories(initial, large_update)
    assert len(merged["modeler"]) == 50
    assert merged["modeler"][-1]["trial"] == 69
