from typing import Dict, Any, Literal
from graph.state import AgentState
from agents import (
    data_explorer_node,
    planner_node,
    coder_node,
    execute_node,
    selector_node
)

try:
    from langgraph.graph import StateGraph, START, END
    HAS_LANGGRAPH = True
except ImportError:
    HAS_LANGGRAPH = False

# Conditional Routing Functions
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

def build_app():
    """Builds and returns the LangGraph compiled state graph application."""
    if not HAS_LANGGRAPH:
        print("[Graph] langgraph package not found. Using direct graph runner.")
        return DirectGraphRunner()

    builder = StateGraph(AgentState)

    # Add Nodes
    builder.add_node("data_explorer", data_explorer_node)
    builder.add_node("planner", planner_node)
    builder.add_node("coder", coder_node)
    builder.add_node("execute", execute_node)
    builder.add_node("selector", selector_node)

    # Add Edges
    builder.add_edge(START, "data_explorer")
    builder.add_edge("data_explorer", "planner")
    builder.add_edge("planner", "coder")

    # Conditional Edges from Coder
    builder.add_conditional_edges(
        "coder",
        route_after_coder,
        {
            "planner": "planner",
            "execute": "execute"
        }
    )

    builder.add_edge("execute", "selector")

    # Conditional Edges from Selector
    builder.add_conditional_edges(
        "selector",
        route_after_selector,
        {
            "planner": "planner",
            "end": END
        }
    )

    return builder.compile()

class DirectGraphRunner:
    """Lightweight standalone fallback executor replicating exact LangGraph state transitions."""
    def invoke(self, state: AgentState) -> AgentState:
        state = data_explorer_node(state)
        state = planner_node(state)

        while state.get("status") not in ["converged", "budget_exhausted"]:
            state = coder_node(state)
            if route_after_coder(state) == "planner":
                state = planner_node(state)
                continue
            
            state = execute_node(state)
            state = selector_node(state)
            
            if route_after_selector(state) == "planner":
                state = planner_node(state)

        return state
