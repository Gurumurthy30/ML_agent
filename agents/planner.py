import json
import time
from pathlib import Path
from typing import Dict, Any, List

from graph.state import AgentState
from graph.budget_guard import enforce_budget
from config.settings import get_settings
from tools.rag_mcp import RagMCP
from agents.utils import call_llm, extract_json, push_event

# Human-in-the-loop support (LangGraph interrupt)
try:
    from langgraph.types import interrupt, Command
    HAS_INTERRUPT = True
except ImportError:
    HAS_INTERRUPT = False


def _should_ask_human(state: AgentState) -> tuple[bool, str, str]:
    """
    Decides whether Planner should interrupt for a human clarification.

    Per brief §3: ask ONLY when:
      (a) target_confidence == "defaulted" AND multiple plausible targets exist
      (b) User's stated goal is contradictory or too vague to act on

    Does NOT ask about: metric choice, hyperparameters, anything with a
    defensible ML-best-practice default.

    Returns (should_ask: bool, question: str, context: str)
    """
    task_ctx = state.get("task_context", {})
    target_confidence = state.get("target_confidence", task_ctx.get("target_confidence", "explicit"))
    user_message = state.get("user_message", "")
    col_names = task_ctx.get("column_names", [])

    # (a) Defaulted target — but only if there are multiple plausible candidates
    if target_confidence == "defaulted" and len(col_names) >= 3:
        # Check whether multiple columns look like plausible targets
        # (name-matched patterns that weren't the actual last column)
        from session.init import _TARGET_NAME_PATTERNS
        plausible = [c for c in col_names if c.lower() in _TARGET_NAME_PATTERNS]
        last_col = col_names[-1] if col_names else None
        if len(plausible) > 1 or (last_col and plausible and plausible[0] != last_col):
            return (
                True,
                f"I defaulted to `{task_ctx.get('target_column')}` as the prediction target because I couldn't infer it from your message. "
                f"The dataset also has these columns that look like potential targets: **{', '.join(plausible)}**. "
                f"Which column should I predict?",
                f"Columns: {col_names}. Target guessed: {task_ctx.get('target_column')!r} (confidence: defaulted).",
            )

    # (b) Goal too vague or contradictory (no task intent words at all)
    from session.init import _TARGET_INTENT_WORDS
    has_intent = any(kw in user_message.lower() for kw in _TARGET_INTENT_WORDS)
    if not has_intent and len(user_message.strip()) < 20:
        return (
            True,
            "What would you like to predict or classify in this dataset? "
            "Please describe the task (e.g. 'predict customer churn', 'classify images by category').",
            f"User message was too short/vague to infer a task: {user_message!r}",
        )

    return False, "", ""


