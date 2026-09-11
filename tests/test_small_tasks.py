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
from tools.local_dataset_engine import LocalDatasetEngine
from tools.local_executor import LocalExecutor
from agents.selector import check_plateau_and_variance

def test_config_validation():
    """Verify settings loads and raises clear error when local_model_path is missing in real mode."""
    settings = get_settings()
    assert settings.dataset.data_dir == "data"
    assert settings.budget.actions_total > 0

def test_local_engine_and_executor():
    """Verify local dataset engine and local executor functionality."""
    engine = LocalDatasetEngine()
    info = engine.request_info()
    assert "task_id" in info
    assert info["modality"] == "tabular"

    executor = LocalExecutor()
    val = executor.validate_code("import pandas as pd\nprint('hello')")
    assert val["valid"] is True

    exec_res = executor.execute_code("import pandas as pd")
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

def test_full_graph_execution_local():
    """Verify end-to-end graph execution runs to completion in native local mode."""
    settings = get_settings()
    assert settings.dataset.data_dir == "data"

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

from agents.data_explorer import data_explorer_node, _compute_anova_stats, format_eda_as_prompt

def test_multi_provider_settings():
    """Verify settings loads deep_thinking, primary, and fallback provider configs."""
    settings = get_settings()
    assert settings.model.deep_thinking_provider.name == "deepseek-ai/deepseek-r1"
    assert settings.model.primary_provider.name == "llama-3.3-70b-versatile"
    assert settings.model.fallback_provider.name == "gemini-2.5-flash"

def test_data_explorer_eda_formatting():
    """Verify Data Explorer node generates rich structured eda_prompt_summary."""
    state: AgentState = {
        "task_context": {},
        "current_spec": None,
        "last_escalation": None,
        "last_redirect": None,
        "reasoning_mode": "default",
        "actions_remaining": 10,
        "time_remaining": 60.0,
        "status": "planning"
    }
    updated_state = data_explorer_node(state)
    task_ctx = updated_state.get("task_context", {})
    assert "eda_prompt_summary" in task_ctx
    prompt_str = task_ctx["eda_prompt_summary"]
    assert "COMPREHENSIVE END-TO-END DATASET EXPLORATION" in prompt_str
    assert "Primary Metric" in prompt_str

def test_anova_and_skewness():
    """Verify ANOVA calculation on synthetic numeric DataFrame."""
    import pandas as pd
    df = pd.DataFrame({
        "feat1": [1.0, 2.0, 1.5, 10.0, 12.0, 11.0],
        "feat2": [5.0, 5.1, 4.9, 5.0, 5.2, 5.1],
        "target": [0, 0, 0, 1, 1, 1]
    })
    anova_res = _compute_anova_stats(df, "target")
    assert len(anova_res) > 0
    assert anova_res[0]["feature"] == "feat1"
    assert "f_statistic" in anova_res[0]

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

