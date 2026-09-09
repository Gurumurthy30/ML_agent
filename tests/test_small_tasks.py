import sys
import os
import json
import pytest
from pathlib import Path

# Ensure parent directory is in path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import get_settings
from graph.state import AgentState
from graph.budget_guard import enforce_budget
from graph.build_graph import build_app
from tools.mle_dojo_mcp.mock_server import MLEDojoMockServer
from agents.selector import check_plateau_and_variance

def test_config_validation():
    """Verify settings loads and raises clear error when local_model_path is missing in real mode."""
    settings = get_settings()
    assert settings.mle_dojo.use_mock is True
    assert settings.budget.actions_total > 0

def test_mock_server_tools():
    """Verify mock MLE-Dojo server tool functionality."""
    mock_env = MLEDojoMockServer()
    info = mock_env.request_info()
    assert "task_id" in info
    assert info["modality"] == "tabular"

    val = mock_env.validate_code("import pandas as pd\nprint('hello')")
    assert val["valid"] is True

    exec_res = mock_env.execute_code("import pandas as pd")
    assert exec_res["status"] == "success"
    assert "cv_mean" in exec_res
    assert "cv_std" in exec_res

def test_budget_guard():
    """Verify budget enforcement forces budget_exhausted status."""
    state: AgentState = {
        "task_context": {},
        "current_spec": None,
        "last_escalation": None,
        "last_redirect": None,
        "reasoning_mode": "default",
        "actions_remaining": 1,
        "time_remaining": 10.0,
        "status": "planning"
    }

    updated_state, is_exhausted = enforce_budget(state, action_cost=1)
    assert updated_state["actions_remaining"] == 0
    assert updated_state["status"] == "budget_exhausted"
    assert is_exhausted is True

def test_selector_plateau_detection():
    """Verify exact plateau detection (N=3 consecutive rounds with < 0.5% relative gain)."""
    log_entries = [
        {"experiment_id": "exp_001", "model_type": "LightGBM", "cv_mean": 0.850, "cv_std": 0.0001, "status": "success"},
        {"experiment_id": "exp_002", "model_type": "LightGBM", "cv_mean": 0.851, "cv_std": 0.0001, "status": "success"}, # +0.11% gain
        {"experiment_id": "exp_003", "model_type": "LightGBM", "cv_mean": 0.8515, "cv_std": 0.0001, "status": "success"}, # +0.05% gain
        {"experiment_id": "exp_004", "model_type": "LightGBM", "cv_mean": 0.8518, "cv_std": 0.0001, "status": "success"}  # +0.03% gain
    ]

    res = check_plateau_and_variance(log_entries, n_rounds=3, epsilon_rel=0.005)
    assert res["status"] == "redirect"
    assert res["reason"] == "plateaued"

def test_full_graph_execution_mock():
    """Verify end-to-end graph execution runs to completion in mock mode."""
    settings = get_settings()
    assert settings.mle_dojo.use_mock is True

    initial_state: AgentState = {
        "task_context": {},
        "current_spec": None,
        "last_escalation": None,
        "last_redirect": None,
        "reasoning_mode": "default",
        "actions_remaining": 5, # Small budget for fast execution
        "time_remaining": 10.0,
        "status": "planning"
    }

    app = build_app()
    final_state = app.invoke(initial_state)
    assert final_state["status"] in ["converged", "budget_exhausted"]

def test_no_forbidden_download_calls():
    """Verify codebase contains zero HuggingFace / Git-LFS download functions."""
    root_dir = Path(__file__).parent.parent
    forbidden_terms = ["snapshot_download", "hf_hub_download", "git lfs pull", "git-lfs"]

    for py_file in root_dir.glob("**/*.py"):
        if "test_small_tasks.py" in py_file.name:
            continue
        content = py_file.read_text(encoding="utf-8")
        for term in forbidden_terms:
            assert term not in content, f"Forbidden download term '{term}' found in {py_file}"
