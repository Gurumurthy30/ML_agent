"""
Modeler Agent — incremental model search over a growing shortlist.

Per spec:
  - Incremental: each iteration extends/narrows a shortlist of tried model families +
    their CV scores, tracked in condensed_history so later iterations don't blindly
    retry an already-tried family.
  - Tier-0 hyperparameter tuning is "internal, free, doesn't touch retry_tier": rather
    than an explicit outer Python loop here, this is delegated INTO each Coder-
    generated script (told to use cross-validation with internal hyperparameter search
    before reporting one final cv_score for that family) — invisible to the
    Supervisor/retry machinery, exactly as the diagram's "tier 0: HP tuning (internal
    loop)" self-loop on Modeler implies.
  - Modeler is the ONLY one of the three loop agents with a mechanical stop condition:
    auto-stop if the best metric hasn't improved over the last 5 iterations, even if
    the LLM would keep going. This is intentionally NOT given to EDA/Features.
  - No hardcoded MODEL_REGISTRY: the Coder sub-agent picks and evaluates model
    families itself based on task_type/recommended_metric.
"""
import os
import re
import json
from typing import Literal, Optional
from pydantic import BaseModel, Field
from tools.llm import get_llm
from langchain_core.messages import SystemMessage, HumanMessage

from state import AgentState
from config import METRIC_IMPROVEMENT_EPSILON, CONVERGENCE_PATIENCE
from agents.coder_agent import coder_agent
from agents.loop_utils import compute_iteration_ceiling, compute_exec_timeout, run_exploration_loop
from memory.run_memory import lookup_run_memory
from tools.logger import get_logger, log_event, step_timer
from tools.streaming import invoke_structured_robust
from utils.safe import to_float, is_better, safe_diff
from utils.exceptions import MetricUnavailableError

_TMP_DIR = "artifacts/models"
os.makedirs(_TMP_DIR, exist_ok=True)
_PLATEAU_WINDOW = CONVERGENCE_PATIENCE
_RESULT_LINE_RE = re.compile(r"RESULT_JSON:\s*(\{.*\})")





class ModelStepDecision(BaseModel):
    decision: Literal["continue", "stop"]
    task_spec: Optional[str] = None
    reasoning: str


def _parse_result_line(stdout: str) -> Optional[dict]:
    for line in (stdout or "").splitlines():
        match = _RESULT_LINE_RE.search(line)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                continue
    return None


_make_llm = get_llm


def _metric_higher_is_better(metric_name: str) -> bool:
    metric_lower = (metric_name or "").lower()
    return not any(tok in metric_lower for tok in ("error", "loss", "mae", "mse", "rmse"))


