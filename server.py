"""
server.py — FastAPI backend (v2)

Endpoints:
  POST /upload                   — file upload, returns handle UUID
  WS   /ws/session/{session_id}  — live chat WebSocket
  GET  /                         — serves ui/index.html
  GET  /static/*                 — serves ui/ static assets

Event schema (backend → frontend): see brief §5 — one JSON object per WS message.
"""

import asyncio
import json
import os
import uuid
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, Form
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse

from config.settings import get_settings
from graph.state import AgentState
from graph.build_graph import build_app
from session.init import run_session_init

app = FastAPI(title="ML Agent — Chat Interface")

BASE_DIR = Path(__file__).parent
ui_dir = BASE_DIR / "ui"
ui_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(ui_dir)), name="static")

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
# Static file serving
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def get_index():
    index_file = ui_dir / "index.html"
    if index_file.exists():
        return HTMLResponse(content=index_file.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>ML Agent UI loading...</h1>")


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
    _is_waiting_for_human = False  # local flag per connection

    async def drain_queue():
        """Drain events from queue to WebSocket."""
        while True:
            try:
                event = queue.get_nowait()
                await websocket.send_text(json.dumps(event, default=str))
            except asyncio.QueueEmpty:
                break

    async def run_graph(initial_state: AgentState):
        """Run the LangGraph in a thread executor, draining events as they're queued."""
        loop = asyncio.get_event_loop()
        graph = get_graph()

        def _blocking_graph_run():
            """
            The graph will fill initial_state["event_queue"] as it runs.
            We poll and drain periodically. For a true streaming experience,
            agents push to the queue; we drain here on a timer.
            """
            return graph.invoke(initial_state, config=graph_config)

        # Run graph in thread pool
        task = loop.run_in_executor(None, _blocking_graph_run)

        # Drain events while graph is running
        while not task.done():
            await asyncio.sleep(0.15)
            await drain_queue_from_state(initial_state)

        try:
            final_state = await task
        except Exception as e:
            final_state = initial_state
            await websocket.send_text(json.dumps({
                "type": "error", "node": "graph", "message": str(e)
            }))

        # Final drain
        await drain_queue_from_state(final_state)

        # Send final assistant message
        status = final_state.get("status", "unknown")
        best = _get_best_experiment(session_id)
        await websocket.send_text(json.dumps({
            "type": "assistant_message",
            "content": _build_summary_message(status, best),
        }))

        _session_graphs[session_id] = final_state
        return final_state

    async def drain_queue_from_state(state: Dict):
        """Drain events from the state's in-place event_queue list."""
        eq = state.get("event_queue")
        if not eq:
            return
        while eq:
            event = eq.pop(0)
            await websocket.send_text(json.dumps(event, default=str))

    try:
        while True:
            raw = await websocket.receive_text()
            msg = json.loads(raw)

            if msg.get("type") == "user_message":
                content = msg.get("content", "")
                attachments = msg.get("attachments", [])  # list of handles

                # ── Echo user message back ────────────────────────────────
                await websocket.send_text(json.dumps({
                    "type": "user_message",
                    "content": content,
                    "attachments": attachments,
                }))

                # ── Check if this is a resume for a waiting session ───────
                if _is_waiting_for_human:
                    # Resume graph after interrupt()
                    try:
                        from langgraph.types import Command
                        graph = get_graph()
                        loop = asyncio.get_event_loop()
                        cur_state = _session_graphs.get(session_id, {})

                        def _resume():
                            return graph.invoke(
                                Command(resume=content),
                                config=graph_config,
                            )

                        final_state = await loop.run_in_executor(None, _resume)
                        await drain_queue_from_state(final_state)
                        _session_graphs[session_id] = final_state
                        _is_waiting_for_human = False
                    except Exception as e:
                        await websocket.send_text(json.dumps({
                            "type": "error", "node": "planner",
                            "message": f"Resume failed: {e}"
                        }))
                    continue

                # ── New session: resolve staged files + run Session Init ───
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
                    "dry_run": os.environ.get("DRY_RUN", "").lower() == "true",
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
    """Returns active provider configuration and usage stats."""
    from agents.utils import get_router_stats
    s = get_settings()
    return {
        "deep_thinking": s.model.deep_thinking_provider.name,
        "primary": s.model.primary_provider.name,
        "fallback": s.model.fallback_provider.name,
        "usage": get_router_stats(),
    }


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
    return max(entries, key=lambda e: e.get("cv_mean", 0.0))


def _build_summary_message(status: str, best: Optional[Dict]) -> str:
    if status == "converged" and best:
        return (
            f"✅ **Session complete.** Best experiment: **{best['experiment_id']}** "
            f"({best.get('model_type', '?')}) — "
            f"CV: **{best.get('cv_mean', 0.0):.4f} ± {best.get('cv_std', 0.0):.4f}**"
        )
    elif status == "budget_exhausted":
        if best:
            return (
                f"⏱️ **Budget exhausted.** Best so far: **{best['experiment_id']}** — "
                f"CV: {best.get('cv_mean', 0.0):.4f}"
            )
        return "⏱️ **Budget exhausted** before any successful experiment completed."
    return f"Session ended with status: **{status}**"


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=True)
