import json
import time
from pathlib import Path
from typing import Dict, Any, List

from graph.state import AgentState
from config.settings import get_settings
from agents.utils import call_llm, extract_json

def check_plateau_and_variance(
    log_entries: List[Dict[str, Any]], 
    n_rounds: int = 3, 
    epsilon_rel: float = 0.005,
    last_redirect_reason: str = None
) -> Dict[str, Any]:
    """
    Evaluates exact plateau and statistical variance rules on experiment_log.jsonl.
    Returns evaluation dictionary.
    """
    successful_entries = [e for e in log_entries if e.get("status") == "success"]
    if len(successful_entries) < 2:
        return {"status": "normal", "reason": None}

    cv_means = [e["cv_mean"] for e in successful_entries]
    cv_stds = [e["cv_std"] for e in successful_entries]
    exp_ids = [e["experiment_id"] for e in successful_entries]

    # 1. Check Near-Tied Candidates (scores within 0.001 of each other among top candidates)
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
                "detail": f"Top candidates ({sorted_entries[0]['experiment_id']} and {sorted_entries[1]['experiment_id']}) have near-tied CV scores ({top1} vs {top2}). High potential for ensembling.",
                "referenced_ids": [sorted_entries[0]["experiment_id"], sorted_entries[1]["experiment_id"]]
            }

    # 2. Check High Variance
    latest_std = cv_stds[-1]
    if len(cv_means) >= 2:
        latest_gain = cv_means[-1] - cv_means[-2]
        if latest_gain > 0 and latest_std > (2 * latest_gain):
            return {
                "status": "redirect",
                "reason": "high_variance",
                "detail": f"Latest CV standard deviation ({latest_std}) is large relative to mean improvement ({latest_gain}).",
                "referenced_ids": [exp_ids[-1]]
            }

    # 3. Check Worse Than Baseline
    baseline_cv = cv_means[0]
    if cv_means[-1] < baseline_cv - 0.01:
        return {
            "status": "redirect",
            "reason": "worse_than_baseline",
            "detail": f"Current experiment score ({cv_means[-1]}) degraded significantly below initial baseline ({baseline_cv}).",
            "referenced_ids": [exp_ids[0], exp_ids[-1]]
        }

    # 4. Check Exact Plateau Rule
    # Requires N consecutive rounds with relative improvement <= epsilon_rel
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
                "referenced_ids": plateau_ids
            }

    return {"status": "normal", "reason": None}

def selector_node(state: AgentState) -> AgentState:
    """
    Selector / Judge Agent Node.
    Analyzes experiment_log.jsonl and decides redirect vs converge.
    Sets reasoning_mode = 'tot' if redirect reason is plateaued, high_variance, or near_tied.
    """
    settings = get_settings()
    base_dir = Path(__file__).parent.parent
    log_path = base_dir / "state" / "experiment_log.jsonl"

    log_entries: List[Dict[str, Any]] = []
    if log_path.exists():
        with open(log_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        log_entries.append(json.loads(line))
                    except Exception:
                        pass

    # If budget is exhausted, force convergence verdict
    if state.get("status") == "budget_exhausted":
        best_exp = max(log_entries, key=lambda x: x.get("cv_mean", 0.0)) if log_entries else {"experiment_id": "exp_001"}
        state["last_redirect"] = None
        state["status"] = "converged"
        print(f"[Selector Node] Budget exhausted. Force converged on best candidate: {best_exp.get('experiment_id')}")
        return state

    # Evaluate exact plateau / variance rules
    last_red = state.get("last_redirect")
    last_red_reason = last_red.get("reason") if last_red else None

    eval_res = check_plateau_and_variance(
        log_entries, 
        n_rounds=settings.selector.plateau_n_rounds, 
        epsilon_rel=settings.selector.plateau_epsilon_relative,
        last_redirect_reason=last_red_reason
    )

    if eval_res["status"] == "redirect":
        # If we already attempted a redirect for plateaued or near_tied and still plateaued, converge
        if last_red_reason in ["plateaued", "near_tied"] and eval_res["reason"] in ["plateaued", "near_tied"]:
            best_exp = max(log_entries, key=lambda x: x.get("cv_mean", 0.0))
            state["last_redirect"] = None
            state["status"] = "converged"
            print(f"[Selector Node] System plateaued after strategic redirect. Converged on best candidate: {best_exp.get('experiment_id')}")
            return state

        redirect = {
            "reason": eval_res["reason"],
            "detail": eval_res["detail"],
            "referenced_experiment_ids": eval_res.get("referenced_ids", [])
        }
        state["last_redirect"] = redirect
        # Set reasoning_mode to 'tot' if uncertainty flag
        if eval_res["reason"] in ["plateaued", "high_variance", "near_tied"]:
            state["reasoning_mode"] = "tot"
        state["status"] = "planning"
        print(f"[Selector Node] Redirecting Planner. Reason: {eval_res['reason']} - {eval_res['detail']}")
        return state

    # If maximum rounds reached or plateaued after many steps -> Converge
    if len(log_entries) >= 10:
        best_exp = max(log_entries, key=lambda x: x.get("cv_mean", 0.0))
        state["last_redirect"] = None
        state["status"] = "converged"
        print(f"[Selector Node] Target experiment threshold reached. Converged on {best_exp.get('experiment_id')}")
        return state

    # Default flow: continue planning next variant
    state["last_redirect"] = {
        "reason": "normal_iteration",
        "detail": "Proceeding with next variant exploration.",
        "referenced_experiment_ids": [e.get("experiment_id") for e in log_entries[-1:]]
    }
    state["status"] = "planning"
    return state
