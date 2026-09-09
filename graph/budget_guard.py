import time
from typing import Tuple
from graph.state import AgentState

def enforce_budget(
    state: AgentState, 
    action_cost: int = 1, 
    elapsed_minutes: float = 0.0
) -> Tuple[AgentState, bool]:
    """
    Enforces action and time budget on AgentState.
    Deducts action_cost from actions_remaining and elapsed_minutes from time_remaining.
    If either budget drops to <= 0, forces state['status'] = 'budget_exhausted'.
    Returns updated state and a boolean flag indicating if budget is exhausted.
    """
    actions = state.get("actions_remaining", 100) - action_cost
    time_rem = state.get("time_remaining", 60.0) - elapsed_minutes
    
    state["actions_remaining"] = max(0, actions)
    state["time_remaining"] = max(0.0, time_rem)
    
    if state["actions_remaining"] <= 0 or state["time_remaining"] <= 0:
        state["status"] = "budget_exhausted"
        return state, True
        
    return state, False
