"""
Shared by EDA, Features, and Modeler. Its only job is "does the code run correctly."
It does NOT judge whether the analysis/feature/model is good — that's the calling
agent's job (see each agent's exploration loop).

Execution goes through the real MCP server (tools/mcp_client.py -> mcp_server/
python_exec_server.py) by default. If spawning the MCP server fails for any reason
(package missing, platform issue, etc.), this falls back to the direct in-process
call in tools/python_exec_tool.py — same contract either way, so nothing downstream
needs to know which path ran. Set PIPELINE_USE_MCP_EXEC=0 to skip MCP entirely.
"""
import os
import json
import asyncio
import threading
from langchain_ollama import ChatOllama
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

from tools.python_exec_tool import run_python_exec
from tools.mcp_client import run_python_exec_via_mcp
from tools.streaming import stream_text
from tools.logger import get_logger, log_event, step_timer

_USE_MCP = os.environ.get("PIPELINE_USE_MCP_EXEC", "1") != "0"


def _make_llm():
    return ChatOllama(
        model="glm-5.3-flash:cloud",
        base_url="https://ollama.com",
        client_kwargs={"headers": {"Authorization": f"Bearer {os.getenv('OLLAMA_API_KEY')}"}},
        temperature=0,
    )


def _run_coro_sync(coro):
    """Run an async coroutine from sync code, safe whether or not an event loop is
    already running in this thread (LangGraph's sync .stream() has none, but this
    stays robust if the pipeline is ever driven via .astream() instead)."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    result_box = {}

    def _runner():
        result_box["value"] = asyncio.run(coro)

    thread = threading.Thread(target=_runner)
    thread.start()
    thread.join()
    return result_box["value"]


def _execute(code: str, input_paths: dict, output_path: str, timeout: int, run_id: str) -> dict:
    """Execute via MCP if enabled, falling back to the direct call on any failure."""
    log_key = run_id or "coder_agent_unscoped"
    if _USE_MCP:
        try:
            return _run_coro_sync(
                run_python_exec_via_mcp(code, input_paths, output_path, timeout=timeout, run_id=run_id)
            )
        except Exception as exc:
            get_logger(log_key).warning(
                "coder_agent: MCP exec failed (%s), falling back to direct call", exc
            )
            log_event(log_key, "coder_agent", "mcp_fallback", error=str(exc))
    return run_python_exec(code, input_paths, output_path, timeout=timeout, run_id=run_id)


def coder_agent(
    task_spec: str,
    input_paths: dict,
    output_path: str,
    context: dict,
    max_attempts: int = 4,
    run_id: str = None,
    timeout: int = 60,
) -> dict:
    """
    task_spec: short natural-language description of what code should accomplish
               (written by the calling agent — EDA/Features/Modeler — not by Coder itself).
    input_paths: if a "dataset" entry is present, its containing directory is
               auto-added as "dataset_dir" (-> INPUT_DATASET_DIR) so generated code can
               resolve relative image/audio file paths that live inside table columns
               (Kaggle-style CV/NLP/audio datasets — see profiler_agent's modality
               detection for how those columns get flagged).
    timeout: seconds allowed per execution attempt. Bump this for non-tabular
               modalities (image/audio decoding, embedding models) — callers pass a
               higher value when profile["modality_summary"] indicates it's needed.
    Returns: {"success": bool, "code": str, "stdout": str, "output_path": str|None, "attempts": int}
    """
    input_paths = dict(input_paths)
    if "dataset" in input_paths and "dataset_dir" not in input_paths:
        input_paths["dataset_dir"] = os.path.dirname(os.path.abspath(input_paths["dataset"])) or "."

    llm = _make_llm()

    system_prompt = f"""You are the Coder sub-agent. Write a complete, self-contained Python
script that accomplishes the task below. Read inputs from paths given in environment variables
(INPUT_<KEY> per the input_paths keys, uppercased), write your result to the path in
OUTPUT_PATH. Print concise findings to stdout. Do not hardcode a fixed technique — use
whatever approach best fits the actual data characteristics given in the context below.

This dataset may be tabular, or a Kaggle-style table that references other modalities
through its columns (check context["profile"]["features"][*]["modality"] if present):
  - "numerical" / "categorical": handle with pandas/numpy/sklearn/scipy as usual.
  - "free_text": a column of raw natural-language strings — use sklearn's text
    vectorizers (TfidfVectorizer/CountVectorizer), or sentence-transformers/
    transformers if installed, for embeddings or NLP features.
  - "image_path": a column of file paths to images, relative to INPUT_DATASET_DIR if
    not absolute — resolve with os.path.join(os.environ["INPUT_DATASET_DIR"], value)
    when the value isn't already absolute. Use PIL/Pillow for basic stats, or
    torchvision/timm for embeddings/models if installed.
  - "audio_path": same path-resolution rule as image_path — use librosa/soundfile/
    torchaudio if installed.
  If a needed library isn't installed, prefer a simpler approach over failing (e.g.
  fall back to file-size/duration-only stats for audio rather than crashing).

Task:
{task_spec}

Rules:
- Read input files from `os.environ["INPUT_<KEY>"]` (e.g. `INPUT_DATASET`).
- If generating plots with matplotlib/seaborn, ALWAYS use the headless Agg backend:
  `import matplotlib; matplotlib.use('Agg')` BEFORE `import matplotlib.pyplot as plt`.
- Write your primary result to `os.environ["OUTPUT_PATH"]` using the matching file format (e.g. `json.dump` if `.json`, `to_csv` if `.csv`, `to_parquet` if `.parquet`).
- Ensure parent output directories exist: `os.makedirs(os.path.dirname(os.path.abspath(os.environ["OUTPUT_PATH"])), exist_ok=True)`.
- Print concise findings and summary lines to stdout.

Context (profile/state relevant to this task):
{json.dumps(context, default=str, indent=2)}

Input paths available: {list(input_paths.keys())}

Output ONLY the Python code, no markdown fences, no commentary."""

    log_key = run_id or "coder_agent_unscoped"
    messages = [SystemMessage(content=system_prompt)]
    code, result = "", {"stdout": ""}

    for attempt in range(1, max_attempts + 1):
        with step_timer(log_key, "coder_agent", f"generate_attempt_{attempt}"):
            response_text = stream_text(
                llm, messages, run_id=run_id, agent=f"coder_agent(attempt {attempt})",
            )
        code = response_text.strip().removeprefix("```python").removesuffix("```").strip()

        with step_timer(log_key, "coder_agent", f"execute_attempt_{attempt}"):
            result = _execute(code, input_paths, output_path, timeout, run_id)

        log_event(log_key, "coder_agent", "attempt_result", attempt=attempt,
                  success=result["success"], code=code,
                  stdout=result.get("stdout", ""), stderr=result.get("stderr", ""))

        if result["success"]:
            return {
                "success": True, "code": code, "stdout": result["stdout"],
                "output_path": result["output_path"], "attempts": attempt,
            }

        messages.append(AIMessage(content=response_text))
        messages.append(HumanMessage(content=(
            f"The code failed. stderr:\n{result['stderr']}\nFix it and return the complete "
            f"corrected script (no markdown fences, no commentary)."
        )))

    return {
        "success": False, "code": code, "stdout": result.get("stdout", ""),
        "output_path": None, "attempts": max_attempts,
    }
