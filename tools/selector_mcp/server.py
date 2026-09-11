"""
selector_mcp/server.py — Selector MCP Server

Exposes compute_log_stats as a standalone callable tool:
- compute_log_stats(session_id, n_rounds, epsilon_rel) — wraps check_plateau_and_variance
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional


def compute_log_stats(
    session_id: str,
    sessions_root: str = "state/sessions/",
    n_rounds: int = 3,
    epsilon_rel: float = 0.005,
    last_redirect_reason: Optional[str] = None,
    direction: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Reads experiment_log.jsonl for the session and evaluates plateau/variance rules.
    Returns evaluation dict: {status, reason, detail, referenced_ids}
    """
    log_path = Path(sessions_root) / session_id / "experiment_log.jsonl"
    log_entries: List[Dict[str, Any]] = []

    if not log_path.exists():
        return {
            "status": "normal",
            "reason": "no_data",
            "detail": "Experiment log does not exist.",
            "referenced_ids": [],
        }

    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                try:
                    log_entries.append(json.loads(line))
                except Exception:
                    pass

    if not log_entries:
        return {
            "status": "normal",
            "reason": "no_data",
            "detail": "Experiment log is empty.",
            "referenced_ids": [],
        }

    # Import the actual computation from selector agent (avoids duplication)
    from agents.selector import check_plateau_and_variance
    return check_plateau_and_variance(
        log_entries,
        n_rounds=n_rounds,
        epsilon_rel=epsilon_rel,
        last_redirect_reason=last_redirect_reason,
        direction=direction,
    )


class SelectorMCP:
    """In-process Selector MCP server."""

    def __init__(self, session_id: str, sessions_root: str = "state/sessions/"):
        self.session_id = session_id
        self.sessions_root = sessions_root

    def compute_log_stats(
        self,
        n_rounds: int = 3,
        epsilon_rel: float = 0.005,
        last_redirect_reason: Optional[str] = None,
        direction: Optional[str] = None,
    ) -> Dict[str, Any]:
        return compute_log_stats(
            session_id=self.session_id,
            sessions_root=self.sessions_root,
            n_rounds=n_rounds,
            epsilon_rel=epsilon_rel,
            last_redirect_reason=last_redirect_reason,
            direction=direction,
        )
