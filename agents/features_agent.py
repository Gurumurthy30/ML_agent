"""
Features Agent — incremental feature engineering.

Per spec: unlike EDA, each iteration builds on the PREVIOUS iteration's transformed
dataset (evolving it), not starting over from raw each time. Stop is purely the LLM's
own call — no mechanical plateau backstop (that's Modeler-only).

No hardcoded action vocabulary: every step is arbitrary pandas/sklearn code written by
the Coder sub-agent. Destructiveness is judged two ways, neither a fixed action list:
  1. the LLM self-reports `destructive_self_assessment` on its own proposed step, and
  2. we structurally diff the resulting dataframe's columns/row-count against the
     previous iteration (a column removed, or the row count changing at all).
Either signal firing, OR guided_mode being on, routes to the Human Approval hard
block. This genuinely pauses the pipeline — the actual pause/resume mechanics live in
the `human_approval` interrupt node in graph.py, not inside this function; this agent
only sets the flags and the plan to persist across that pause.
"""
import os
import json
from typing import Literal, Optional
import pandas as pd
from pydantic import BaseModel, Field
from tools.llm import get_llm
from langchain_core.messages import SystemMessage, HumanMessage

from state import AgentState
from agents.coder_agent import coder_agent
from agents.loop_utils import compute_iteration_ceiling, compute_exec_timeout, run_exploration_loop
from memory.run_memory import lookup_run_memory
from tools.logger import get_logger, log_event, step_timer

_TMP_DIR = "artifacts/features"
os.makedirs(_TMP_DIR, exist_ok=True)





def _load_df(path: str) -> pd.DataFrame:
    if path.endswith((".parquet", ".pq")):
        return pd.read_parquet(path)
    return pd.read_csv(path)


class FeatureStepDecision(BaseModel):
    decision: Literal["continue", "stop"]
    task_spec: Optional[str] = Field(
        default=None,
        description="What the next feature-engineering step should do, building on "
                    "the CURRENT transformed dataset (not the raw one).")
    reasoning: str
    destructive_self_assessment: bool = Field(
        default=False,
        description="Self-report True if this step could irreversibly lose information "
                    "(dropping rows/columns, lossy encoding, overwriting raw values).")


from tools.streaming import invoke_structured_robust


