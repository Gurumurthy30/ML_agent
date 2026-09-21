"""
Scoped Memory and Open Summarization Memory System.

Architecture:
1. Profiler: Strictly NO memory (simple one-time dataset profiling).
2. Specialist Working Agents (Coder, EDA, Features, Modeler):
   - Strictly PRIVATE / SCORE memory.
   - Each agent only reads its own scoped domain history.
   - Modeler tracks past models, hyperparams, CV scores, and mistakes/blunders
     to avoid repeating failed approaches or degenerate blunders.
   - Coder tracks past execution errors/fixes to prevent repeating broken patterns.
   - EDA & Features track their own exploration/transformation attempts and scores.
3. Executive Agents (Supervisor, Judge, Reporter):
   - OPEN memory with SUMMARIZATION to give pipeline-wide visibility
     while strictly bounding token size to prevent context leaks.
"""
from typing import Dict, Any, List, Optional
import copy


def merge_private_memories(existing: Optional[dict], update: Optional[dict]) -> dict:
    """
    LangGraph reducer for AgentState["private_memories"].
    Merges updates per agent bucket without overwriting other agents' private memory.
    Caps each agent's history at 50 records to prevent memory leaks.
    """
    merged: Dict[str, List[Any]] = {
        "coder": list((existing or {}).get("coder", [])),
        "eda": list((existing or {}).get("eda", [])),
        "features": list((existing or {}).get("features", [])),
        "modeler": list((existing or {}).get("modeler", [])),
    }

    if not update or not isinstance(update, dict):
        return merged

    for agent_key, entries in update.items():
        if agent_key not in merged:
            merged[agent_key] = []
        if isinstance(entries, list):
            merged[agent_key].extend(entries)
        elif entries is not None:
            merged[agent_key].append(entries)
        
        # Enforce bounding cap per agent
        if len(merged[agent_key]) > 50:
            merged[agent_key] = merged[agent_key][-50:]

    return merged


def merge_open_summary(existing: Optional[dict], update: Optional[dict]) -> dict:
    """
    LangGraph reducer for AgentState["open_summary_memory"].
    Maintains a structured, bounded summary of all completed pipeline phases.
    """
    merged = dict(existing or {})
    if not update or not isinstance(update, dict):
        return merged

    for phase_key, content in update.items():
        if phase_key == "recent_events":
            prior_events = list(merged.get("recent_events", []))
            new_events = content if isinstance(content, list) else [content]
            prior_events.extend(new_events)
            merged["recent_events"] = prior_events[-5:]  # rolling window of 5 events
        else:
            # Phase summary string/dict overwrite with latest bounded summary
            if isinstance(content, str):
                # Truncate to 600 chars per phase to strictly prevent size leaks
                merged[phase_key] = content.strip()[:600]
            else:
                merged[phase_key] = content

    return merged


# ---------------------------------------------------------------------------
# Modeler Private Scorecard & Blunder Tracking
# ---------------------------------------------------------------------------

def format_modeler_scorecard(private_memories: Optional[dict], current_best: Optional[float] = None) -> str:
    """
    Builds a concise scorecard and blunder log from Modeler's private memory.
    Injected directly into Modeler's prompt so it knows its own past attempts,
    scores, and mistakes/blunders to avoid.
    """
    modeler_records = (private_memories or {}).get("modeler", [])
    if not modeler_records:
        return "No prior model training attempts in private memory (first exploration)."

    lines = ["=== MODELER PRIVATE SCORECARD & ATTEMPTS ==="]
    blunders = []

    for idx, rec in enumerate(modeler_records, 1):
        if not isinstance(rec, dict):
            lines.append(f"- Trial {idx}: {str(rec)[:120]}")
            continue

        family = rec.get("model_family") or rec.get("family", "Unknown")
        metric_name = rec.get("metric_name", "metric")
        score = rec.get("score") or rec.get("metric")
        status = rec.get("status", "completed")
        delta = rec.get("metric_delta")
        blunder_note = rec.get("blunder_note")

        score_str = f"{score:.4f}" if isinstance(score, (int, float)) else str(score)
        delta_str = f" (delta: {delta:+.4f})" if isinstance(delta, (int, float)) else ""
        lines.append(f"- Attempt {idx}: [{family}] {metric_name}={score_str}{delta_str} | Status: {status}")

        if blunder_note:
            blunders.append(f"Attempt {idx} [{family}]: {blunder_note}")
        elif status == "failed" or rec.get("error"):
            err = rec.get("error", "execution failed")
            blunders.append(f"Attempt {idx} [{family}]: Crashed with '{err[:100]}'")
        elif delta is not None and isinstance(delta, (int, float)) and delta < 0:
            blunders.append(f"Attempt {idx} [{family}]: Metric degraded by {delta:.4f}. Avoid this architecture/hyperparameter range.")

    if current_best is not None:
        lines.append(f"Current Best Validation Score: {current_best:.4f}")

    if blunders:
        lines.append("\n=== RECORDED BLUNDERS / MISTAKES TO AVOID ===")
        for b in blunders[-5:]:  # Show up to 5 most recent blunders
            lines.append(f"CRITICAL: {b}")
        lines.append("DO NOT repeat the above blunders, failing configurations, or degraded model families.")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Coder Private Execution & Error Tracking
