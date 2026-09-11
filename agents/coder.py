"""
agents/coder.py — Coder Agent (minimal skeleton)

Takes an experiment spec from Planner, generates Python code via LLM,
validates it, and passes to Execute.
"""

import re
from pathlib import Path
from typing import Dict, Any

from graph.state import AgentState
from agents.utils import call_llm, extract_json, push_event

# TODO: re-add when these are back in place
# from graph.budget_guard import enforce_budget
# from tools.local_env_mcp import LocalEnvMCP
# from tools.rag_mcp import RagMCP


def coder_node(state: AgentState) -> AgentState:
    """
    Coder Agent: generates Python ML code from an experiment spec.

    Flow: load prompt → LLM call → extract code block → set state
    """
    spec = state.get("current_spec") or {}
    task_ctx = state.get("task_context", {})
    session_data_dir = state.get("session_data_dir", "")

    # Load system prompt from prompts/coder/
    base_dir = Path(__file__).parent.parent
    prompt_path = base_dir / "prompts" / "coder" / "index_prompt.md"
    system_prompt = prompt_path.read_text(encoding="utf-8") if prompt_path.exists() else "You are a code generator."

    # Build user prompt
    user_prompt = (
        f"Implement Python code for this experiment:\n"
        f"Data path: {session_data_dir}\n"
        f"Spec: {spec}\n"
        f"Task context: {task_ctx}\n"
    )

    # LLM call
    generated_code = None
    escalation = None

    try:
        # TODO: wire up provider_config from settings
        raw_resp, _ = call_llm(system_prompt, user_prompt, role="coder", provider_config=None)

        parsed = extract_json(raw_resp)
        if parsed and "escalation_type" in parsed:
            escalation = parsed
        else:
            code_match = re.search(r"```python\s*(.*?)\s*```", raw_resp, re.DOTALL)
            generated_code = code_match.group(1) if code_match else raw_resp
    except Exception as e:
        print(f"[Coder] LLM call failed: {e}")

    # TODO: validate code via MCP tool
    # TODO: add fallback code generation if needed

    # Update state
    if escalation:
        state["last_escalation"] = escalation
        state["status"] = "planning"
    else:
        state["last_escalation"] = None
        if spec:
            spec["validated_code"] = generated_code
        state["current_spec"] = spec
        state["status"] = "executing"

    return state
