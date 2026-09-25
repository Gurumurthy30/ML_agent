import re
from typing import Any
from langchain_core.messages import SystemMessage, HumanMessage
from app.core.model_router import ModelRouter
from app.tools.execution_manager import ExecutionManager
from app.tools.file_tools import FileTools


CODER_SYSTEM_PROMPT = """You are an expert Python machine learning engineer who writes short, correct, standalone scripts to accomplish one narrow task at a time.
 
You will be given a precise task description and the minimal context needed to do it (file paths, column names/dtypes, prior findings). You are NOT given the full project history — do not assume it exists.
 
OUTPUT FORMAT
- Respond with exactly one ```python ... ``` code block and nothing else outside it.
- The script must run top-to-bottom with no manual edits, placeholders, or "# TODO".
 
ALLOWED LIBRARIES
pandas, numpy, scipy, pyarrow, scikit-learn, joblib, mlflow, json, pathlib, and the standard library. Do not import anything outside this list unless the task explicitly calls for it. Never attempt `pip install` or any network call.
 
HARD RULES
1. NEVER import or use a plotting/visualization library (matplotlib, seaborn, plotly, bokeh, altair, or anything that renders an image). All output is numbers, text, JSON, or files (parquet/csv/pickle/joblib).
2. Save every requested artifact to the EXACT path given — never invent your own paths or filenames.
3. Set a random_state/seed on every stochastic operation for reproducibility.
4. Wrap the risky part of the script in try/except. On failure: print the exception and a short diagnosis to stderr, then exit with a non-zero status — never fail silently or continue past a broken step.
5. End every successful run by printing ONE line to stdout starting with `RESULT_JSON:` followed by a single-line, minified JSON object summarizing what happened — key values/metrics computed and a list of artifact paths written. This is the only line the calling agent parses programmatically; print other human-readable progress lines before it, never after.
6. Do not read or write anything outside the working directory you were given.
"""


class CoderSubAgent:
    """Sub-agent responsible for writing, executing, debugging, and retrying Python scripts."""

    def __init__(self, project_id: str, model_router: ModelRouter, file_tools: FileTools, execution_manager: ExecutionManager):
        self.project_id = project_id
        self.router = model_router
        self.file_tools = file_tools
        self.execution = execution_manager
        self.llm = self.router.get_model("coder", temperature=0.1)

    def _extract_code(self, response_text: str) -> str:
        """Extracts python code from markdown block or returns raw text."""
        code_match = re.search(r"```python\s*(.*?)\s*```", response_text, re.DOTALL | re.IGNORECASE)
        if code_match:
            return code_match.group(1).strip()
        # Fallback for generic code block
        code_match = re.search(r"```\s*(.*?)\s*```", response_text, re.DOTALL)
        if code_match:
            return code_match.group(1).strip()
        return response_text.strip()

    def run_task(
        self,
        task_description: str,
        context: dict[str, Any],
        max_retries: int = 2,
    ) -> dict[str, Any]:
        """Iteratively writes, runs, and debugs a Python script to satisfy the given task."""
        history = [
            SystemMessage(content=CODER_SYSTEM_PROMPT),
            HumanMessage(content=f"Task Description:\n{task_description}\n\nTask Context:\n{context}"),
        ]

        attempt = 0
        last_error = None
        last_code = ""
        last_stdout = ""

        while attempt <= max_retries:
            # 1. Ask LLM to generate or repair the code
            ai_msg = self.llm.invoke(history)
            raw_content = ai_msg.content
            if isinstance(raw_content, list):
                # Handle possible multimodality or structured blocks if returned as list
                raw_content = "\n".join(str(part) for part in raw_content)

            code = self._extract_code(raw_content)
            last_code = code

            # 2. Execute script
            res = self.execution.run_script(code)

            # Detect soft failures in execution output
            if res.success and "<MODEL_RESULTS>" in res.stdout:
                if '"models": []' in res.stdout or '"best_model_name": null' in res.stdout:
                    res.success = False
                    res.stderr = (res.stderr or "") + "\nExecution resulted in empty models list. Check data types or pipeline errors."

            if res.success:
                return {
                    "status": "SUCCESS",
                    "stdout_summary": res.stdout[-2000:] if len(res.stdout) > 2000 else res.stdout,
                    "full_stdout": res.stdout,
                    "error": None,
                    "attempts": attempt + 1,
                    "executed_code": code,
                }

            # On failure, prepare feedback for retry
            attempt += 1
            last_error = res.stderr or f"Non-zero exit code: {res.exit_code}"
            last_stdout = res.stdout

            if attempt <= max_retries:
                history.append(ai_msg)
                retry_feedback = (
                    f"Execution failed with exit code {res.exit_code}.\n"
                    f"STDERR:\n{res.stderr[-2000:]}\n\n"
                    f"STDOUT:\n{res.stdout[-1000:]}\n\n"
                    "Please debug the error and rewrite the entire Python script inside a single ```python ``` block."
                )
                history.append(HumanMessage(content=retry_feedback))

        return {
            "status": "FAILED",
            "stdout_summary": last_stdout[-2000:],
            "full_stdout": last_stdout,
            "error": last_error,
            "attempts": attempt,
            "executed_code": last_code,
        }
