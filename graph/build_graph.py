from typing import Dict, Any, Literal
from graph.state import AgentState
from agents import (
    data_explorer_node,
    planner_node,
    coder_node,
    execute_node,
    selector_node,
)

try:
    from langgraph.graph import StateGraph, START, END
    HAS_LANGGRAPH = True
except ImportError:
    HAS_LANGGRAPH = False

try:
    from langgraph.checkpoint.memory import MemorySaver
    HAS_MEMORY_SAVER = True
except ImportError:
    HAS_MEMORY_SAVER = False


# ─────────────────────────────────────────────────────────────────────────────
# Conditional routing functions
# ─────────────────────────────────────────────────────────────────────────────

def route_after_coder(state: AgentState) -> str:
    """Routes to planner if escalation raised, otherwise to execute."""
    if state.get("last_escalation") is not None:
        return "planner"
    return "execute"


def route_after_selector(state: AgentState) -> str:
    """Routes to END if converged or budget_exhausted, otherwise back to planner."""
    status = state.get("status")
    if status in ["converged", "budget_exhausted"]:
        return "end"
    return "planner"


def route_after_planner(state: AgentState) -> str:
    """
    Routes to coder normally, or to the interrupt node if Planner raised
    a human-in-the-loop question (status == 'waiting_for_human').
    """
    if state.get("status") == "waiting_for_human":
        return "waiting"
    return "coder"


# ─────────────────────────────────────────────────────────────────────────────
# Graph builder
# ─────────────────────────────────────────────────────────────────────────────

def build_app(checkpointer=None):
    """
    Builds and returns the LangGraph compiled state graph application.

    Args:
        checkpointer: LangGraph checkpointer instance.
            Pass MemorySaver() for local dev with interrupt() support.
            Pass a SQLite/Postgres checkpointer for production (survives restarts).
            Defaults to MemorySaver if available, None otherwise.
    """
    if not HAS_LANGGRAPH:
        print("[Graph] langgraph package not found. Using DirectGraphRunner fallback.")
        return DirectGraphRunner()

    if checkpointer is None and HAS_MEMORY_SAVER:
        checkpointer = MemorySaver()

    builder = StateGraph(AgentState)

    # ── Nodes ──────────────────────────────────────────────────────────────
    builder.add_node("data_explorer", data_explorer_node)
    builder.add_node("planner", planner_node)
    builder.add_node("coder", coder_node)
    builder.add_node("execute", execute_node)
    builder.add_node("selector", selector_node)

    # ── Edges ──────────────────────────────────────────────────────────────
    builder.add_edge(START, "data_explorer")
    builder.add_edge("data_explorer", "planner")

    # Planner → Coder (normal) or surfaces interrupt() for human-in-the-loop
    # LangGraph's interrupt() pauses the graph automatically; no extra node needed.
    builder.add_edge("planner", "coder")

    # Conditional Edges from Coder
    builder.add_conditional_edges(
        "coder",
        route_after_coder,
        {
            "planner": "planner",
            "execute": "execute",
        },
    )

    builder.add_edge("execute", "selector")

    # Conditional Edges from Selector
    builder.add_conditional_edges(
        "selector",
        route_after_selector,
        {
            "planner": "planner",
            "end": END,
        },
    )

    return builder.compile(checkpointer=checkpointer)


# ─────────────────────────────────────────────────────────────────────────────
# Fallback (no langgraph installed)
# ─────────────────────────────────────────────────────────────────────────────

class DirectGraphRunner:
    """
    Lightweight standalone fallback replicating exact LangGraph state transitions.
    Does NOT support interrupt() / human-in-the-loop.
    """

    def invoke(self, state: AgentState, **kwargs) -> AgentState:
        state = data_explorer_node(state)
        state = planner_node(state)

        while state.get("status") not in ["converged", "budget_exhausted"]:
            if state.get("status") == "waiting_for_human":
                print("[DirectGraphRunner] interrupt() not supported in fallback — skipping human input.")
                state["status"] = "coding"
                state["pending_human_question"] = None

            state = coder_node(state)
            if route_after_coder(state) == "planner":
                state = planner_node(state)
                continue

            state = execute_node(state)
            state = selector_node(state)

            if route_after_selector(state) == "planner":
                state = planner_node(state)

        return state