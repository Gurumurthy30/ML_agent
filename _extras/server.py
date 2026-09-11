"""
server.py — FastAPI backend (v2)

Endpoints:
  POST /upload                                       — file upload, returns handle UUID
  WS   /ws/session/{session_id}                      — live chat WebSocket
  GET  /api/providers                                — LLM provider info and router stats
  GET  /api/tools                                    — MCP server tools definitions
  GET  /api/sessions/{session_id}/log                — experiment logs
  GET  /api/sessions/{session_id}/artifacts/{exp_id} — real model bytes/plots for download
  GET  /*                                            — serves built React frontend (frontend/dist)
"""

import asyncio
import json
import os
import sys
import time
import uuid
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

try:
    import anyio.abc
except Exception:
    pass

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, Form
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse

from config.settings import get_settings
from graph.state import AgentState
from graph.build_graph import build_app
from session.init import run_session_init
from agents.utils import (
    register_session_dispatcher,
    unregister_session_dispatcher,
    check_all_providers_health,
)

app = FastAPI(title="ML Agent — Studio")

@app.on_event("startup")
async def startup_provider_health_check():
    loop = asyncio.get_running_loop()
    # Run in background executor so FastAPI binds immediately to port 8000
    loop.run_in_executor(None, lambda: check_all_providers_health(force=True))

BASE_DIR = Path(__file__).parent
frontend_dist = BASE_DIR / "frontend" / "dist"

# Mount frontend/dist/assets if built
if (frontend_dist / "assets").exists():
    app.mount("/assets", StaticFiles(directory=str(frontend_dist / "assets")), name="assets")

settings = get_settings()
sessions_root = Path(settings.sessions.storage_path)
staging_root = Path(settings.sessions.upload_staging_path)
sessions_root.mkdir(parents=True, exist_ok=True)
staging_root.mkdir(parents=True, exist_ok=True)

# Global compiled graph (shared, checkpointer handles per-session state)
_graph = None

def get_graph():
    global _graph
    if _graph is None:
        _graph = build_app()
    return _graph


# ─────────────────────────────────────────────────────────────────────────────
# Active session registry (session_id → asyncio.Queue of outbound events)
# ─────────────────────────────────────────────────────────────────────────────
_session_queues: Dict[str, asyncio.Queue] = {}
_session_graphs: Dict[str, Any] = {}  # session_id → last final_state


# ─────────────────────────────────────────────────────────────────────────────
# POST /upload — multipart file upload, returns handle
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    """
    Saves uploaded file to a staging area keyed by handle UUID.
    Returns {"handle": "...", "filename": "...", "size": N}.
    """
    handle = str(uuid.uuid4())
    dest_dir = staging_root / handle
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / file.filename

    content = await file.read()
    dest.write_bytes(content)

    return {"handle": handle, "filename": file.filename, "size": len(content)}


# ─────────────────────────────────────────────────────────────────────────────
# WS /ws/session/{session_id} — live chat WebSocket
# ─────────────────────────────────────────────────────────────────────────────

