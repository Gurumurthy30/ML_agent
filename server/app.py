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
import traceback as _traceback
from datetime import datetime, timezone, timedelta
from typing import Literal, Optional

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, File, HTTPException, UploadFile, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from langgraph.types import Command
from pydantic import BaseModel

from state import build_initial_state
from tools.logger import get_logger, log_event, publish_to_subscribers, read_events, subscribe, unsubscribe
from tools import tracer
from utils.safe import safe_json

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

# Intent descriptions emitted on node_start events so the UI shows "what this node is about to do"
_NODE_INTENTS = {
    "supervisor": "Analyse pipeline state and decide which specialist agent runs next",
    "profiler": "Profile the dataset — infer types, statistics, quality flags, and recommended metric",
    "eda_agent": "Explore the dataset — compute correlations, distributions, and statistical insights",
    "features": "Engineer feature transformations and compute a structural diff of the dataset",
    "modeler": "Search model families, tune hyperparameters internally, and select the best CV score",
    "judge": "Evaluate result quality and decide whether to accept or retry at a specific tier",
    "human_approval": "Pause for human review of a proposed feature transformation or escalation decision",
    "reporter": "Synthesise the full pipeline run into a structured Markdown report",
}

# Per-run node start timestamps for duration_ms computation
_NODE_START_TIMES: dict[str, dict[str, float]] = {}
_NODE_TIMES_LOCK = threading.Lock()


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


class ControlRequest(BaseModel):
    action: Literal["pause", "resume", "stop", "escalate", "retry_node"]
    prompt_override: Optional[str] = None
    node: Optional[str] = None


class CompareRequest(BaseModel):
    run_id_a: str
    run_id_b: str


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
    elif agent == "supervisor" and event_type in ("routed", "supervisor_decision"):
        canonical_type = "supervisor_decision"
    elif agent == "coder_agent" and event_type == "attempt_result":
        canonical_type = "attempt_result"
        if "stdout" in data:
            data["stdout"] = _truncate_text(data.get("stdout"))
        if "stderr" in data:
            data["stderr"] = _truncate_text(data.get("stderr"))
    elif agent == "coder_agent" and event_type == "mcp_fallback":
        canonical_type = "mcp_fallback"
    elif event_type in ("retry_cap_override", "stalled_retry_escalation",
                        "global_iteration_ceiling", "iteration_result", "run_stop_reason",
                        "supervisor_decision", "node_start", "node_end",
                        "approval_required", "run_complete", "run_error", "run_stopped",
                        "approval_resumed", "duplicate_idea_rejected"):
        canonical_type = event_type  # pass through

    data["type"] = canonical_type
    data["event"] = canonical_type
    return data


