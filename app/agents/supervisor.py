from typing import Any
from langchain_core.messages import SystemMessage, HumanMessage

from app.core.state import ProjectState, SupervisorReview
from app.core.model_router import ModelRouter
from app.core.memory import SupervisorMemory
from app.tools.registry import ToolRegistry



SUPERVISOR_SYSTEM_PROMPT = """You are the Lead Supervisor Agent for an autonomous tabular ML workflow. You are the planner, router, reviewer, and state manager — never the one doing the analysis or the modeling.
 
RESPONSIBILITIES
- Understand the user's goal, target column, target metric, and constraints.
- Decide which agent runs next and give it only the context it actually needs — not the full project history.
- Review every agent's structured output before advancing: does it look complete and internally consistent? If not, retry that stage (bounded) or surface NEEDS_INPUT rather than silently continuing.
- Maintain persistent project memory: goal, target, key findings, decisions made, best experiment so far, current stage, iteration count, known issues, recommendations. Update it after every stage — never let it balloon into a full transcript.
- Drive the Model<->Evaluator loop: on IMPROVE, route to the Evaluator's recommended_next_stage (feature_engineering by default, model when the Evaluator says the issue is model-only). Enforce max_iterations — on hitting the limit without a PASS, route straight to Report with an explicit note that the limit was reached.
- Trigger Report once Evaluator returns PASS, or once the iteration limit is hit.
 
SCOPE ENFORCEMENT
Keep every routed task inside locked project scope: tabular data only (binary/multiclass classification or regression), scikit-learn models only, zero visualization/plots anywhere, no timeout on code execution. If a request from the user would violate this scope, say so plainly instead of routing it.
 
WHEN TO ASK THE USER
Only surface a question when the workflow genuinely cannot proceed safely: the target column can't be determined, the metric is ambiguous and materially changes what "success" means, the dataset looks unusable, or an ambiguity carries real risk of wasted work. Do not ask about anything you can reasonably decide yourself.
 
COMMUNICATION
Every decision you make becomes a line in the live activity feed. Keep it short and concrete — state what happened and what happens next. Never expose internal chain-of-thought reasoning; summarize the decision, not the deliberation.
 
OUTPUT FORMAT — return exactly this JSON shape after each review:
{
  "status": "SUCCESS" | "FAILED" | "NEEDS_INPUT" | "RETRY",
  "current_stage": "...",
  "next_action": "...",
  "decision_summary": "<one or two sentences, UI-facing>",
  "memory_update": { ... }
}
"""


def supervisor_node(state: ProjectState, router: ModelRouter, registry: ToolRegistry) -> dict[str, Any]:
    """The central Supervisor node: reviews current state, updates memory, and selects the next action."""
    project_id = state["project_id"]
    memory = SupervisorMemory(project_id)
    current_stage = state.get("current_stage", "start")
    iteration = state.get("iteration", 1)
    max_iterations = state.get("max_iterations", 3)

    next_action = "profile"
    reasoning = ""

    if current_stage in ("start", "", None):
        next_action = "profile"
        reasoning = "Initiating run. Starting with deterministic dataset profiling."
        memory.record_decision("init", "DISPATCH_PROFILE", reasoning)

    elif current_stage == "profile":
        next_action = "eda"
        reasoning = f"Profile complete. Guessed task type: '{state.get('task_type')}'. Dispatching to EDA."
        memory.record_decision("profile_review", "DISPATCH_EDA", reasoning, {
            "task_type": state.get("task_type"),
            "rows": state.get("profile_summary", {}).get("row_count"),
        })

    elif current_stage == "eda":
        next_action = "features"
        findings_count = len(state.get("eda_findings", {}).get("findings", []))
        reasoning = f"EDA complete with {findings_count} findings. Dispatching to Feature Engineering."
        memory.record_decision("eda_review", "DISPATCH_FEATURES", reasoning)

    elif current_stage == "feature_engineering":
        next_action = "model"
        reasoning = "Feature pipeline executed and parquet artifact generated. Dispatching to Model training."
        memory.record_decision("features_review", "DISPATCH_MODEL", reasoning)

    elif current_stage == "model":
        next_action = "evaluator"
        best_m = state.get("model_summary", {}).get("best_model_name", "model")
        best_s = state.get("model_summary", {}).get("best_score", 0.0)
        reasoning = f"Models trained. Best candidate: {best_m} ({best_s:.4f}). Dispatching to independent Evaluator."
        memory.record_decision("model_review", "DISPATCH_EVALUATOR", reasoning, {
            "best_model": best_m,
            "best_score": best_s,
        })

    elif current_stage == "evaluator":
        eval_summary = state.get("evaluation_summary", {})
        verdict = eval_summary.get("verdict", "PASS")
        rec_stage = eval_summary.get("recommended_next_stage", "feature_engineering")

        if verdict == "PASS":
            next_action = "report"
            reasoning = "Evaluator awarded PASS verdict. Moving to final reporting."
            memory.record_decision("evaluator_review", "TRIGGER_REPORT", reasoning)
        else:
            if iteration >= max_iterations:
                next_action = "report"
                reasoning = (
                    f"Evaluator requested IMPROVE, but iteration limit ({max_iterations}) reached. "
                    "Proceeding to Report with best model found so far."
                )
                memory.record_decision("evaluator_review", "LIMIT_REACHED_TRIGGER_REPORT", reasoning)
            else:
                next_action = "features" if rec_stage == "feature_engineering" else "model"
                iteration += 1
                reasoning = (
                    f"Evaluator requested IMPROVE (loop iteration {iteration}/{max_iterations}). "
                    f"Routing back to '{next_action}' based on feedback."
                )
                memory.record_decision("evaluator_review", f"LOOP_TO_{next_action.upper()}", reasoning)

    elif current_stage == "report":
        next_action = "finish"
        reasoning = "Final report and summary artifacts generated successfully."
        memory.record_decision("report_review", "COMPLETE", reasoning)

    # Sync supervisor memory state
    mem_data = memory.load()
    mem_data["current_stage"] = current_stage
    mem_data["next_action"] = next_action
    mem_data["iteration_count"] = iteration
    mem_data["best_experiment"] = state.get("best_experiment_id")
    mem_data["best_metric_value"] = state.get("best_metric_value")
    memory.save(mem_data)

    return {
        "next_action": next_action,
        "iteration": iteration,
        "supervisor_memory": mem_data,
        "status": "RUNNING" if next_action != "finish" else "SUCCESS",
    }
