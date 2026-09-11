"""
graph/build_graph.py — LangGraph state graph builder (minimal skeleton)

Wires agents into the execution flow:
  data_explorer → planner → coder → execute → selector → (loop or end)
"""

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
# Routing functions
# ─────────────────────────────────────────────────────────────────────────────

def route_after_coder(state: AgentState) -> str:
    """Escalation → back to planner, otherwise → execute."""
    if state.get("last_escalation") is not None:
        return "planner"
    return "execute"


def route_after_selector(state: AgentState) -> str:
    """Converged/budget_exhausted → END, otherwise → planner for next round."""
    if state.get("status") in ["converged", "budget_exhausted"]:
        return "end"
    return "planner"


# ─────────────────────────────────────────────────────────────────────────────
# Graph builder
# ─────────────────────────────────────────────────────────────────────────────

def build_app(checkpointer=None):
    """Builds and compiles the LangGraph state graph."""
    if not HAS_LANGGRAPH:
        raise ImportError("langgraph is required. Install with: pip install langgraph")

    if checkpointer is None and HAS_MEMORY_SAVER:
        checkpointer = MemorySaver()

    builder = StateGraph(AgentState)

    # Nodes
    builder.add_node("data_explorer", data_explorer_node)
    builder.add_node("planner", planner_node)
    builder.add_node("coder", coder_node)
    builder.add_node("execute", execute_node)
    builder.add_node("selector", selector_node)

    # Edges
    builder.add_edge(START, "data_explorer")
    builder.add_edge("data_explorer", "planner")
    builder.add_edge("planner", "coder")

    builder.add_conditional_edges(
        "coder",
        route_after_coder,
        {"planner": "planner", "execute": "execute"},
    )

    builder.add_edge("execute", "selector")

    builder.add_conditional_edges(
        "selector",
        route_after_selector,
        {"planner": "planner", "end": END},
    )

    return builder.compile(checkpointer=checkpointer)