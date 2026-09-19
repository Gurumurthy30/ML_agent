"""
FastAPI bridge server for the Multi-Agent ML Pipeline UI.

Exposes REST and SSE endpoints wrapping the pipeline graph:
  - POST /api/runs: start a new pipeline run in background thread
  - GET  /api/runs/{run_id}/stream: SSE event stream of all agent events & tokens
  - POST /api/runs/{run_id}/approve: approve, modify, or reject human-approval hard-block
  - GET  /api/runs/{run_id}/report: get the completed run's report markdown & artifact path
  - GET  /api/runs: list all recent runs
  - POST /api/datasets/upload: upload a dataset file; returns server-side path
  - GET  /api/runs/{run_id}/artifacts: catalog all artifacts for a run
  - GET  /api/runs/{run_id}/events/{event_idx}/full_output: untruncated stdout/stderr for an event
  - StaticFiles mounted at / serving the web UI

Hygiene:
  - _RUNS_LOCK guards all read-modify-write access to RUNS dict
  - TTL eviction: completed/errored runs older than RUN_TTL_HOURS are dropped; max RUN_MAX kept
  - Graph is compiled once at first use (lazy singleton via _get_compiled_graph()) —
    concurrent runs are fine because LangGraph keys state by thread_id
  - CORS origins configurable via CORS_ORIGINS env var (comma-separated)
"""
import asyncio
import json
import logging
import os
import queue
import threading
import time
from datetime import datetime, timezone, timedelta
from typing import Literal, Optional

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from langgraph.types import Command
from pydantic import BaseModel

from state import build_initial_state
from tools.logger import get_logger, log_event, publish_to_subscribers, read_events, subscribe, unsubscribe

logger = logging.getLogger("server.app")
logging.basicConfig(level=logging.INFO)

app = FastAPI(title="ML Pipeline UI Server", version="1.0.0")

