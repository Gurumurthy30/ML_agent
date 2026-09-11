import json
import time
from pathlib import Path
from typing import Dict, Any

from graph.state import AgentState
from graph.budget_guard import enforce_budget
from config.settings import get_settings
from tools.local_env_mcp import LocalEnvMCP
from agents.utils import push_event


def execute_node(state: AgentState) -> AgentState:
    """
    Execute Agent Node (v2) — thin mechanical wrapper.

    Changes from v1:
    - Uses local_env_mcp for real subprocess execution (not simulated step-counter).
    - Writes experiment log to session-scoped path:
        state/sessions/{session_id}/experiment_log.jsonl
    - Emits execution_result event to state event_queue.
    - Emits node_start / node_end events.
    """
    push_event(state, {"type": "node_start", "node": "execute"})

    start_time = time.time()
    state, is_exhausted = enforce_budget(state, action_cost=1)
    if is_exhausted:
        push_event(state, {"type": "node_end", "node": "execute"})
        return state

    settings = get_settings()
    dry_run = state.get("dry_run", False)
    session_id = state.get("session_id", "default")
    sessions_root = settings.sessions.storage_path

    mcp = LocalEnvMCP(
        session_id=session_id,
        sessions_root=sessions_root,
        exec_timeout=settings.sessions.exec_timeout_seconds,
        dry_run=dry_run,
    )

    spec = state.get("current_spec") or {}
    code = spec.get("validated_code", "# Empty code\nprint('CV_MEAN=0.0')\nprint('CV_STD=0.0')")

    # Run via MCP tool (real subprocess or dry-run canned response)
    result = mcp.execute_code(code)

    exp_id = spec.get("experiment_id", "exp_000")
    approach_summary = spec.get("approach_rationale", "Standard execution run")
    model_type = spec.get("model_family", "Unknown")

    log_entry = {
        "experiment_id": exp_id,
        "approach_summary": approach_summary,
        "model_type": model_type,
        "cv_mean": result.get("cv_mean", 0.0),
        "cv_std": result.get("cv_std", 0.0),
        "submission_score": result.get("cv_mean", 0.0),  # use CV mean as proxy when no leaderboard
        "status": result.get("status", "success"),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    # Append to session-scoped experiment_log.jsonl
    session_dir = Path(sessions_root) / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    log_path = session_dir / "experiment_log.jsonl"
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(log_entry) + "\n")

    # Emit execution_result event
    push_event(state, {
        "type": "execution_result",
        "node": "execute",
        "experiment_id": exp_id,
        "cv_mean": result.get("cv_mean", 0.0),
        "cv_std": result.get("cv_std", 0.0),
        "status": result.get("status", "success"),
        "stdout_tail": result.get("stdout_tail", ""),
        "stderr_tail": result.get("stderr_tail", ""),
        "error": result.get("error"),
    })

    elapsed_minutes = (time.time() - start_time) / 60.0
    state, _ = enforce_budget(state, action_cost=0, elapsed_minutes=elapsed_minutes)

    push_event(state, {"type": "node_end", "node": "execute"})

    state["status"] = "judging"
    return state
