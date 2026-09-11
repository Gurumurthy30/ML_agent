"""
agents/selector.py — Selector/Judge Agent (minimal skeleton)

Evaluates experiment results and decides: continue iterating or converge.
"""

import json
from pathlib import Path
from typing import Dict, Any, List

from graph.state import AgentState
from agents.utils import push_event

# TODO: re-add when these are back in place
# from config.settings import get_settings


MAX_ROUNDS = 10


def selector_node(state: AgentState) -> AgentState:
    """
    Selector Agent: judges experiment results and decides next action.

    Flow: read experiment log → decide converge or continue → set state
    """
    # TODO: load experiment log from session path
    log_entries: List[Dict[str, Any]] = []

    # Budget exhausted → converge immediately
    if state.get("status") == "budget_exhausted":
        state["status"] = "converged"
        return state

    # Max rounds → converge
    if len(log_entries) >= MAX_ROUNDS:
        state["last_redirect"] = None
        state["status"] = "converged"
        print(f"[Selector] Max rounds ({MAX_ROUNDS}) reached. Converging.")
        return state

    # TODO: add plateau detection, variance checks, near-tied logic
    # TODO: add LLM-based methodology commentary

    # Default: continue iterating
    state["last_redirect"] = {
        "reason": "normal_iteration",
        "detail": "Continuing exploration.",
    }
    state["status"] = "planning"
    return state