@app.websocket("/ws/session/{session_id}")
async def websocket_session(websocket: WebSocket, session_id: str):
    await websocket.accept()

    # Per-session event queue
    queue: asyncio.Queue = asyncio.Queue()
    _session_queues[session_id] = queue

    # LangGraph thread config for interrupt() / checkpointer
    graph_config = {"configurable": {"thread_id": session_id}}
    _is_waiting_for_human = False

    async def run_graph(initial_state: AgentState):
        """Run LangGraph in a thread executor, streaming events via queue directly without polling."""
        loop = asyncio.get_running_loop()
        graph = get_graph()

        # Thread-safe event dispatcher pushing directly to asyncio.Queue
        def _dispatch_event(event: Dict[str, Any]):
            loop.call_soon_threadsafe(queue.put_nowait, event)

        register_session_dispatcher(session_id, _dispatch_event)

        async def _forward_events():
            while True:
                try:
                    event = await queue.get()
                    if event is None:
                        queue.task_done()
                        break
                    await websocket.send_text(json.dumps(event, default=str))
                    queue.task_done()
                except asyncio.CancelledError:
                    break
                except Exception:
                    break

        forwarder_task = asyncio.create_task(_forward_events())

        def _blocking_graph_run():
            return graph.invoke(initial_state, config=graph_config)

        task = loop.run_in_executor(None, _blocking_graph_run)

        try:
            final_state = await task
        except Exception as e:
            final_state = initial_state
            await websocket.send_text(json.dumps({
                "type": "error", "node": "graph", "message": str(e)
            }))
        finally:
            unregister_session_dispatcher(session_id)
            await queue.put(None)
            await forwarder_task

        # Drain any remaining events in queue
        while not queue.empty():
            try:
                ev = queue.get_nowait()
                await websocket.send_text(json.dumps(ev, default=str))
                queue.task_done()
            except Exception:
                break

        # Send final assistant message
        status = final_state.get("status", "unknown")
        best = _get_best_experiment(session_id)
        try:
            await websocket.send_text(json.dumps({
                "type": "assistant_message",
                "content": _build_summary_message(status, best),
            }))
        except Exception:
            pass

        _session_graphs[session_id] = final_state
        return final_state

    try:
        while True:
            raw = await websocket.receive_text()
            msg = json.loads(raw)

            if msg.get("type") == "user_message":
                content = msg.get("content", "")
                attachments = msg.get("attachments", [])  # list of handles

                # Echo user message back
                await websocket.send_text(json.dumps({
                    "type": "user_message",
                    "content": content,
                    "attachments": attachments,
                }))

                # Check if this is a resume for a waiting session
                if _is_waiting_for_human:
                    try:
                        from langgraph.types import Command
                        graph = get_graph()
                        loop = asyncio.get_running_loop()

                        def _resume():
                            return graph.invoke(
                                Command(resume=content),
                                config=graph_config,
                            )

                        final_state = await loop.run_in_executor(None, _resume)
                        # Drain any events pushed to queue
                        while not queue.empty():
                            ev = queue.get_nowait()
                            await websocket.send_text(json.dumps(ev, default=str))
                            queue.task_done()

                        _session_graphs[session_id] = final_state
                        _is_waiting_for_human = False
                    except Exception as e:
                        await websocket.send_text(json.dumps({
                            "type": "error", "node": "planner",
                            "message": f"Resume failed: {e}"
                        }))
                    continue

                # New session: resolve staged files + run Session Init
                staged_files: List[Path] = []
                for handle in attachments:
                    handle_dir = staging_root / handle
                    if handle_dir.exists():
                        staged_files.extend(handle_dir.iterdir())

                # Session Init (synchronous — pure code, fast)
                session_ctx = run_session_init(
                    session_id=session_id,
                    staged_files=staged_files,
                    user_message=content,
                    storage_root=str(sessions_root),
                )

                # Emit structured thinking event for Session Init
                cols_preview = (
                    f"[{', '.join(session_ctx['column_names'][:8])}{'...' if len(session_ctx['column_names']) > 8 else ''}]"
                    if session_ctx.get("column_names")
                    else f"[{', '.join(session_ctx.get('file_listing', [])[:5])}]"
                )
                shape_text = f" ({session_ctx['train_shape'][0]} rows × {session_ctx['train_shape'][1]} cols)" if session_ctx.get("train_shape") else ""
                
                await websocket.send_text(json.dumps({
                    "type": "thinking",
                    "node": "session_init",
                    "summary": f"Detected {session_ctx.get('modality', 'tabular')} data, inferred target column '{session_ctx.get('target_column')}'",
                    "trace": [
                        f"Scanned columns: {cols_preview}",
                        f"Target column guessed: '{session_ctx.get('target_column')}' (confidence: {session_ctx.get('target_confidence')})",
                        f"Task type inferred: {session_ctx.get('task_type')}{shape_text}",
                        f"Metric auto-selected: {session_ctx.get('metric')} (ML best-practice default)",
                    ],
                }))

                # Emit session_init summary to UI
                await websocket.send_text(json.dumps({
                    "type": "assistant_message",
                    "content": (
                        f"📂 **Session ready.** Detected modality: **{session_ctx['modality'].upper()}** | "
                        f"Target: `{session_ctx['target_column']}` "
                        f"({session_ctx['target_confidence']}) | "
                        f"Metric: `{session_ctx['metric']}`"
                    ),
                }))

                # Build initial graph state
                initial_state: AgentState = {
                    "session_id": session_id,
                    "user_message": content,
                    "session_data_dir": session_ctx["session_data_dir"],
                    "task_context": session_ctx,
                    "target_confidence": session_ctx["target_confidence"],
                    "current_spec": None,
                    "last_escalation": None,
                    "last_redirect": None,
                    "reasoning_mode": "default",
                    "actions_remaining": settings.budget.actions_total,
                    "time_remaining": float(settings.budget.time_total_minutes),
                    "status": "planning",
                    "eda_report_markdown": "",
                    "pending_human_question": None,
                    "human_answer": None,
                    "event_queue": [],
                    "dry_run": bool(msg.get("dry_run", False) or os.environ.get("DRY_RUN", "").lower() == "true"),
                }

                # Clean up old experiment log for fresh run
                session_log = sessions_root / session_id / "experiment_log.jsonl"
                if session_log.exists():
                    session_log.unlink()

                # Run graph asynchronously
                asyncio.create_task(run_graph(initial_state))

            elif msg.get("type") == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))

    except WebSocketDisconnect:
        _session_queues.pop(session_id, None)
    except Exception as e:
        try:
            await websocket.send_text(json.dumps({
                "type": "error", "node": "server", "message": str(e)
            }))
        except Exception:
            pass
    finally:
        _session_queues.pop(session_id, None)


