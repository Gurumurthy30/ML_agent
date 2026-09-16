"""
Supervisor node — routes everything, tracks retries. Kept as-is from the prior
implementation; local logging has been layered on top. Its output is a structured
Pydantic decision (via `.with_structured_output`), so it intentionally stays on
`.invoke()` rather than the streaming helper — token-by-token streaming of a small
structured JSON decision isn't meaningful the way streaming a Coder script or a
final report is.
"""
import os
import json
from typing import Literal, Optional
from pydantic import BaseModel, Field
from langchain_ollama import ChatOllama
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.tools import tool

from state import AgentState
from tools.logger import get_logger, log_event, step_timer


@tool
def lookup_artifact(artifact_path: str) -> str:
    """Look up a previously saved artifact (model, metadata, logs) and return its contents."""
    if not os.path.exists(artifact_path):
        return f"No artifact found at {artifact_path}"
    with open(artifact_path, "r") as f:
        return f.read()


class SupervisorDecision(BaseModel):
    next_agent: Literal["profiler", "features", "modeler", "judge",
        "human_approval", "reporter", "eda_agent"] = Field(description="Which agent should run next.")
    reasoning: str = Field(description="Short justification for this routing decision.")
    requires_human_approval: bool = Field(default=False)
    retry_tier: Optional[Literal[1, 2]] = Field(default=None,
        description="1 = new model family (Judge rejected model). 2 = re-engineered features "
                    "(Judge rejected features/deeper issue). None if not a retry.")
    task_instructions: str = Field(description="Specific instructions to pass to the next agent.")


def _determine_fallback_next_agent(state: AgentState) -> SupervisorDecision:
    """Deterministic routing fallback if LLM structured output is None or attempts redundant loops."""
    mode = state.get("mode", "full_pipeline")
    profile = state.get("profile")
    eda_findings = state.get("eda_findings")
    feature_set = state.get("feature_set")
    candidate_models = state.get("candidate_models") or []
    last_verdict = state.get("last_verdict")
    retry_tier = state.get("retry_tier", 0)
    retry_counts = state.get("retry_counts") or {}

    if not profile:
        return SupervisorDecision(
            next_agent="profiler",
            reasoning="Dataset not yet profiled; start with profiling.",
            task_instructions="Profile dataset statistics, column modalities, and detect target column.",
        )
    if not eda_findings:
        return SupervisorDecision(
            next_agent="eda_agent",
            reasoning="Dataset profiled; proceed to exploratory data analysis (EDA).",
            task_instructions="Analyze column distributions, correlations with target, and data quality flags.",
        )
    if mode == "eda_only":
        return SupervisorDecision(
            next_agent="reporter",
            reasoning="EDA-only mode complete; synthesize EDA findings into final report.",
            task_instructions="Generate final comprehensive EDA report.",
        )
    if not feature_set:
        return SupervisorDecision(
            next_agent="features",
            reasoning="EDA completed; engineer and transform features for modeling.",
            task_instructions="Generate feature engineering code and produce transformed dataset.",
        )
    if not candidate_models:
        return SupervisorDecision(
            next_agent="modeler",
            reasoning="Features ready; train and evaluate baseline candidate models.",
            task_instructions="Train model families, evaluate metrics, and save best model.",
        )
    if last_verdict is None:
        return SupervisorDecision(
            next_agent="judge",
            reasoning="Models trained; evaluate candidate models and feature quality against acceptance bar.",
            task_instructions="Evaluate best candidate model and feature quality.",
        )
    if last_verdict == "accept":
        return SupervisorDecision(
            next_agent="reporter",
            reasoning="Judge accepted the model and features; compile final deliverable report.",
            task_instructions="Compile final pipeline report with metrics and monitoring trace.",
        )
    if last_verdict == "reject":
        tier1_count = retry_counts.get(1, 0)
        tier2_count = retry_counts.get(2, 0)
        if retry_tier == 1 and tier1_count < 2:
            return SupervisorDecision(
                next_agent="modeler",
                retry_tier=1,
                reasoning=f"Judge rejected model (tier 1, attempt {tier1_count}); retry modeling with alternative families.",
                task_instructions="Explore alternative model algorithms to improve validation metric.",
            )
        elif retry_tier == 2 and tier2_count < 2:
            return SupervisorDecision(
                next_agent="features",
                retry_tier=2,
                reasoning=f"Judge rejected features (tier 2, attempt {tier2_count}); re-engineer features.",
                task_instructions="Re-engineer features to address data quality and representation flags.",
            )
        return SupervisorDecision(
            next_agent="human_approval",
            requires_human_approval=True,
            reasoning="Maximum automated retries reached without convergence; escalate to human approval.",
            task_instructions="Review retry failure and provide guidance.",
        )

    return SupervisorDecision(
        next_agent="reporter",
        reasoning="Pipeline execution completed; synthesize report.",
        task_instructions="Generate final report.",
    )


