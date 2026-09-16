"""
Shared "try -> look -> adjust" loop shape used by EDA, Features, and Modeler.

This is the core new-architecture design: not a binary accept/reject gate, but an
iterative loop like a data scientist actually works. The three agents differ in how
they decide the next step and what "destructive"/"plateaued" means for them, but the
driving loop (ceiling, condensed vs. full history, exit-reason bookkeeping) is
identical, so it lives here once instead of being copy-pasted three times.
"""
from tools.logger import log_event


def compute_iteration_ceiling(profile: dict) -> int:
    """
    Auto-scales the safety ceiling from the dataset profile instead of a flat
    hardcoded number: floor of 5, +1 per data-quality flag present, plus a
    size/complexity bump based on column count, capped at 25.

    This is a safety limit, not a target to fill — most runs should stop earlier via
    the agent's own "I'm satisfied" decision.
    """
    floor, cap = 5, 25
    profile = profile or {}
    flags = profile.get("data_quality_flags") or []
    n_cols = profile.get("columns") or len(profile.get("features") or [])

    ceiling = floor + len(flags)
    if n_cols > 50:
        ceiling += 6
    elif n_cols > 20:
        ceiling += 3
    elif n_cols > 10:
        ceiling += 1

    return max(floor, min(ceiling, cap))


def compute_exec_timeout(profile: dict, base: int = 60, bumped: int = 300) -> int:
    """
    Non-tabular modalities (image decoding, audio loading, embedding models) can take
    far longer per Coder-generated script than plain pandas/sklearn code. Bump the
    per-attempt subprocess timeout when the profile shows anything beyond plain
    tabular data; stay at the tight default otherwise so runaway tabular scripts still
    get caught quickly.
    """
    profile = profile or {}
    detected = profile.get("detected_modalities") or ["tabular"]
    return bumped if any(m != "tabular" for m in detected) else base


def run_exploration_loop(
    *,
    run_id: str,
    agent_name: str,
    ceiling: int,
    decide_next_step,
    execute_step,
    plateau_check=None,
) -> dict:
    """
    Shared driver for the EDA / Features / Modeler exploration loop.

    decide_next_step(condensed_history: list[str]) -> object with
        .decision ("continue" | "stop"), .task_spec, .reasoning

    execute_step(decision, iteration: int) -> dict with
        "condensed": str            one-line summary fed back into the next decision
        "record": dict              full detail, archived (not fed back to the LLM)
        "hard_block": bool          optional — signals a genuine pause (Features only)

    plateau_check(iteration: int) -> bool, optional
        Only Modeler passes this — a mechanical "stop even if the LLM wants to keep
        going" backstop. EDA/Features never get one (spec-confirmed, do not add it).

    Returns {"full_history", "condensed_history", "exit_reason", "iterations"} where
    exit_reason is one of "llm_stop", "hard_block", "plateau", "ceiling".
    """
    condensed_history = []
    full_history = []
    exit_reason = "ceiling"

    for iteration in range(1, ceiling + 1):
        decision = decide_next_step(condensed_history)
        log_event(run_id, agent_name, "loop_decision", iteration=iteration,
                  decision=decision.decision, reasoning=decision.reasoning,
                  task_spec=getattr(decision, "task_spec", None))

        if decision.decision == "stop":
            exit_reason = "llm_stop"
            break

        step_result = execute_step(decision, iteration)
        full_history.append(step_result["record"])
        condensed_history.append(step_result["condensed"])

        if step_result.get("hard_block"):
            exit_reason = "hard_block"
            break

        if plateau_check and plateau_check(iteration):
            exit_reason = "plateau"
            break
    else:
        exit_reason = "ceiling"

    return {
        "full_history": full_history,
        "condensed_history": condensed_history,
        "exit_reason": exit_reason,
        "iterations": len(full_history),
    }
