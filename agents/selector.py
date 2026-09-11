import json
import time
from pathlib import Path
from typing import Dict, Any, List, Optional

from graph.state import AgentState
from config.settings import get_settings
from agents.utils import call_llm, extract_json, push_event


# ---------------------------------------------------------------------- #
# Deterministic plateau / variance evaluation (unchanged from v1)
# ---------------------------------------------------------------------- #

def check_plateau_and_variance(
    log_entries: List[Dict[str, Any]],
    n_rounds: int = 3,
    epsilon_rel: float = 0.005,
    last_redirect_reason: str = None,
) -> Dict[str, Any]:
    """
    Evaluates exact plateau and statistical variance rules on experiment log entries.
    Returns evaluation dict: {status, reason, detail, referenced_ids}
    """
    successful_entries = [e for e in log_entries if e.get("status") == "success"]
    if len(successful_entries) < 2:
        return {"status": "normal", "reason": None}

    cv_means = [e["cv_mean"] for e in successful_entries]
    cv_stds = [e["cv_std"] for e in successful_entries]
    exp_ids = [e["experiment_id"] for e in successful_entries]

    # 1. Near-tied candidates
    sorted_entries = sorted(successful_entries, key=lambda x: x["cv_mean"], reverse=True)
    if len(sorted_entries) >= 2 and last_redirect_reason != "near_tied":
        top1 = sorted_entries[0]["cv_mean"]
        top2 = sorted_entries[1]["cv_mean"]
        m_type1 = sorted_entries[0].get("model_type", "ModelA")
        m_type2 = sorted_entries[1].get("model_type", "ModelB")
        if abs(top1 - top2) <= 0.001 and m_type1 != m_type2:
            return {
                "status": "redirect",
                "reason": "near_tied",
                "detail": (
                    f"Top candidates ({sorted_entries[0]['experiment_id']} and "
                    f"{sorted_entries[1]['experiment_id']}) have near-tied CV scores "
                    f"({top1} vs {top2}). High potential for ensembling."
                ),
                "referenced_ids": [sorted_entries[0]["experiment_id"], sorted_entries[1]["experiment_id"]],
            }

    # 2. High variance
    latest_std = cv_stds[-1]
    if len(cv_means) >= 2:
        latest_gain = cv_means[-1] - cv_means[-2]
        if latest_gain > 0 and latest_std > (2 * latest_gain):
            return {
                "status": "redirect",
                "reason": "high_variance",
                "detail": f"Latest CV std ({latest_std}) is large relative to mean improvement ({latest_gain}).",
                "referenced_ids": [exp_ids[-1]],
            }

    # 3. Worse than baseline
    baseline_cv = cv_means[0]
    if cv_means[-1] < baseline_cv - 0.01:
        return {
            "status": "redirect",
            "reason": "worse_than_baseline",
            "detail": f"Current score ({cv_means[-1]}) degraded below initial baseline ({baseline_cv}).",
            "referenced_ids": [exp_ids[0], exp_ids[-1]],
        }

    # 4. Plateau check
    if len(cv_means) >= n_rounds + 1:
        is_plateaued = True
        plateau_ids = []
        for i in range(len(cv_means) - n_rounds, len(cv_means)):
            prev_best = max(cv_means[:i])
            curr_score = cv_means[i]
            rel_gain = (curr_score - prev_best) / (abs(prev_best) if prev_best != 0 else 1.0)
            plateau_ids.append(exp_ids[i])
            if rel_gain > epsilon_rel:
                is_plateaued = False
                break
        if is_plateaued:
            return {
                "status": "redirect",
                "reason": "plateaued",
                "detail": f"CV mean showed no improvement > {epsilon_rel*100:.2f}% for {n_rounds} consecutive rounds.",
                "referenced_ids": plateau_ids,
            }

    return {"status": "normal", "reason": None}


# ---------------------------------------------------------------------- #
# Node
# ---------------------------------------------------------------------- #

