"""
Supervisor node — routes everything, tracks retries. Kept as-is from the prior
implementation; local logging has been layered on top. Its output is a structured
Pydantic decision (via `.with_structured_output`), so it intentionally stays on
`.invoke()` rather than the streaming helper — token-by-token streaming of a small
structured JSON decision isn't meaningful the way streaming a Coder script or a
final report is.

Key changes in this revision:
  1. Global iteration ceiling check at the top (before LLM call) — skips the LLM
     entirely and short-circuits to human_approval when state["iteration"] exceeds
     PIPELINE_GLOBAL_ITER_CEILING. This is the genuine last-resort circuit breaker;
     it should rarely fire once retry caps and stall detection are enforced.
  2. Code-enforced retry caps — after the LLM returns a decision, it is always
     cross-validated against state["retry_counts"]. The LLM CANNOT bypass the cap.
     Note: judge_agent already increments retry_counts before control returns here;
     supervisor reads it but does NOT write it (no double-counting risk).
  3. Stall-retry escalation — if the LLM proposes a tier-1 retry but metric_history
     shows no improvement since the last attempt, escalate to human_approval
     immediately rather than burning the remaining budget on a pointless repeat.
"""
import os
import json
import hashlib
from typing import Literal, Optional
from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.tools import tool

from state import AgentState
from config import GLOBAL_ITER_CEILING, METRIC_IMPROVEMENT_EPSILON, TIER1_RETRY_BUDGET, TIER2_RETRY_BUDGET
from tools.llm import get_llm
from tools.logger import get_logger, log_event, step_timer
from utils.safe import to_float, safe_diff, safe_round, safe_json

_make_llm = get_llm
PIPELINE_GLOBAL_ITER_CEILING = int(os.environ.get("PIPELINE_GLOBAL_ITER_CEILING", GLOBAL_ITER_CEILING))


def compute_agent_fingerprint(agent_name: str, state: AgentState) -> str:
    """Deterministic hash of relevant state slice for an agent attempt/retry."""
    h = hashlib.sha256()
    h.update(agent_name.encode("utf-8"))

    if agent_name in ("modeler", "modeler_agent"):
        transformed_path = str(state.get("transformed_dataset_path") or state.get("dataset_path", ""))
        h.update(transformed_path.encode("utf-8"))
        feature_steps = (state.get("feature_set") or {}).get("steps") or []
        h.update(json.dumps(feature_steps, sort_keys=True, default=str).encode("utf-8"))
        candidates = state.get("candidate_models") or []
        cand_sig = [
            (c.get("model_family"), safe_round(to_float(c.get("cv_score")), 4, default=0.0))
            for c in candidates
        ]
        h.update(json.dumps(cand_sig, sort_keys=True).encode("utf-8"))
        feedback = str(state.get("judge_feedback") or "")
        h.update(feedback.encode("utf-8"))

    elif agent_name in ("features", "features_agent"):
        dataset_path = str(state.get("transformed_dataset_path") or state.get("dataset_path", ""))
        h.update(dataset_path.encode("utf-8"))
        feature_steps = (state.get("feature_set") or {}).get("steps") or []
        h.update(json.dumps(feature_steps, sort_keys=True, default=str).encode("utf-8"))
        quality_flags = (state.get("profile") or {}).get("data_quality_flags") or []
        h.update(json.dumps(quality_flags, sort_keys=True, default=str).encode("utf-8"))
        feedback = str(state.get("judge_feedback") or "")
        h.update(feedback.encode("utf-8"))

    return h.hexdigest()[:16]


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
    approval_reason: Optional[str] = Field(default=None, description="Reason when human approval is required.")
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
        # If Modeler just ran on a retry, route to Judge to evaluate the new models
        if state.get("last_executed_agent") == "modeler":
            return SupervisorDecision(
                next_agent="judge",
                reasoning="Modeler finished retry; evaluate candidate models against acceptance bar.",
                task_instructions="Evaluate best candidate model and feature quality.",
            )
        # If Features just ran on a tier-2 retry, route to Modeler to train on the new features
        if state.get("last_executed_agent") == "features" and retry_tier == 2:
            return SupervisorDecision(
                next_agent="modeler",
                retry_tier=1,
                reasoning="Features re-engineered; train candidate models on the updated features.",
                task_instructions="Train model families on updated feature set and evaluate metrics.",
            )

        tier1_count = retry_counts.get(1, 0)
        tier2_count = retry_counts.get(2, 0)
        if retry_tier == 1 and tier1_count < TIER1_RETRY_BUDGET:
            return SupervisorDecision(
                next_agent="modeler",
                retry_tier=1,
                reasoning=f"Judge rejected model (tier 1, attempt {tier1_count}); retry modeling with alternative families.",
                task_instructions="Explore alternative model algorithms to improve validation metric.",
            )
        elif retry_tier == 2 and tier2_count < TIER2_RETRY_BUDGET:
            return SupervisorDecision(
                next_agent="features",
                retry_tier=2,
                reasoning=f"Judge rejected features (tier 2, attempt {tier2_count}); re-engineer features.",
                task_instructions="Re-engineer features to address data quality and representation flags.",
            )
        return SupervisorDecision(
            next_agent="human_approval",
            requires_human_approval=True,
            approval_reason="retry_cap_exceeded",
            reasoning="Maximum automated retries reached without convergence; escalate to human approval.",
            task_instructions="Review retry failure and provide guidance.",
        )

    return SupervisorDecision(
        next_agent="reporter",
        reasoning="Pipeline execution completed; synthesize report.",
        task_instructions="Generate final report.",
    )


