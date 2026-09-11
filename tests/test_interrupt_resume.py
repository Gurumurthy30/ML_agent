"""
tests/test_interrupt_resume.py — Correctness test for LangGraph interrupt and resume

Verifies:
1. Graph execution pauses at interrupt()
2. Event queue captures events prior to interrupt
3. Resuming via Command(resume="use label column") passes value to human_answer
4. Full planner turn completes with status == "coding"
"""

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from graph.state import AgentState
from tools.rag_mcp import RagMCP
from agents.utils import push_event

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import interrupt, Command


def test_interrupt_resume():
    print("[Test] Setting up mock graph with MemorySaver and mock planner node...")

    rag = RagMCP()
    call_counts = {"rag": 0, "planner_runs": 0}
    rag_tool_cache: Dict[str, Any] = {}

    def mock_planner_node(state: AgentState) -> Dict[str, Any]:
        call_counts["planner_runs"] += 1
        print(f"[MockPlanner] Run #{call_counts['planner_runs']}")

        # Step 1: Call search_library_docs once (cached so it is not re-executed on resume)
        query = "target encoding"
        if query not in rag_tool_cache:
            call_counts["rag"] += 1
            rag_docs = rag.search_library_docs(query, top_k=1)
            rag_tool_cache[query] = rag_docs
            push_event(state, {
                "type": "tool_call",
                "node": "planner",
                "tool": "search_library_docs",
                "input": {"query": query, "top_k": 1},
            })
            push_event(state, {
                "type": "tool_result",
                "node": "planner",
                "tool": "search_library_docs",
                "output": {"results_count": len(rag_docs)},
            })
        else:
            # Re-attach the cached event if LangGraph re-initialized state
            existing = [e for e in state.get("event_queue", []) if e.get("type") == "tool_call"]
            if not existing:
                push_event(state, {
                    "type": "tool_call",
                    "node": "planner",
                    "tool": "search_library_docs",
                    "input": {"query": query, "top_k": 1},
                })

        # Step 2: Interrupt for human input
        human_answer = interrupt({"question": "Which column is the target?"})

        # Step 3: Resume logic: process human_answer
        print(f"[MockPlanner] Resumed with human_answer: {human_answer}")
        return {
            "human_answer": human_answer,
            "status": "coding",
            "event_queue": state.get("event_queue", []),
        }

    builder = StateGraph(AgentState)
    builder.add_node("planner", mock_planner_node)
    builder.add_edge(START, "planner")
    builder.add_edge("planner", END)

    checkpointer = MemorySaver()
    app = builder.compile(checkpointer=checkpointer)

    thread_id = "test_thread_resume_001"
    config = {"configurable": {"thread_id": thread_id}}

    initial_state: AgentState = {
        "task_context": {},
        "current_spec": None,
        "last_escalation": None,
        "last_redirect": None,
        "reasoning_mode": "default",
        "actions_remaining": 10,
        "time_remaining": 60.0,
        "status": "planning",
        "event_queue": [],
    }

    print("[Test] Invoking graph until interrupt...")
    interrupted_result = app.invoke(initial_state, config)
    print(f"[Test] Interrupted result keys: {list(interrupted_result.keys()) if isinstance(interrupted_result, dict) else interrupted_result}")

    # Verify RAG tool was called and recorded in event_queue before interrupt
    events_before = interrupted_result.get("event_queue", [])
    rag_tool_events = [e for e in events_before if e.get("type") == "tool_call" and e.get("tool") == "search_library_docs"]
    assert len(rag_tool_events) == 1, f"Expected 1 RAG tool call event before interrupt, found {len(rag_tool_events)}"
    assert call_counts["rag"] == 1, f"Expected RAG called once, got {call_counts['rag']}"

    # Step 4: Resume graph with Command
    print("[Test] Resuming graph via Command(resume='use label column')...")
    resumed_result = app.invoke(Command(resume="use label column"), config)
    print(f"[Test] Resumed result status: {resumed_result.get('status')}")

    # Step 5: Assertions
    assert resumed_result.get("human_answer") == "use label column", (
        f"Expected human_answer 'use label column', got: {resumed_result.get('human_answer')}"
    )
    assert resumed_result.get("status") == "coding", (
        f"Expected status 'coding', got: {resumed_result.get('status')}"
    )

    # Confirm RAG was not re-executed redundantly
    final_events = resumed_result.get("event_queue", [])
    final_rag_events = [e for e in final_events if e.get("type") == "tool_call" and e.get("tool") == "search_library_docs"]
    assert len(final_rag_events) == 1, f"Expected exactly 1 RAG event after resume, got {len(final_rag_events)}"
    assert call_counts["rag"] == 1, f"RAG should not have been called again after resume, got {call_counts['rag']}"

    print("[PASS] Interrupt and resume correctness verified!")


if __name__ == "__main__":
    test_interrupt_resume()