# ---------------------------------------------------------------------------
# CORS — configurable via env var; defaults to permissive for local dev
# ---------------------------------------------------------------------------
_cors_origins = os.environ.get("CORS_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _cors_origins],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# In-memory run store with lock + TTL eviction
# ---------------------------------------------------------------------------
RUNS: dict[str, dict] = {}
_RUNS_LOCK = threading.Lock()

RUN_TTL_HOURS = int(os.environ.get("RUN_TTL_HOURS", "24"))
RUN_MAX = int(os.environ.get("RUN_MAX_KEPT", "50"))

# Max length for stdout/stderr sent over SSE to avoid overwhelming the browser
MAX_STREAM_OUTPUT_LEN = 5000

# Upload directory
_UPLOAD_DIR = os.path.join("artifacts", "uploads")
os.makedirs(_UPLOAD_DIR, exist_ok=True)

# Allowed dataset extensions for upload
_ALLOWED_EXTS = {".csv", ".parquet", ".pq"}
_MAX_UPLOAD_BYTES = 500 * 1024 * 1024  # 500 MB


# ---------------------------------------------------------------------------
# Compiled graph — lazy singleton (MemorySaver keys by thread_id, so a single
# compiled graph safely handles multiple concurrent runs)
# ---------------------------------------------------------------------------
_compiled_graph_lock = threading.Lock()
_compiled_graph = None


def _get_compiled_graph():
    """Return the lazily-compiled graph instance, building it once on first use."""
    global _compiled_graph
    if _compiled_graph is not None:
        return _compiled_graph
    with _compiled_graph_lock:
        if _compiled_graph is None:
            from graph import build_graph
            _compiled_graph = build_graph()
            logger.info("Pipeline graph compiled and cached")
    return _compiled_graph


# ---------------------------------------------------------------------------
# RUNS dict helpers (always call with _RUNS_LOCK held or via these fns)
# ---------------------------------------------------------------------------

def _evict_old_runs():
    """Remove completed/errored runs older than RUN_TTL_HOURS, cap at RUN_MAX.
    Called from create_run (non-critical path) — must be called with _RUNS_LOCK held.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=RUN_TTL_HOURS)
    to_delete = []
    for run_id, entry in RUNS.items():
        if entry["status"] in ("completed", "error"):
            created = entry.get("created_at", "")
            try:
                ts = datetime.fromisoformat(created)
                if ts < cutoff:
                    to_delete.append(run_id)
            except ValueError:
                pass
    for run_id in to_delete:
        del RUNS[run_id]
        logger.info("Evicted stale run %s", run_id)

    # Cap total
    if len(RUNS) > RUN_MAX:
        sorted_runs = sorted(
            RUNS.items(),
            key=lambda kv: kv[1].get("created_at", ""),
        )
        excess = len(RUNS) - RUN_MAX
        for run_id, _ in sorted_runs[:excess]:
            del RUNS[run_id]
            logger.info("Evicted oldest run %s (cap=%d)", run_id, RUN_MAX)


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class CreateRunRequest(BaseModel):
    dataset_path: str
    mode: Literal["eda_only", "full_pipeline"] = "full_pipeline"
    guided_mode: bool = False


class ApproveRequest(BaseModel):
    approval_status: Literal["approved", "modify", "reject"]


# ---------------------------------------------------------------------------
# Event translation
# ---------------------------------------------------------------------------

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
    elif event_type == "lookup" and raw.get("triggering_agent"):
        # RAG lookup attributed to the calling agent — expose triggering_agent for UI
        canonical_type = "run_memory_lookup"
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
    elif agent == "coder_agent" and event_type == "mcp_fallback":
        canonical_type = "mcp_fallback"
    elif event_type in ("retry_cap_override", "stalled_retry_escalation",
                        "global_iteration_ceiling", "iteration_result", "run_stop_reason"):
        canonical_type = event_type  # pass through for raw event log & UI visibility

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
                            with _RUNS_LOCK:
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
            reason = final_state.values.get("approval_reason")
            feature_plan = final_state.values.get("feature_plan")
            stop_reason = final_state.values.get("stop_reason") or (
                "stalled" if reason == "stalled" else "hit_safety_ceiling" if reason == "global_iteration_ceiling" else "paused"
            )
            with _RUNS_LOCK:
                RUNS[run_id]["status"] = "paused_for_approval"
                RUNS[run_id]["stop_reason"] = stop_reason
            publish_to_subscribers(run_id, {
                "type": "approval_required",
                "event": "approval_required",
                "run_id": run_id,
                "reason": reason,
                "stop_reason": stop_reason,
                "feature_plan": feature_plan,
                "ts": datetime.now(timezone.utc).isoformat(),
            })
        else:
            # Fully completed
            stop_reason = final_state.values.get("stop_reason") or "converged"
            with _RUNS_LOCK:
                RUNS[run_id]["status"] = "completed"
                RUNS[run_id]["stop_reason"] = stop_reason
                if not RUNS[run_id].get("report") and final_state.values.get("report"):
                    RUNS[run_id]["report"] = final_state.values.get("report")
                    RUNS[run_id]["artifact_path"] = final_state.values.get("artifact_path")
            report = RUNS[run_id].get("report")
            if report:
                publish_to_subscribers(run_id, {
                    "type": "report_ready",
                    "event": "report_ready",
                    "run_id": run_id,
                    "report": report,
                    "artifact_path": RUNS[run_id].get("artifact_path"),
                    "ts": datetime.now(timezone.utc).isoformat(),
                })
            publish_to_subscribers(run_id, {
                "type": "run_complete",
                "event": "run_complete",
                "run_id": run_id,
                "stop_reason": stop_reason,
                "ts": datetime.now(timezone.utc).isoformat(),
            })
    except Exception as exc:
        logger.exception("Error executing pipeline run %s: %s", run_id, exc)
        with _RUNS_LOCK:
            RUNS[run_id]["status"] = "error"
            RUNS[run_id]["stop_reason"] = "errored"
            RUNS[run_id]["error"] = str(exc)
        publish_to_subscribers(run_id, {
            "type": "run_error",
            "event": "run_error",
            "run_id": run_id,
            "stop_reason": "errored",
            "error": str(exc),
            "ts": datetime.now(timezone.utc).isoformat(),
        })


# ---------------------------------------------------------------------------
# API Routes
# ---------------------------------------------------------------------------

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
    graph = _get_compiled_graph()
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

    with _RUNS_LOCK:
        RUNS[run_id] = run_entry
        _evict_old_runs()

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
    with _RUNS_LOCK:
        run_exists = run_id in RUNS
    if not run_exists:
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
    with _RUNS_LOCK:
        run_entry = RUNS.get(run_id)

    if run_entry is None:
        raise HTTPException(
            status_code=404,
            detail=f"Run '{run_id}' not found in active session (the server may have been restarted).",
        )

    if run_entry["status"] != "paused_for_approval":
        if run_entry["status"] == "running":
            return {"status": "already_running", "approval_status": req.approval_status}
        raise HTTPException(
            status_code=400,
            detail=f"Run is not paused for approval (current status: {run_entry['status']})",
        )

    with _RUNS_LOCK:
        RUNS[run_id]["status"] = "running"

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
    with _RUNS_LOCK:
        RUNS[run_id]["thread"] = thread
    thread.start()

    return {"status": "resumed", "approval_status": req.approval_status}


@app.get("/api/runs/{run_id}/report")
def get_run_report(run_id: str):
    """Retrieve report markdown and artifact path for a run."""
    with _RUNS_LOCK:
        run_entry = RUNS.get(run_id)
    if run_entry is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    return {
        "run_id": run_id,
        "status": run_entry["status"],
        "report": run_entry.get("report"),
        "artifact_path": run_entry.get("artifact_path"),
    }


@app.get("/api/runs")
def list_runs():
    """List all tracked runs with metadata for the UI sidebar."""
    with _RUNS_LOCK:
        runs_snapshot = list(RUNS.values())
    return [
        {
            "run_id": r["run_id"],
            "status": r["status"],
            "stop_reason": r.get("stop_reason"),
            "dataset_path": r["dataset_path"],
            "mode": r["mode"],
            "guided_mode": r["guided_mode"],
            "has_report": bool(r.get("report")),
            "created_at": r["created_at"],
        }
        for r in runs_snapshot
    ]


@app.post("/api/datasets/upload")
async def upload_dataset(file: UploadFile = File(...)):
    """
    Upload a dataset file to the server and return its path.
    The UI can then use the returned path to start a run without needing the user
    to know or type a server-side filesystem path.

    Validates:
      - File extension: must be .csv, .parquet, or .pq
      - File size: must be <= MAX_UPLOAD_BYTES (500 MB)
    """
    # Validate extension — sanitize filename first
    original_name = os.path.basename(file.filename or "upload")
    name_clean = "".join(c for c in original_name if c.isalnum() or c in (".", "_", "-"))
    if not name_clean:
        name_clean = "upload.csv"

    ext = os.path.splitext(name_clean)[1].lower()
    if ext not in _ALLOWED_EXTS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Allowed: {', '.join(_ALLOWED_EXTS)}",
        )

    # Read and size-check
    contents = await file.read()
    if len(contents) > _MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large ({len(contents) // (1024*1024)} MB). Max allowed: {_MAX_UPLOAD_BYTES // (1024*1024)} MB",
        )

    # Write with timestamp prefix to avoid collisions
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    dest_name = f"{ts}_{name_clean}"
    dest_path = os.path.abspath(os.path.join(_UPLOAD_DIR, dest_name))

    with open(dest_path, "wb") as f:
        f.write(contents)

    logger.info("Dataset uploaded: %s (%d bytes)", dest_path, len(contents))
    return {"path": dest_path, "filename": dest_name, "size_bytes": len(contents)}


@app.get("/api/runs/{run_id}/artifacts")
def get_run_artifacts(run_id: str):
    """
    Catalog all artifacts produced for a run: report, model files, RAG entries.
    Built on-demand by reading the run's state and JSONL event log — no database needed.
    """
    with _RUNS_LOCK:
        run_entry = RUNS.get(run_id)

    artifacts = {"run_id": run_id, "report": None, "models": [], "rag_entries": []}

    # Report
    if run_entry and run_entry.get("report"):
        # Try to find the written .md file
        from tools.logger import LOG_DIR
        report_path = os.path.join("artifacts", "reports", f"{run_id}_report.md")
        artifacts["report"] = {
            "path": report_path if os.path.exists(report_path) else None,
            "artifact_path": run_entry.get("artifact_path"),
        }

    # Models and RAG entries — read from event log
    events = read_events(run_id)
    for ev in events:
        if ev.get("event") == "attempt_result" and ev.get("agent") == "coder_agent":
            # Check if it produced a .joblib file
            pass  # artifact_path from candidate_models is more reliable

    # candidate_models from event log (modeler loop_end carries n_candidates count;
    # the model files are in artifacts/models/)
    model_dir = os.path.abspath("artifacts/models")
    if os.path.exists(model_dir):
        for fname in os.listdir(model_dir):
            if fname.startswith(run_id):
                artifacts["models"].append({
                    "filename": fname,
                    "path": os.path.join(model_dir, fname),
                    "size_bytes": os.path.getsize(os.path.join(model_dir, fname)),
                })

    # RAG entries written during this run
    for ev in events:
        if ev.get("event") == "stored" and "dataset_fingerprint" in ev:
            artifacts["rag_entries"].append({
                "run_id": ev.get("run_id"),
                "text_len": ev.get("text_len"),
                "ts": ev.get("ts"),
            })

    return artifacts


@app.get("/api/runs/{run_id}/events/{event_idx}/full_output")
def get_event_full_output(run_id: str, event_idx: int):
    """
    Return full (untruncated) stdout/stderr for a specific event index.
    The stream truncates to MAX_STREAM_OUTPUT_LEN; this reads the raw JSONL log for the
    complete content — useful for long Coder execution outputs.
    """
    events = read_events(run_id)
    if event_idx < 0 or event_idx >= len(events):
        raise HTTPException(
            status_code=404,
            detail=f"Event index {event_idx} out of range (run has {len(events)} events)",
        )
    ev = events[event_idx]
    return {
        "event_idx": event_idx,
        "run_id": run_id,
        "agent": ev.get("agent"),
        "event": ev.get("event"),
        "ts": ev.get("ts"),
        "stdout": ev.get("stdout"),
        "stderr": ev.get("stderr"),
        "code": ev.get("code"),
    }


# Mount static files at the root ONLY AFTER all API routes are defined
web_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web")
os.makedirs(web_dir, exist_ok=True)
app.mount("/", StaticFiles(directory=web_dir, html=True), name="web")
