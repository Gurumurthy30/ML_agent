"""
AgentState — finalized, consolidated across all prior iterations of this project.

Reducer note (important, was a real bug caught mid-project): LangGraph's default merge
for a TypedDict state key is overwrite-on-return, not append. Any field a node updates
multiple times across retries/iterations (`candidate_models`, `metric_history`,
`run_memory`) MUST use `Annotated[list, operator.add]` or every retry silently wipes
prior history.

`best_metric` is explicitly NOT a reducer — it's a plain `Optional[float]` that gets
compare-and-replaced ("is this better than what we had?"), not accumulated.
"""
import hashlib
import operator
import os
import uuid
from typing import Literal, Optional, Annotated
from typing_extensions import TypedDict
from langgraph.graph.message import add_messages
from utils.scoped_memory import merge_private_memories, merge_open_summary


def _fingerprint(path: str) -> str:
    """Calculate deterministic content hash for a dataset file."""
    if not os.path.exists(path):
        return hashlib.sha256(path.encode("utf-8")).hexdigest()[:16]
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


class AgentState(TypedDict):
    # --- Input ---
    mode: Literal["eda_only", "full_pipeline"]
    guided_mode: bool
    dataset_path: str
    dataset_fingerprint: str
    run_id: str

    # --- Specialist outputs ---
    profile: dict                  # Profiler output
    eda_findings: dict             # EDA Agent output
    feature_set: dict              # Features Agent output
    transformed_dataset_path: Optional[str]  # written by Features, read by Modeler
    candidate_models: Annotated[list, operator.add]   # accumulates across tiers/iterations
    metric_history: Annotated[list, operator.add]
    best_metric: Optional[float]   # compare-and-replace, NOT a reducer (best-so-far, not accumulation)

    # --- Convenience fields promoted out of `profile` so downstream nodes don't re-parse it ---
    target_column: Optional[str]
    task_type: Optional[Literal["classification", "regression"]]

    # --- Supervisor routing ---
    next_agent: Optional[Literal[
        "profiler", "features", "modeler", "judge",
        "human_approval", "reporter", "eda_agent"
    ]]
    task_instructions: str
    supervisor_reasoning: str

    # --- Retry control ---
    retry_tier: Literal[0, 1, 2]
    retry_counts: dict   # {1: n_attempts, 2: n_attempts} -> escalation guard

    # --- Judge + Human Approval ---
    last_verdict: Optional[Literal["accept", "reject"]]
    judge_feedback: Optional[str]
    requires_human_approval: bool
    approval_reason: Optional[Literal[
        "destructive_action", "guided_mode", "policy_sensitive", "high_risk",
        "unresolved_exploration", "stalled", "global_iteration_ceiling", "retry_cap_exceeded"
    ]]
    approval_status: Optional[Literal["approved", "modify", "reject"]]
    feature_plan: Optional[dict]   # persists {code, description, destructive_self_assessment}
                                    # across the human-approval interrupt/resume cycle

    # --- Scoped Memory System ---
    # Profiler has NO memory (simple, one-time execution).
    # Private / Score memory for specialist working agents (coder, eda, features, modeler).
    # Modeler tracks past models, hyperparams, CV scores, and mistakes/blunders to avoid repeats.
    private_memories: Annotated[dict, merge_private_memories]
    # Open summarization memory for executive agents (supervisor, judge, reporter).
    # Token-bounded digest preventing context leaks.
    open_summary_memory: Annotated[dict, merge_open_summary]

    # --- Tool-calling trace ---
    messages: Annotated[list, add_messages]

    # --- Output & storage ---
    report: str
    artifact_path: str
    run_memory: Annotated[list, operator.add]

    # --- Safety, Stall Detection & Stop Reasons ---
    iteration: int  # global step counter, guards against infinite Supervisor cycling
    stop_reason: Optional[Literal["converged", "stalled", "hit_safety_ceiling", "errored", "user_rejected"]]
    agent_fingerprints: dict  # {agent_name: hash_str} for stall detection
    last_executed_agent: Optional[str]


def build_initial_state(
    dataset_path: str,
    mode: Literal["eda_only", "full_pipeline"] = "full_pipeline",
    guided_mode: bool = False,
    run_id: Optional[str] = None,
) -> AgentState:
    """Build a clean initial AgentState, computing dataset fingerprint and run_id."""
    fingerprint = _fingerprint(dataset_path)
    actual_run_id = run_id or f"{fingerprint}_{uuid.uuid4().hex[:6]}"

    return {
        "mode": mode,
        "guided_mode": guided_mode,
        "dataset_path": dataset_path,
        "dataset_fingerprint": fingerprint,
        "run_id": actual_run_id,
        "profile": {},
        "eda_findings": {},
        "feature_set": {},
        "transformed_dataset_path": None,
        "candidate_models": [],
        "metric_history": [],
        "best_metric": None,
        "target_column": None,
        "task_type": None,
        "next_agent": None,
        "task_instructions": "",
        "supervisor_reasoning": "",
        "retry_tier": 0,
        "retry_counts": {},
        "last_verdict": None,
        "judge_feedback": None,
        "requires_human_approval": False,
        "approval_reason": None,
        "approval_status": None,
        "feature_plan": None,
        "private_memories": {"coder": [], "eda": [], "features": [], "modeler": []},
        "open_summary_memory": {},
        "messages": [],
        "report": "",
        "artifact_path": "",
        "run_memory": [],
        "iteration": 0,
        "stop_reason": None,
        "agent_fingerprints": {},
        "last_executed_agent": None,
    }