def planner_node(state: AgentState) -> AgentState:
    """
    Planner Agent Node (v2).

    Changes from v1:
    - TASK_CONTEXT is the full rendered EDA report + user's original chat message.
    - Human-in-the-loop via LangGraph interrupt() per brief §3 (when to ask, when not to).
    - Role-based LLM routing: planner_deep (NIM DeepSeek) for ToT, planner_default (Groq/Google) otherwise.
    - Emits thinking/tool_call/tool_result events to state event_queue (only real traces, never synthesised).
    - Reads experiment log from session-scoped path.
    """
    push_event(state, {"type": "node_start", "node": "planner"})

    start_time = time.time()
    state, is_exhausted = enforce_budget(state, action_cost=1)
    if is_exhausted:
        push_event(state, {"type": "node_end", "node": "planner"})
        return state

    settings = get_settings()
    dry_run = state.get("dry_run", False)
    session_id = state.get("session_id", "default")
    sessions_root = settings.sessions.storage_path

    # Session-scoped experiment log
    log_path = Path(sessions_root) / session_id / "experiment_log.jsonl"
    log_entries: List[Dict[str, Any]] = []
    if log_path.exists():
        with open(log_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        log_entries.append(json.loads(line))
                    except Exception:
                        pass

    exp_count = len(log_entries) + 1
    exp_id = f"exp_{exp_count:03d}"

    # ── Human-in-the-loop check ───────────────────────────────────────────
    # Only on the very first round (no log yet) — subsequent rounds have enough context.
    if exp_count == 1 and not dry_run:
        should_ask, question, context = _should_ask_human(state)
        if should_ask and HAS_INTERRUPT:
            push_event(state, {
                "type": "human_input_request",
                "question": question,
                "context": context,
            })
            state["pending_human_question"] = {"question": question, "context": context}
            state["status"] = "waiting_for_human"
            # interrupt() pauses the LangGraph graph; the WebSocket layer resumes via
            # graph.invoke(Command(resume=user_reply), config) once the user answers.
            human_answer = interrupt({"question": question, "context": context})
            # Execution resumes here after the user replies
            state["human_answer"] = human_answer
            state["user_message"] = human_answer  # update task context with clarification
            state["pending_human_question"] = None

    # ── Reasoning mode ────────────────────────────────────────────────────
    last_redirect = state.get("last_redirect")
    redirect_reason = last_redirect.get("reason") if last_redirect else None
    if exp_count == 1 or redirect_reason in ["plateaued", "high_variance", "near_tied"]:
        reasoning_mode = "tot"
    else:
        reasoning_mode = state.get("reasoning_mode", "default")
    state["reasoning_mode"] = reasoning_mode
    role = "planner_deep" if reasoning_mode == "tot" else "planner_default"

    # ── RAG lookups (emitted as tool_call / tool_result events) ──────────
    task_ctx = state.get("task_context", {})
    modality = task_ctx.get("modality", "tabular")
    rag = RagMCP()

    rag_docs_query = f"{modality} cross validation feature engineering"
    push_event(state, {"type": "tool_call", "node": "planner", "tool": "search_library_docs",
                       "input": {"query": rag_docs_query, "top_k": 2}})
    rag_docs = rag.search_library_docs(rag_docs_query, top_k=2)
    push_event(state, {"type": "tool_result", "node": "planner", "tool": "search_library_docs",
                       "output": {"results_count": len(rag_docs)}})

    rag_cheats_query = f"{modality} techniques and hyperparameter optimization"
    push_event(state, {"type": "tool_call", "node": "planner", "tool": "search_technique_cheatsheet",
                       "input": {"query": rag_cheats_query, "modality": modality, "top_k": 2}})
    rag_cheats = rag.search_technique_cheatsheet(rag_cheats_query, modality=modality, top_k=2)
    push_event(state, {"type": "tool_result", "node": "planner", "tool": "search_technique_cheatsheet",
                       "output": {"results_count": len(rag_cheats)}})

    # ── System prompt ─────────────────────────────────────────────────────
    base_dir = Path(__file__).parent.parent
    prompt_path = base_dir / "prompts" / "planner_prompt.md"
    with open(prompt_path, "r", encoding="utf-8") as f:
        system_prompt = f.read()

    # ── User prompt: full EDA report + original chat message ─────────────
    eda_report = state.get("eda_report_markdown", task_ctx.get("eda_prompt_summary", ""))
    human_answer = state.get("human_answer")

    user_prompt_data = {
        "experiment_id": exp_id,
        "reasoning_mode": reasoning_mode,
        "task_context": task_ctx,
        "user_message": state.get("user_message", ""),
        "human_clarification": human_answer,
        "experiment_log": log_entries,           # full log, not just last 5
        "last_redirect": last_redirect,
        "last_escalation": state.get("last_escalation"),
        "budget": {
            "actions_remaining": state.get("actions_remaining"),
            "time_remaining_minutes": state.get("time_remaining"),
        },
        "rag_documentation_snippets": rag_docs,
        "rag_technique_snippets": rag_cheats,
    }

    user_prompt = (
        f"## TASK_CONTEXT\n\n{eda_report}\n\n"
        f"**User's Original Request:** {state.get('user_message', '')}\n"
        + (f"**User Clarification:** {human_answer}\n" if human_answer else "")
        + f"\n---\n"
        f"Design experiment {exp_id}. Current state & history:\n"
        f"{json.dumps(user_prompt_data, indent=2, default=str)}"
    )

    # ── LLM call ──────────────────────────────────────────────────────────
    spec = None
    try:
        raw_resp, has_thinking = call_llm(
            system_prompt, user_prompt,
            role=role, dry_run=dry_run
        )
        # Only emit thinking event if provider actually returned a real trace
        if has_thinking:
            push_event(state, {"type": "thinking", "node": "planner", "content": raw_resp[:4000]})
        spec = extract_json(raw_resp)
    except Exception as e:
        print(f"[Planner] LLM call failed: {e}")

    # ── Fallback spec ─────────────────────────────────────────────────────
    if not spec:
        if exp_count == 1:
            approach_type, model_family = "baseline", "LightGBM" if modality == "tabular" else "BaselineModel"
            rationale = "Initial baseline experiment to establish cross-validation benchmark."
            fe_notes = "Standard missing value imputation and ordinal/one-hot encoding."
            hparams = {"n_estimators": 500, "learning_rate": 0.05, "max_depth": 6}
        elif redirect_reason == "near_tied":
            approach_type, model_family = "ensemble", "WeightedBlend"
            rationale = "Ensembling top near-tied candidates across out-of-fold predictions."
            fe_notes = "Rank average of out-of-fold prediction probabilities."
            hparams = {"blend_weights": [0.5, 0.5]}
        else:
            approach_type, model_family = "variant", "CatBoost" if modality == "tabular" else "VariantModel"
            rationale = f"Testing model family variation for round {exp_count}."
            fe_notes = "Target encoding for categorical columns and ratio features."
            hparams = {"iterations": 1000, "learning_rate": 0.03, "depth": 6}
        spec = {
            "experiment_id": exp_id,
            "approach_type": approach_type,
            "model_family": model_family,
            "modality": modality,
            "reasoning_mode": reasoning_mode,
            "approach_rationale": rationale,
            "feature_engineering_notes": fe_notes,
            "hyperparameter_ranges": hparams,
        }

    elapsed_minutes = (time.time() - start_time) / 60.0
    state, _ = enforce_budget(state, action_cost=0, elapsed_minutes=elapsed_minutes)

    push_event(state, {"type": "node_end", "node": "planner"})

    state["current_spec"] = spec
    state["status"] = "coding"
    return state
