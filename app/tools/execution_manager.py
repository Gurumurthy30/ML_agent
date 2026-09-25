import os
import sys
import shutil
import subprocess
from pathlib import Path
from typing import Any
from app.config import PROJECTS_DIR


class ExecutionResult:
    def __init__(self, exit_code: int, stdout: str, stderr: str, workspace_dir: str):
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr
        self.workspace_dir = workspace_dir
        self.success = (exit_code == 0)

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "workspace_dir": self.workspace_dir,
        }


class ExecutionManager:
    """Manages Python script execution in isolated per-run workspace directories without timeouts."""

    def __init__(self, project_id: str):
        self.project_id = project_id
        self.workspace_base = PROJECTS_DIR / project_id / "workspace"
        self.workspace_base.mkdir(parents=True, exist_ok=True)

    def _prepare_workspace(self) -> Path:
        """Cleans and re-prepares the workspace directory for a fresh execution."""
        if self.workspace_base.exists():
            shutil.rmtree(self.workspace_base, ignore_errors=True)
        self.workspace_base.mkdir(parents=True, exist_ok=True)
        return self.workspace_base

    def run_script(
        self,
        script_content: str,
        script_name: str = "run_task.py",
        env_vars: dict[str, str] | None = None,
        stage: str | None = None,
        run_id: str | None = None,
        task_description: str | None = None,
        attempt: int | None = None,
    ) -> ExecutionResult:
        """Writes script_content into the clean workspace, executes it via subprocess, and records execution history."""
        import time
        import uuid
        import json
        from datetime import datetime, timezone

        ws = self._prepare_workspace()
        script_file = ws / script_name
        script_file.write_text(script_content, encoding="utf-8")

        env = os.environ.copy()
        if env_vars:
            env.update(env_vars)
        # Ensure project root is in PYTHONPATH so imports work if needed
        project_root = str(Path(__file__).resolve().parent.parent.parent)
        env["PYTHONPATH"] = project_root + os.pathsep + env.get("PYTHONPATH", "")

        python_executable = sys.executable

        start_time = time.time()
        # Execute subprocess without timeout
        process = subprocess.Popen(
            [python_executable, str(script_file.resolve())],
            cwd=str(ws.resolve()),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
        )

        stdout, stderr = process.communicate()
        duration_ms = int((time.time() - start_time) * 1000)

        # Persist execution history for monitoring the coder agent
        try:
            exec_dir = PROJECTS_DIR / self.project_id / "code_executions"
            exec_dir.mkdir(parents=True, exist_ok=True)
            now_dt = datetime.now(timezone.utc)
            record_id = f"exec_{int(now_dt.timestamp())}_{uuid.uuid4().hex[:6]}"
            record = {
                "id": record_id,
                "project_id": self.project_id,
                "run_id": run_id,
                "stage": stage or "coder",
                "script_name": script_name,
                "task_description": task_description,
                "attempt": attempt or 1,
                "code": script_content,
                "exit_code": process.returncode,
                "stdout": stdout,
                "stderr": stderr,
                "success": (process.returncode == 0),
                "executed_at": now_dt.isoformat(),
                "duration_ms": duration_ms,
            }
            rec_file = exec_dir / f"{record_id}.json"
            rec_file.write_text(json.dumps(record, indent=2), encoding="utf-8")

            # Broadcast event to SSE subscribers if run_id provided
            if run_id:
                from app.core.events import event_manager
                event_manager.emit_event(
                    project_id=self.project_id,
                    run_id=run_id,
                    event_type="CODE_EXECUTION_COMPLETED",
                    stage=stage or "coder",
                    message=f"Coder executed '{script_name}' (exit code: {process.returncode}, {duration_ms}ms)",
                    data=record,
                )
        except Exception as e:
            # Execution recording should never crash the workflow
            print(f"[ExecutionManager] Warning: failed to save code execution log: {e}", flush=True)

        return ExecutionResult(
            exit_code=process.returncode,
            stdout=stdout,
            stderr=stderr,
            workspace_dir=str(ws),
        )
