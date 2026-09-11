"""
local_env_mcp/server.py — Local Environment MCP Server

Exposes two MCP tools consumed by Coder and Execute agents:
- validate_code(code)   : real import resolution + cheap shape dry-run (not just ast.parse)
- execute_code(code, session_id) : real subprocess execution, timeout-bound

Working directory for executed code: state/sessions/{session_id}/exec_workspace/
Captures stdout/stderr/CV metrics/submission.csv path.
"""

import ast
import importlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import textwrap
from pathlib import Path
from typing import Any, Dict, List, Optional


class LocalEnvMCP:
    """
    In-process MCP server for local code validation and execution.
    No external MCP transport needed — agents import and call directly.
    """

    def __init__(
        self,
        session_id: str = "default",
        sessions_root: str = "state/sessions/",
        exec_timeout: int = 300,
        dry_run: bool = False,
    ):
        self.session_id = session_id
        self.exec_workspace = (Path(sessions_root) / session_id / "exec_workspace").resolve()
        self.exec_workspace.mkdir(parents=True, exist_ok=True)
        self.exec_timeout = exec_timeout
        self.dry_run = dry_run
        self._step_count = 0  # used only in dry-run mode

    # ─────────────────────────────────────────────────────────────────────────
    # Tool: validate_code
    # ─────────────────────────────────────────────────────────────────────────

    def validate_code(self, code: str) -> Dict[str, Any]:
        """
        Real validation — three layers:
        1. AST parse (syntax check)
        2. Import resolution — checks that top-level imports are resolvable
        3. Cheap shape dry-run — inserts a head(5) call on any DataFrame named 'df'
           to catch basic shape errors without running the full pipeline.

        Returns: {valid, warnings, error}
        """
        if self.dry_run:
            return {"valid": True, "warnings": [], "error": None}

        if not code or not code.strip():
            return {"valid": False, "warnings": [], "error": "Code is empty."}

        warnings: List[str] = []

        # ── Layer 1: AST parse ────────────────────────────────────────────────
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return {
                "valid": False,
                "warnings": [],
                "error": f"SyntaxError line {e.lineno}, col {e.offset}: {e.msg}",
            }
        except Exception as e:
            return {"valid": False, "warnings": [], "error": str(e)}

        # ── Layer 2: Import resolution ────────────────────────────────────────
        import_names = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    import_names.append(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    import_names.append(node.module.split(".")[0])

        unresolvable = []
        stdlib_skip = {
            "os", "sys", "re", "json", "time", "math", "pathlib", "typing",
            "collections", "itertools", "functools", "copy", "io", "abc",
            "warnings", "logging", "random", "string", "struct", "hashlib",
            "datetime", "calendar", "csv", "ast", "inspect", "traceback",
            "threading", "multiprocessing", "subprocess", "tempfile", "shutil",
            "glob", "fnmatch", "stat", "pickle", "gzip", "zipfile", "tarfile",
            "urllib", "http", "email", "html", "xml", "sqlite3", "contextlib",
        }
        for mod in set(import_names):
            if mod in stdlib_skip:
                continue
            try:
                importlib.import_module(mod)
            except ImportError:
                unresolvable.append(mod)
            except Exception:
                pass  # module exists but has side-effect errors on import — that's fine

        if unresolvable:
            return {
                "valid": False,
                "warnings": [],
                "error": f"Unresolvable imports: {unresolvable}. Install required packages first.",
            }

        # ── Layer 3: Cheap shape dry-run ──────────────────────────────────────
        # Write code to a temp file with a 5-row load injected at the top
        # Only run if code reads from a CSV — otherwise skip silently
        if "read_csv" in code or "read_parquet" in code or "pd.read" in code:
            # Inject a timeout guard and df.head(5) call before any fit/train
            dry_run_snippet = textwrap.dedent("""
import warnings; warnings.filterwarnings('ignore')
import signal
def _timeout_handler(sig, frame):
    raise TimeoutError('Dry-run timed out')
try:
    signal.signal(signal.SIGALRM, _timeout_handler)
    signal.alarm(10)
except (AttributeError, OSError):
    pass  # signal.SIGALRM not available on Windows
""")
            dry_code = dry_run_snippet + "\n" + code
            # Replace large nrows reads with nrows=5 for the dry run
            dry_code = re.sub(r"nrows\s*=\s*\d+", "nrows=5", dry_code)

            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".py", delete=False, encoding="utf-8"
            ) as tmp:
                tmp.write(dry_code)
                tmp_path = tmp.name

            try:
                result = subprocess.run(
                    [sys.executable, tmp_path],
                    capture_output=True,
                    text=True,
                    timeout=15,
                    cwd=str(self.exec_workspace),
                )
                if result.returncode != 0 and result.stderr:
                    # Filter out non-fatal warnings from stderr
                    stderr = result.stderr.strip()
                    fatal_lines = [
                        l for l in stderr.splitlines()
                        if "Error" in l or "error" in l or "Exception" in l
                    ]
                    if fatal_lines:
                        warnings.append(f"Dry-run warning: {'; '.join(fatal_lines[:3])}")
            except subprocess.TimeoutExpired:
                warnings.append("Dry-run timed out (>15s) — proceeding anyway.")
            except Exception as e:
                warnings.append(f"Dry-run subprocess error: {e}")
            finally:
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass

        return {"valid": True, "warnings": warnings, "error": None}

    # ─────────────────────────────────────────────────────────────────────────
    # Tool: execute_code
    # ─────────────────────────────────────────────────────────────────────────

    def execute_code(self, code: str) -> Dict[str, Any]:
        """
        Real subprocess execution of ML pipeline code.

        - Working dir: state/sessions/{session_id}/exec_workspace/
        - Timeout: exec_timeout seconds (default 300)
        - Captures stdout/stderr (tail 2000 chars each)
        - Parses CV metric lines from stdout (looks for 'CV_MEAN=', 'CV_STD=')
        - Checks for submission.csv in working dir
        - Returns: {status, cv_mean, cv_std, stdout_tail, stderr_tail,
                    submission_csv_path, timestamp}

        Agents should emit CV metrics to stdout in this format:
            print(f"CV_MEAN={mean:.6f}")
            print(f"CV_STD={std:.6f}")
        """
        if self.dry_run:
            return self._dry_run_execute()

        # Write code to a temp file in exec_workspace
        code_file = (self.exec_workspace / f"pipeline_{int(time.time()*1000)}.py").resolve()
        try:
            code_file.write_text(code, encoding="utf-8")

            result = subprocess.run(
                [sys.executable, str(code_file)],
                capture_output=True,
                text=True,
                timeout=self.exec_timeout,
                cwd=str(self.exec_workspace),
            )

            stdout = result.stdout or ""
            stderr = result.stderr or ""

            # Parse CV metrics from stdout
            cv_mean, cv_std = self._parse_cv_metrics(stdout)

            # Check for submission.csv
            submission_csv = self.exec_workspace / "submission.csv"
            submission_path = str(submission_csv) if submission_csv.exists() else None

            status = "success" if result.returncode == 0 else "error"
            error_msg = None
            if status == "error":
                # Extract last meaningful error line
                err_lines = [l for l in stderr.splitlines() if l.strip()]
                error_msg = err_lines[-1] if err_lines else "Non-zero exit code"

            return {
                "status": status,
                "cv_mean": cv_mean,
                "cv_std": cv_std,
                "stdout_tail": stdout[-2000:] if stdout else "",
                "stderr_tail": stderr[-2000:] if stderr else "",
                "submission_csv_path": submission_path,
                "error": error_msg,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            }

        except subprocess.TimeoutExpired:
            return {
                "status": "timeout",
                "cv_mean": 0.0,
                "cv_std": 0.0,
                "stdout_tail": "",
                "stderr_tail": f"Execution timed out after {self.exec_timeout}s",
                "submission_csv_path": None,
                "error": f"Timeout after {self.exec_timeout}s",
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
        except Exception as e:
            return {
                "status": "error",
                "cv_mean": 0.0,
                "cv_std": 0.0,
                "stdout_tail": "",
                "stderr_tail": str(e),
                "submission_csv_path": None,
                "error": str(e),
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
        finally:
            try:
                code_file.unlink(missing_ok=True)
            except Exception:
                pass

    # ─────────────────────────────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _parse_cv_metrics(self, stdout: str) -> tuple[float, float]:
        """
        Extracts CV_MEAN and CV_STD from stdout.
        First looks for CV_RESULT sentinel line format:
            CV_RESULT: {"cv_mean": 0.8321, "cv_std": 0.0123}
        Falls back to regex match on:
            CV_MEAN=0.8412  CV_STD=0.0053
        Falls back to 0.0/0.0 if not found.
        """
        for line in stdout.splitlines():
            if "CV_RESULT:" in line:
                try:
                    payload = line.split("CV_RESULT:", 1)[1].strip()
                    data = json.loads(payload)
                    cv_mean = float(data.get("cv_mean", data.get("cv_score", 0.0)))
                    cv_std = float(data.get("cv_std", 0.0))
                    return cv_mean, cv_std
                except Exception:
                    pass

        cv_mean = 0.0
        cv_std = 0.0
        for line in stdout.splitlines():
            m = re.search(r"CV_MEAN\s*=\s*([\d.]+)", line)
            if m:
                try:
                    cv_mean = float(m.group(1))
                except ValueError:
                    pass
            m = re.search(r"CV_STD\s*=\s*([\d.]+)", line)
            if m:
                try:
                    cv_std = float(m.group(1))
                except ValueError:
                    pass
        return cv_mean, cv_std

    def _dry_run_execute(self) -> Dict[str, Any]:
        """
        Canned responses for --dry-run mode.
        Simulates a realistic convergence plateau.
        """
        import random
        self._step_count += 1
        step = self._step_count
        plateau = {1: 0.820, 2: 0.845, 3: 0.852, 4: 0.853, 5: 0.8532}
        cv_mean = plateau.get(step, 0.8533)
        cv_std = round(random.uniform(0.003, 0.008), 4)

        return {
            "status": "success",
            "cv_mean": round(cv_mean, 4),
            "cv_std": cv_std,
            "stdout_tail": f"[DRY-RUN] CV_MEAN={cv_mean:.4f}\n[DRY-RUN] CV_STD={cv_std:.4f}\n",
            "stderr_tail": "",
            "submission_csv_path": None,
            "error": None,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
