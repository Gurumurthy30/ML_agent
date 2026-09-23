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


_make_llm = get_llm


def features_agent(state: AgentState) -> dict:
    run_id = state.get("run_id") or state.get("dataset_fingerprint", "run")
    logger = get_logger(run_id)
    llm = _make_llm()

    profile = state.get("profile", {})
    ceiling = compute_iteration_ceiling(profile)
    exec_timeout = compute_exec_timeout(profile)
    private_features = (state.get("private_memories") or {}).get("features", [])
    coder_records = []

    current_path = state.get("transformed_dataset_path") or state["dataset_path"]
    is_retry = state.get("retry_tier") == 2
    log_event(run_id, "features_agent", "loop_start", ceiling=ceiling, retry_tier_2=is_retry,
              starting_dataset=current_path, exec_timeout=exec_timeout)

    # Mutated by execute_step (closure); read by the code after the loop finishes.
    hard_block_info = {"triggered": False, "reason": None, "plan": None}

    modifications = state.get("modifications") or (state.get("feature_plan") or {}).get("modifications")
    if modifications:
        log_event(run_id, "features_agent", "operator_modification_acknowledged",
                  modifications=modifications)

    def decide_next_step(condensed_history):
        context = {
            "profile": profile,
            "eda_findings": state.get("eda_findings"),
            "eda_narrative": (state.get("eda_findings") or {}).get("narrative"),
            "target_column": state.get("target_column"),
            "task_type": state.get("task_type"),
            "steps_taken_this_run": condensed_history,
            "private_features_history": private_features,
        }
        modifications = state.get("modifications") or (state.get("feature_plan") or {}).get("modifications")
        if modifications:
            context["human_modifications"] = modifications

        judge_fb = state.get("judge_feedback")
        latest_judge_feedback = (
            judge_fb[-1] if isinstance(judge_fb, list) and judge_fb else str(judge_fb or "")
        ).strip()

        retry_note = ""
        if is_retry:
            retry_note = (
                f"\n\n<retry_context>\n"
                f"This is a RETRY (tier 2). The Judge rejected the previous feature set.\n"
                f"Judge feedback: {latest_judge_feedback}\n"
                f"Address ONLY this feedback. Do not re-run or repeat prior steps from scratch.\n"
                f"</retry_context>"
            )

        modify_note = ""
        if modifications:
            modify_note = (
                f"\n\n<operator_instructions priority=\"overrides_default_order\">\n"
                f"Human operator reviewed the previous feature proposal and requested modifications:\n"
                f"\"{modifications}\"\n"
                f"Follow these instructions exactly in your next step. They take precedence "
                f"over the default priority order below if the two conflict.\n"
                f"</operator_instructions>"
            )

        target_col = state.get("target_column")
        target_rule = ""
        if target_col:
            target_rule = (
                f"\n\n<invariants>\n"
                f"- Never drop, rename, or alter the dtype/cardinality of the target column '{target_col}'.\n"
                f"- Every transformation applies to predictor columns only; '{target_col}' passes "
                f"through unchanged in the output dataframe.\n"
                f"- Never use '{target_col}' to derive or encode another feature (target leakage) "
                f"outside of a leakage-safe scheme (e.g. out-of-fold target encoding).\n"
                f"</invariants>"
            )

        system_prompt = (
            "You are the Features agent for a tabular-data ML pipeline. Decide the SINGLE next "
            "feature-engineering step, building on the CURRENT transformed dataset (not the raw one).\n\n"

            "<inputs_to_review>\n"
            "Review `eda_narrative` and `eda_findings` for: missing values, high/low correlation "
            "pairs, skewed distributions, outliers, and high-cardinality or mixed-type categoricals.\n"
            "</inputs_to_review>\n\n"

            "<priority_order>\n"
            "1. Missing values — apply the imputation strategy EDA identified (mean/median for "
            "numeric, mode/constant for categorical; use a 'missing' indicator flag if missingness "
            "itself looks informative).\n"
            "2. Multicollinearity — for numeric pairs with |r| > 0.7, drop or combine, keeping the "
            "one with stronger target relationship or fewer missing values.\n"
            "3. Skewed numeric distributions — log1p for strictly positive skewed columns; "
            "Yeo-Johnson (not Box-Cox) if the column contains zero or negative values.\n"
            "4. Categorical encoding — choose by cardinality: one-hot for low cardinality "
            "(roughly <10 categories), frequency or ordinal encoding for higher cardinality. "
            "If target encoding is used, it MUST be computed in a leakage-safe way "
            "(e.g. out-of-fold / cross-fitted), never fit on the full dataset at once.\n"
            "</priority_order>\n\n"

            "<stopping_rule>\n"
            "Stop as soon as the key issues identified in EDA are addressed — do not keep "
            "engineering once the primary issues are resolved. Check `steps_taken_this_run` and "
            "never repeat a transformation that already appears there.\n"
            "</stopping_rule>\n\n"

            "<honesty>\n"
            "Flag explicitly, before proposing it, any step that could irreversibly lose "
            "information — e.g. dropping a column, coarse binning, aggressive outlier clipping — "
            "and explain the tradeoff.\n"
            "</honesty>"
            + target_rule
            + retry_note
            + modify_note
        )
        human_prompt = f"Context:\n{json.dumps(context, default=str, indent=2)}"
        with step_timer(run_id, "features_agent", "decide_next_step"):
            try:
                return invoke_structured_robust(
                    llm, FeatureStepDecision,
                    [SystemMessage(content=system_prompt), HumanMessage(content=human_prompt)],
                    run_id=run_id, agent="features_agent"
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
        spec_text = decision.task_spec or "Transform and engineer features."
        is_cur_parquet = current_path.lower().endswith(".parquet")
        loader_hint = "using pd.read_parquet" if is_cur_parquet else "using pd.read_csv"
        coder_spec = (
            f"{spec_text} (Load input dataset from INPUT_DATASET {loader_hint}. "
            "Write the resulting transformed dataframe to OUTPUT_PATH using pandas to_parquet, "
            "preserving all rows that should be kept.)"
        )
        with step_timer(run_id, "features_agent", f"iteration_{iteration}",
                        task_spec=spec_text):
            result = coder_agent(
                task_spec=coder_spec,
                input_paths={"dataset": current_path},
                output_path=output_path,
                context={"profile": profile, "target_column": state.get("target_column")},
                run_id=run_id, timeout=exec_timeout,
                parent_agent="features_agent", parent_iteration=iteration,
                private_memory=state.get("private_memories"),
            )
        if result.get("private_memory_entry"):
            coder_records.append(result["private_memory_entry"])

        diff_info = {}
        structural_destructive = False
        target_col = state.get("target_column")
        if result["success"]:
            try:
                before_df, after_df = _load_df(current_path), _load_df(result["output_path"])
                # Hard invariant: target_column must not be missing
                if target_col and target_col not in after_df.columns:
                    logger.warning("features_agent: step dropped target_column '%s'! Reverting step.", target_col)
                    log_event(run_id, "features_agent", "target_column_dropped",
                              target_column=target_col, iteration=iteration)
                    result["success"] = False
                    result["stderr"] = (result.get("stderr") or "") + f"\nError: target_column '{target_col}' was removed from the dataset."
                else:
                    cols_removed = sorted(set(before_df.columns) - set(after_df.columns))
                    row_delta = len(after_df) - len(before_df)
                    structural_destructive = bool(cols_removed) or row_delta != 0
                    diff_info = {
                        "dropped_columns": cols_removed,
                        "row_delta": row_delta,
                        "row_count_delta": row_delta,
                    }
            except Exception as exc:
                logger.warning("features_agent: structural diff failed: %s", exc)
                diff_info = {"error": str(exc)}

        is_destructive = decision.destructive_self_assessment or structural_destructive
        guided = bool(state.get("guided_mode"))
        needs_approval = result["success"] and (guided or is_destructive)

        record = {
            "iteration": iteration, "task_spec": spec_text, **result,
            "structural_diff": diff_info,
            "destructive_self_assessment": decision.destructive_self_assessment,
        }
        stdout_preview = (result["stdout"] or "").strip().splitlines()
        headline = stdout_preview[0][:120] if stdout_preview else ("failed" if not result["success"] else "ok")
        condensed = f"iter {iteration}: {spec_text[:100]} -> {headline}"

        if needs_approval:
            hard_block_info["triggered"] = True
            hard_block_info["reason"] = "guided_mode" if (guided and not is_destructive) else "destructive_action"
            hard_block_info["plan"] = {
                "code": result["code"],
                "description": spec_text,
                "destructive_self_assessment": decision.destructive_self_assessment,
                "structural_diff": diff_info,
                "proposed_output_path": result["output_path"],
                "modifications": modifications,
            }
            log_event(run_id, "features_agent", "hard_block",
                      reason=hard_block_info["reason"], diff=diff_info,
                      plan=hard_block_info["plan"], feature_plan=hard_block_info["plan"])
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
        "operator_acknowledged": bool(modifications),
        "modifications": modifications,
    }

    update = {
        "feature_set": feature_set,
        "transformed_dataset_path": current_path,
        "private_memories": {
            "features": [{
                "steps": loop_result["condensed_history"],
                "exit_reason": loop_result["exit_reason"],
                "iterations": loop_result["iterations"],
                "output_path": current_path,
            }],
            "coder": coder_records,
        },
        "open_summary_memory": {
            "features": f"Completed {loop_result['iterations']} feature engineering steps ({loop_result['exit_reason']}). Transformed dataset: {os.path.basename(current_path)}."
        },
        "run_memory": [f"[Features] {c}" for c in loop_result["condensed_history"]],
        "iteration": state.get("iteration", 0) + loop_result["iterations"],
        "last_executed_agent": "features",
        "modifications": None,
    }

    # Hard block vs. advisory — destructive action always blocks; guided mode also blocks on unresolved exploration:
    if hard_block_info["triggered"]:
        update["requires_human_approval"] = True
        update["approval_reason"] = hard_block_info["reason"]
        update["feature_plan"] = hard_block_info["plan"]
    elif bool(state.get("guided_mode")) and loop_result["exit_reason"] != "llm_stop":
        update["requires_human_approval"] = True
        update["approval_reason"] = "unresolved_exploration"


    log_event(run_id, "features_agent", "loop_end",
              **{k: v for k, v in feature_set.items() if k != "steps"})
    return update
