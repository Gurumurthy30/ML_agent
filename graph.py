"""
Wires the implemented nodes into a LangGraph StateGraph — now including the Judge
Agent (previously out of scope). The `human_approval` node here is deliberately a
thin, generic PAUSE point (calls LangGraph's `interrupt()` and passes the resumed
value straight into state) — it does NOT implement the Human Approval agent's own
reasoning, which stays out of scope (that's a human decision, not an LLM one).
Building it this way is what actually makes Features' "hard block, genuinely pauses"
requirement real rather than just a flag nobody acts on.
"""
from langgraph.graph import StateGraph, END
from langgraph.types import interrupt
from langgraph.checkpoint.memory import MemorySaver

from state import AgentState
from agents.supervisor import graph_node_supervisor
from agents.profiler_agent import profile_agent
from agents.eda_agent import eda_agent
from agents.features_agent import features_agent
from agents.modeler_agent import modeler_agent
from agents.judge_agent import judge_agent
from agents.reporter_agent import reporter_agent
from tools.logger import log_event


import os

def human_approval_node(state: AgentState) -> dict:
    """Generic pause point — genuinely blocks graph execution until resumed with a
    human's decision. Does not decide anything itself."""
    run_id = state.get("run_id") or state.get("dataset_fingerprint", "run")
    log_event(run_id, "human_approval", "paused", reason=state.get("approval_reason"),
              feature_plan=state.get("feature_plan"))

    # `decision` is whatever is passed via Command(resume=...) when resuming, e.g.
    # {"approval_status": "approved" | "modify" | "reject"}.
    decision = interrupt({
        "reason": state.get("approval_reason"),
        "feature_plan": state.get("feature_plan"),
    })

    log_event(run_id, "human_approval", "resumed", decision=decision)
    approval_status = decision.get("approval_status")
    update = {
        "approval_status": approval_status,
        "requires_human_approval": False,
    }

    # If approved, adopt the proposed output dataset path from the reviewed feature plan
    feature_plan = state.get("feature_plan") or {}
    proposed_path = feature_plan.get("proposed_output_path")
    if approval_status == "approved" and proposed_path and os.path.exists(proposed_path):
        update["transformed_dataset_path"] = proposed_path

    return update


def route_after_features(state: AgentState) -> str:
    if state.get("requires_human_approval") and state.get("approval_reason") in (
        "destructive_action", "guided_mode"
    ):
        return "human_approval"
    return "supervisor"


def route_after_human_approval(state: AgentState) -> str:
    # If modify, hand back to Features to continue from where it paused with user modifications;
    # if approved, the transformation is committed and supervisor takes over to route to Modeler;
    # if rejected, supervisor decides what happens next (e.g. tier-2 retry or abort).
    if state.get("approval_status") == "modify":
        return "features"
    return "supervisor"


def route_after_judge(state: AgentState) -> str:
    # accept -> Reporter (per diagram). reject -> back to Supervisor, which reads
    # retry_tier/retry_counts (already set by judge_agent) to route to Modeler(1) or
    # Features(2), or to escalate to human_approval per its own guard.
    return "reporter" if state.get("last_verdict") == "accept" else "supervisor"


def route_from_supervisor(state: AgentState) -> str:
    implemented = {
        "profiler": "profiler", "eda_agent": "eda_agent", "features": "features",
        "modeler": "modeler", "judge": "judge", "reporter": "reporter",
        # human_approval can be reached from supervisor via:
        #   - global iteration ceiling (graph_node_supervisor short-circuit)
        #   - retry cap overflow (_validate_and_override_decision)
        #   - stall-retry escalation
        "human_approval": "human_approval",
    }
    next_agent = state.get("next_agent")
    if next_agent in implemented:
        return implemented[next_agent]
    return END


def build_graph():
    graph = StateGraph(AgentState)

    graph.add_node("supervisor", graph_node_supervisor)
    graph.add_node("profiler", profile_agent)
    graph.add_node("eda_agent", eda_agent)
    graph.add_node("features", features_agent)
    graph.add_node("modeler", modeler_agent)
    graph.add_node("judge", judge_agent)
    graph.add_node("human_approval", human_approval_node)
    graph.add_node("reporter", reporter_agent)

    graph.set_entry_point("supervisor")

    graph.add_conditional_edges("supervisor", route_from_supervisor, {
        "profiler": "profiler", "eda_agent": "eda_agent", "features": "features",
        "modeler": "modeler", "judge": "judge", "reporter": "reporter",
        "human_approval": "human_approval", END: END,
    })

    graph.add_edge("profiler", "supervisor")
    graph.add_edge("eda_agent", "supervisor")
    graph.add_edge("modeler", "supervisor")

    graph.add_conditional_edges("features", route_after_features, {
        "human_approval": "human_approval", "supervisor": "supervisor",
    })
    graph.add_conditional_edges("human_approval", route_after_human_approval, {
        "features": "features", "supervisor": "supervisor",
    })
    graph.add_conditional_edges("judge", route_after_judge, {
        "reporter": "reporter", "supervisor": "supervisor",
    })

    graph.add_edge("reporter", END)

    return graph.compile(checkpointer=MemorySaver())
