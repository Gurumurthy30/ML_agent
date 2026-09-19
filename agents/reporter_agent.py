"""
Reporter Agent — NEW, added because the request explicitly asked to "monitor each and
every thing as a report" via a separate report-generation agent. (The base spec listed
Reporter as an unimplemented placeholder shown only in the diagrams; this is the real
implementation, scoped narrowly to reporting — it does not implement Judge's
accept/reject logic, which is a separate, still-unimplemented concern.)

Aggregates everything the pipeline produced — Profiler output, EDA findings, the
feature-engineering trail, every modeling candidate + score, any approval flags raised
— together with the FULL structured event trace from the local logger (every agent's
steps, decisions, durations, errors) into one final report.

The narrative half is LLM-generated and streamed to the console as it's written. The
monitoring half is pure aggregation over `tools.logger.read_events(...)` — exact
counts/durations that don't depend on the model summarizing correctly.
"""
import os
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from tools.llm import get_llm
from langchain_core.messages import SystemMessage, HumanMessage

from state import AgentState
from memory.run_memory import store_run_memory
from tools.logger import get_logger, log_event, read_events, step_timer
from tools.streaming import stream_text

_ARTIFACT_DIR = "artifacts/reports"
os.makedirs(_ARTIFACT_DIR, exist_ok=True)





def _build_monitoring_summary(run_id: str) -> dict:
    """Pure aggregation over the structured event trace — no LLM involved, so these
    numbers are exact regardless of how well the model narrates them."""
    events = read_events(run_id)
    per_agent_steps = Counter()
    per_agent_duration = defaultdict(float)
    errors, decisions, hard_blocks = [], [], []

    for ev in events:
        agent = ev.get("agent", "unknown")
        etype = ev.get("event")
        if etype == "step_end":
            per_agent_steps[agent] += 1
            per_agent_duration[agent] += ev.get("duration_sec", 0)
        elif etype == "step_error":
            errors.append({"agent": agent, "step": ev.get("step"), "error": ev.get("error")})
        elif etype == "loop_decision":
            decisions.append({"agent": agent, "iteration": ev.get("iteration"),
                              "decision": ev.get("decision"), "reasoning": ev.get("reasoning")})
        elif etype == "hard_block":
            hard_blocks.append({"agent": agent, "reason": ev.get("reason")})

    return {
        "total_events": len(events),
        "steps_per_agent": dict(per_agent_steps),
        "duration_sec_per_agent": {k: round(v, 2) for k, v in per_agent_duration.items()},
        "total_duration_sec": round(sum(per_agent_duration.values()), 2),
        "errors": errors,
        "hard_blocks": hard_blocks,
        "n_loop_decisions": len(decisions),
    }


def reporter_agent(state: AgentState) -> dict:
    run_id = state.get("run_id") or state.get("dataset_fingerprint", "run")
    logger = get_logger(run_id)

    with step_timer(run_id, "reporter_agent", "aggregate_monitoring"):
        monitoring = _build_monitoring_summary(run_id)

    context = {
        "mode": state.get("mode"),
        "profile": state.get("profile"),
        "eda_findings": state.get("eda_findings"),
        "feature_set": state.get("feature_set"),
        "candidate_models": state.get("candidate_models"),
        "metric_history": state.get("metric_history"),
        "best_metric": state.get("best_metric"),
        "last_verdict": state.get("last_verdict"),
        "judge_feedback": state.get("judge_feedback"),
        "requires_human_approval": state.get("requires_human_approval"),
        "approval_reason": state.get("approval_reason"),
        "monitoring": monitoring,
    }

    system_prompt = """You are the Reporter agent, the final step of a multi-agent ML
pipeline. Write a clear final report for a human stakeholder who did not watch the run
happen. Cover, in order: (1) what dataset/task this was, (2) key EDA findings, (3) what
feature engineering was done and why, (4) every model family tried and its score, with
the winner clearly called out, (5) any flags that need human attention and why, (6) a
short monitoring/health summary of the run itself (steps taken, time spent, any errors).
Never invent numbers not present in the context — only report what's actually there.
Write in plain prose with short section headers, not a wall of JSON."""
    human_prompt = f"Run context:\n{json.dumps(context, default=str, indent=2)}"

    llm = get_llm()
    with step_timer(run_id, "reporter_agent", "generate_report"):
        report_text = stream_text(
            llm, [SystemMessage(content=system_prompt), HumanMessage(content=human_prompt)],
            run_id=run_id, agent="reporter_agent",
        )

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report_path = os.path.join(_ARTIFACT_DIR, f"{run_id}_{timestamp}_report.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_text)

    metadata_path = os.path.join(_ARTIFACT_DIR, f"{run_id}_{timestamp}_metadata.json")
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump({
            "monitoring": monitoring,
            "best_metric": state.get("best_metric"),
            "n_candidate_models": len(state.get("candidate_models") or []),
        }, f, indent=2, default=str)

    log_event(run_id, "reporter_agent", "report_written",
              report_path=report_path, metadata_path=metadata_path)

    # Reporter -> Run Memory/RAG: persist a retrievable digest of this run so future
    # EDA/Features/Modeler/Judge calls on similar datasets get a head start.
    memory_digest = (
        f"Task type: {state.get('task_type')}. Modalities: "
        f"{(state.get('profile') or {}).get('detected_modalities')}. "
        f"Metric: {(state.get('profile') or {}).get('recommended_metric')}. "
        f"Best score: {state.get('best_metric')}. "
        f"Models tried: {[m.get('model_family') for m in (state.get('candidate_models') or [])]}. "
        f"Feature steps: {(state.get('feature_set') or {}).get('steps')}. "
        f"Verdict: {state.get('last_verdict')}."
    )
    with step_timer(run_id, "reporter_agent", "store_run_memory"):
        store_run_memory(
            dataset_fingerprint=state.get("dataset_fingerprint", run_id),
            run_id=run_id, text=memory_digest,
            metadata={"best_metric": state.get("best_metric"), "report_path": report_path},
        )

    return {
        "report": report_text,
        "artifact_path": report_path,
        "run_memory": [f"[Reporter] final report written to {report_path}"],
    }