def _execute_graph_stream(run_id: str, graph, stream_input, config: dict):
    """
    Stream graph execution, emitting node_start, node_end, and detecting pauses/completion.
    All lifecycle events are routed through tracer.record_event() so they receive an
    event_id, seq number, and are persisted to JSONL + SQLite for SSE replay.
    """
    ctrl = tracer.get_run_control(run_id)
    start_time = time.time()
    try:
        for mode, payload in graph.stream(stream_input, config=config, stream_mode=["updates", "debug"]):
            if not ctrl.wait_if_paused():
                break
            if ctrl.stopped:
                tracer.record_event(run_id, "server", "run_stopped", reason="user_stopped", stop_reason="user_stopped")
                break

            if mode == "debug" and payload.get("type") == "task":
                node_name = payload.get("payload", {}).get("name")
                if node_name and node_name not in ("__start__", "__end__"):
                    with _NODE_TIMES_LOCK:
                        _NODE_START_TIMES.setdefault(run_id, {})[node_name] = time.time()
                    tracer.record_event(
                        run_id, node_name, "node_start",
                        intent=_NODE_INTENTS.get(node_name, f"Running {node_name}"),
                        node=node_name,
                        state_replace=False,
                    )
            elif mode == "updates":
                for node_name, state_update in payload.items():
                    if node_name == "__interrupt__":
                        continue
                    # Compute duration_ms if we recorded a start time
                    duration_ms = None
                    with _NODE_TIMES_LOCK:
                        t0 = _NODE_START_TIMES.get(run_id, {}).pop(node_name, None)
                    if t0 is not None:
                        duration_ms = int((time.time() - t0) * 1000)

                    # Generate a summary line from the keys written
                    if isinstance(state_update, dict):
                        written_keys = [k for k, v in state_update.items() if v is not None]
                        summary = f"{node_name} wrote: {', '.join(written_keys[:6])}" if written_keys else f"{node_name} completed"
                    else:
                        summary = f"{node_name} completed"

                    tracer.record_event(
                        run_id, node_name, "node_end",
                        duration_ms=duration_ms,
                        summary=summary,
                        node=node_name,
                        state_update=safe_json(state_update) if isinstance(state_update, dict) else None,
                        state_replace=False,
                    )

                    if node_name == "reporter" and isinstance(state_update, dict):
                        if state_update.get("report"):
                            with _RUNS_LOCK:
                                RUNS[run_id]["report"] = state_update["report"]
                                RUNS[run_id]["artifact_path"] = state_update.get("artifact_path")
                            tracer.record_event(
                                run_id, "reporter", "report_ready",
                                report=state_update["report"],
                                artifact_path=state_update.get("artifact_path"),
                            )

        # Check final graph state after stream exits
        final_state = graph.get_state(config)
        duration_s = round(time.time() - start_time, 2)

        if ctrl.stopped:
            with _RUNS_LOCK:
                RUNS[run_id]["status"] = "stopped"
                RUNS[run_id]["stop_reason"] = "user_stopped"
            tracer.update_run_status(run_id, status="stopped", stop_reason="user_stopped", duration_s=duration_s)
            tracer.record_event(run_id, "server", "run_stopped",
                                stop_reason="user_stopped", duration_ms=int(duration_s * 1000))
        elif final_state.next:
            # Paused at interrupt (e.g. human_approval)
            reason = final_state.values.get("approval_reason")
            feature_plan = final_state.values.get("feature_plan")
            stop_reason = final_state.values.get("stop_reason") or (
                "stalled" if reason == "stalled" else "hit_safety_ceiling" if reason == "global_iteration_ceiling" else "paused"
            )
            with _RUNS_LOCK:
                RUNS[run_id]["status"] = "paused_for_approval"
                RUNS[run_id]["stop_reason"] = stop_reason
            tracer.update_run_status(run_id, status="paused_for_approval", stop_reason=stop_reason, duration_s=duration_s)
            tracer.record_event(
                run_id, "server", "approval_required",
                approval_reason=reason,
                reason=reason,
                stop_reason=stop_reason,
                feature_plan=safe_json(feature_plan),
            )
        else:
            # Fully completed
            stop_reason = final_state.values.get("stop_reason") or "converged"
            best_score = final_state.values.get("best_score")
            with _RUNS_LOCK:
                RUNS[run_id]["status"] = "completed"
                RUNS[run_id]["stop_reason"] = stop_reason
                if not RUNS[run_id].get("report") and final_state.values.get("report"):
                    RUNS[run_id]["report"] = final_state.values.get("report")
                    RUNS[run_id]["artifact_path"] = final_state.values.get("artifact_path")
            tracer.update_run_status(run_id, status="completed", stop_reason=stop_reason, best_score=best_score, duration_s=duration_s)
            # Final state snapshot for UI browser-refresh
            final_vals = safe_json(dict(final_state.values)) if final_state.values else {}
            tracer.record_event(
                run_id, "server", "run_complete",
                stop_reason=stop_reason,
                state_update=final_vals,
                state_replace=True,
                duration_ms=int(duration_s * 1000),
            )
    except Exception as exc:
        logger.exception("Error executing pipeline run %s: %s", run_id, exc)
        duration_s = round(time.time() - start_time, 2)
        tb = _traceback.format_exc()
        err_sig = tracer.compute_error_signature(type(exc).__name__, str(exc))
        with _RUNS_LOCK:
            RUNS[run_id]["status"] = "error"
            RUNS[run_id]["stop_reason"] = "errored"
            RUNS[run_id]["error"] = str(exc)
        tracer.update_run_status(run_id, status="error", stop_reason="errored", duration_s=duration_s)
        tracer.record_event(
            run_id, "server", "run_error",
            stop_reason="errored",
            error=str(exc),
            error_trace=tb,
            error_signature=err_sig,
            duration_ms=int(duration_s * 1000),
        )


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

    # Register run in SQLite index
    try:
        tracer.register_run(
            run_id=run_id,
            dataset_path=req.dataset_path,
            mode=req.mode,
            guided_mode=req.guided_mode,
        )
    except Exception as exc:
        logger.warning("Failed to register run in SQLite: %s", exc)

    thread = threading.Thread(
        target=_execute_graph_stream,
        args=(run_id, graph, initial_state, config),
        daemon=True,
    )
    run_entry["thread"] = thread
    thread.start()

    return {"run_id": run_id, "status": "running"}


