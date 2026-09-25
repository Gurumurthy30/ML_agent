import json
from pathlib import Path
from typing import Any
from langchain_core.messages import SystemMessage, HumanMessage

from app.core.state import ProjectState, EvaluatorOutput
from app.core.model_router import ModelRouter
from app.core.memory import get_stage_context
from app.tools.registry import ToolRegistry
from app.config import PROJECTS_DIR



EVALUATOR_SYSTEM_PROMPT = """You are an independent Machine Learning Evaluation Agent. You do not trust the Model Agent's self-reported success — you verify.
 
Given the task type, target metric, and training/validation results (and, when something looks off, numbers recomputed by Coder), decide whether the current model is acceptable or needs another iteration.
 
CHOOSE CHECKS THAT MATTER FOR THIS CASE — do not run a fixed checklist blindly. Relevant checks typically include a subset of:
- Overfitting: a meaningful train/validation gap for the metric in use (judge relative to the metric's scale and validation stability, not a fixed universal cutoff)
- Suspiciously perfect performance (near-1.0 scores, near-zero error) without a plausible reason — treat as a likely leakage signal and investigate the feature set before accepting
- Metric appropriateness for the stated objective and class balance (e.g. accuracy on a heavily imbalanced target is misleading — check whether the metric choice itself is the problem)
- Class imbalance effects (classification): is the model actually distinguishing classes, or defaulting toward the majority class?
- Validation quality: is the split appropriate for this data (e.g. no temporal leakage across folds if there's a time dimension)?
- Anything specific to this model family or run history worth a second look
 
DECISION
- "PASS": performance is solid, the train/validation gap is reasonable, no leakage or validation red flags.
- "IMPROVE": meaningful overfitting, weak performance, leakage risk, or a validation problem.
  - recommended_next_stage = "feature_engineering" when the fix is about the data/features (leaky column, weak representation, missing transform).
  - recommended_next_stage = "model" when the features look fine and the fix is about model choice, hyperparameters, or regularization.
- On the final allowed iteration, still return your honest verdict — do not pass a model just because iterations ran out; that tradeoff is the Supervisor's call, not yours.
 
OUTPUT FORMAT — return exactly this JSON shape:
{
  "status": "PASS" | "IMPROVE",
  "issues": [ { "type": "...", "severity": "low" | "medium" | "high", "evidence": {...} } ],
  "recommendations": ["..."],
  "recommended_next_stage": "feature_engineering" | "model" | null
}
 
HARD RULE: no plots, charts, or images — every check must resolve to numbers or text.
"""


def run_evaluator(state: ProjectState, router: ModelRouter, registry: ToolRegistry) -> dict[str, Any]:
    """Independent evaluation agent assessing model validity, overfitting, and leakage."""
    project_id = state["project_id"]
    tools = registry.get_tools_for_role("evaluator")
    ctx = get_stage_context(state, "evaluator")
    iteration = state.get("iteration", 1)

    llm = router.get_model("evaluator", temperature=0.0)
    structured_llm = llm.with_structured_output(EvaluatorOutput)

    eval_prompt = f"""Critique the latest modeling results:
Project Goal: {state.get('user_goal')}
Task Type: {state.get('task_type')}
Target Metric: {state.get('target_metric')}
Current Iteration: {iteration} of {state.get('max_iterations', 3)}

Model Stage Summary:
{json.dumps(state.get('model_summary', {}), indent=2)}

Provide your independent evaluation verdict (PASS or IMPROVE), identify any issues found, provide reasoning, and specify recommended_next_stage ("feature_engineering" or "model").
"""

    eval_output = None
    try:
        eval_output = structured_llm.invoke([
            SystemMessage(content=EVALUATOR_SYSTEM_PROMPT),
            HumanMessage(content=eval_prompt),
        ])
    except Exception as e:
        print(f"[EVALUATOR] Structured output warning: {e}", flush=True)

    if eval_output is None:
        best_score = float(state.get("model_summary", {}).get("best_score", 0.0) or 0.0)
        target_met = state.get("target_metric") or "f1"
        # Determine pass if score is reasonable
        verdict = "PASS" if best_score > 0.5 else "IMPROVE"
        eval_output = EvaluatorOutput(
            verdict=verdict,
            target_metric=target_met,
            primary_metric_value=best_score,
            issues_found=[],
            recommended_next_stage="feature_engineering",
            reasoning=f"Evaluated model performance on {target_met}: {best_score:.4f}.",
        )

    eval_dict = eval_output.model_dump()

    # Save to projects/<id>/evaluations/
    eval_dir = PROJECTS_DIR / project_id / "evaluations"
    eval_dir.mkdir(parents=True, exist_ok=True)
    json_path = eval_dir / f"evaluation_iter_{iteration}.json"
    md_path = eval_dir / f"evaluation_iter_{iteration}.md"

    tools.files.write_file(f"evaluations/evaluation_iter_{iteration}.json", json.dumps(eval_dict, indent=2))

    # Create readable evaluation markdown (no plots)
    md_lines = [
        f"# Evaluation Verdict: Project `{project_id}` (Iteration {iteration})",
        f"- **Verdict:** `{eval_output.verdict}`",
        f"- **Target Metric ({eval_output.target_metric}):** {eval_output.primary_metric_value:.4f}",
        f"- **Recommended Next Stage:** `{eval_output.recommended_next_stage}`",
        "",
        "## Reasoning",
        eval_output.reasoning,
        "",
        "## Issues Detected",
    ]
    if eval_output.issues_found:
        md_lines.extend(["| Check | Severity | Description | Suggested Fix |", "|---|---|---|---|"])
        for issue in eval_output.issues_found:
            clean_desc = issue.description.replace("|", "/")
            clean_fix = issue.suggested_fix.replace("|", "/")
            md_lines.append(f"| {issue.check_name} | {issue.severity} | {clean_desc} | {clean_fix} |")
    else:
        md_lines.append("- No critical issues found.")

    tools.files.write_file(f"evaluations/evaluation_iter_{iteration}.md", "\n".join(md_lines))

    # Register artifact
    art_eval = tools.artifacts.register_artifact(
        project_id=project_id,
        artifact_type="evaluation_report",
        path=str(md_path),
        run_id=state.get("run_id"),
        version=f"iter_{iteration}",
    )

    artifacts_list = list(state.get("artifacts", []))
    artifacts_list.append(art_eval)

    return {
        "evaluation_summary": eval_dict,
        "current_stage": "evaluator",
        "artifacts": artifacts_list,
        "status": "SUCCESS",
    }
