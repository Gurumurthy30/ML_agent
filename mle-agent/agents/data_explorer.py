import os
import json
from pathlib import Path
from typing import Dict, Any

from graph.state import AgentState
from config.settings import get_settings
from tools.mle_dojo_mcp import get_mle_dojo_client
from agents.utils import call_llm, extract_json

def data_explorer_node(state: AgentState) -> AgentState:
    """
    Data Explorer Agent Node.
    Runs once at start. Reads task info, runs EDA prompt, and writes state/task_context.json.
    """
    settings = get_settings()
    client = get_mle_dojo_client(use_mock=settings.mle_dojo.use_mock)
    
    # 1. Fetch info from MLE-Dojo tool
    info = client.request_info()

    # 2. Read system prompt
    prompt_path = Path(__file__).parent.parent / "prompts" / "data_explorer_prompt.md"
    with open(prompt_path, "r", encoding="utf-8") as f:
        system_prompt = f.read()

    user_prompt = f"Analyze the following dataset information and produce a structured task_context JSON:\n{json.dumps(info, indent=2)}"

    task_context = None
    if not settings.mle_dojo.use_mock:
        try:
            raw_resp = call_llm(system_prompt, user_prompt)
            task_context = extract_json(raw_resp)
        except Exception as e:
            print(f"[DataExplorer Node] LLM call failed or offline, falling back to tool info: {e}")

    if not task_context:
        task_context = {
            "task_id": info.get("task_id", "task_01"),
            "task_name": info.get("task_name", "Kaggle Benchmark Task"),
            "modality": info.get("modality", "tabular"),
            "target_column": info.get("target_column", "target"),
            "metric": info.get("metric", "roc_auc"),
            "train_shape": info.get("train_shape", [10000, 25]),
            "test_shape": info.get("test_shape", [2500, 24]),
            "eda_summary": {
                "missing_values_flag": False,
                "class_imbalance_flag": False,
                "potential_leakage_notes": "None detected in preliminary check."
            },
            "sample_submission_format": info.get("sample_submission_format", {
                "id_column": "id",
                "pred_column": "target"
            })
        }

    # Write task_context.json to disk
    state_dir = Path(__file__).parent.parent / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    task_context_path = state_dir / "task_context.json"
    with open(task_context_path, "w", encoding="utf-8") as f:
        json.dump(task_context, f, indent=2)

    state["task_context"] = task_context
    state["status"] = "planning"
    return state
