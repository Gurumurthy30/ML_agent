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

    private_eda = (state.get("private_memories") or {}).get("eda", [])
    coder_records = []

    def decide_next_step(condensed_history):
        context = {
            "profile": profile,
            "target_column": state.get("target_column"),
            "task_type": state.get("task_type"),
            "prior_analyses_this_run": condensed_history,
            "private_eda_history": private_eda,
        }
        system_prompt = """You are the EDA agent in a multi-agent ML pipeline for tabular data. You
decide what exploratory analysis to run next on the raw dataset. Each analysis is
independent — you don't need to build on the previous one. Never invent findings
yourself — only decide what code should compute.

<hard_constraint priority="absolute">
NO VISUAL PLOTS OR FIGURES. Do not propose scripts that plot charts, graphs, or use
matplotlib/seaborn/plotly to render any image. Downstream agents are text-only and
cannot see visual output — a plot step wastes runtime and produces zero consumable
signal. Every analysis must produce numbers and structured tables printed to stdout.
</hard_constraint>

<scale_to_the_data>
Let the dataset's actual shape and quality drive how much you do — don't run a fixed
sequence of steps by default.
- A small, clean, low-column dataset with no obvious issues may only need 1-2 targeted
  checks (e.g. missing values + target correlation) before you're ready to hand off.
- A large, messy, high-cardinality, or many-column dataset may genuinely need several
  rounds — including techniques not listed below — before the open questions are
  answered.
- Never run an analysis just because it exists as an option. Run it because something
  about this specific dataset is still unknown and that analysis would resolve it.
</scale_to_the_data>

<starting_analyses non_exhaustive="true">
These are common building blocks, not a checklist to complete — use what's relevant,
skip what isn't, and go beyond this list whenever the data calls for something else
(examples below):
- Missing values: exact null count and percentage per column.
- Correlation: pairwise correlations among numeric features, flagging |r| >= 0.70 pairs
  as dedup candidates. For feature-target relationship, branch on target type — Pearson/
  Spearman correlation if the target is numeric (regression), mutual information and
  ANOVA F-statistics if the target is categorical (classification).
- Distributions & outliers: skewness, kurtosis, IQR-based outlier counts, 5-number
  summaries for numeric columns.
- Categoricals: cardinality (distinct value count), frequency of rare categories (<1%
  of rows), and any high-cardinality columns that will need special encoding later.
</starting_analyses>

<reach_beyond_the_list_when>
Propose whatever numerical/statistical check actually fits, even if it's not above —
for example: duplicate row detection, constant/near-constant column detection, class
imbalance ratio for a categorical target, chi-square association between two
categorical columns, datetime columns needing range/gap/frequency checks, ID-like
columns that should be excluded from modeling, or multicollinearity via VIF instead of
pairwise correlation when many numeric features are involved. Use your judgment about
what a competent data scientist would actually want to know about THIS dataset, not
just what's on the menu above.
</reach_beyond_the_list_when>

<efficiency>
On large datasets (many rows or many columns), use sampling or vectorized/approximate
methods for expensive computations (mutual information, full pairwise correlation
matrices, VIF) rather than exhaustive exact computation.
</efficiency>

<stopping_rule>
Check `prior_analyses_this_run` before proposing anything — never repeat an analysis
already listed there. Stop as soon as you understand distributions, relationships to
target, and data quality issues well enough to hand off to feature engineering — for a
simple dataset this may be after a single step.
</stopping_rule>

<output_contract>
Print a concise, clearly labeled summary table to stdout for human/log readability, and
write structured JSON metrics to OUTPUT_PATH — one entry per column analyzed, keyed by
column name, containing whatever of {null_pct, dtype, skewness, kurtosis, outlier_count,
cardinality, correlation_with_target, mi_score} this step computed, plus any additional
keys needed for a check not in that list (name them clearly and consistently — e.g.
`vif_score`, `class_imbalance_ratio`, `duplicate_row_count`). The Feature Engineer agent
consumes this JSON directly, so keep key names consistent across steps rather than
inventing a new name for the same concept each time.
</output_contract>"""
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
        spec_text = decision.task_spec or "Perform exploratory data analysis."
        with step_timer(run_id, "eda_agent", f"iteration_{iteration}", task_spec=spec_text):
            result = coder_agent(
                task_spec=spec_text,
                input_paths={"dataset": state["dataset_path"]},
                output_path=output_path,
                context={"profile": profile, "target_column": state.get("target_column")},
                run_id=run_id, timeout=exec_timeout,
                parent_agent="eda_agent", parent_iteration=iteration,
                private_memory=state.get("private_memories"),
            )
        if result.get("private_memory_entry"):
            coder_records.append(result["private_memory_entry"])
        stdout_preview = (result["stdout"] or "").strip().splitlines()
        headline = stdout_preview[0][:160] if stdout_preview else ("failed" if not result["success"] else "no output")
        condensed = f"iter {iteration}: {spec_text[:100]} -> {headline}"
        record = {"iteration": iteration, "task_spec": spec_text, **result}
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
        "private_memories": {
            "eda": [{
                "analyses": loop_result["condensed_history"],
                "exit_reason": loop_result["exit_reason"],
                "iterations": loop_result["iterations"],
            }],
            "coder": coder_records,
        },
        "open_summary_memory": {
            "eda": f"Completed {loop_result['iterations']} analyses ({loop_result['exit_reason']}). {narrative[:350]}"
        },
        "run_memory": [f"[EDA] {c}" for c in loop_result["condensed_history"]],
        "iteration": state.get("iteration", 0) + loop_result["iterations"],
        "last_executed_agent": "eda_agent",
    }
    if loop_result["exit_reason"] not in ("llm_stop", "user_stopped"):
        update["requires_human_approval"] = True
        update["approval_reason"] = "unresolved_exploration"

    log_event(run_id, "eda_agent", "loop_end",
              **{k: v for k, v in eda_findings.items() if k != "narrative"})
    return update
