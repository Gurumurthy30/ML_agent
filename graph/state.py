from typing import TypedDict, Literal, Optional, Dict, Any

class AgentState(TypedDict):
    task_context: Dict[str, Any]
    current_spec: Optional[Dict[str, Any]]
    last_escalation: Optional[Dict[str, Any]]
    last_redirect: Optional[Dict[str, Any]]
    reasoning_mode: Literal["default", "tot"]
    actions_remaining: int
    time_remaining: float
    status: Literal["planning", "coding", "executing", "judging", "converged", "budget_exhausted"]