def modeler_agent(state: AgentState) -> dict:
    run_id = state.get("run_id") or state.get("dataset_fingerprint", "run")
    logger = get_logger(run_id)
    llm = _make_llm()

    profile = state.get("profile", {})
    ceiling = compute_iteration_ceiling(profile)
    exec_timeout = compute_exec_timeout(profile)
    memory_query = (f"Modeling for a {state.get('task_type', 'unknown')} task, "
                    f"modalities: {profile.get('detected_modalities')}")
    prior_memory = lookup_run_memory(state["dataset_fingerprint"], memory_query, run_id=run_id,
                                     calling_agent="modeler_agent")

    dataset_path = state.get("transformed_dataset_path") or state["dataset_path"]
    task_type = state.get("task_type") or "classification"
    metric_name = profile.get("recommended_metric") or ("accuracy" if task_type == "classification" else "rmse")
    higher_is_better = _metric_higher_is_better(metric_name)

    is_retry = state.get("retry_tier") == 1
    rejected_family = None
    if is_retry and state.get("candidate_models"):
        rejected_family = state["candidate_models"][-1].get("model_family")

    tried_families = [m.get("model_family") for m in (state.get("candidate_models") or [])]
    best_metric = state.get("best_metric")
    new_candidates, new_scores = [], []
    best_snapshots = {}  # iteration -> best_metric-so-far, used by the plateau backstop

    log_event(run_id, "modeler_agent", "loop_start", ceiling=ceiling, retry_tier_1=is_retry,
              rejected_family=rejected_family, metric=metric_name, higher_is_better=higher_is_better,
              exec_timeout=exec_timeout)

    def decide_next_step(condensed_history):
        context = {
            "profile": profile,
            "target_column": state.get("target_column"),
            "task_type": state.get("task_type"),
            "recommended_metric": metric_name,
            "already_tried_this_run": condensed_history,
            "already_tried_overall": tried_families,
            "avoid_family": rejected_family,
            "similar_past_runs": prior_memory,
        }
        retry_note = ""
        if is_retry:
            retry_note = (f"\nThis is a retry (tier 1): the Judge rejected the model family "
                          f"'{rejected_family}'. Do not retry that family. "
                          f"Feedback: {state.get('judge_feedback')}")
        system_prompt = ("You are the Modeler agent. Decide the next model family to try. "
                         "Never reuse a family already listed in already_tried_overall or "
                         "already_tried_this_run. If profile.detected_modalities includes "
                         "image_path/audio_path/free_text columns, the task_spec should tell "
                         "the Coder to derive features/embeddings from those columns first "
                         "(e.g. CNN/transfer-learning embeddings for images, TF-IDF or "
                         "transformer embeddings for text, spectral features for audio) before "
                         "fitting a model — pick whatever's appropriate given what's installed, "
                         "don't assume a specific library is available without a fallback. "
                         "Instruct the Coder to use cross-validation with internal "
                         "hyperparameter search (e.g. GridSearchCV/RandomizedSearchCV) so "
                         "tuning happens inside a single iteration — this is free tier-0 "
                         "tuning and should never be surfaced as a separate retry. The Coder "
                         "script MUST print a line of the exact form RESULT_JSON: "
                         "{\"model_family\": <name>, \"cv_score\": <float>, \"metric\": <name>} "
                         "before finishing. "
                         "STOP once you have tried 3+ model families and have a model you're "
                         "confident recommending — do not explore indefinitely. "
                         "Never reuse a family; if all reasonable families are tried, stop. "
                         "If on a tier-1 retry, address only the specific judge feedback cited "
                         "and stop as soon as that issue is addressed."
                         + retry_note)
        human_prompt = f"Context:\n{json.dumps(context, default=str, indent=2)}"
        with step_timer(run_id, "modeler_agent", "decide_next_step"):
            try:
                return invoke_structured_robust(
                    llm, ModelStepDecision,
                    [SystemMessage(content=system_prompt), HumanMessage(content=human_prompt)],
                    run_id=run_id, agent="modeler_agent"
                )
            except Exception as exc:
                logger.warning("Modeler decide_next_step failed (%s); using fallback decision", exc)
                if not condensed_history:
                    return ModelStepDecision(
                        decision="continue",
                        task_spec=f"Train a baseline LogisticRegression/RandomForest {task_type} model with 5-fold cross-validation. Print RESULT_JSON with model_family, cv_score, and metric.",
                        reasoning="Initial baseline candidate model training."
                    )
                return ModelStepDecision(
                    decision="stop",
                    reasoning="Candidate models evaluated; selecting best model."
                )

    def execute_step(decision, iteration):
        nonlocal best_metric
        output_path = os.path.join(_TMP_DIR, f"{run_id}_{iteration}.joblib")
        with step_timer(run_id, "modeler_agent", f"iteration_{iteration}",
                        task_spec=decision.task_spec):
            result = coder_agent(
                task_spec=decision.task_spec,
                input_paths={"dataset": dataset_path},
                output_path=output_path,
                context={"profile": profile, "target_column": state.get("target_column"),
                        "task_type": state.get("task_type"), "metric": metric_name},
                run_id=run_id, timeout=exec_timeout,
                parent_agent="modeler_agent", parent_iteration=iteration,
            )

        parsed = _parse_result_line(result["stdout"]) if result["success"] else None
        record = {"iteration": iteration, "task_spec": decision.task_spec, **result,
                   "parsed_result": parsed}

        if not result["success"] or not parsed or "cv_score" not in parsed:
            best_snapshots[iteration] = best_metric
            condensed = f"iter {iteration}: {decision.task_spec[:80]} -> failed/no parsable score"
            return {
                "condensed": condensed, "record": record,
                "metric": None, "metric_name": metric_name, "metric_delta": 0.0,
                "is_improvement": False, "is_stall": True,
            }

        family = parsed.get("model_family", "unknown") if parsed else "unknown"
        score = to_float(parsed.get("cv_score")) if parsed else None

        if score is None:
            best_snapshots[iteration] = best_metric
            log_event(run_id, "modeler_agent", "metric_unavailable",
                      iteration=iteration, family=family,
                      reason="No parseable finite cv_score found in Coder output")
            condensed = f"iter {iteration}: {family} -> metric unavailable / execution failed"
            return {
                "condensed": condensed, "record": record,
                "metric": None, "metric_name": metric_name, "metric_delta": 0.0,
                "is_improvement": False, "is_stall": True,
            }

        tried_families.append(family)

        prev_score = new_scores[-1] if new_scores else (state.get("metric_history") or [None])[-1]
        prev_score_float = to_float(prev_score)
        if prev_score_float is not None:
            delta = safe_diff(score, prev_score_float, higher_is_better)
            is_improvement = is_better(score, prev_score_float, higher_is_better, epsilon=METRIC_IMPROVEMENT_EPSILON)
            is_stall = not is_improvement
        else:
            delta = 0.0
            is_improvement = True
            is_stall = False

        new_candidates.append({
            "model_family": family, "cv_score": score,
            "metric": parsed.get("metric", metric_name),
            "artifact_path": result["output_path"], "iteration": iteration,
        })
        new_scores.append(score)

        if is_better(score, best_metric, higher_is_better):
            best_metric = score
        best_snapshots[iteration] = best_metric

        # Emit a merged attempt_result: Coder output + CV score + tier + decision in one event.
        decision_str = "improvement" if is_improvement else "stall"
        log_event(run_id, "modeler_agent", "attempt_result",
                  attempt=result.get("attempts", 1),
                  iteration=iteration,
                  tier=state.get("retry_tier", 0),
                  model_family=family,
                  score=score,
                  metric_name=parsed.get("metric", metric_name),
                  metric_delta=delta,
                  is_improvement=is_improvement,
                  higher_is_better=higher_is_better,
                  decision=decision_str,
                  reason="improvement" if is_improvement else "no improvement above epsilon",
                  code=result.get("code", ""),
                  stdout=result.get("stdout", ""),
                  stderr=result.get("stderr", ""),
                  success=result["success"],
                  parent_agent="modeler_agent",
                  parent_iteration=iteration)

        condensed = f"iter {iteration}: {family} -> {parsed.get('metric', metric_name)}={score:.4f}"
        return {
            "condensed": condensed, "record": record,
            "metric": score, "metric_name": parsed.get("metric", metric_name),
            "metric_delta": delta, "is_improvement": is_improvement, "is_stall": is_stall,
        }

    def plateau_check(iteration):
        """Modeler's mechanical backstop: stop if `best_metric` hasn't improved beyond
        METRIC_IMPROVEMENT_EPSILON over the last _PLATEAU_WINDOW iterations."""
        if iteration < _PLATEAU_WINDOW or best_metric is None:
            return False
        window_start = iteration - _PLATEAU_WINDOW
        baseline = to_float(best_snapshots.get(window_start))
        current = to_float(best_snapshots.get(iteration))
        if baseline is None or current is None:
            return False
        improvement = (current - baseline) if higher_is_better else (baseline - current)
        return improvement < METRIC_IMPROVEMENT_EPSILON

    loop_result = run_exploration_loop(
        run_id=run_id, agent_name="modeler_agent", ceiling=ceiling,
        decide_next_step=decide_next_step, execute_step=execute_step,
        plateau_check=plateau_check,
        higher_is_better=higher_is_better,
    )

    update = {
        "candidate_models": new_candidates,   # operator.add reducer accumulates
        "metric_history": new_scores,          # operator.add reducer accumulates
        "best_metric": best_metric,            # plain overwrite; compare-and-replace already done above
        "run_memory": [f"[Modeler] {c}" for c in loop_result["condensed_history"]],
        "iteration": state.get("iteration", 0) + loop_result["iterations"],
        "last_executed_agent": "modeler",
    }

    # Both "ceiling" and "plateau" mean the LLM didn't call it converged on its own ->
    # advisory only, never blocks (best-so-far model is already recorded above).
    if loop_result["exit_reason"] != "llm_stop":
        update["requires_human_approval"] = True
        update["approval_reason"] = "unresolved_exploration"

    log_event(run_id, "modeler_agent", "loop_end", exit_reason=loop_result["exit_reason"],
              iterations=loop_result["iterations"], best_metric=best_metric,
              n_candidates=len(new_candidates))
    return update
