"""
EDA Agent — independent explorations of the raw dataset.

Per spec: EDA's iterations are independent looks at the same raw data (try
correlation, then try a different angle) — it does NOT need to build on the previous
iteration's output the way Features does. Stop is purely the LLM's own "I'm satisfied"
call; there is no mechanical backstop (that's Modeler-only). No hardcoded set of
analyses — the Coder sub-agent is told the data characteristics via context and
decides what code to write for each analysis.
"""
import os
import uuid
import json
from typing import Literal, Optional
from pydantic import BaseModel, Field
from tools.llm import get_llm
from langchain_core.messages import SystemMessage, HumanMessage

from state import AgentState
from agents.coder_agent import coder_agent
from agents.loop_utils import compute_iteration_ceiling, compute_exec_timeout, run_exploration_loop
from memory.run_memory import lookup_run_memory
from tools.logger import get_logger, log_event, step_timer
from tools.streaming import stream_text

_TMP_DIR = "artifacts/eda"
os.makedirs(_TMP_DIR, exist_ok=True)





class EdaStepDecision(BaseModel):
    decision: Literal["continue", "stop"] = Field(
        description="'continue' to run another independent exploration, 'stop' once "
                    "you have enough understanding of the data to hand off to Features.")
    task_spec: Optional[str] = Field(
        default=None,
        description="Natural-language description of the next analysis to run "
                    "(e.g. 'compute pairwise correlations between numeric features and "
                    "the target'). Required when decision == 'continue'.")
    reasoning: str = Field(description="Short justification for this decision.")


from tools.streaming import stream_text, invoke_structured_robust

_make_llm = get_llm


