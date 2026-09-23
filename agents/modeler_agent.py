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
    auto-stop if the best metric hasn't improved over the last config.CONVERGENCE_PATIENCE
    iterations (defaults to 3), even if the LLM would keep going. This is intentionally NOT
    given to EDA/Features.
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
from utils.scoped_memory import format_modeler_scorecard
from tools.logger import get_logger, log_event, step_timer
from tools.streaming import invoke_structured_robust
from utils.safe import to_float, is_better, safe_diff
from utils.exceptions import MetricUnavailableError
from utils.run_context import format_run_context

_TMP_DIR = "artifacts/models"
os.makedirs(_TMP_DIR, exist_ok=True)
_PLATEAU_WINDOW = CONVERGENCE_PATIENCE
_RESULT_LINE_RE = re.compile(r"RESULT_JSON:\s*(\{.*\})")





class ModelStepDecision(BaseModel):
    decision: Literal["continue", "stop"]
    task_spec: Optional[str] = None
    reasoning: str


import ast


def _parse_result_line(stdout: str) -> Optional[dict]:
    lines = (stdout or "").splitlines()
    # 1. Search for RESULT_JSON: pattern
    for line in lines:
        match = _RESULT_LINE_RE.search(line)
        if match:
            text = match.group(1).strip()
            try:
                data = json.loads(text)
                if isinstance(data, dict):
                    return data
            except Exception:
                pass
            try:
                data = ast.literal_eval(text)
                if isinstance(data, dict):
                    return data
            except Exception:
                pass

    # 2. Search for any JSON / dict line containing cv_score or model_family
    for line in lines:
        line_s = line.strip()
        if (line_s.startswith("{") and line_s.endswith("}")) and ("cv_score" in line_s or "model_family" in line_s or "score" in line_s):
            try:
                data = json.loads(line_s)
                if isinstance(data, dict):
                    return data
            except Exception:
                pass
            try:
                data = ast.literal_eval(line_s)
                if isinstance(data, dict):
                    return data
            except Exception:
                pass

    # 3. Fallback regex search for cv_score or common metric patterns in stdout
    score_match = re.search(r"(?:cv_score|validation_score|score|accuracy|f1|rmse|auc)\s*[:=]\s*([0-9\.]+)", stdout or "", re.IGNORECASE)
    if score_match:
        try:
            val = float(score_match.group(1))
            return {"model_family": "CandidateModel", "cv_score": val, "metric": "score"}
        except Exception:
            pass

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

    dataset_path = state.get("transformed_dataset_path") or state["dataset_path"]
    task_type = state.get("task_type") or "classification"
    metric_name = profile.get("recommended_metric") or ("accuracy" if task_type == "classification" else "rmse")
    higher_is_better = _metric_higher_is_better(metric_name)

    is_retry = state.get("retry_tier") == 1
    rejected_family = None
    if is_retry:
        rejected_family = state.get("rejected_family")
        if not rejected_family and state.get("candidate_models"):
            rejected_family = state["candidate_models"][-1].get("model_family")

    judge_fb = state.get("judge_feedback")
    latest_judge_feedback = (
        judge_fb[-1] if isinstance(judge_fb, list) and judge_fb else str(judge_fb or "")
    ).strip()

    tried_families = [m.get("model_family") for m in (state.get("candidate_models") or [])]
    best_metric = state.get("best_metric")
    new_candidates, new_scores = [], []
    private_trials = []
    coder_records = []
    best_snapshots = {}  # iteration -> best_metric-so-far, used by the plateau backstop
    consecutive_failures = 0  # tracks iterations with no valid score (for no_viable_attempts exit)

    scorecard_text = format_modeler_scorecard(state.get("private_memories"), current_best=best_metric)

    log_event(run_id, "modeler_agent", "loop_start", ceiling=ceiling, retry_tier_1=is_retry,
              rejected_family=rejected_family, metric=metric_name, higher_is_better=higher_is_better,
              exec_timeout=exec_timeout)

    retry_note = ""
    if is_retry:
        retry_note = (
            f"\n\n<retry_context>\n"
            f"This is a RETRY (tier 1). The Judge rejected the model family '{rejected_family}'.\n"
            f"Do not retry that family.\n"
            f"Judge feedback: {latest_judge_feedback}\n"
            f"Address ONLY this feedback and stop as soon as it's addressed — do not "
            f"re-explore other families from scratch.\n"
            f"</retry_context>"
        )
        log_event(run_id, "modeler_agent", "retry_context",
                  rejected_family=rejected_family,
                  feedback=latest_judge_feedback,
                  retry_note=retry_note.strip())

    def decide_next_step(condensed_history):
        context = {
            "profile": profile,
            "target_column": state.get("target_column"),
            "task_type": state.get("task_type"),
            "recommended_metric": metric_name,
            "already_tried_this_run": condensed_history,
            "already_tried_overall": tried_families,
            "avoid_family": rejected_family,
            "private_scorecard_and_blunders": scorecard_text,
        }

        run_context_block = format_run_context(
            state.get("target_column"),
            state.get("exclude_columns"),
            state.get("feature_columns"),
        )

        system_prompt = (
            run_context_block + "\n\n"
            + "You are the Modeler agent for a tabular-data ML pipeline. Decide the next model "
            "family to try, given the current feature set.\n\n"

            "<already_tried>\n"
            "Never propose a family listed in `already_tried_overall` (tried in any prior run) "
            "or `already_tried_this_run` (tried already in this run) — check both before deciding.\n"
            "</already_tried>\n\n"

            "<model_family_menu>\n"
            "Choose a family appropriate to the data size, dimensionality, and problem type "
            "(regression/classification), e.g.: linear/logistic regression (with L1/L2), tree "
            "ensembles (Random Forest, Gradient Boosting, XGBoost/LightGBM/CatBoost), SVM, k-NN, "
            "or a simple MLP for larger tabular sets. Prefer libraries actually installed in the "
            "environment; if a preferred library (e.g. XGBoost/LightGBM) is unavailable, fall "
            "back to the closest scikit-learn equivalent rather than failing the step.\n"
            "</model_family_menu>\n\n"

            "<tuning_instructions>\n"
            "Instruct the Coder to use cross-validation with internal hyperparameter search "
            "(GridSearchCV/RandomizedSearchCV or equivalent) so tuning happens inside this single "
            "iteration. This is free tier-0 tuning and must never be surfaced as a separate retry.\n"
            "</tuning_instructions>\n\n"

            "<output_contract>\n"
            "The Coder script MUST print a line of the exact form, before finishing:\n"
            "RESULT_JSON: {\"model_family\": <name>, \"cv_score\": <float>, \"metric\": <name>}\n"
            "</output_contract>\n\n"

            "<blunder_prevention priority=\"critical\">\n"
            "Review the private scorecard and recorded mistakes provided above, if any. Do not "
            "repeat failed hyperparameter choices, crashing configurations, or other blunders "
            "from prior trials.\n"
            "</blunder_prevention>\n\n"

            "<stopping_rule>\n"
            "1. Stop IMMEDIATELY if cv_score reaches 1.0 (or within 0.0001 of 1.0) — a perfect score cannot be improved upon.\n"
            "2. Stop once you have tried 2-3 model families and have one you're confident recommending, or once every reasonable family for this data has been exhausted — whichever comes first.\n"
            "3. Do not explore indefinitely, and never reuse a family.\n"
            "</stopping_rule>"
            + retry_note
        )
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

    def _normalize_family(spec: str) -> str:
        s = (spec or "").lower()
        if "xgboost" in s or "xgb" in s: return "xgboost"
        if "lightgbm" in s or "lgb" in s: return "lightgbm"
        if "catboost" in s: return "catboost"
        if "random forest" in s or "randomforest" in s: return "randomforest"
        if "extra trees" in s or "extratrees" in s: return "extratrees"
        if "gradient boost" in s or "gradientboosting" in s: return "gradientboosting"
        if "logistic" in s: return "logisticregression"
        if "ridge" in s: return "ridge"
        if "elasticnet" in s: return "elasticnet"
        if "svm" in s or "svc" in s or "svr" in s: return "svm"
        if "knn" in s or "neighbors" in s: return "kneighbors"
        if "neural" in s or "mlp" in s: return "mlp"
        return "custom"

    def execute_step(decision, iteration):
        nonlocal best_metric, consecutive_failures
        output_path = os.path.join(_TMP_DIR, f"{run_id}_{iteration}.joblib")

        # Repetition Guard: detect if the proposed family was already attempted
        target_col = state.get("target_column")
        proposed_fam = _normalize_family(decision.task_spec or "")
        normalized_tried = [_normalize_family(f) for f in tried_families]
        enhanced_spec = decision.task_spec or f"Train a {task_type} model"
        if proposed_fam in normalized_tried and proposed_fam != "custom":
            fallback_families = ["gradientboosting", "randomforest", "lightgbm", "logisticregression", "extratrees"]
            untried = [f for f in fallback_families if f not in normalized_tried]
            if untried:
                alt_fam = untried[0]
                enhanced_spec = f"Train an alternative {alt_fam} {task_type} model (since {proposed_fam} was already evaluated). Use 5-fold cross-validation."
                logger.info("Modeler repetition guard: redirected from %s to %s", proposed_fam, alt_fam)

        target_col = state.get("target_column")
        exclude_cols = state.get("exclude_columns") or []
        is_parquet = dataset_path.lower().endswith(".parquet")
        loader_snippet = (
            "pd.read_parquet(os.environ['INPUT_DATASET'])"
            if is_parquet
            else "pd.read_csv(os.environ['INPUT_DATASET']) (with fallback to encoding='latin1' or on_bad_lines='skip' if needed)"
        )
        data_instruction = (
            f"Ensure robust data handling: load dataset from INPUT_DATASET using {loader_snippet}. "
            f"Drop target '{target_col}' and exclude columns {exclude_cols} before building X: X = df.drop(columns=[c for c in ['{target_col}'] + {exclude_cols} if c in df.columns]). "
            f"Set y = df['{target_col}']. "
            f"If classification and target is string/categorical, encode with LabelEncoder. "
            f"Impute missing numeric values using SimpleImputer(strategy='median'). "
            f"Evaluate using 5-fold cross-validation with metric '{metric_name}'. "
            f"Fit the final model on the full feature set and save it using: "
            f"import joblib; os.makedirs(os.path.dirname(os.path.abspath(os.environ['OUTPUT_PATH'])), exist_ok=True); joblib.dump(model, os.environ['OUTPUT_PATH']). "
            f"ALWAYS print a final line: import json; print('RESULT_JSON: ' + json.dumps({{'model_family': '<FamilyName>', 'cv_score': float(score), 'metric': '{metric_name}'}}))\n\n"
        )
        final_task_spec = f"{data_instruction}Task: {enhanced_spec}"

        with step_timer(run_id, "modeler_agent", f"iteration_{iteration}",
                        task_spec=final_task_spec):
            result = coder_agent(
                task_spec=final_task_spec,
                input_paths={"dataset": dataset_path},
                output_path=output_path,
                context={
                    "profile": profile,
                    "target_column": state.get("target_column"),
                    "exclude_columns": state.get("exclude_columns"),
                    "feature_columns": state.get("feature_columns"),
                    "task_type": state.get("task_type"),
                    "metric": metric_name,
                    "data_instruction": data_instruction,
                },
                run_id=run_id, timeout=exec_timeout,
                parent_agent="modeler_agent", parent_iteration=iteration,
                private_memory=state.get("private_memories"),
            )
        if result.get("private_memory_entry"):
            coder_records.append(result["private_memory_entry"])

        parsed = _parse_result_line(result["stdout"]) if result["success"] else None
        record = {"iteration": iteration, "task_spec": final_task_spec, **result,
                   "parsed_result": parsed}

        task_label = (decision.task_spec[:80] if decision.task_spec else enhanced_spec[:80])
        fam_label = (decision.task_spec[:40] if decision.task_spec else (proposed_fam or "unknown"))

        if not result["success"] or not parsed or "cv_score" not in parsed:
            consecutive_failures += 1
            best_snapshots[iteration] = best_metric
            err_msg = result.get("stderr") or result.get("error") or "Script failed or returned no RESULT_JSON line"
            failure_reason = "execution_error" if not result["success"] else "no_result_json"
            private_trials.append({
                "model_family": fam_label,
                "metric_name": metric_name,
                "score": None,
                "metric_delta": None,
                "status": "failed",
                "blunder_note": f"Execution crashed: {err_msg[:120]}",
                "iteration": iteration,
            })
            condensed = f"iter {iteration}: {task_label} -> failed/no parsable score"
            # Emit attempt_result even on failure so the UI shows every attempt
            log_event(run_id, "modeler_agent", "attempt_result",
                      attempt=result.get("attempts", 1),
                      iteration=iteration,
                      tier=state.get("retry_tier", 0),
                      model_family=fam_label,
                      score=None,
                      metric_name=metric_name,
                      metric_delta=None,
                      is_improvement=False,
                      higher_is_better=higher_is_better,
                      decision="failed",
                      reason=failure_reason,
                      failure_reason=failure_reason,
                      code=result.get("code", ""),
                      stdout=result.get("stdout", ""),
                      stderr=result.get("stderr", ""),
                      success=False,
                      parent_agent="modeler_agent",
                      parent_iteration=iteration)

            should_exit = consecutive_failures >= CONVERGENCE_PATIENCE
            if should_exit:
                log_event(run_id, "modeler_agent", "no_viable_attempts_exit",
                          consecutive_failures=consecutive_failures, iteration=iteration)
            return {
                "condensed": condensed, "record": record,
                "metric": None, "metric_name": metric_name, "metric_delta": 0.0,
                "is_improvement": False, "is_stall": True,
                "should_exit": should_exit,
                "exit_reason": "no_viable_attempts" if should_exit else None,
            }

        family = parsed.get("model_family", "unknown") if parsed else "unknown"
        score = to_float(parsed.get("cv_score")) if parsed else None

        if score is None:
            consecutive_failures += 1
            best_snapshots[iteration] = best_metric
            log_event(run_id, "modeler_agent", "metric_unavailable",
                      iteration=iteration, family=family,
                      reason="No parseable finite cv_score found in Coder output")
            private_trials.append({
                "model_family": family,
                "metric_name": metric_name,
                "score": None,
                "metric_delta": None,
                "status": "failed",
                "blunder_note": "Metric returned was NaN or non-finite",
                "iteration": iteration,
            })
            condensed = f"iter {iteration}: {family} -> metric unavailable / execution failed"
            should_exit = consecutive_failures >= CONVERGENCE_PATIENCE
            if should_exit:
                log_event(run_id, "modeler_agent", "no_viable_attempts_exit",
                          consecutive_failures=consecutive_failures, iteration=iteration)
            return {
                "condensed": condensed, "record": record,
                "metric": None, "metric_name": metric_name, "metric_delta": 0.0,
                "is_improvement": False, "is_stall": True,
                "should_exit": should_exit,
                "exit_reason": "no_viable_attempts" if should_exit else None,
            }

        consecutive_failures = 0  # Reset on any valid finite score
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

        blunder_note = None
        if prev_score_float is not None and not is_improvement:
            blunder_note = f"Score degraded or stalled ({delta:+.4f} vs prior {prev_score_float:.4f}). Avoid this architecture or parameter configuration."

        private_trials.append({
            "model_family": family,
            "metric_name": parsed.get("metric", metric_name),
            "score": score,
            "metric_delta": delta,
            "status": "success" if is_improvement else "stalled",
            "blunder_note": blunder_note,
            "iteration": iteration,
        })

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

        # Check if score reached 1.0 (or within 1e-4 of 1.0) on bounded metrics
        is_perfect = (
            higher_is_better and score is not None and score >= 0.9999
            and any(m in metric_name.lower() for m in ["acc", "f1", "auc", "roc", "precision", "recall", "score", "r2"])
        )
        if is_perfect:
            logger.info("Modeler achieved perfect score (%.4f). Stopping exploration loop early (converged).", score)
            condensed = f"iter {iteration}: {family} -> {parsed.get('metric', metric_name)}={score:.4f} (CONVERGED: PERFECT SCORE)"
            return {
                "condensed": condensed, "record": record,
                "metric": score, "metric_name": parsed.get("metric", metric_name),
                "metric_delta": delta, "is_improvement": is_improvement, "is_stall": False,
                "should_exit": True, "exit_reason": "converged",
            }

        condensed = f"iter {iteration}: {family} -> {parsed.get('metric', metric_name)}={score:.4f}"
        return {
            "condensed": condensed, "record": record,
            "metric": score, "metric_name": parsed.get('metric', metric_name),
            "metric_delta": delta, "is_improvement": is_improvement, "is_stall": is_stall,
        }

    def plateau_check(iteration):
        """Modeler's mechanical backstop: stop if `best_metric` hasn't improved beyond
        METRIC_IMPROVEMENT_EPSILON over the last _PLATEAU_WINDOW iterations."""
        if higher_is_better and best_metric is not None and best_metric >= 0.9999:
            return True
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
        "private_memories": {
            "modeler": private_trials,
            "coder": coder_records,
        },
        "open_summary_memory": {
            "modeler": (
                f"Trained {len(new_candidates)} candidate models across families {list({c.get('model_family', 'unknown') for c in new_candidates})}. Best {metric_name}: {best_metric if best_metric is not None else 'N/A'}. Exit: {loop_result['exit_reason']}."
                if new_candidates
                else f"Attempted {len(private_trials)} model iterations. No viable candidate models produced. Exit: {loop_result['exit_reason']}."
            )
        },
        "run_memory": [f"[Modeler] {c}" for c in loop_result["condensed_history"]],
        "iteration": state.get("iteration", 0) + loop_result["iterations"],
        "last_executed_agent": "modeler",
    }

    # Both "ceiling" and "plateau" mean the LLM didn't call it converged on its own ->
    # advisory only, never blocks (best-so-far model is already recorded above).
    if loop_result["exit_reason"] not in ("llm_stop", "converged", "user_stopped"):
        update["requires_human_approval"] = True
        update["approval_reason"] = "unresolved_exploration"

    log_event(run_id, "modeler_agent", "loop_end", exit_reason=loop_result["exit_reason"],
              iterations=loop_result["iterations"], best_metric=best_metric,
              n_candidates=len(new_candidates))
    return update
