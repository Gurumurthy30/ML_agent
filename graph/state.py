from typing import Any, Dict, List, Literal, Optional, TypedDict


class AgentState(TypedDict):
    # ── Session identity ───────────────────────────────────────────────────
    session_id: str
    user_message: str                   # original chat message from the user
    session_data_dir: str               # absolute path to state/sessions/{id}/data/

    # ── Task context (set by Session Init + enriched by Data Explorer) ─────
    task_context: Dict[str, Any]
    target_confidence: Literal["explicit", "name_matched", "defaulted"]

    # ── Experiment control ─────────────────────────────────────────────────
    current_spec: Optional[Dict[str, Any]]
    last_escalation: Optional[Dict[str, Any]]
    last_redirect: Optional[Dict[str, Any]]
    reasoning_mode: Literal["default", "tot"]
    actions_remaining: int
    time_remaining: float
    status: Literal["init", "planning", "coding", "executing", "judging", "converged", "budget_exhausted", "waiting_for_human"]

    # ── EDA output ─────────────────────────────────────────────────────────
    eda_report_markdown: str            # full rendered markdown for the UI eda_report block

    # ── Human-in-the-loop ─────────────────────────────────────────────────
    pending_human_question: Optional[Dict[str, Any]]  # {question, context}
    human_answer: Optional[str]

    # ── Event stream ──────────────────────────────────────────────────────
    # Outbound events buffer — agents append here, server drains to WebSocket
    event_queue: List[Dict[str, Any]]

    # ── Flags ─────────────────────────────────────────────────────────────
    dry_run: bool                       # if True, use canned responses (no API calls)