def eda_agent(state: AgentState) -> dict:
    run_id = state.get("run_id") or state.get("dataset_fingerprint", "run")
    logger = get_logger(run_id)
    llm = _make_llm()

    profile = state.get("profile", {})
    ceiling = compute_iteration_ceiling(profile)
    exec_timeout = compute_exec_timeout(profile)
    log_event(run_id, "eda_agent", "loop_start", ceiling=ceiling, exec_timeout=exec_timeout)

    memory_query = (f"EDA for a {state.get('task_type', 'unknown')} task, "
                    f"modalities: {profile.get('detected_modalities')}, "
                    f"metric: {profile.get('recommended_metric')}")
    prior_memory = lookup_run_memory(state["dataset_fingerprint"], memory_query, run_id=run_id,
                                     calling_agent="eda_agent")

    def decide_next_step(condensed_history):
        context = {
            "profile": profile,
            "target_column": state.get("target_column"),
            "task_type": state.get("task_type"),
            "prior_analyses_this_run": condensed_history,
            "similar_past_runs": prior_memory,
        }
        system_prompt = """You are the EDA agent in a multi-agent ML pipeline. You decide
what exploratory analysis to run next on the raw dataset. Each analysis is independent —
you don't need to build on the previous one, just avoid repeating an analysis already
listed in `prior_analyses_this_run`. Stop once you understand the data well enough
(distributions, relationships to target, data quality issues) to hand off to feature
engineering. Never invent findings yourself — only decide what code should compute.

CRITICAL RULES:
0. Only do nessasery things don't do unwanted test or things.
1. NO VISUAL PLOTS OR FIGURES: Do NOT propose scripts that plot charts, graphs, or use matplotlib/seaborn to render figures. The downstream LLM agents are text-only models and CANNOT see visual plots. Plotting wastes runtime and produces zero consumable signal.
2. STATISTICAL & NUMERICAL SUMMARIES ONLY: Instead of plots, write task specifications that compute explicit numerical values and print structured tables to stdout:
   - Pairwise correlations: find all feature pairs with high correlation (|r| >= 0.70) as candidates for deduplication, low correlation features, and correlation of every feature with the target column.
   - Missing values: exact null count and percentage for every column.
   - Distributions & Outliers: calculate skewness, kurtosis, IQR-based outlier counts, and 5-number summaries.
   - Categoricals: cardinality, distinct counts, frequency of rare categories (<1%).
   - Informative Feature Importance: mutual information scores or ANOVA F-statistics with the target.
3. OUTPUT: Instruct code to print clear, concise summary tables to stdout and write JSON metrics to OUTPUT_PATH so the Feature Engineer agent has rich column-level data."""
        human_prompt = f"Context:\n{json.dumps(context, default=str, indent=2)}"
        with step_timer(run_id, "eda_agent", "decide_next_step"):
            try:
                return invoke_structured_robust(
                    llm, EdaStepDecision,
                    [SystemMessage(content=system_prompt), HumanMessage(content=human_prompt)],
                    run_id=run_id, agent="eda_agent"
                )
            except Exception as exc:
                logger.warning("EDA decide_next_step failed (%s); using fallback decision", exc)
                if not condensed_history:
                    return EdaStepDecision(
                        decision="continue",
                        task_spec="Compute full column correlation matrix identifying high correlation pairs (|r| > 0.7), missing value counts, skewness, and correlation with the target column.",
                        reasoning="Initial exploratory analysis of dataset structure, correlations, and distributions."
                    )
                return EdaStepDecision(
                    decision="stop",
                    reasoning="Sufficient exploration completed; handing off to feature engineering."
                )

    def execute_step(decision, iteration):
        output_path = os.path.join(_TMP_DIR, f"{run_id}_{iteration}_{uuid.uuid4().hex[:8]}.json")
        with step_timer(run_id, "eda_agent", f"iteration_{iteration}", task_spec=decision.task_spec):
            result = coder_agent(
                task_spec=decision.task_spec,
                input_paths={"dataset": state["dataset_path"]},
                output_path=output_path,
                context={"profile": profile, "target_column": state.get("target_column")},
                run_id=run_id, timeout=exec_timeout,
                parent_agent="eda_agent", parent_iteration=iteration,
            )
        stdout_preview = (result["stdout"] or "").strip().splitlines()
        headline = stdout_preview[0][:160] if stdout_preview else ("failed" if not result["success"] else "no output")
        condensed = f"iter {iteration}: {decision.task_spec[:100]} -> {headline}"
        record = {"iteration": iteration, "task_spec": decision.task_spec, **result}
        return {"condensed": condensed, "record": record}

    loop_result = run_exploration_loop(
        run_id=run_id, agent_name="eda_agent", ceiling=ceiling,
        decide_next_step=decide_next_step, execute_step=execute_step,
    )

    # Short narrative synthesis for downstream agents (Features/Reporter), streamed live.
    synth_llm = _make_llm()
    synth_system = ("You are an expert ML statistician synthesizing exploratory data analysis (EDA) results "
                    "for the downstream Feature Engineer agent.\n"
                    "CRITICAL: Do NOT mention charts, plots, or visual figures.\n"
                    "Provide a concise, highly specific, column-by-column briefing covering:\n"
                    "1. Multicollinearity: specific pairs with high correlation (|r| > 0.7) and recommendations to drop or combine.\n"
                    "2. Missing Values: columns with missing values and recommended imputation strategies (median/mean/mode/flag).\n"
                    "3. Outliers & Skew: columns with high skewness (>1.0) requiring log1p/Box-Cox or outlier clipping.\n"
                    "4. Categorical Encodings: high vs. low cardinality columns, recommending one-hot, target, or frequency encoding.\n"
                    "5. Target Predictors: top 3-5 columns strongest associated with the target.\n"
                    "Be concrete and actionable with exact column names and values.")
    synth_human = json.dumps(loop_result["full_history"], default=str, indent=2)[:12000]
    with step_timer(run_id, "eda_agent", "synthesize_narrative"):
        narrative = stream_text(
            synth_llm, [SystemMessage(content=synth_system), HumanMessage(content=synth_human)],
            run_id=run_id, agent="eda_agent(synthesis)",
        )

    eda_findings = {
        "iterations_run": loop_result["iterations"],
        "converged": loop_result["exit_reason"] == "llm_stop",
        "exit_reason": loop_result["exit_reason"],
        "analyses": loop_result["condensed_history"],
        "narrative": narrative,
    }

    update = {
        "eda_findings": eda_findings,
        "run_memory": [f"[EDA] {c}" for c in loop_result["condensed_history"]],
        "iteration": state.get("iteration", 0) + loop_result["iterations"],
    }
    if loop_result["exit_reason"] != "llm_stop":
        update["requires_human_approval"] = True
        update["approval_reason"] = "unresolved_exploration"

    log_event(run_id, "eda_agent", "loop_end",
              **{k: v for k, v in eda_findings.items() if k != "narrative"})
    return update