from tools.streaming import invoke_structured_robust


def graph_node_supervisor(state: AgentState) -> dict:
    run_id = state.get("run_id") or state.get("dataset_fingerprint", "run")
    logger = get_logger(run_id)

    llm = ChatOllama(model="gpt-oss:20b-cloud", base_url="https://ollama.com",
        client_kwargs={"headers": {"Authorization": f"Bearer {os.getenv('OLLAMA_API_KEY')}"}},
        temperature=0)

    system_prompt = """You are the Supervisor node in a multi-agent ML pipeline. You route to
the correct specialist agent based on the current progress in state:

Pipeline Order:
1. If `profile` is empty or missing -> route to 'profiler'.
2. If `profile` is present and `eda_findings` is empty -> route to 'eda_agent'.
3. If mode == 'eda_only' and `eda_findings` is present -> route to 'reporter'.
4. If mode == 'full_pipeline':
   - If `feature_set` is empty -> route to 'features'.
   - If `feature_set` is present and `candidate_models` is empty -> route to 'modeler'.
   - If `candidate_models` is present and `last_verdict` is empty -> route to 'judge'.
   - If `last_verdict` == 'accept' -> route to 'reporter'.
   - If `last_verdict` == 'reject':
     * If retry_tier == 1 and retry count < 2 -> route to 'modeler' (retry_tier=1).
     * If retry_tier == 2 and retry count < 2 -> route to 'features' (retry_tier=2).
     * If retries >= 2 -> route to 'human_approval'.

CRITICAL: If a stage (e.g. `profile`) is ALREADY populated in state, DO NOT route to that agent again! Advance to the next agent.
Respond with a single structured decision, not prose."""

    human_prompt = f"Current agent state:\n{json.dumps(state, default=str, indent=2)}"

    decision = None
    with step_timer(run_id, "supervisor", "route"):
        try:
            decision = invoke_structured_robust(
                llm, SupervisorDecision,
                [SystemMessage(content=system_prompt), HumanMessage(content=human_prompt)]
            )
        except Exception as exc:
            logger.warning("Supervisor LLM call failed (%s); using deterministic routing fallback", exc)

    # Fallback guard if LLM returned None or failed
    if decision is None or not hasattr(decision, "next_agent") or not decision.next_agent:
        logger.warning("Supervisor received None from LLM; using deterministic routing fallback")
        decision = _determine_fallback_next_agent(state)
    # Loop guard: prevent looping back to profiler if profile is already non-empty
    elif decision.next_agent == "profiler" and bool(state.get("profile")):
        logger.warning("Supervisor attempted to route to 'profiler' when profile is already present; advancing.")
        decision = _determine_fallback_next_agent(state)

    log_event(run_id, "supervisor", "routed", next_agent=decision.next_agent,
              retry_tier=decision.retry_tier, reasoning=decision.reasoning,
              task_instructions=decision.task_instructions)
    logger.info("Supervisor -> %s (%s)", decision.next_agent, decision.reasoning)

    return {
        "next_agent": decision.next_agent,
        "requires_human_approval": decision.requires_human_approval,
        "retry_tier": decision.retry_tier,
        "task_instructions": decision.task_instructions,
        "supervisor_reasoning": decision.reasoning,
    }

