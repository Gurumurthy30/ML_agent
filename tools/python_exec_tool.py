"""
Placeholder for what will eventually be a real MCP server. Implemented as a
subprocess-based tool (not in-process `exec`, not `multiprocessing.Process` —
subprocess specifically, per requirements). Since it's a separate process, data
cannot be shared in-memory: the contract is path-in, path-out.

This also serves as the placeholder for "Filesystem MCP" (read dataset / save plots) —
reading/writing by path is already the whole contract, no separate filesystem tool
needed.

Intentionally a placeholder: no sandboxing/security hardening yet. Restricted-import
allowlisting etc. can be added later when this becomes a real MCP server.
"""
import subprocess
import tempfile
import os
import sys

from tools.logger import log_event


def run_python_exec(
    code: str,
    input_paths: dict,
    output_path: str,
    timeout: int = 60,
    run_id: str = None,
    agent: str = "python_exec_tool",
) -> dict:
    """
    Writes `code` to a temp .py file and runs it via subprocess.

    Convention the generated code MUST follow:
      - Read inputs from the paths given in `input_paths` (e.g. {"dataset": "/path/to.csv"}),
        available to the script via env vars INPUT_<KEY> (uppercased).
      - Write its primary result to the path in env var OUTPUT_PATH.
      - Print any human-readable findings/log lines to stdout (captured and returned).

    Returns: {"success": bool, "stdout": str, "stderr": str, "output_path": str|None}
    """
    script_path = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
            f.write(code)
            script_path = f.name

        env = os.environ.copy()
        for key, path in (input_paths or {}).items():
            env[f"INPUT_{key.upper()}"] = path
        env["OUTPUT_PATH"] = output_path
        env["TARGET_COLUMN"] = os.environ.get("TARGET_COLUMN", "")
        env["EXCLUDE_COLUMNS"] = os.environ.get("EXCLUDE_COLUMNS", "")
        env["PYTHONIOENCODING"] = "utf-8"
        env["MPLBACKEND"] = "Agg"

        if output_path:
            out_dir = os.path.dirname(os.path.abspath(output_path))
            if out_dir:
                os.makedirs(out_dir, exist_ok=True)

        if run_id:
            log_event(run_id, agent, "subprocess_start", output_path=output_path,
                      input_keys=list((input_paths or {}).keys()), timeout=timeout)

        proc = subprocess.run(
            [sys.executable, script_path],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=env,
        )
        success = proc.returncode == 0 and os.path.exists(output_path)
        result = {
            "success": success,
            "stdout": proc.stdout or "",
            "stderr": proc.stderr or "",
            "output_path": output_path if success else None,
        }
    except subprocess.TimeoutExpired:
        result = {
            "success": False,
            "stdout": "",
            "stderr": f"Timed out after {timeout}s",
            "output_path": None,
        }
    except Exception as exc:
        result = {
            "success": False,
            "stdout": "",
            "stderr": f"Execution error: {exc}",
            "output_path": None,
        }
    finally:
        if script_path and os.path.exists(script_path):
            try:
                os.unlink(script_path)
            except OSError:
                pass

    if run_id:
        log_event(run_id, agent, "subprocess_end", success=result["success"],
                  stderr_tail=(result["stderr"] or "")[-500:])

    return result
