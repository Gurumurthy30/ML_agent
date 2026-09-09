import json
import time
import re
from pathlib import Path
from typing import Dict, Any

from graph.state import AgentState
from graph.budget_guard import enforce_budget
from config.settings import get_settings
from tools.mle_dojo_mcp import get_mle_dojo_client
from rag import query_library_docs
from agents.utils import call_llm, extract_json

def coder_node(state: AgentState) -> AgentState:
    """
    Coder Agent Node.
    Implements Planner's spec as self-validated Python code or raises an escalation.
    Enforces budget before calling tools/LLM.
    """
    start_time = time.time()
    state, is_exhausted = enforce_budget(state, action_cost=1)
    if is_exhausted:
        return state

    settings = get_settings()
    client = get_mle_dojo_client(use_mock=settings.mle_dojo.use_mock)

    spec = state.get("current_spec") or {}
    modality = spec.get("modality", "tabular")

    # Load router prompt + matching modality file only
    base_dir = Path(__file__).parent.parent
    index_prompt_path = base_dir / "prompts" / "coder" / "index_prompt.md"
    modality_prompt_path = base_dir / "prompts" / "coder" / f"{modality}.md"

    with open(index_prompt_path, "r", encoding="utf-8") as f:
        router_prompt = f.read()

    modality_guide = ""
    if modality_prompt_path.exists():
        with open(modality_prompt_path, "r", encoding="utf-8") as f:
            modality_guide = f.read()

    system_prompt = f"{router_prompt}\n\n## Modality Specific Guidelines ({modality})\n{modality_guide}"

    # RAG lookup for code libraries
    model_family = spec.get("model_family", "GBDT")
    library_docs = query_library_docs(f"{model_family} python implementation cross validation", top_k=2)

    user_prompt_data = {
        "spec": spec,
        "task_context": state.get("task_context", {}),
        "library_docs": library_docs
    }

    user_prompt = f"Implement Python code for the following experiment spec:\n{json.dumps(user_prompt_data, indent=2)}"

    generated_code = None
    escalation = None

    if not settings.mle_dojo.use_mock:
        try:
            raw_resp = call_llm(system_prompt, user_prompt)
            # Check if LLM output an escalation JSON
            parsed_json = extract_json(raw_resp)
            if parsed_json and "escalation_type" in parsed_json:
                escalation = parsed_json
            else:
                # Extract code block
                code_match = re.search(r"```python\s*(.*?)\s*```", raw_resp, re.DOTALL)
                if code_match:
                    generated_code = code_match.group(1)
                else:
                    generated_code = raw_resp
        except Exception as e:
            print(f"[Coder Node] LLM call failed or offline: {e}")

    # If mock mode or LLM call fallback
    if not generated_code and not escalation:
        # Check mock validation logic
        sample_code = f"""
# Implementation for experiment {spec.get('experiment_id', 'exp_001')}
import pandas as pd
import numpy as np
from sklearn.model_selection import StratifiedKFold
from sklearn.metrics import roc_auc_score

print("Running pipeline for {spec.get('experiment_id', 'exp_001')}...")
"""
        val_res = client.validate_code(sample_code)
        if val_res["valid"]:
            generated_code = sample_code
        else:
            escalation = {
                "experiment_id": spec.get("experiment_id", "exp_001"),
                "escalation_type": "infeasible_library",
                "blocking": True,
                "description": f"Validation failed: {val_res.get('error')}",
                "proposed_workaround": "Switch to standard LightGBM baseline."
            }

    elapsed_minutes = (time.time() - start_time) / 60.0
    state, _ = enforce_budget(state, action_cost=0, elapsed_minutes=elapsed_minutes)

    if escalation:
        state["last_escalation"] = escalation
        state["status"] = "planning"  # Route back to Planner
    else:
        state["last_escalation"] = None
        state["current_spec"]["validated_code"] = generated_code
        state["status"] = "executing"

    return state