def _validate_and_override_decision(
    decision: SupervisorDecision,
    state: AgentState,
    logger,
    run_id: str,
) -> SupervisorDecision:
    """
    Cross-validate the LLM's routing decision against code-enforced retry caps
    and stall-retry detection. The LLM CANNOT bypass these — if it tries, we
    override with the deterministic fallback and log a warning.

    NOTE: supervisor does NOT write retry_counts back. judge_agent already
    increments and writes retry_counts before control returns here. Supervisor
    only reads it. No double-counting risk.
    """
    last_verdict = state.get("last_verdict")
    retry_counts = state.get("retry_counts") or {}
    metric_history = state.get("metric_history") or []

    if last_verdict != "reject":
        return decision  # No cap to enforce outside a reject cycle

    # Determine which tier the LLM is routing to
    tier_being_routed = decision.retry_tier or state.get("retry_tier", 0)
    count = retry_counts.get(tier_being_routed, 0)

    # -----------------------------------------------------------------------
    # 1. Hard retry cap enforcement
    # -----------------------------------------------------------------------
    if tier_being_routed == 1 and count >= TIER1_RETRY_BUDGET:
        log_event(run_id, "supervisor", "retry_cap_override",
                  reason="tier1_cap_exceeded",
                  llm_wanted=decision.next_agent,
                  retry_counts=retry_counts,
                  tier=1, count=count)
        logger.warning(
            "Supervisor LLM would exceed tier-1 retry cap (%d/%d); "
            "overriding to human_approval", count, TIER1_RETRY_BUDGET
        )
        return _determine_fallback_next_agent(state)

    if tier_being_routed == 2 and count >= TIER2_RETRY_BUDGET:
        log_event(run_id, "supervisor", "retry_cap_override",
                  reason="tier2_cap_exceeded",
                  llm_wanted=decision.next_agent,
                  retry_counts=retry_counts,
                  tier=2, count=count)
        logger.warning(
            "Supervisor LLM would exceed tier-2 retry cap (%d/%d); "
            "overriding to human_approval", count, TIER2_RETRY_BUDGET
        )
        return _determine_fallback_next_agent(state)

    # -----------------------------------------------------------------------
    # 2. Stall-retry escalation with state fingerprinting and epsilon delta
    # On tier-1 retries, check if consecutive attempts produced the same
    # fingerprinted state or no metric improvement beyond METRIC_IMPROVEMENT_EPSILON.
    # -----------------------------------------------------------------------
    if tier_being_routed == 1 and count >= 1:
        is_stall = False
        stall_reason = ""
        curr_fp = compute_agent_fingerprint("modeler", state)
        prev_fp = (state.get("agent_fingerprints") or {}).get("modeler")

        if prev_fp is not None and prev_fp == curr_fp:
            is_stall = True
            stall_reason = "identical_state_fingerprint"
        elif len(metric_history) >= 2:
            m_last = to_float(metric_history[-1])
            m_prev = to_float(metric_history[-2])
            if m_last is None or m_prev is None:
                is_stall = True
                stall_reason = "metric_unavailable_in_history"
            else:
                delta = safe_diff(m_last, m_prev)
                if abs(delta) < METRIC_IMPROVEMENT_EPSILON or m_last == m_prev:
                    is_stall = True
                    stall_reason = "no_metric_improvement_between_retries"

        if is_stall:
            log_event(run_id, "supervisor", "stalled_retry_escalation",
                      tier=1,
                      metric_history_tail=metric_history[-2:] if len(metric_history) >= 2 else metric_history,
                      fingerprint=curr_fp,
                      reason=stall_reason)
            logger.warning(
                "Tier-1 retry stall detected (%s, %.4f -> %.4f); escalating to human_approval",
                stall_reason,
                metric_history[-2] if len(metric_history) >= 2 else 0.0,
                metric_history[-1] if len(metric_history) >= 1 else 0.0,
            )
            return SupervisorDecision(
                next_agent="human_approval",
                requires_human_approval=True,
                approval_reason="stalled",
                reasoning=(
                    f"Tier-1 retry escalation: {stall_reason} "
                    f"(metric unchanged beyond epsilon {METRIC_IMPROVEMENT_EPSILON}) — escalating."
                ),
                task_instructions=(
                    "Modeler has been retried without measurable metric improvement. "
                    "Human review needed to provide new direction."
                ),
            )

    # Check Tier 2 stall
    if tier_being_routed == 2 and count >= 1:
        curr_fp = compute_agent_fingerprint("features", state)
        prev_fp = (state.get("agent_fingerprints") or {}).get("features")
        if prev_fp is not None and prev_fp == curr_fp:
            log_event(run_id, "supervisor", "stalled_retry_escalation",
                      tier=2, fingerprint=curr_fp, reason="identical_features_state")
            logger.warning("Tier-2 retry produced identical feature state; escalating to human_approval")
            return SupervisorDecision(
                next_agent="human_approval",
                requires_human_approval=True,
                approval_reason="stalled",
                reasoning="Tier-2 feature re-engineering produced identical feature set; escalating.",
                task_instructions="Feature re-engineering stalled on identical state. Review feature plan.",
            )

    return decision


