import json
import time
from pathlib import Path
from typing import Dict, Any

from graph.state import AgentState
from graph.budget_guard import enforce_budget
from config.settings import get_settings
from tools.mle_dojo_mcp import get_mle_dojo_client

def execute_node(state: AgentState) -> AgentState:
    """
    Execute Agent Node (thin mechanical wrapper).
    Runs validated code via MLE-Dojo execute_code tool and appends a row to experiment_log.jsonl.
    Enforces budget before tool execution.
    """
    start_time = time.time()
    state, is_exhausted = enforce_budget(state, action_cost=1)
    if is_exhausted:
        return state

    settings = get_settings()
    client = get_mle_dojo_client(use_mock=settings.mle_dojo.use_mock)

    spec = state.get("current_spec") or {}
    code = spec.get("validated_code", "# Empty code")

    # Run execute_code tool
    result = client.execute_code(code)

    exp_id = spec.get("experiment_id", "exp_000")
    approach_summary = spec.get("approach_rationale", "Standard execution run")
    model_type = spec.get("model_family", "Unknown")

    log_entry = {
        "experiment_id": exp_id,
        "approach_summary": approach_summary,
        "model_type": model_type,
        "cv_mean": result.get("cv_mean", 0.0),
        "cv_std": result.get("cv_std", 0.0),
        "submission_score": result.get("submission_score", 0.0),
        "status": result.get("status", "success"),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ")
    }

    # Append to state/experiment_log.jsonl
    base_dir = Path(__file__).parent.parent
    state_dir = base_dir / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    log_path = state_dir / "experiment_log.jsonl"

    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(log_entry) + "\n")

    elapsed_minutes = (time.time() - start_time) / 60.0
    state, _ = enforce_budget(state, action_cost=0, elapsed_minutes=elapsed_minutes)

    state["status"] = "judging"
    return state
