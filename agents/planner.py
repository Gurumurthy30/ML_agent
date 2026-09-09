import os
import json
import time
from pathlib import Path
from typing import Dict, Any, List

from graph.state import AgentState
from graph.budget_guard import enforce_budget
from config.settings import get_settings
from rag import query_library_docs, query_technique_cheatsheet
from agents.utils import call_llm, extract_json

def planner_node(state: AgentState) -> AgentState:
    """
    Planner Agent Node.
    Drafts the next experiment spec based on task_context, experiment_log.jsonl, last redirect/escalation, and RAG hints.
    Enforces budget before calling RAG/LLM tools.
    """
    start_time = time.time()
    state, is_exhausted = enforce_budget(state, action_cost=1)
    if is_exhausted:
        return state

    settings = get_settings()
    base_dir = Path(__file__).parent.parent
    log_path = base_dir / "state" / "experiment_log.jsonl"

    # Read log
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

    # Determine adaptive reasoning mode
    last_redirect = state.get("last_redirect")
    redirect_reason = last_redirect.get("reason") if last_redirect else None
    
    if exp_count == 1 or redirect_reason in ["plateaued", "high_variance", "near_tied"]:
        reasoning_mode = "tot"
    else:
        reasoning_mode = state.get("reasoning_mode", "default")

    state["reasoning_mode"] = reasoning_mode

    # RAG Lookups
    modality = state.get("task_context", {}).get("modality", "tabular")
    rag_docs = query_library_docs(f"{modality} cross validation feature engineering", top_k=2)
    rag_cheats = query_technique_cheatsheet(f"{modality} techniques and hyperparameter optimization", top_k=2)

    # Read system prompt
    prompt_path = base_dir / "prompts" / "planner_prompt.md"
    with open(prompt_path, "r", encoding="utf-8") as f:
        system_prompt = f.read()

    user_prompt_data = {
        "experiment_id": exp_id,
        "reasoning_mode": reasoning_mode,
        "task_context": state.get("task_context", {}),
        "experiment_log_summary": log_entries[-5:],  # Last 5 experiments
        "last_redirect": last_redirect,
        "last_escalation": state.get("last_escalation"),
        "rag_documentation_snippets": rag_docs,
        "rag_technique_snippets": rag_cheats
    }

    user_prompt = f"Design experiment {exp_id}. Current state & history:\n{json.dumps(user_prompt_data, indent=2)}"

    spec = None
    if not settings.mle_dojo.use_mock:
        try:
            raw_resp = call_llm(system_prompt, user_prompt)
            spec = extract_json(raw_resp)
        except Exception as e:
            print(f"[Planner Node] LLM call failed or offline: {e}")

    if not spec:
        # Fallback structured spec matching exact schema
        if exp_count == 1:
            approach_type = "baseline"
            model_family = "LightGBM" if modality == "tabular" else "BaselineModel"
            rationale = "Initial baseline experiment to establish cross-validation benchmark."
            fe_notes = "Standard missing value imputation and ordinal/one-hot encoding."
            hparams = {"n_estimators": 500, "learning_rate": 0.05, "max_depth": 6}
        elif redirect_reason == "near_tied":
            approach_type = "ensemble"
            model_family = "WeightedBlend"
            rationale = "Ensembling top near-tied candidates across out-of-fold predictions."
            fe_notes = "Rank average of out-of-fold prediction probabilities."
            hparams = {"blend_weights": [0.5, 0.5]}
        else:
            approach_type = "variant"
            model_family = "CatBoost" if modality == "tabular" else "VariantModel"
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
            "hyperparameter_ranges": hparams
        }

    # Deduct time taken
    elapsed_minutes = (time.time() - start_time) / 60.0
    state, _ = enforce_budget(state, action_cost=0, elapsed_minutes=elapsed_minutes)

    state["current_spec"] = spec
    state["status"] = "coding"
    return state
