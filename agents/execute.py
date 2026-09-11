"""
agents/execute.py — Execute Agent (minimal skeleton)

Runs the generated Python code in a sandbox and logs the result.
"""

import json
import time
from pathlib import Path
from typing import Dict, Any

from graph.state import AgentState
from agents.utils import push_event

# TODO: re-add when these are back in place
# from graph.budget_guard import enforce_budget
# from config.settings import get_settings
# from tools.local_env_mcp import LocalEnvMCP


def execute_node(state: AgentState) -> AgentState:
    """
    Execute Agent: runs experiment code and records results.

    Flow: get code from spec → run via MCP → write to experiment log → set state
    """
    spec = state.get("current_spec") or {}
    code = spec.get("validated_code", "print('No code provided')")
    exp_id = spec.get("experiment_id", "exp_000")
    model_type = spec.get("model_family", "Unknown")

    # TODO: run code via LocalEnvMCP
    # result = mcp.execute_code(code)
    result = {
        "status": "success",
        "cv_mean": 0.0,
        "cv_std": 0.0,
    }

    # Build log entry
    log_entry = {
        "experiment_id": exp_id,
        "model_type": model_type,
        "cv_mean": result.get("cv_mean", 0.0),
        "cv_std": result.get("cv_std", 0.0),
        "status": result.get("status", "success"),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    # TODO: write log_entry to session experiment_log.jsonl
    print(f"[Execute] {exp_id}: cv_mean={log_entry['cv_mean']:.4f}")

    state["status"] = "judging"
    return state