# ---------------------------------------------------------------------------

def format_coder_private_history(private_memories: Optional[dict]) -> str:
    """
    Summarizes recent script execution failures and patterns from Coder's private memory.
    """
    coder_records = (private_memories or {}).get("coder", [])
    if not coder_records:
        return ""

    failures = []
    for rec in coder_records[-6:]:
        if isinstance(rec, dict) and not rec.get("success", True):
            err = rec.get("stderr") or rec.get("error", "")
            if err:
                first_line = err.strip().splitlines()[-1][:150]
                failures.append(first_line)

    if not failures:
        return ""

    lines = ["\n[Coder Private Memory: Avoid repeating recent execution mistakes]"]
    for f in failures[-3:]:
        lines.append(f"- Previous error: {f}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Open Memory Summarizer for Executive Agents (Supervisor, Judge, Reporter)
# ---------------------------------------------------------------------------

def format_open_memory_digest(
    open_summary: Optional[dict],
    state: Optional[dict] = None,
    max_chars: int = 2500,
) -> str:
    """
    Formats a concise, structured executive summary across all pipeline stages.
    Bounded strictly in length to prevent LLM context blowup and token size leaks.
    """
    summary = dict(open_summary or {})
    sections = []

    # 1. Profiler Stage (Read-only summary of facts)
    prof_text = summary.get("profiler")
    if not prof_text and state and state.get("profile"):
        prof = state["profile"]
        n_rows = prof.get("rows") or prof.get("n_rows", "unknown")
        n_cols = prof.get("columns") or len(prof.get("features", []))
        target = state.get("target_column") or prof.get("target_column", "none")
        task = state.get("task_type") or prof.get("task_type", "unknown")
        metric = prof.get("recommended_metric", "accuracy")
        flags = prof.get("data_quality_flags", [])
        flag_str = f" Flags: {flags}." if flags else ""
        prof_text = f"Dataset: {n_rows} rows x {n_cols} cols. Task: {task}. Target: '{target}'. Metric: {metric}.{flag_str}"
    if prof_text:
        sections.append(f"[Profiler]: {str(prof_text).strip()}")

    # 2. EDA Stage
    eda_text = summary.get("eda")
    if not eda_text and state and state.get("eda_findings"):
        findings = state["eda_findings"]
        iters = findings.get("iterations_run", 0)
        exit_r = findings.get("exit_reason", "completed")
        narrative = (findings.get("narrative") or "")[:200]
        eda_text = f"Completed {iters} iterations ({exit_r}). {narrative}"
    if eda_text:
        sections.append(f"[EDA]: {str(eda_text).strip()}")

    # 3. Features Stage
    feat_text = summary.get("features")
    if not feat_text and state and state.get("feature_set"):
        fset = state["feature_set"]
        iters = fset.get("iterations_run", 0)
        exit_r = fset.get("exit_reason", "completed")
        t_path = state.get("transformed_dataset_path") or "baseline"
        feat_text = f"Completed {iters} feature steps ({exit_r}). Active dataset: {t_path}"
    if feat_text:
        sections.append(f"[Features]: {str(feat_text).strip()}")

    # 4. Modeler Stage
    model_text = summary.get("modeler")
    if not model_text and state and state.get("candidate_models"):
        candidates = state["candidate_models"]
        best_m = state.get("best_metric")
        best_str = f"{best_m:.4f}" if isinstance(best_m, (int, float)) else str(best_m)
        families = list({m.get("model_family", "unknown") for m in candidates})
        model_text = f"Trained {len(candidates)} candidate models across families {families}. Best score: {best_str}."
    if model_text:
        sections.append(f"[Modeler]: {str(model_text).strip()}")

    # 5. Judge Stage
    judge_text = summary.get("judge")
    if not judge_text and state and state.get("last_verdict"):
        verdict = state.get("last_verdict")
        feedback = (state.get("judge_feedback") or "")[:200]
        judge_text = f"Verdict: {verdict}. Feedback: {feedback}"
    if judge_text:
        sections.append(f"[Judge]: {str(judge_text).strip()}")

    # 6. Recent Events
    events = summary.get("recent_events", [])
    if events:
        sections.append(f"[Recent Milestones]: {'; '.join(str(e) for e in events[-3:])}")

    if not sections:
        return "Pipeline initialized; no phase summaries recorded yet."

    digest = "\n".join(sections)
    return digest[:max_chars]