@app.get("/api/runs/{run_id}/stream")
@app.get("/api/runs/{run_id}/events/stream")
async def stream_run_events(
    run_id: str,
    request: Request,
    last_event_id: Optional[str] = Query(None),
):
    """
    Server-Sent Events endpoint streaming all structured logs, node changes,
    tokens, verdicts, approvals, and report ready notifications for a run.
    Supports reconnection and catch-up replay via Last-Event-ID header or query param.
    """
    with _RUNS_LOCK:
        run_exists = run_id in RUNS
    if not run_exists and not tracer.get_run(run_id):
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")

    client_last_id = request.headers.get("Last-Event-ID") or last_event_id
    since_seq = 0
    if client_last_id:
        try:
            parts = str(client_last_id).split("_")
            since_seq = int(parts[-1])
        except Exception:
            since_seq = 0

    q = subscribe(run_id)

    async def event_generator():
        try:
            # 1. Replay missed events from SQLite / disk if reconnecting
            if since_seq > 0:
                past_events = tracer.get_run_events(run_id, since_seq=since_seq)
                for pe in past_events:
                    translated = translate_event(pe)
                    ev_id = translated.get("event_id", f"{run_id}_{translated.get('seq', 0):05d}")
                    ev_type = translated.get("type", "message")
                    yield f"id: {ev_id}\nevent: {ev_type}\ndata: {json.dumps(safe_json(translated))}\n\n"

            # 2. Live streaming from queue
            while True:
                try:
                    item = await asyncio.to_thread(q.get, timeout=10.0)
                    translated = translate_event(item)
                    ev_id = translated.get("event_id", f"{run_id}_{translated.get('seq', 0):05d}")
                    ev_type = translated.get("type", "message")
                    yield f"id: {ev_id}\nevent: {ev_type}\ndata: {json.dumps(safe_json(translated))}\n\n"
                    if translated.get("type") in ("run_complete", "run_error", "run_stopped"):
                        break
                except queue.Empty:
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

    graph = run_entry["graph"]
    config = run_entry["config"]
    curr_state = graph.get_state(config)
    is_interrupted = bool(curr_state.next)

    if not is_interrupted and run_entry["status"] != "paused_for_approval":
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

    tracer.record_event(
        run_id, "server", "approval_resumed",
        decision=req.approval_status,
    )

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
        mem_runs = {r["run_id"]: r for r in RUNS.values()}

    db_runs = tracer.list_runs(limit=50)
    result = []
    seen = set()

    # Prioritize active in-memory runs first
    for r in mem_runs.values():
        seen.add(r["run_id"])
        result.append({
            "run_id": r["run_id"],
            "status": r["status"],
            "stop_reason": r.get("stop_reason"),
            "dataset_path": r["dataset_path"],
            "mode": r["mode"],
            "guided_mode": r["guided_mode"],
            "has_report": bool(r.get("report")),
            "created_at": r["created_at"],
        })

    # Add historical runs from SQLite
    for dbr in db_runs:
        rid = dbr["run_id"]
        if rid not in seen:
            seen.add(rid)
            result.append({
                "run_id": rid,
                "status": dbr.get("status", "unknown"),
                "stop_reason": dbr.get("stop_reason"),
                "dataset_path": dbr.get("dataset_path", ""),
                "mode": dbr.get("mode", "full_pipeline"),
                "guided_mode": bool(dbr.get("guided_mode")),
                "best_score": dbr.get("best_score"),
                "has_report": os.path.exists(os.path.join("artifacts", "reports", f"{rid}_report.md")),
                "created_at": dbr.get("created_at", ""),
            })

    return result


@app.get("/api/runs/{run_id}")
def get_run_details(run_id: str):
    """Retrieve full status, best score, resource metrics, and metadata for a run."""
    with _RUNS_LOCK:
        mem = RUNS.get(run_id)
    db_run = tracer.get_run(run_id) or {}
    if not mem and not db_run:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")

    status = (mem.get("status") if mem else None) or db_run.get("status", "unknown")
    stop_reason = (mem.get("stop_reason") if mem else None) or db_run.get("stop_reason")
    report = (mem.get("report") if mem else None)
    artifact_path = (mem.get("artifact_path") if mem else None)

    if not report:
        report_file = os.path.join("artifacts", "reports", f"{run_id}_report.md")
        if os.path.exists(report_file):
            try:
                with open(report_file, "r", encoding="utf-8") as f:
                    report = f.read()
            except Exception:
                pass

    return {
        "run_id": run_id,
        "status": status,
        "stop_reason": stop_reason,
        "dataset_path": (mem.get("dataset_path") if mem else None) or db_run.get("dataset_path"),
        "mode": (mem.get("mode") if mem else None) or db_run.get("mode"),
        "guided_mode": (mem.get("guided_mode") if mem else None) or bool(db_run.get("guided_mode")),
        "best_score": db_run.get("best_score"),
        "baseline_score": db_run.get("baseline_score"),
        "total_attempts": db_run.get("total_attempts", 0),
        "total_tokens_in": db_run.get("total_tokens_in", 0),
        "total_tokens_out": db_run.get("total_tokens_out", 0),
        "total_cost_usd": db_run.get("total_cost_usd", 0.0),
        "duration_s": db_run.get("duration_s", 0.0),
        "error_count": db_run.get("error_count", 0),
        "has_report": bool(report),
        "report": report,
        "artifact_path": artifact_path,
        "created_at": (mem.get("created_at") if mem else None) or db_run.get("created_at"),
    }