from tools.streaming import invoke_structured_robust


def graph_node_supervisor(state: AgentState) -> dict:
    run_id = state.get("run_id") or state.get("dataset_fingerprint", "run")
    logger = get_logger(run_id)

    # -----------------------------------------------------------------------
    # Global iteration ceiling — check BEFORE calling the LLM to save a call
    # and to set approval_reason correctly (routing fn can't set state fields).
    # -----------------------------------------------------------------------
    current_iter = state.get("iteration", 0)
    ceiling = int(os.environ.get("PIPELINE_GLOBAL_ITER_CEILING", PIPELINE_GLOBAL_ITER_CEILING))
    if current_iter >= ceiling:
        log_event(run_id, "supervisor", "global_iteration_ceiling",
                  iteration=current_iter, ceiling=ceiling)
        log_event(run_id, "supervisor", "run_stop_reason", reason="hit_safety_ceiling",
                  approval_reason="global_iteration_ceiling")
        logger.warning(
            "Global iteration ceiling (%d) reached at iteration %d; escalating to human_approval",
            ceiling, current_iter
        )
        return {
            "next_agent": "human_approval",
            "requires_human_approval": True,
            "approval_reason": "global_iteration_ceiling",
            "stop_reason": "hit_safety_ceiling",
            "supervisor_reasoning": (
                f"Global iteration ceiling ({ceiling}) reached at "
                f"iteration {current_iter}. This is a safety circuit breaker — "
                f"manual review required to assess run state."
            ),
            "task_instructions": (
                "Pipeline hit the global iteration ceiling. Review the run log "
                "and decide whether to approve continuation or abort."
            ),
        }

    # Adaptive Stopping & Safety Envelope Check
    from agents.adaptive_controller import adaptive_controller
    adaptive_rec = adaptive_controller.evaluate_next_action(
        run_id=run_id,
        state=state,
        proposed_tier=state.get("retry_tier", 1),
    )
    if adaptive_rec.get("action") == "wind_down":
        logger.info("Adaptive controller recommended wind-down: %s", adaptive_rec.get("reason"))
        log_event(run_id, "supervisor", "adaptive_wind_down", reason=adaptive_rec.get("reason"))
        return {
            "next_agent": "reporter",
            "requires_human_approval": False,
            "stop_reason": adaptive_rec.get("stop_reason", "converged"),
            "task_instructions": "Synthesize final report with best candidate models and features.",
            "supervisor_reasoning": adaptive_rec.get("reason"),
            "last_executed_agent": "supervisor",
        }

    llm = _make_llm(temperature=0)

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
     * If candidate_models were just retrained -> route to 'judge' for evaluation!
     * If retry_tier == 1 and retry count < 2 -> route to 'modeler' (retry_tier=1).
     * If retry_tier == 2 and retry count < 2 -> route to 'features' (retry_tier=2).
     * If retries >= 2 -> route to 'human_approval'.

