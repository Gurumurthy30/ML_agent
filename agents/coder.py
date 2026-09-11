import json
import time
import re
from pathlib import Path
from typing import Dict, Any

from graph.state import AgentState
from graph.budget_guard import enforce_budget
from config.settings import get_settings
from tools.local_env_mcp import LocalEnvMCP
from tools.rag_mcp import RagMCP
from agents.utils import call_llm, extract_json, push_event


def coder_node(state: AgentState) -> AgentState:
    """
    Coder Agent Node (v2).

    Changes from v1:
    - Uses local_env_mcp for validate_code (real import resolution, not just ast.parse).
    - Role-based LLM routing: "coder" → Groq primary / Google fallback.
    - Emits tool_call/tool_result events for validate_code.
    - Emits code_block event with the generated code.
    - Emits node_start / node_end events.
    """
    push_event(state, {"type": "node_start", "node": "coder"})

    start_time = time.time()
    state, is_exhausted = enforce_budget(state, action_cost=1)
    if is_exhausted:
        push_event(state, {"type": "node_end", "node": "coder"})
        return state

    settings = get_settings()
    dry_run = state.get("dry_run", False)
    session_id = state.get("session_id", "default")
    sessions_root = settings.sessions.storage_path

    mcp = LocalEnvMCP(
        session_id=session_id,
        sessions_root=sessions_root,
        exec_timeout=settings.sessions.exec_timeout_seconds,
        dry_run=dry_run,
    )
    rag = RagMCP()

    spec = state.get("current_spec") or {}
    modality = spec.get("modality", "tabular")

    # Load router prompt + modality guide
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

    # RAG lookup
    model_family = spec.get("model_family", "GBDT")
    rag_query = f"{model_family} python implementation cross validation"
    push_event(state, {"type": "tool_call", "node": "coder", "tool": "search_library_docs",
                       "input": {"query": rag_query, "top_k": 2}})
    library_docs = rag.search_library_docs(rag_query, top_k=2)
    push_event(state, {"type": "tool_result", "node": "coder", "tool": "search_library_docs",
                       "output": {"results_count": len(library_docs)}})

    task_ctx = state.get("task_context", {})
    session_data_dir = state.get("session_data_dir", task_ctx.get("session_data_dir", ""))

    user_prompt_data = {
        "spec": spec,
        "task_context": task_ctx,
        "user_message": state.get("user_message", ""),
        "session_data_dir": session_data_dir,
        "library_docs": library_docs,
    }
    user_prompt = (
        f"Implement Python code for the following experiment spec.\n"
        f"IMPORTANT: The training data is at: {session_data_dir}\n"
        "Print CV metrics to stdout as:\n"
        '  print(f\'CV_RESULT: {{"cv_mean": {mean:.6f}, "cv_std": {std:.6f}}}\')\n\n'
        f"{json.dumps(user_prompt_data, indent=2)}"
    )

    generated_code = None
    escalation = None

    try:
        raw_resp, has_thinking = call_llm(system_prompt, user_prompt, role="coder", dry_run=dry_run)
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
        print(f"[Coder] LLM call failed: {e}")

    # If no code generated, produce a minimal fallback
    if not generated_code and not escalation:
        generated_code = (
            f"# Fallback pipeline for {spec.get('experiment_id', 'exp_001')}\n"
            f"import pandas as pd\nimport numpy as np\n"
            f"from sklearn.model_selection import StratifiedKFold\n"
            f"from sklearn.metrics import roc_auc_score\n"
            f"print('CV_MEAN=0.0000')\nprint('CV_STD=0.0000')\n"
        )

    # Validate generated code via MCP tool
    if generated_code and not dry_run:
        push_event(state, {"type": "tool_call", "node": "coder", "tool": "validate_code",
                           "input": {"code_length": len(generated_code)}})
        val_res = mcp.validate_code(generated_code)
        push_event(state, {"type": "tool_result", "node": "coder", "tool": "validate_code",
                           "output": val_res})

        if not val_res["valid"]:
            escalation = {
                "experiment_id": spec.get("experiment_id", "exp_001"),
                "escalation_type": "infeasible_library",
                "blocking": True,
                "description": f"Code validation failed: {val_res.get('error')}",
                "proposed_workaround": "Switch to a simpler approach using only standard libraries.",
            }
            generated_code = None
        elif val_res.get("warnings"):
            # Emit warnings but continue
            push_event(state, {"type": "assistant_message", "node": "coder",
                               "content": f"⚠️ Validation warnings: {'; '.join(val_res['warnings'])}"})

    # Emit code_block event
    if generated_code:
        push_event(state, {
            "type": "code_block",
            "node": "coder",
            "language": "python",
            "content": generated_code,
        })

    elapsed_minutes = (time.time() - start_time) / 60.0
    state, _ = enforce_budget(state, action_cost=0, elapsed_minutes=elapsed_minutes)

    push_event(state, {"type": "node_end", "node": "coder"})

    if escalation:
        state["last_escalation"] = escalation
        state["status"] = "planning"
    else:
        state["last_escalation"] = None
        state["current_spec"]["validated_code"] = generated_code
        state["status"] = "executing"

    return state