@app.get("/api/runs/{run_id}/events")
def get_run_events_api(run_id: str, since_seq: int = 0, limit: Optional[int] = None):
    """Retrieve structured events for run, supporting incremental polling / replay."""
    return tracer.get_run_events(run_id, since_seq=since_seq, limit=limit)


@app.get("/api/runs/{run_id}/attempts")
def get_run_attempts_api(run_id: str):
    """Retrieve structured model/feature attempt ledger for the run."""
    return tracer.get_run_attempts(run_id)


@app.get("/api/runs/{run_id}/errors")
def get_run_errors_api(run_id: str):
    """Retrieve aggregated error center grouped by signature with loop detection."""
    return tracer.get_run_errors(run_id)


@app.post("/api/runs/{run_id}/control")
def control_run_api(run_id: str, req: ControlRequest):
    """Interactive human-in-the-loop control (pause, resume, stop, escalate, retry_node)."""
    ctrl = tracer.get_run_control(run_id)
    if req.action == "pause":
        ctrl.pause()
        tracer.record_event(run_id, "control", "run_paused", intent="User requested pause")
        with _RUNS_LOCK:
            if run_id in RUNS:
                RUNS[run_id]["status"] = "paused"
        tracer.update_run_status(run_id, status="paused")
        return {"status": "paused", "run_id": run_id}
    elif req.action == "resume":
        ctrl.resume()
        tracer.record_event(run_id, "control", "run_resumed", intent="User requested resume")
        with _RUNS_LOCK:
            if run_id in RUNS and RUNS[run_id].get("status") != "paused_for_approval":
                RUNS[run_id]["status"] = "running"
        db_run = tracer.get_run(run_id)
        if db_run and db_run.get("status") != "paused_for_approval":
            tracer.update_run_status(run_id, status="running")
        return {"status": "resumed", "run_id": run_id}
    elif req.action == "stop":
        ctrl.stop()
        tracer.record_event(run_id, "control", "run_stopped", intent="User requested emergency stop")
        with _RUNS_LOCK:
            if run_id in RUNS:
                RUNS[run_id]["status"] = "stopped"
                RUNS[run_id]["stop_reason"] = "user_stopped"
        tracer.update_run_status(run_id, status="stopped", stop_reason="user_stopped")
        return {"status": "stopped", "run_id": run_id}
    elif req.action == "escalate":
        ctrl.escalate()
        tracer.record_event(run_id, "control", "force_escalate", intent="User requested force escalation to next tier")
        return {"status": "escalated", "run_id": run_id}
    elif req.action == "retry_node":
        ctrl.set_prompt_override(req.prompt_override or "", req.node)
        tracer.record_event(run_id, "control", "retry_node", node=req.node, prompt_override=req.prompt_override)
        return {"status": "retry_scheduled", "run_id": run_id, "node": req.node}
    raise HTTPException(status_code=400, detail=f"Unknown control action '{req.action}'")


@app.post("/api/runs/compare")
def compare_runs_api(req: CompareRequest):
    """Side-by-side run comparison for configs, metrics, tokens, and best code."""
    return tracer.compare_runs(req.run_id_a, req.run_id_b)


@app.get("/api/runs/{run_id}/export")
def export_run_bundle_api(run_id: str):
    """Download full run debug bundle as a ZIP file."""
    zip_path = tracer.export_run_bundle(run_id)
    if not os.path.exists(zip_path):
        raise HTTPException(status_code=404, detail=f"Export bundle could not be generated for {run_id}")
    return FileResponse(
        path=zip_path,
        filename=f"{run_id}_debug_bundle.zip",
        media_type="application/zip",
    )


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