def features_agent(state: AgentState) -> dict:
    run_id = state.get("run_id") or state.get("dataset_fingerprint", "run")
    logger = get_logger(run_id)
    llm = get_llm()

    profile = state.get("profile", {})
    ceiling = compute_iteration_ceiling(profile)
    exec_timeout = compute_exec_timeout(profile)
    memory_query = (f"Feature engineering for a {state.get('task_type', 'unknown')} task, "
                    f"modalities: {profile.get('detected_modalities')}")
    prior_memory = lookup_run_memory(state["dataset_fingerprint"], memory_query, run_id=run_id,
                                     calling_agent="features_agent")

    current_path = state.get("transformed_dataset_path") or state["dataset_path"]
    is_retry = state.get("retry_tier") == 2
    log_event(run_id, "features_agent", "loop_start", ceiling=ceiling, retry_tier_2=is_retry,
              starting_dataset=current_path, exec_timeout=exec_timeout)

    # Mutated by execute_step (closure); read by the code after the loop finishes.
    hard_block_info = {"triggered": False, "reason": None, "plan": None}

    def decide_next_step(condensed_history):
        context = {
            "profile": profile,
            "eda_findings": state.get("eda_findings"),
            "eda_narrative": (state.get("eda_findings") or {}).get("narrative"),
            "target_column": state.get("target_column"),
            "task_type": state.get("task_type"),
            "steps_taken_this_run": condensed_history,
            "similar_past_runs": prior_memory,
        }
        retry_note = ""
        if is_retry:
            retry_note = (f"\nThis is a retry (tier 2): the Judge rejected the previous "
                          f"feature set. Feedback: {state.get('judge_feedback')}. "
                          f"Address that feedback rather than repeating the same approach.")
        system_prompt = ("You are the Features agent. Decide the next feature-engineering "
                         "step, building on the CURRENT transformed dataset (not raw). "
                         "Carefully review `eda_narrative` and `eda_findings` for high/low correlation "
                         "pairs, missing values, skewness, and outliers. Prioritize: "
                         "1) Handling missing values and imputation identified in EDA. "
                         "2) Resolving multicollinearity (dropping or combining highly correlated features |r| > 0.7). "
                         "3) Transforming skewed numerical distributions (log1p/Box-Cox). "
                         "4) Encoding categorical columns. "
                         "STOP as soon as the key issues identified in EDA are addressed — "
                         "do NOT keep engineering after the primary issues are resolved. "
                         "Check steps_taken_this_run carefully — do NOT repeat a transformation "
                         "that already appears there. If this is a tier-2 retry, address ONLY "
                         "the specific judge feedback cited and stop immediately after — do not "
                         "re-run all prior steps from scratch. "
                         "Self-report honestly if a step could irreversibly lose "
                         "information. Stop once the feature set is ready for modeling."
                         + retry_note)
        human_prompt = f"Context:\n{json.dumps(context, default=str, indent=2)}"
        with step_timer(run_id, "features_agent", "decide_next_step"):
            try:
                return invoke_structured_robust(
                    llm, FeatureStepDecision,
                    [SystemMessage(content=system_prompt), HumanMessage(content=human_prompt)]
                )
            except Exception as exc:
                logger.warning("Features decide_next_step failed (%s); using fallback decision", exc)
                if not condensed_history:
                    return FeatureStepDecision(
                        decision="continue",
                        task_spec="Handle missing values with imputation, encode categorical features, and scale numerical variables.",
                        reasoning="Standard baseline feature engineering transformation.",
                        destructive_self_assessment=False
                    )
                return FeatureStepDecision(
                    decision="stop",
                    reasoning="Features are transformed and ready for modeling.",
                    destructive_self_assessment=False
                )

    def execute_step(decision, iteration):
        nonlocal current_path
        output_path = os.path.join(_TMP_DIR, f"{run_id}_{iteration}.parquet")
        with step_timer(run_id, "features_agent", f"iteration_{iteration}",
                        task_spec=decision.task_spec):
            result = coder_agent(
                task_spec=decision.task_spec + " Write the resulting dataframe to "
                          "OUTPUT_PATH using pandas to_parquet, preserving all rows "
                          "that should be kept.",
                input_paths={"dataset": current_path},
                output_path=output_path,
                context={"profile": profile, "target_column": state.get("target_column")},
                run_id=run_id, timeout=exec_timeout,
                parent_agent="features_agent", parent_iteration=iteration,
            )

        diff_info = {}
        structural_destructive = False
        if result["success"]:
            try:
                before_df, after_df = _load_df(current_path), _load_df(result["output_path"])
                cols_removed = sorted(set(before_df.columns) - set(after_df.columns))
                row_delta = len(after_df) - len(before_df)
                structural_destructive = bool(cols_removed) or row_delta != 0
                diff_info = {"dropped_columns": cols_removed, "row_delta": row_delta}
            except Exception as exc:
                logger.warning("features_agent: structural diff failed: %s", exc)
                diff_info = {"error": str(exc)}

        is_destructive = decision.destructive_self_assessment or structural_destructive
        guided = bool(state.get("guided_mode"))
        needs_approval = result["success"] and (guided or is_destructive)

        record = {
            "iteration": iteration, "task_spec": decision.task_spec, **result,
            "structural_diff": diff_info,
            "destructive_self_assessment": decision.destructive_self_assessment,
        }
        stdout_preview = (result["stdout"] or "").strip().splitlines()
        headline = stdout_preview[0][:120] if stdout_preview else ("failed" if not result["success"] else "ok")
        condensed = f"iter {iteration}: {decision.task_spec[:100]} -> {headline}"

        if needs_approval:
            hard_block_info["triggered"] = True
            hard_block_info["reason"] = "guided_mode" if guided and not is_destructive else "destructive_action"
            hard_block_info["plan"] = {
                "code": result["code"],
                "description": decision.task_spec,
                "destructive_self_assessment": decision.destructive_self_assessment,
                "structural_diff": diff_info,
                "proposed_output_path": result["output_path"],
            }
            log_event(run_id, "features_agent", "hard_block",
                      reason=hard_block_info["reason"], diff=diff_info)
            return {"condensed": condensed, "record": record, "hard_block": True}

        if result["success"]:
            current_path = result["output_path"]

        return {"condensed": condensed, "record": record}

    loop_result = run_exploration_loop(
        run_id=run_id, agent_name="features_agent", ceiling=ceiling,
        decide_next_step=decide_next_step, execute_step=execute_step,
    )

    feature_set = {
        "iterations_run": loop_result["iterations"],
        "converged": loop_result["exit_reason"] == "llm_stop",
        "exit_reason": loop_result["exit_reason"],
        "steps": loop_result["condensed_history"],
    }

    update = {
        "feature_set": feature_set,
        "transformed_dataset_path": current_path,
        "run_memory": [f"[Features] {c}" for c in loop_result["condensed_history"]],
        "iteration": state.get("iteration", 0) + loop_result["iterations"],
        "last_executed_agent": "features",
    }

    # Hard block vs. advisory — two different mechanisms, do not conflate:
    if hard_block_info["triggered"]:
        update["requires_human_approval"] = True
        update["approval_reason"] = hard_block_info["reason"]
        update["feature_plan"] = hard_block_info["plan"]
    elif loop_result["exit_reason"] != "llm_stop":
        # Ceiling reached without the LLM's own stop -> advisory only, never blocks;
        # best-so-far (current_path) is still written into state above.
        update["requires_human_approval"] = True
        update["approval_reason"] = "unresolved_exploration"

    log_event(run_id, "features_agent", "loop_end",
              **{k: v for k, v in feature_set.items() if k != "steps"})
    return update