CRITICAL: If a stage (e.g. `profile`) is ALREADY populated in state, DO NOT route to that agent again! Advance to the next agent.
CRITICAL: Do NOT route to the same agent at the same retry_tier if retry_counts[tier] >= 2. This is a hard code-enforced limit that will override your decision regardless — routing past it wastes a call.
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
    else:
        # Always cross-validate LLM decision against code-enforced caps.
        # This is NOT optional — the deterministic guard is the authoritative backstop.
        decision = _validate_and_override_decision(decision, state, logger, run_id)

    log_event(run_id, "supervisor", "supervisor_decision", next_agent=decision.next_agent,
              tier=decision.retry_tier, retry_tier=decision.retry_tier, reasoning=decision.reasoning,
              task_instructions=decision.task_instructions)
    logger.info("Supervisor -> %s (%s)", decision.next_agent, decision.reasoning)

    # Determine stop reason and approval reason
    stop_reason = state.get("stop_reason")
    approval_reason = getattr(decision, "approval_reason", None) or state.get("approval_reason")
    if decision.next_agent == "reporter":
        stop_reason = "converged"
        log_event(run_id, "supervisor", "run_stop_reason", reason="converged")
    elif decision.requires_human_approval:
        if not approval_reason:
            if "stall" in decision.reasoning.lower():
                approval_reason = "stalled"
            elif "cap" in decision.reasoning.lower():
                approval_reason = "retry_cap_exceeded"
            elif "ceiling" in decision.reasoning.lower():
                approval_reason = "global_iteration_ceiling"
            else:
                approval_reason = "unresolved_exploration"
        stop_reason = "stalled" if approval_reason == "stalled" else "hit_safety_ceiling" if approval_reason == "global_iteration_ceiling" else "paused"
        log_event(run_id, "supervisor", "run_stop_reason", reason=stop_reason, approval_reason=approval_reason)

    # Fingerprint tracking for the agent being routed to
    agent_fps = dict(state.get("agent_fingerprints") or {})
    if decision.next_agent in ("modeler", "features", "eda_agent"):
        agent_fps[decision.next_agent] = compute_agent_fingerprint(decision.next_agent, state)

    return {
        "next_agent": decision.next_agent,
        "requires_human_approval": decision.requires_human_approval,
        "approval_reason": approval_reason,
        "stop_reason": stop_reason,
        "retry_tier": decision.retry_tier,
        "task_instructions": decision.task_instructions,
        "supervisor_reasoning": decision.reasoning,
        "agent_fingerprints": agent_fps,
        "last_executed_agent": "supervisor",
    }
