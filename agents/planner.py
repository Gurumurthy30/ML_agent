"""
agents/planner.py — Planner Agent (minimal skeleton)

Reads experiment history, uses LLM to design the next experiment spec,
and passes it to the Coder.
"""

import json
from pathlib import Path
from typing import Dict, Any, List

from graph.state import AgentState
from agents.utils import call_llm, extract_json, push_event

# TODO: re-add when these are back in place
# from graph.budget_guard import enforce_budget
# from config.settings import get_settings
# from tools.rag_mcp import RagMCP


def planner_node(state: AgentState) -> AgentState:
    """
    Planner Agent: designs experiment specs based on task context and history.

    Flow: load experiment log → load prompt → LLM call → parse spec → set state
    """
    task_ctx = state.get("task_context", {})
    user_message = state.get("user_message", "")

    # TODO: load experiment log from session path
    log_entries: List[Dict[str, Any]] = []
    exp_id = f"exp_{len(log_entries) + 1:03d}"

    # Load system prompt
    base_dir = Path(__file__).parent.parent
    prompt_path = base_dir / "prompts" / "planner_prompt.md"
    system_prompt = prompt_path.read_text(encoding="utf-8") if prompt_path.exists() else "You are an ML experiment planner."

    # Build user prompt
    eda_report = state.get("eda_report_markdown", "")
    user_prompt = (
        f"## Task Context\n\n{eda_report}\n\n"
        f"**User Request:** {user_message}\n\n"
        f"Design experiment {exp_id}.\n"
        f"History: {json.dumps(log_entries, default=str)}\n"
    )

    # LLM call
    spec = None
    try:
        # TODO: wire up provider_config from settings
        raw_resp, _ = call_llm(system_prompt, user_prompt, role="planner", provider_config=None)
        spec = extract_json(raw_resp)
    except Exception as e:
        print(f"[Planner] LLM call failed: {e}")

    # Fallback: minimal spec
    if not spec:
        spec = {
            "experiment_id": exp_id,
            "approach_type": "baseline",
            "model_family": "LightGBM",
            "modality": task_ctx.get("modality", "tabular"),
        }

    # Update state
    state["current_spec"] = spec
    state["status"] = "coding"
    return state
