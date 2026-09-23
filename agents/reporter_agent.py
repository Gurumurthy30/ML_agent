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
from utils.scoped_memory import format_open_memory_digest
from tools.logger import get_logger, log_event, read_events, step_timer
from tools.streaming import stream_text
from utils.safe import safe_round

_ARTIFACT_DIR = "artifacts/reports"
os.makedirs(_ARTIFACT_DIR, exist_ok=True)





def _build_monitoring_summary(run_id: str) -> dict:
    """Pure aggregation over structured tracer telemetry — no LLM involved, preserving exact counts,
    parent-nesting, attempts, and grouped error signatures."""
    from tools.tracer import get_run_events, get_run_attempts, get_run_errors
    events = get_run_events(run_id)
    attempts = get_run_attempts(run_id)
    raw_errors = get_run_errors(run_id)

    per_agent_steps = Counter()
    per_agent_duration = defaultdict(float)
    decisions, hard_blocks = [], []

    attempts_by_parent = defaultdict(list)
    for att in attempts:
        p = att.get("parent_agent") or att.get("agent") or "unattributed"
        attempts_by_parent[p].append(att)

    errors_by_parent = defaultdict(list)
    for err in raw_errors:
        p = err.get("parent_agent") or err.get("agent") or "unattributed"
        errors_by_parent[p].append(err)

    for ev in events:
        agent = ev.get("agent", "unknown")
        parent = ev.get("parent_agent")
        target_bucket = f"{parent}/{agent}" if parent and parent != agent else agent
        etype = ev.get("event") or ev.get("type")
        if etype in ("step_end", "iteration_result", "attempt_result", "coder_attempt"):
            per_agent_steps[target_bucket] += 1
            dur = ev.get("duration_sec") or ((ev.get("duration_ms") or 0) / 1000.0)
            per_agent_duration[target_bucket] += dur
        elif etype == "loop_decision":
            decisions.append({"agent": agent, "parent_agent": parent, "iteration": ev.get("iteration"),
                              "decision": ev.get("decision"), "reasoning": ev.get("reasoning")})
        elif etype == "hard_block":
            hard_blocks.append({"agent": agent, "parent_agent": parent, "reason": ev.get("reason")})

    return {
        "total_events": len(events),
        "steps_per_agent": dict(per_agent_steps),
        "duration_sec_per_agent": {k: round(v, 2) for k, v in per_agent_duration.items()},
        "total_duration_sec": round(sum(per_agent_duration.values()), 2),
        "attempts": attempts,
        "attempts_by_parent": dict(attempts_by_parent),
        "errors": raw_errors,
        "errors_by_parent": dict(errors_by_parent),
        "hard_blocks": hard_blocks,
        "n_loop_decisions": len(decisions),
    }


_make_llm = get_llm


def reporter_agent(state: AgentState) -> dict:
    run_id = state.get("run_id") or state.get("dataset_fingerprint", "run")
    logger = get_logger(run_id)

    with step_timer(run_id, "reporter_agent", "aggregate_monitoring"):
        monitoring = _build_monitoring_summary(run_id)

    open_digest = format_open_memory_digest(state.get("open_summary_memory"), state=state)

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
        "approval_status": state.get("approval_status"),
        "modifications": state.get("modifications") or (state.get("feature_plan") or {}).get("modifications"),
        "feature_plan": state.get("feature_plan"),
        "monitoring": monitoring,
        "pipeline_summary": open_digest,
    }

    system_prompt = """You are the Reporter agent, the final step of a multi-agent ML
pipeline for tabular data. Write a clear final report for a human stakeholder who did
not watch the run happen. Never invent numbers, findings, or events not present in the
context — only report what's actually there. Write in plain prose with short section
headers, not a wall of JSON.

<mode_branch>
Check `mode` first — it determines which sections apply:
- mode == 'eda_only': cover only (1), (2), and (6) below. There is no feature
  engineering or modeling to report — do not fabricate or apologize for their absence,
  just omit those sections.
- mode == 'full_pipeline': cover all sections (1) through (6).
</mode_branch>

<sections order="required">
1. Dataset/task: what the data was and what problem was being solved.
2. Key EDA findings: from `eda_findings` — missingness, correlations, distributions,
   data quality issues that mattered.
3. [full_pipeline only] Feature engineering: what was done and why, from the
   `feature_set` steps.
4. [full_pipeline only] Modeling: every model family tried and its score, drawn from
   `candidate_models`/`metric_history`, with the winning model (`best_metric`) clearly
   called out. If any attempt was rejected and retried (check retry_tier /
   retry_counts / judge_feedback history), briefly note why and what changed.
5. Flags for human attention: draw from the Judge's `feedback` (populated on every
   verdict, not just rejections) and any `human_approval` escalation reached during the
   run. If there are no material limitations, say so briefly rather than omitting the
   section.
6. Run health summary: steps taken this run (`steps_taken_this_run` /
   `prior_analyses_this_run` as applicable), retry counts if any, and any logged errors.
   If the run field data isn't present in context, state that a health summary isn't
   available rather than estimating.
</sections>"""
    human_prompt = f"Run context:\n{json.dumps(context, default=str, indent=2)}"

    llm = _make_llm()
    with step_timer(run_id, "reporter_agent", "generate_report"):
        report_text = stream_text(
            llm, [SystemMessage(content=system_prompt), HumanMessage(content=human_prompt)],
            run_id=run_id, agent="reporter_agent",
        )

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    os.makedirs(_ARTIFACT_DIR, exist_ok=True)
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
              report=report_text, report_path=report_path, metadata_path=metadata_path)

    return {
        "report": report_text,
        "artifact_path": report_path,
        "open_summary_memory": {
            "reporter": f"Final report generated and written to {report_path}"
        },
        "run_memory": [f"[Reporter] final report written to {report_path}"],
        "last_executed_agent": "reporter",
    }
