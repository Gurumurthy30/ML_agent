import json
from pathlib import Path
from typing import Any
from app.config import PROJECTS_DIR
from app.core.state import ProjectState


class SupervisorMemory:
    """Persistent per-project supervisor memory storing decisions, summaries, and artifact references."""

    def __init__(self, project_id: str):
        self.project_id = project_id
        self.memory_dir = PROJECTS_DIR / project_id / "memory"
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self.file_path = self.memory_dir / "supervisor.json"

    def load(self) -> dict[str, Any]:
        """Loads persistent memory from disk, returning default structure if not found."""
        if not self.file_path.exists():
            return {
                "project_id": self.project_id,
                "goal": None,
                "target_column": None,
                "target_metric": None,
                "task_type": None,
                "key_findings": [],
                "decisions": [],
                "best_experiment": None,
                "current_stage": None,
                "iteration_count": 0,
                "known_issues": [],
                "recommendations": [],
                "artifacts": [],
            }
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def save(self, data: dict[str, Any]) -> None:
        """Writes persistent memory to disk."""
        with open(self.file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def record_decision(self, stage: str, action: str, reason: str, details: dict[str, Any] | None = None) -> None:
        """Appends a strategic decision to supervisor memory."""
        mem = self.load()
        decisions = mem.setdefault("decisions", [])
        decisions.append({
            "stage": stage,
            "action": action,
            "reason": reason,
            "details": details or {},
        })
        mem["current_stage"] = stage
        self.save(mem)

    def update_key_findings(self, findings: list[str]) -> None:
        mem = self.load()
        mem.setdefault("key_findings", []).extend(findings)
        self.save(mem)


def get_stage_context(state: ProjectState, stage: str) -> dict[str, Any]:
    """Extracts only the minimal necessary context for a specific agent stage.
    
    Ensures that no agent receives raw data or unnecessary conversation history.
    """
    base_ctx = {
        "project_id": state["project_id"],
        "user_goal": state["user_goal"],
        "target_column": state["target_column"],
        "target_metric": state["target_metric"],
        "task_type": state.get("task_type"),
    }

    if stage == "profile":
        return {
            **base_ctx,
            "dataset_id": state["dataset_id"],
            "dataset_version": state["dataset_version"],
        }

    if stage == "eda":
        return {
            **base_ctx,
            "profile_summary": state.get("profile_summary", {}),
            "dataset_id": state["dataset_id"],
            "dataset_version": state["dataset_version"],
        }

    if stage == "feature_engineering":
        return {
            **base_ctx,
            "profile_summary": state.get("profile_summary", {}),
            "eda_findings": state.get("eda_findings", {}),
            "evaluation_feedback": state.get("evaluation_summary", {}),
            "iteration": state.get("iteration", 1),
            "dataset_id": state["dataset_id"],
            "dataset_version": state["dataset_version"],
        }

    if stage == "model":
        return {
            **base_ctx,
            "profile_summary": state.get("profile_summary", {}),
            "feature_summary": state.get("feature_summary", {}),
            "evaluation_feedback": state.get("evaluation_summary", {}),
            "iteration": state.get("iteration", 1),
            "best_metric_value": state.get("best_metric_value"),
        }

    if stage == "evaluator":
        return {
            **base_ctx,
            "model_summary": state.get("model_summary", {}),
            "iteration": state.get("iteration", 1),
            "max_iterations": state.get("max_iterations", 3),
        }

    if stage == "report":
        return {
            **base_ctx,
            "profile_summary": state.get("profile_summary", {}),
            "eda_findings": state.get("eda_findings", {}),
            "feature_summary": state.get("feature_summary", {}),
            "model_summary": state.get("model_summary", {}),
            "evaluation_summary": state.get("evaluation_summary", {}),
            "iteration": state.get("iteration", 1),
            "best_experiment_id": state.get("best_experiment_id"),
            "best_metric_value": state.get("best_metric_value"),
            "artifacts": state.get("artifacts", []),
        }

    return base_ctx