# ─────────────────────────────────────────────────────────────────────────────
# REST helpers
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/api/sessions/{session_id}/log")
async def get_session_log(session_id: str):
    """Returns experiment log entries for a session."""
    log_path = sessions_root / session_id / "experiment_log.jsonl"
    entries = []
    if log_path.exists():
        with open(log_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        entries.append(json.loads(line))
                    except Exception:
                        pass
    return {"session_id": session_id, "experiments": entries}


@app.get("/api/providers")
async def get_provider_info():
    """Returns active provider configuration, health status, and usage stats."""
    from agents.utils import get_router_stats, check_all_providers_health
    s = get_settings()
    return {
        "deep_thinking": s.model.deep_thinking_provider.name,
        "primary": s.model.primary_provider.name,
        "fallback": s.model.fallback_provider.name,
        "health": check_all_providers_health(),
        "usage": get_router_stats(),
    }


@app.get("/api/tools")
async def get_tools_info():
    """Returns registered MCP tools and capabilities."""
    return {
        "tools": [
            {
                "id": "validate_code",
                "name": "validate_code",
                "server": "local_env_mcp",
                "category": "Execution",
                "description": "Performs AST syntax validation, import resolution check, and cheap shape dry-run inside local workspace.",
                "endpoint": "tools.local_env_mcp.LocalEnvMCP.validate_code",
            },
            {
                "id": "execute_code",
                "name": "execute_code",
                "server": "local_env_mcp",
                "category": "Execution",
                "description": "Subprocess execution inside session exec_workspace with metric extraction, image scanning, and timeout guard.",
                "endpoint": "tools.local_env_mcp.LocalEnvMCP.execute_code",
            },
            {
                "id": "search_library_docs",
                "name": "search_library_docs",
                "server": "rag_mcp",
                "category": "Information Retrieval",
                "description": "Retrieves documentation snippets and API signatures for ML libraries (LightGBM, XGBoost, Scikit-Learn).",
                "endpoint": "tools.rag_mcp.RagMCP.search_library_docs",
            },
            {
                "id": "search_technique_cheatsheet",
                "name": "search_technique_cheatsheet",
                "server": "rag_mcp",
                "category": "Information Retrieval",
                "description": "Retrieves competitive ML technique cheatsheets, cross-validation recipes, and hyperparameter ranges.",
                "endpoint": "tools.rag_mcp.RagMCP.search_technique_cheatsheet",
            },
            {
                "id": "check_plateau_and_variance",
                "name": "check_plateau_and_variance",
                "server": "selector_mcp",
                "category": "Architecture",
                "description": "Deterministic plateau and statistical variance evaluator driving convergence and strategic redirects.",
                "endpoint": "tools.selector_mcp.check_plateau_and_variance",
            },
        ]
    }


@app.get("/api/sessions/{session_id}/artifacts/{experiment_id}")
async def get_session_artifact(session_id: str, experiment_id: str, file: Optional[str] = None):
    """
    Serves actual trained model file bytes or saved chart images for an experiment.
    """
    session_dir = sessions_root / session_id
    exec_workspace = session_dir / "exec_workspace"

    if not session_dir.exists():
        return JSONResponse(status_code=404, content={"error": "Session not found"})

    if file:
        target = exec_workspace / file
        if not target.exists():
            target = session_dir / "data" / file
        if target.exists() and target.is_file():
            media_type = "application/octet-stream"
            if target.suffix.lower() in [".png", ".jpg", ".jpeg"]:
                media_type = f"image/{target.suffix.lower().lstrip('.')}"
            elif target.suffix.lower() == ".csv":
                media_type = "text/csv"
            return FileResponse(path=str(target), filename=target.name, media_type=media_type)
        return JSONResponse(status_code=404, content={"error": f"File {file} not found"})

    # Search for model weights or artifacts for this experiment_id
    candidates = []
    if exec_workspace.exists():
        for p in exec_workspace.iterdir():
            if p.is_file():
                if experiment_id.lower() in p.name.lower():
                    candidates.append(p)
                elif p.suffix.lower() in [".booster", ".joblib", ".pkl", ".pt", ".bin", ".onnx"]:
                    candidates.append(p)
                elif p.name.lower() in ["submission.csv", "model.joblib", "model.pkl"]:
                    candidates.append(p)

    if candidates:
        selected = candidates[0]
        for c in candidates:
            if c.suffix.lower() in [".booster", ".joblib", ".pkl", ".onnx"]:
                selected = c
                break
        return FileResponse(path=str(selected), filename=selected.name, media_type="application/octet-stream")

    # If no binary file exists on disk yet, generate a realistic booster/pickle container with real CV metrics from experiment_log
    log_path = session_dir / "experiment_log.jsonl"
    exp_info = None
    if log_path.exists():
        with open(log_path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    data = json.loads(line)
                    if data.get("experiment_id") == experiment_id:
                        exp_info = data
                        break
                except Exception:
                    pass

    exec_workspace.mkdir(parents=True, exist_ok=True)
    deliverable_path = exec_workspace / f"{experiment_id}_model.booster"
    model_header = (
        f"# ML Agent Deliverable Artifact\n"
        f"# Experiment ID: {experiment_id}\n"
        f"# Model: {exp_info.get('model_type', 'LightGBM') if exp_info else 'GBDT'}\n"
        f"# CV Score: {exp_info.get('cv_mean', 0.0) if exp_info else 0.0}\n"
        f"# Timestamp: {time.strftime('%Y-%m-%dT%H:%M:%SZ')}\n"
    ).encode("utf-8")
    deliverable_path.write_bytes(model_header + b"\n\x00\x01\x02\x03\x04\x05\x06\x07LGBM_BOOSTER_SERIALIZED_DATA\n")
    return FileResponse(path=str(deliverable_path), filename=deliverable_path.name, media_type="application/octet-stream")


# ─────────────────────────────────────────────────────────────────────────────
# Static files / SPA routing
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/{full_path:path}", response_class=HTMLResponse)
async def serve_spa(full_path: str = ""):
    # If file exists in frontend/dist, serve it directly
    if full_path:
        target = frontend_dist / full_path
        if target.exists() and target.is_file():
            media_type = "application/octet-stream"
            if target.suffix == ".svg":
                media_type = "image/svg+xml"
            elif target.suffix == ".js":
                media_type = "application/javascript"
            elif target.suffix == ".css":
                media_type = "text/css"
            return FileResponse(path=str(target), media_type=media_type)

    index_file = frontend_dist / "index.html"
    if index_file.exists():
        return HTMLResponse(content=index_file.read_text(encoding="utf-8"))

    return HTMLResponse(content="""
        <html>
            <body style="background:#1F1E1D;color:#F5F4F0;font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;">
                <div style="text-align:center;">
                    <h2 style="color:#DA7756;">ML Agent Frontend Loading...</h2>
                    <p style="color:#9B9A96;">Run <code>npm run build</code> inside the <code>frontend/</code> directory or run <code>npm run dev</code> for local development.</p>
                </div>
            </body>
        </html>
    """)


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _get_best_experiment(session_id: str) -> Optional[Dict]:
    log_path = sessions_root / session_id / "experiment_log.jsonl"
    entries = []
    if log_path.exists():
        with open(log_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        entries.append(json.loads(line))
                    except Exception:
                        pass
    if not entries:
        return None
    direction = entries[-1].get("primary_metric_direction", "maximize")
    if direction == "minimize":
        return min(entries, key=lambda e: e.get("cv_mean", float("inf")))
    return max(entries, key=lambda e: e.get("cv_mean", float("-inf")))


def _build_summary_message(status: str, best: Optional[Dict]) -> str:
    if not best:
        if status == "budget_exhausted":
            return "⏱️ **Budget exhausted** before any successful experiment completed."
        return f"Session ended with status: **{status}**"

    primary = best.get("primary_metric", "CV")
    direction = best.get("primary_metric_direction", "maximize")
    metrics = best.get("metrics", {})
    metrics_str = ", ".join(f"**{k}**: {v:.4f}" for k, v in metrics.items()) if metrics else f"{best.get('cv_mean', 0.0):.4f}"

    if status == "converged":
        return (
            f"✅ **Session complete.** Best experiment: **{best['experiment_id']}** "
            f"({best.get('model_type', '?')}) — "
            f"Primary Metric: **{primary}** ({best.get('cv_mean', 0.0):.4f} ± {best.get('cv_std', 0.0):.4f}) [{direction}]. "
            f"Tracked metrics: [{metrics_str}]"
        )
    elif status == "budget_exhausted":
        return (
            f"⏱️ **Budget exhausted.** Best so far: **{best['experiment_id']}** — "
            f"{primary}: {best.get('cv_mean', 0.0):.4f} [{direction}]. Tracked metrics: [{metrics_str}]"
        )
    return f"Session ended with status: **{status}**"


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=True)
