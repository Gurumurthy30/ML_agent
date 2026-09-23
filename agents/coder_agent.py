"""
Shared by EDA, Features, and Modeler. Its only job is "does the code run correctly."
It does NOT judge whether the analysis/feature/model is good — that's the calling
agent's job (see each agent's exploration loop).

Execution goes through the real MCP server (tools/mcp_client.py ->
mcp_server/python_exec_server.py) by default. If spawning the MCP server fails for any reason
(package missing, platform issue, etc.), this falls back to the direct in-process
call in tools/python_exec_tool.py — same contract either way, so nothing downstream
needs to know which path ran. Set PIPELINE_USE_MCP_EXEC=0 to skip MCP entirely.

parent_agent / parent_iteration: passed by EDA/Features/Modeler so every Coder
log event is attributed to the correct parent turn, not a generic "coder_agent" bucket.
The UI uses these to nest Coder sub-cards inside the parent agent's turn card.
"""
import os
import json
import asyncio
import threading
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

from tools.llm import get_llm
from tools.python_exec_tool import run_python_exec
from tools.mcp_client import run_python_exec_via_mcp
from tools.streaming import stream_text
from tools.logger import get_logger, log_event, step_timer

_USE_MCP = os.environ.get("PIPELINE_USE_MCP_EXEC", "1") != "0"


def _run_coro_sync(coro):
    """Run an async coroutine from sync code, safe whether or not an event loop is
    already running in this thread (LangGraph's sync .stream() has none, but this
    stays robust if the pipeline is ever driven via .astream() instead)."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    result_box = {}
    error_box = {}

    def _runner():
        try:
            result_box["value"] = asyncio.run(coro)
        except BaseException as exc:  # noqa: BLE001 - propagate exactly what happened
            error_box["error"] = exc

    thread = threading.Thread(target=_runner)
    thread.start()
    thread.join()

    if "error" in error_box:
        raise error_box["error"]
    return result_box["value"]


_make_llm = lambda *args, **kwargs: get_llm(*args, large=True, **kwargs)


def _execute(code: str, input_paths: dict, output_path: str, timeout: int, run_id: str) -> dict:
    """Execute via MCP if enabled, falling back to the direct call on any failure."""
    log_key = run_id or "coder_agent_unscoped"
    use_mcp = globals().get("_USE_MCP", _USE_MCP)
    if use_mcp:
        try:
            return _run_coro_sync(
                run_python_exec_via_mcp(code, input_paths, output_path, timeout=timeout, run_id=run_id)
            )
        except Exception as exc:
            get_logger(log_key).warning(
                "coder_agent: MCP exec failed (%s), falling back to direct call", exc
            )
            log_event(log_key, "coder_agent", "mcp_fallback", error=str(exc))
    exec_fn = globals().get("run_python_exec", run_python_exec)
    return exec_fn(code, input_paths, output_path, timeout=timeout, run_id=run_id)


def _strip_code_fences(text: str) -> str:
    """Strip a leading/trailing markdown code fence, tolerating ```python, ```py,
    or a bare ``` opener."""
    code = text.strip()
    for prefix in ("```python", "```py", "```"):
        if code.startswith(prefix):
            code = code[len(prefix):]
            break
    return code.removesuffix("```").strip()