def selector_node(state: AgentState) -> AgentState:
    """
    Selector / Judge Agent Node (v2).

    Changes from v1:
    - Adds an LLM call (NIM DeepSeek, role="selector") for methodology commentary.
    - Reads experiment log from session-scoped path.
    - Emits selector_verdict event to state event_queue.
    - Emits node_start / node_end events.

    The LLM verdict is additive: deterministic plateau rules still decide
    redirect vs. converge, but the LLM adds the methodology-soundness rationale
    that the UI displays in the selector_verdict block.
    """
    push_event(state, {"type": "node_start", "node": "selector"})

    settings = get_settings()
    dry_run = state.get("dry_run", False)
    session_id = state.get("session_id", "default")
    sessions_root = settings.sessions.storage_path

    log_path = Path(sessions_root) / session_id / "experiment_log.jsonl"
    log_entries: List[Dict[str, Any]] = []
    if log_path.exists():
        with open(log_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        log_entries.append(json.loads(line))
                    except Exception:
                        pass

    # ── Budget-exhausted fast path ────────────────────────────────────────
    if state.get("status") == "budget_exhausted":
        best_exp = max(log_entries, key=lambda x: x.get("cv_mean", 0.0)) if log_entries else {"experiment_id": "exp_001", "cv_mean": 0.0}
        push_event(state, {
            "type": "selector_verdict",
            "decision": "converge",
            "detail": f"Budget exhausted. Best experiment: {best_exp.get('experiment_id')} (CV {best_exp.get('cv_mean', 0.0):.4f})",
            "methodology_note": "Session ended due to budget limit.",
        })
        push_event(state, {"type": "node_end", "node": "selector"})
        state["last_redirect"] = None
        state["status"] = "converged"
        return state

    # ── Deterministic plateau/variance evaluation ─────────────────────────
    last_red = state.get("last_redirect")
    last_red_reason = last_red.get("reason") if last_red else None

    eval_res = check_plateau_and_variance(
        log_entries,
        n_rounds=settings.selector.plateau_n_rounds,
        epsilon_rel=settings.selector.plateau_epsilon_relative,
        last_redirect_reason=last_red_reason,
    )

    # ── LLM call for methodology commentary ───────────────────────────────
    methodology_note = ""
    if log_entries:
        base_dir = Path(__file__).parent.parent
        prompt_path = base_dir / "prompts" / "selector_prompt.md"
        if prompt_path.exists():
            with open(prompt_path, "r", encoding="utf-8") as f:
                selector_system = f.read()
        else:
            selector_system = "You are the Selector. Assess experiment results and provide methodology commentary."

        selector_user = (
            f"## Experiment Log\n```json\n{json.dumps(log_entries, indent=2, default=str)}\n```\n\n"
            f"## Plateau/Variance Evaluation\n```json\n{json.dumps(eval_res, indent=2)}\n```\n\n"
            f"Provide a JSON response with:\n"
            f"  decision: 'redirect' or 'converge'\n"
            f"  detail: brief explanation\n"
            f"  methodology_note: 1-2 sentence assessment of the methodology's soundness\n"
        )

        try:
            raw_resp, has_thinking = call_llm(
                selector_system, selector_user,
                role="selector", dry_run=dry_run
            )
            if has_thinking:
                push_event(state, {"type": "thinking", "node": "selector", "content": raw_resp[:2000]})
            parsed = extract_json(raw_resp)
            if parsed and isinstance(parsed, dict):
                methodology_note = parsed.get("methodology_note", "")
        except Exception as e:
            print(f"[Selector] LLM call failed: {e} — using deterministic verdict only.")

    # ── Decision logic (deterministic rules take precedence) ──────────────
    if eval_res["status"] == "redirect":
        # If already attempted redirect for same reason → converge
        if last_red_reason in ["plateaued", "near_tied"] and eval_res["reason"] in ["plateaued", "near_tied"]:
            best_exp = max(log_entries, key=lambda x: x.get("cv_mean", 0.0))
            push_event(state, {
                "type": "selector_verdict",
                "decision": "converge",
                "detail": f"System plateaued after strategic redirect. Best: {best_exp.get('experiment_id')} (CV {best_exp.get('cv_mean', 0.0):.4f})",
                "methodology_note": methodology_note or "Converging after exhausting strategic alternatives.",
            })
            push_event(state, {"type": "node_end", "node": "selector"})
            state["last_redirect"] = None
            state["status"] = "converged"
            print(f"[Selector] Converged after redirect. Best: {best_exp.get('experiment_id')}")
            return state

        redirect = {
            "reason": eval_res["reason"],
            "detail": eval_res["detail"],
            "referenced_experiment_ids": eval_res.get("referenced_ids", []),
        }
        push_event(state, {
            "type": "selector_verdict",
            "decision": "redirect",
            "detail": eval_res["detail"],
            "methodology_note": methodology_note or f"Redirecting due to: {eval_res['reason']}",
        })
        push_event(state, {"type": "node_end", "node": "selector"})
        state["last_redirect"] = redirect
        if eval_res["reason"] in ["plateaued", "high_variance", "near_tied"]:
            state["reasoning_mode"] = "tot"
        state["status"] = "planning"
        print(f"[Selector] Redirecting. Reason: {eval_res['reason']}")
        return state

    # ── Max rounds threshold ──────────────────────────────────────────────
    if len(log_entries) >= 10:
        best_exp = max(log_entries, key=lambda x: x.get("cv_mean", 0.0))
        push_event(state, {
            "type": "selector_verdict",
            "decision": "converge",
            "detail": f"Reached maximum experiment threshold. Best: {best_exp.get('experiment_id')} (CV {best_exp.get('cv_mean', 0.0):.4f})",
            "methodology_note": methodology_note or "Target experiment count reached.",
        })
        push_event(state, {"type": "node_end", "node": "selector"})
        state["last_redirect"] = None
        state["status"] = "converged"
        print(f"[Selector] Max rounds reached. Converged on {best_exp.get('experiment_id')}")
        return state

    # ── Default: continue iterating ───────────────────────────────────────
    push_event(state, {
        "type": "selector_verdict",
        "decision": "redirect",
        "detail": "Proceeding with next variant exploration — no plateau detected.",
        "methodology_note": methodology_note or "Results are progressing. Continuing exploration.",
    })
    push_event(state, {"type": "node_end", "node": "selector"})
    state["last_redirect"] = {
        "reason": "normal_iteration",
        "detail": "Proceeding with next variant exploration.",
        "referenced_experiment_ids": [e.get("experiment_id") for e in log_entries[-1:]],
    }
    state["status"] = "planning"
    return state
