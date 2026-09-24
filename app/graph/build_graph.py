from typing import Literal
from langgraph.graph import StateGraph, START, END

from app.core.state import ProjectState
from app.core.model_router import ModelRouter
from app.tools.registry import ToolRegistry

from app.agents.supervisor import supervisor_node
from app.agents.profile import profile_dataset
from app.agents.eda import run_eda
from app.agents.feature_engineering import run_feature_engineering
from app.agents.model import run_modeling
from app.agents.evaluator import run_evaluator
from app.agents.report import run_report


def build_ml_graph(project_id: str, router: ModelRouter | None = None) -> StateGraph:
    """Constructs the LangGraph tabular ML workflow graph conforming to PROJECT_SPEC.md §6."""
    if router is None:
        router = ModelRouter()
    registry = ToolRegistry(project_id)

    builder = StateGraph(ProjectState)

    # 1. Define nodes
    def _supervisor(state: ProjectState):
        print(f"\n[SUPERVISOR] Evaluating stage: '{state.get('current_stage')}' (Iteration {state.get('iteration', 1)})", flush=True)
        result = supervisor_node(state, router, registry)
        print(f"[SUPERVISOR] Next action: '{result.get('next_action')}'", flush=True)
        return result

    def _profile(state: ProjectState):
        print("\n--> [STAGE: PROFILE] Running deterministic tabular profiling...", flush=True)
        return profile_dataset(state, registry)

    def _eda(state: ProjectState):
        print("\n--> [STAGE: EDA] Running adaptive LLM EDA and statistical analysis...", flush=True)
        return run_eda(state, router, registry)

    def _features(state: ProjectState):
        print("\n--> [STAGE: FEATURES] Designing & executing feature pipeline...", flush=True)
        return run_feature_engineering(state, router, registry)

    def _model(state: ProjectState):
        print("\n--> [STAGE: MODEL] Training scikit-learn models & logging to MLflow...", flush=True)
        return run_modeling(state, router, registry)

    def _evaluator(state: ProjectState):
        print("\n--> [STAGE: EVALUATOR] Running independent evaluation & verification...", flush=True)
        return run_evaluator(state, router, registry)

    def _report(state: ProjectState):
        print("\n--> [STAGE: REPORT] Assembling final markdown report & summary JSON...", flush=True)
        return run_report(state, router, registry)

    builder.add_node("supervisor", _supervisor)
    builder.add_node("profile", _profile)
    builder.add_node("eda", _eda)
    builder.add_node("features", _features)
    builder.add_node("model", _model)
    builder.add_node("evaluator", _evaluator)
    builder.add_node("report", _report)

    # 2. Add edges
    builder.add_edge(START, "supervisor")
    builder.add_edge("profile", "supervisor")
    builder.add_edge("eda", "supervisor")
    builder.add_edge("features", "supervisor")
    builder.add_edge("model", "supervisor")
    builder.add_edge("evaluator", "supervisor")
    builder.add_edge("report", "supervisor")

    # 3. Conditional routing from supervisor
    def route_supervisor(state: ProjectState) -> Literal["profile", "eda", "features", "model", "evaluator", "report", "__end__"]:
        action = state.get("next_action")
        if action == "profile":
            return "profile"
        elif action == "eda":
            return "eda"
        elif action == "features":
            return "features"
        elif action == "model":
            return "model"
        elif action == "evaluator":
            return "evaluator"
        elif action == "report":
            return "report"
        elif action == "finish":
            return END
        return END

    builder.add_conditional_edges(
        "supervisor",
        route_supervisor,
        {
            "profile": "profile",
            "eda": "eda",
            "features": "features",
            "model": "model",
            "evaluator": "evaluator",
            "report": "report",
            END: END,
        },
    )

    return builder.compile()