def coder_agent(
    task_spec: str,
    input_paths: dict,
    output_path: str,
    context: dict,
    max_attempts: int = 4,
    run_id: str = None,
    timeout: int = 60,
    parent_agent: str = None,
    parent_iteration: int = None,
    private_memory: dict = None,
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
    parent_agent: name of the calling agent (e.g. "eda_agent", "features_agent",
               "modeler_agent"). Included in every log event so the UI can nest
               Coder sub-cards inside the parent agent's turn card.
    parent_iteration: iteration number within the parent's exploration loop.
               Combined with parent_agent for precise sub-card grouping.
    private_memory: optional dictionary containing Coder's private execution memory.
    Returns: {"success": bool, "code": str, "stdout": str, "output_path": str|None, "attempts": int, "private_memory_entry": dict}
    """
    input_paths = dict(input_paths)
    if "dataset" in input_paths and "dataset_dir" not in input_paths:
        input_paths["dataset_dir"] = os.path.dirname(os.path.abspath(input_paths["dataset"])) or "."

    llm = _make_llm()  # Coder uses the larger model for better code generation

    target_column = None
    exclude_columns = None
    feature_columns = None
    if isinstance(context, dict):
        target_column = context.get("target_column")
        exclude_columns = context.get("exclude_columns")
        feature_columns = context.get("feature_columns")
    if not target_column:
        target_column = os.environ.get("TARGET_COLUMN")
    if exclude_columns is None and os.environ.get("EXCLUDE_COLUMNS"):
        exclude_columns = [c.strip() for c in os.environ.get("EXCLUDE_COLUMNS", "").split(",") if c.strip()]

    from utils.run_context import format_run_context, sync_run_context_env
    sync_run_context_env(target_column, exclude_columns)
    run_context_block = format_run_context(target_column, exclude_columns, feature_columns)

    from utils.scoped_memory import format_coder_private_history
    pm = private_memory or (context.get("private_memories") if isinstance(context, dict) else None)
    memory_notes = format_coder_private_history(pm)

    system_prompt = f"""{run_context_block}

You are the Coder sub-agent for a tabular-data ML pipeline. Write a
complete, self-contained Python script that accomplishes the task below. Do not hardcode
a fixed technique — choose whatever approach best fits the actual data characteristics
given in the context.

<io_contract>
- Read input files from `os.environ["INPUT_<KEY>"]` per the input_paths keys listed
  below (e.g. `INPUT_DATASET`).
- To load a dataset from `INPUT_DATASET`: check the file extension:
  if path ends with `.parquet` or `.pq`: use `pd.read_parquet(path)`.
  if path ends with `.csv`: use `pd.read_csv(path)` (with encoding fallback to 'latin1' or on_bad_lines='skip' if needed).
- Loading target and feature columns:
  target_col = os.environ.get("TARGET_COLUMN", "target")
  exclude_cols = [c.strip() for c in os.environ.get("EXCLUDE_COLUMNS", "").split(",") if c.strip()]
  Before building X, ALWAYS drop both target_col and every column in exclude_cols:
      X = df.drop(columns=[c for c in [target_col] + exclude_cols if c in df.columns])
      y = df[target_col] if target_col in df.columns else None
- Inspect column dtypes/characteristics from context to decide preprocessing per column
  (numeric vs categorical vs datetime vs high-cardinality string, etc.) — use
  pandas/numpy/sklearn/scipy as appropriate.
- Write your primary result to `os.environ["OUTPUT_PATH"]` using the format matching its
  extension (supporting both forward and backward slashes on Windows):
  * For `.joblib` (trained models / estimators): use `import joblib; joblib.dump(model, path)`.
  * For `.pkl` or `.pickle`: use `import pickle; pickle.dump(model, open(path, "wb"))`.
  * For `.json`: use `with open(path, "w", encoding="utf-8") as f: json.dump(data, f, default=str, indent=2)` (use default=str so numpy int64/float64 serializes safely).
  * For `.csv`: use `df.to_csv(path, index=False)`.
  * For `.parquet`: use `df.to_parquet(path, index=False)`.
- Never abort or print "Unsupported OUTPUT_PATH extension". Always inspect the extension of `os.environ["OUTPUT_PATH"]` and save accordingly.
- Ensure the parent output directory exists before writing:
  `os.makedirs(os.path.dirname(os.path.abspath(os.environ["OUTPUT_PATH"])), exist_ok=True)`.
</io_contract>

<hard_constraints priority="absolute">
- NO visual plots, charts, or figures — no matplotlib/seaborn figures, no saved image
  files. The pipeline is headless and downstream agents are text-only. If matplotlib is
  imported by any third-party dependency, guard against a display crash by running
  `import matplotlib; matplotlib.use('Agg')` before any plotting import happens.
- Instead of visuals, compute and print detailed numerical summaries to stdout:
  correlation matrices, missing-value tables, distribution/skewness metrics, etc. as
  relevant to the task.
- Set random seeds (e.g. `random_state=42` / `np.random.seed(42)`) wherever
  stochasticity is involved, so results are reproducible across retries.
- For OneHotEncoder: ALWAYS use `OneHotEncoder(handle_unknown="ignore", sparse_output=False)` (NEVER `sparse=False`, which was removed in modern scikit-learn).
- For pandas select_dtypes: When selecting string/object columns, use `df.select_dtypes(include=['object', 'string', 'category'])` to avoid deprecation warnings.
- For VIF (Variance Inflation Factor) / Multicollinearity:
  * Select ONLY numeric columns: `numeric_cols = df.select_dtypes(include=[np.number]).columns`.
  * Drop constant columns (std == 0) and fill missing values before computing VIF.
  * Always wrap VIF calculation in a try/except block; if a singular matrix or LinAlgError occurs, fall back to correlation matrix summary without crashing.
- For cross-validation (cross_val_score / StratifiedKFold):
  * For classification, ensure n_splits does not exceed the minimum class count: `n_splits = min(5, max(2, int(df[target_col].value_counts().min())))`.
  * If sample count is small (< 10), use `n_splits = min(3, len(df))`.
</hard_constraints>

{memory_notes}

Output ONLY the Python code, no markdown fences, no commentary."""

    human_prompt = f"""Please write the complete executable Python script for the following task:

<task>
{task_spec}
</task>

<context>
{json.dumps(context, default=str, indent=2)}
</context>

<input_paths_available>
{list(input_paths.keys())}
</input_paths_available>

Output only the executable Python script."""

    log_key = run_id or "coder_agent_unscoped"
    messages = [SystemMessage(content=system_prompt), HumanMessage(content=human_prompt)]
    code, result = "", {"stdout": ""}

    from tools.tracer import compute_error_signature

    consecutive_empty = 0
    consecutive_error_sig = 0
    last_error_sig = None

    for attempt in range(1, max_attempts + 1):
        if attempt > 1 and run_id:
            from tools.tracer import get_run_control
            if get_run_control(run_id).consume_escape():
                log_event(log_key, "coder_agent", "user_escape_consumed",
                          level="coder_retry", attempt=attempt,
                          parent_agent=parent_agent, parent_iteration=parent_iteration)
                return {
                    "success": False, "code": code, "stdout": result.get("stdout", ""),
                    "output_path": None, "attempts": attempt - 1,
                    "exhausted_early": True,
                    "exit_reason": "user_escape",
                    "escaped": True,
                    "private_memory_entry": {
                        "task_spec": task_spec, "success": False, "code": code,
                        "stderr": result.get("stderr", "Execution skipped via user escape."),
                        "attempts": attempt - 1, "exhausted_early": True,
                        "exit_reason": "user_escape",
                    },
                }

        with step_timer(log_key, "coder_agent", f"generate_attempt_{attempt}"):
            response_text = stream_text(
                llm, messages, run_id=run_id,
                agent=f"coder_agent(attempt {attempt})",
            )
        code = _strip_code_fences(response_text)

        if len(code) == 0:
            consecutive_empty += 1
            consecutive_error_sig = 0
            last_error_sig = None
            result = {
                "success": False,
                "stdout": "",
                "stderr": "Model returned empty code (nothing left after stripping code fences).",
                "output_path": None,
            }
        else:
            consecutive_empty = 0
            with step_timer(log_key, "coder_agent", f"execute_attempt_{attempt}"):
                result = _execute(code, input_paths, output_path, timeout, run_id)

            if not result["success"]:
                err_text = result.get("stderr") or "Execution failed without stderr"
                sig = compute_error_signature("stderr", err_text)
                if sig == last_error_sig:
                    consecutive_error_sig += 1
                else:
                    last_error_sig = sig
                    consecutive_error_sig = 1

        event_name = "coder_attempt" if parent_agent == "modeler_agent" else "code_execution"
        log_event(log_key, "coder_agent", event_name, attempt=attempt,
                  success=result["success"], code=code,
                  stdout=result.get("stdout", ""), stderr=result.get("stderr", ""),
                  parent_agent=parent_agent, parent_iteration=parent_iteration)

        if result["success"]:
            return {
                "success": True, "code": code, "stdout": result["stdout"],
                "output_path": result["output_path"], "attempts": attempt,
                "private_memory_entry": {
                    "task_spec": task_spec, "success": True, "code": code, "attempts": attempt,
                },
            }

        # Early exit check 1: consecutive empty completions (>= 2)
        if consecutive_empty >= 2:
            log_event(log_key, "coder_agent", "coder_exhausted_early",
                      reason="consecutive_empty_code",
                      attempts=attempt, parent_agent=parent_agent, parent_iteration=parent_iteration)
            return {
                "success": False, "code": code, "stdout": result.get("stdout", ""),
                "output_path": None, "attempts": attempt,
                "exhausted_early": True,
                "exit_reason": "consecutive_empty_code",
                "private_memory_entry": {
                    "task_spec": task_spec, "success": False, "code": code,
                    "stderr": result.get("stderr", ""), "attempts": attempt,
                    "exhausted_early": True,
                    "exit_reason": "consecutive_empty_code",
                },
            }

        # Early exit check 2: consecutive identical error signatures (>= 3)
        if consecutive_error_sig >= 3:
            log_event(log_key, "coder_agent", "coder_exhausted_early",
                      reason="repeated_identical_error",
                      error_signature=last_error_sig,
                      attempts=attempt, parent_agent=parent_agent, parent_iteration=parent_iteration)
            return {
                "success": False, "code": code, "stdout": result.get("stdout", ""),
                "output_path": None, "attempts": attempt,
                "exhausted_early": True,
                "exit_reason": "repeated_identical_error",
                "private_memory_entry": {
                    "task_spec": task_spec, "success": False, "code": code,
                    "stderr": result.get("stderr", ""), "attempts": attempt,
                    "exhausted_early": True,
                    "exit_reason": "repeated_identical_error",
                },
            }

        # Build retry instruction: on 2nd consecutive identical error, urge fundamentally different approach
        if consecutive_error_sig == 2:
            retry_directive = (
                "Your last fix produced the identical error — try a fundamentally different approach. "
                "Fix it and return the complete corrected script (no markdown fences, no commentary)."
            )
        else:
            retry_directive = "Fix it and return the complete corrected script (no markdown fences, no commentary)."

        messages.append(AIMessage(content=response_text))
        messages.append(HumanMessage(content=(
            f"The code failed. stderr:\n{result['stderr']}\n{retry_directive}"
        )))

    return {
        "success": False, "code": code, "stdout": result.get("stdout", ""),
        "output_path": None, "attempts": max_attempts,
        "private_memory_entry": {
            "task_spec": task_spec, "success": False, "code": code,
            "stderr": result.get("stderr", ""), "attempts": max_attempts,
        },
    }