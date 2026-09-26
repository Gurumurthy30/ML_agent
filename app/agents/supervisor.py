from typing import Any
from langchain_core.messages import SystemMessage, HumanMessage

from app.core.state import ProjectState, SupervisorReview
from app.core.model_router import ModelRouter
from app.core.memory import SupervisorMemory
from app.tools.registry import ToolRegistry


SUPERVISOR_SYSTEM_PROMPT = """You are the Lead Machine Learning Supervisor Agent.
Your responsibility is to plan, review stage outcomes, ensure high standards, and route workflow progression.

RULES:
1. You NEVER perform EDA or code training yourself. You dispatch and review.
2. Ensure strict adherence to project scope: tabular only, scikit-learn models only, zero visualization plots.
3. Review agent outputs, summarize decisions, and guide the next step.
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
