"""
FastAPI bridge server for the Multi-Agent ML Pipeline UI.

Exposes REST and SSE endpoints wrapping the pipeline graph:
  - POST /api/runs: start a new pipeline run in background thread
  - GET  /api/runs/{run_id}/stream: SSE event stream of all agent events & tokens
  - POST /api/runs/{run_id}/approve: approve, modify, or reject human-approval hard-block
  - GET  /api/runs/{run_id}/report: get the completed run's report markdown & artifact path
  - GET  /api/runs: list all recent runs
  - StaticFiles mounted at / serving the web UI
"""
import asyncio
import json
import logging
import os
import queue
import threading
from datetime import datetime, timezone
from typing import Literal, Optional

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from langgraph.types import Command
from pydantic import BaseModel

from graph import build_graph
from state import build_initial_state
from tools.logger import get_logger, publish_to_subscribers, subscribe, unsubscribe

logger = logging.getLogger("server.app")
logging.basicConfig(level=logging.INFO)

app = FastAPI(title="ML Pipeline UI Server", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory store: run_id -> run details
RUNS: dict[str, dict] = {}

# Max length for stdout/stderr sent over SSE to avoid overwhelming the browser
MAX_STREAM_OUTPUT_LEN = 5000


class CreateRunRequest(BaseModel):
    dataset_path: str
    mode: Literal["eda_only", "full_pipeline"] = "full_pipeline"
    guided_mode: bool = False


class ApproveRequest(BaseModel):
    approval_status: Literal["approved", "modify", "reject"]


def _truncate_text(text: Optional[str], max_len: int = MAX_STREAM_OUTPUT_LEN) -> Optional[str]:
    if text is None or len(text) <= max_len:
        return text
    half = max_len // 2
    return text[:half] + f"\n\n[... {len(text) - max_len} characters truncated for streaming, full output in logs ...]\n\n" + text[-half:]


def translate_event(raw: dict) -> dict:
    """
    Translate internal agent log_event payloads to canonical SSE event types.
    Ensures both `type` and `event` keys are present and consistent.
    """
    event_type = raw.get("event") or raw.get("type", "unknown")
    agent = raw.get("agent", "")
    data = dict(raw)

    canonical_type = event_type
    if agent == "judge_agent" and event_type == "verdict":
        canonical_type = "judge_verdict"
    elif agent == "run_memory" and event_type == "lookup":
        canonical_type = "run_memory_lookup"
    elif agent == "features_agent" and event_type == "hard_block":
        canonical_type = "hard_block"
    elif agent == "reporter_agent" and event_type == "report_written":
        canonical_type = "report_ready"
    elif agent == "profiler_agent" and event_type == "profile_ready":
        canonical_type = "profile_ready"
    elif agent == "supervisor" and event_type == "routed":
        canonical_type = "supervisor_routed"
    elif agent == "coder_agent" and event_type == "attempt_result":
        canonical_type = "attempt_result"
        if "stdout" in data:
            data["stdout"] = _truncate_text(data.get("stdout"))
        if "stderr" in data:
            data["stderr"] = _truncate_text(data.get("stderr"))

    data["type"] = canonical_type
    data["event"] = canonical_type
    return data


def _execute_graph_stream(run_id: str, graph, stream_input, config: dict):
    """
    Stream graph execution, emitting node_start, node_end, and detecting pauses/completion.
    """
    try:
        for mode, payload in graph.stream(stream_input, config=config, stream_mode=["updates", "debug"]):
            if mode == "debug" and payload.get("type") == "task":
                node_name = payload.get("payload", {}).get("name")
                if node_name and node_name not in ("__start__", "__end__"):
                    publish_to_subscribers(run_id, {
                        "type": "node_start",
                        "event": "node_start",
                        "node": node_name,
                        "agent": node_name,
                        "run_id": run_id,
                        "ts": datetime.now(timezone.utc).isoformat(),
                    })
            elif mode == "updates":
                for node_name, state_update in payload.items():
                    if node_name == "__interrupt__":
                        continue
                    publish_to_subscribers(run_id, {
                        "type": "node_end",
                        "event": "node_end",
                        "node": node_name,
                        "agent": node_name,
                        "run_id": run_id,
                        "state_update": state_update,
                        "ts": datetime.now(timezone.utc).isoformat(),
                    })
                    if node_name == "reporter" and isinstance(state_update, dict):
                        if state_update.get("report"):
                            RUNS[run_id]["report"] = state_update["report"]
                            RUNS[run_id]["artifact_path"] = state_update.get("artifact_path")
                            publish_to_subscribers(run_id, {
                                "type": "report_ready",
                                "event": "report_ready",
                                "run_id": run_id,
                                "report": state_update["report"],
                                "artifact_path": state_update.get("artifact_path"),
                                "ts": datetime.now(timezone.utc).isoformat(),
                            })

        # Check final graph state after stream exits
        final_state = graph.get_state(config)
        if final_state.next:
            # Paused at interrupt (e.g. human_approval)
            RUNS[run_id]["status"] = "paused_for_approval"
            reason = final_state.values.get("approval_reason")
            feature_plan = final_state.values.get("feature_plan")
            publish_to_subscribers(run_id, {
                "type": "approval_required",
                "event": "approval_required",
                "run_id": run_id,
                "reason": reason,
                "feature_plan": feature_plan,
                "ts": datetime.now(timezone.utc).isoformat(),
            })
        else:
            # Fully completed
            RUNS[run_id]["status"] = "completed"
            if not RUNS[run_id].get("report") and final_state.values.get("report"):
                RUNS[run_id]["report"] = final_state.values.get("report")
                RUNS[run_id]["artifact_path"] = final_state.values.get("artifact_path")
                publish_to_subscribers(run_id, {
                    "type": "report_ready",
                    "event": "report_ready",
                    "run_id": run_id,
                    "report": RUNS[run_id]["report"],
                    "artifact_path": RUNS[run_id]["artifact_path"],
                    "ts": datetime.now(timezone.utc).isoformat(),
                })
            publish_to_subscribers(run_id, {
                "type": "run_complete",
                "event": "run_complete",
                "run_id": run_id,
                "ts": datetime.now(timezone.utc).isoformat(),
            })
    except Exception as exc:
        logger.exception("Error executing pipeline run %s: %s", run_id, exc)
        RUNS[run_id]["status"] = "error"
        RUNS[run_id]["error"] = str(exc)
        publish_to_subscribers(run_id, {
            "type": "run_error",
            "event": "run_error",
            "run_id": run_id,
            "error": str(exc),
            "ts": datetime.now(timezone.utc).isoformat(),
        })


@app.post("/api/runs")
def create_run(req: CreateRunRequest):
    """
    Start a new pipeline run in a background thread.
    Returns immediately with run_id.
    """
    if not os.path.exists(req.dataset_path):
        raise HTTPException(
            status_code=400,
            detail=f"Dataset file not found at path: {req.dataset_path}",
        )

    initial_state = build_initial_state(
        dataset_path=req.dataset_path,
        mode=req.mode,
        guided_mode=req.guided_mode,
    )
    run_id = initial_state["run_id"]
    graph = build_graph()
    config = {"configurable": {"thread_id": run_id}}

    run_entry = {
        "run_id": run_id,
        "status": "running",
        "dataset_path": req.dataset_path,
        "mode": req.mode,
        "guided_mode": req.guided_mode,
        "graph": graph,
        "config": config,
        "report": None,
        "artifact_path": None,
        "error": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    RUNS[run_id] = run_entry

    thread = threading.Thread(
        target=_execute_graph_stream,
        args=(run_id, graph, initial_state, config),
        daemon=True,
    )
    run_entry["thread"] = thread
    thread.start()

    return {"run_id": run_id, "status": "running"}


@app.get("/api/runs/{run_id}/stream")
async def stream_run_events(run_id: str):
    """
    Server-Sent Events endpoint streaming all structured logs, node changes,
    tokens, verdicts, approvals, and report ready notifications for a run.
    """
    if run_id not in RUNS:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")

    q = subscribe(run_id)

    async def event_generator():
        try:
            while True:
                try:
                    # Non-blocking wait in thread pool with 10s timeout for keep-alive ping
                    item = await asyncio.to_thread(q.get, timeout=10.0)
                    translated = translate_event(item)
                    yield f"data: {json.dumps(translated, default=str)}\n\n"
                    if translated.get("type") in ("run_complete", "run_error"):
                        break
                except queue.Empty:
                    # Keep-alive comment so browser connection stays alive during slow LLM calls
                    yield ": ping\n\n"
        finally:
            unsubscribe(run_id, q)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/runs/{run_id}/approve")
def approve_run(run_id: str, req: ApproveRequest):
    """
    Resume a paused run with human decision (approved, modify, or reject).
    """
    if run_id not in RUNS:
        raise HTTPException(
            status_code=404,
            detail=f"Run '{run_id}' not found in active session (the server may have been restarted).",
        )

    run_entry = RUNS[run_id]
    if run_entry["status"] != "paused_for_approval":
        if run_entry["status"] == "running":
            return {"status": "already_running", "approval_status": req.approval_status}
        raise HTTPException(
            status_code=400,
            detail=f"Run is not paused for approval (current status: {run_entry['status']})",
        )

    run_entry["status"] = "running"
    graph = run_entry["graph"]
    config = run_entry["config"]

    publish_to_subscribers(run_id, {
        "type": "approval_resumed",
        "event": "approval_resumed",
        "run_id": run_id,
        "decision": req.approval_status,
        "ts": datetime.now(timezone.utc).isoformat(),
    })

    resume_command = Command(resume={"approval_status": req.approval_status})

    thread = threading.Thread(
        target=_execute_graph_stream,
        args=(run_id, graph, resume_command, config),
        daemon=True,
    )
    run_entry["thread"] = thread
    thread.start()

    return {"status": "resumed", "approval_status": req.approval_status}


@app.get("/api/runs/{run_id}/report")
def get_run_report(run_id: str):
    """
    Retrieve report markdown and artifact path for a run.
    """
    if run_id not in RUNS:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")

    run_entry = RUNS[run_id]
    return {
        "run_id": run_id,
        "status": run_entry["status"],
        "report": run_entry.get("report"),
        "artifact_path": run_entry.get("artifact_path"),
    }


@app.get("/api/runs")
def list_runs():
    """
    List all tracked runs with metadata for the UI sidebar.
    """
    return [
        {
            "run_id": r["run_id"],
            "status": r["status"],
            "dataset_path": r["dataset_path"],
            "mode": r["mode"],
            "guided_mode": r["guided_mode"],
            "has_report": bool(r.get("report")),
            "created_at": r["created_at"],
        }
        for r in RUNS.values()
    ]


# Mount static files at the root ONLY AFTER all API routes are defined
web_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web")
os.makedirs(web_dir, exist_ok=True)
app.mount("/", StaticFiles(directory=web_dir, html=True), name="web")
