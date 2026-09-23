"""
FastAPI backend application for ML_agent pipeline telemetry, monitoring, and run control.

Implements:
  - POST /runs: Validate inputs, create run record, spawn graph in background
  - GET  /runs: List runs with tag and is_baseline filters
  - GET  /runs/{id}: Get run metadata
  - GET  /runs/{id}/events: SSE stream (historical catch-up from since_seq + live stream)
  - GET  /runs/{id}/attempts: Materialized attempt ledger
  - GET  /runs/{id}/errors: Aggregated error ledger
  - POST /runs/{id}/resume: Resume paused/guided graph run with decision
  - POST /runs/{id}/pause | /unpause | /stop: Run lifecycle controls
  - GET  /runs/{a}/compare/{b}: Side-by-side run comparison
  - GET  /runs/{id}/export: ZIP debug bundle download
  - POST /runs/{id}/tags: Update run tags
  - POST /runs/{id}/baseline: Set run baseline flag and score
"""
from dotenv import load_dotenv

load_dotenv()

import asyncio
import json
import logging
import os
import queue
import threading
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse
from langgraph.types import Command

from state import build_initial_state
from graph import build_graph
from tools.tracer import (
    init_db,
    rotate_and_prune_storage,
    create_run,
    list_runs,
    get_run,
    get_run_events,
    get_run_attempts,
    get_run_errors,
    get_run_iterations,
    update_run_status,
    get_run_control,
    compare_runs,
    export_run_bundle,
    set_run_tags,
    add_run_tag,
    set_run_baseline,
)
from tools.logger import subscribe, unsubscribe, get_logger

logger = logging.getLogger("api.main")

# ---------------------------------------------------------------------------
# Lifespan Management
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application startup and shutdown management.
    Ensures SQLite migrations are applied and runs the storage retention policy.
    """
    init_db()
    try:
        prune_summary = rotate_and_prune_storage()
        logger.info("Storage retention check completed on startup: %s", prune_summary)
    except Exception as exc:
        logger.warning("Startup storage prune encountered an error: %s", exc)
    yield


app = FastAPI(
    title="ML_agent API",
    description="Telemetry, monitoring, and run control backend for ML_agent",
    version="1.0.0",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# CORS Configuration (Local development friendly)
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Graph & Background Execution Helper
# ---------------------------------------------------------------------------
_APP_GRAPH = None
_GRAPH_LOCK = threading.Lock()


def get_pipeline_graph():
    global _APP_GRAPH
    with _GRAPH_LOCK:
        if _APP_GRAPH is None:
            _APP_GRAPH = build_graph()
        return _APP_GRAPH


def _execute_graph_worker(graph, stream_input, config: Dict[str, Any], run_id: str):
    log = get_logger(run_id)
    ctrl = get_run_control(run_id)
    log.info("Beginning graph execution for run %s", run_id)
    try:
        for event in graph.stream(stream_input, config=config):
            if ctrl.stopped:
                log.info("Run %s received STOP signal; aborting execution.", run_id)
                update_run_status(run_id, status="stopped", stop_reason="user_stopped")
                return
            ctrl.wait_if_paused()

        state = graph.get_state(config)
        if state and state.next:
            log.info("Run %s paused at node(s): %s", run_id, state.next)
            update_run_status(
                run_id,
                status="paused",
                stop_reason="human_approval_required" if "human_approval" in state.next else "graph_interrupted",
            )
        else:
            best_score = None
            report = None
            report_path = None
            if state and hasattr(state, "values") and isinstance(state.values, dict):
                best_score = state.values.get("best_metric") if state.values.get("best_metric") is not None else state.values.get("best_score")
                report = state.values.get("report")
                report_path = state.values.get("artifact_path")
            log.info("Run %s completed successfully. Best score: %s", run_id, best_score)
            update_run_status(run_id, status="completed", best_score=best_score, report=report, report_path=report_path)
    except Exception as exc:
        log.exception("Run %s failed with exception: %s", run_id, exc)
        update_run_status(run_id, status="failed", stop_reason=str(exc))


def _run_graph_in_background(stream_input, run_id: str) -> threading.Thread:
    graph = get_pipeline_graph()
    config = {"configurable": {"thread_id": run_id}}
    thread = threading.Thread(
        target=_execute_graph_worker,
        args=(graph, stream_input, config, run_id),
        daemon=True,
    )
    thread.start()
    return thread


# ---------------------------------------------------------------------------
# Request / Response Schemas
# ---------------------------------------------------------------------------
class RunCreateRequest(BaseModel):
    dataset_path: str = Field(..., description="Absolute or relative path to the dataset file (.csv or .parquet)")
    mode: str = Field("full_pipeline", description="Pipeline mode: 'full_pipeline' or 'eda_only'")
    guided_mode: bool = Field(False, description="Whether to require human approval on every feature modification")
    metric_name: Optional[str] = Field(None, description="Target optimization metric (e.g., 'f1', 'rmse')")
    tags: Optional[List[str]] = Field(None, description="Initial list of tags")
    labels: Optional[Dict[str, str]] = Field(None, description="Initial key-value labels")
    user_instructions: Optional[str] = Field(None, description="Custom prompt instructions for the run")
    is_baseline: bool = Field(False, description="Whether this run is designated as the baseline benchmark")
    baseline_score: Optional[float] = Field(None, description="Known baseline metric score")


class ResumeRequest(BaseModel):
    approval_status: Optional[str] = Field(None, description="Human approval verdict: 'approved', 'modify', or 'reject'")
    modifications: Optional[str] = Field(None, description="Optional modification instructions if status is 'modify'")


class TagUpdateRequest(BaseModel):
    tags: Optional[List[str]] = Field(None, description="Full replacement list of tags")
    tag: Optional[str] = Field(None, description="Single tag to append")


class BaselineUpdateRequest(BaseModel):
    is_baseline: bool = Field(True, description="Whether this run is designated as baseline")
    baseline_score: Optional[float] = Field(None, description="Optional baseline metric score")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.post("/runs", status_code=201)
def create_pipeline_run(req: RunCreateRequest):
    """
    Creates a new pipeline run, initializes state, records it in SQLite, and
    spawns execution in a background task without blocking the HTTP request.
    """
    # 1. Input validation
    if not req.dataset_path or not os.path.exists(req.dataset_path):
        raise HTTPException(
            status_code=400,
            detail=f"Dataset file not found: '{req.dataset_path}'. Please provide an existing file path.",
        )

    valid_modes = {"full_pipeline", "eda_only"}
    if req.mode not in valid_modes:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid pipeline mode '{req.mode}'. Allowed modes: {sorted(list(valid_modes))}.",
        )

    # 2. Build initial state
    try:
        initial_state = build_initial_state(
            dataset_path=req.dataset_path,
            mode=req.mode,
            guided_mode=req.guided_mode,
        )
        if req.user_instructions:
            initial_state["task_instructions"] = req.user_instructions
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed building initial pipeline state: {exc}")

    run_id = initial_state["run_id"]

    # 3. Create persistent run entry in SQLite
    create_run(
        run_id=run_id,
        dataset_path=req.dataset_path,
        mode=req.mode,
        guided_mode=req.guided_mode,
        metric_name=req.metric_name,
        is_baseline=req.is_baseline,
        baseline_score=req.baseline_score,
        tags=req.tags,
        labels=req.labels,
    )

    # 4. Spawn background execution
    _run_graph_in_background(stream_input=initial_state, run_id=run_id)

    run_record = get_run(run_id)
    return JSONResponse(
        status_code=201,
        content=run_record or {"run_id": run_id, "status": "running"},
    )


@app.get("/runs")
def list_pipeline_runs(
    limit: int = 50,
    tag: Optional[str] = None,
    is_baseline: Optional[bool] = None,
):
    """
    List recent runs with support for filtering by tag and/or baseline status.
    """
    return list_runs(limit=limit, tag=tag, is_baseline=is_baseline)


@app.get("/runs/{run_id}")
def get_pipeline_run(run_id: str):
    """
    Retrieve run metadata by run_id. Returns 404 if run does not exist.
    """
    run = get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run not found: '{run_id}'")
    return run


@app.get("/runs/{run_id}/events")
async def get_pipeline_run_events_sse(
    run_id: str,
    request: Request,
    since_seq: int = 0,
    live: bool = True,
):
    """
    SSE stream endpoint for run events.
    First yields historical events where seq > since_seq, then streams live events in real-time.
    """
    run = get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run not found: '{run_id}'")

    async def event_generator():
        last_seq = since_seq

        # 1. Historical catch-up replay
        historical = get_run_events(run_id, since_seq=since_seq)
        for ev in historical:
            seq = ev.get("seq", 0)
            if seq > last_seq:
                last_seq = seq
            yield f"event: message\ndata: {json.dumps(ev)}\n\n"

        if not live or run.get("status") in ("completed", "stopped", "failed"):
            return

        # 2. Subscribe to live queue for new events
        q = subscribe(run_id)
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    record = q.get_nowait()
                    if record:
                        seq = record.get("seq", 0)
                        if seq > last_seq:
                            last_seq = seq
                            yield f"event: message\ndata: {json.dumps(record)}\n\n"
                except queue.Empty:
                    # Check if run reached terminal state
                    current_run = get_run(run_id)
                    if current_run and current_run.get("status") in ("completed", "stopped", "failed"):
                        break
                    await asyncio.sleep(0.1)
        finally:
            unsubscribe(run_id, q)

    from starlette.responses import StreamingResponse
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/runs/{run_id}/attempts")
def get_pipeline_run_attempts(run_id: str):
    """
    Retrieve structured attempt ledger for a run.
    """
    run = get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run not found: '{run_id}'")
    return get_run_attempts(run_id)


@app.get("/runs/{run_id}/errors")
def get_pipeline_run_errors(run_id: str):
    """
    Retrieve aggregated error ledger grouped by error_signature.
    """
    run = get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run not found: '{run_id}'")
    return get_run_errors(run_id)


@app.get("/runs/{run_id}/iterations")
def get_pipeline_run_iterations(run_id: str, agent: str = "modeler_agent"):
    """
    Retrieve all code-execution iterations for a given agent (default: modeler_agent).
    Includes both successful (scored) and failed attempts with full code, stdout, stderr.
    Used by the All Code & Results tab to show every execution try.
    """
    run = get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run not found: '{run_id}'")
    return get_run_iterations(run_id, agent=agent)


@app.get("/runs/{run_id}/dataset-preview")
def get_pipeline_run_dataset_preview(run_id: str, limit: int = 50):
    """
    Retrieve column names and preview rows for the run's dataset.
    Reads transformed_dataset_path if present, else dataset_path, via pandas.
    Handles missing or unreadable files with clean 404 or 422 HTTP responses.
    """
    run = get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run not found: '{run_id}'")

    # 1. Determine target dataset path
    target_path = None
    is_transformed = False

    try:
        graph = get_pipeline_graph()
        state = graph.get_state({"configurable": {"thread_id": run_id}})
        if state and hasattr(state, "values") and isinstance(state.values, dict):
            trans_path = state.values.get("transformed_dataset_path")
            if trans_path and os.path.exists(trans_path):
                target_path = trans_path
                is_transformed = True
            elif state.values.get("dataset_path"):
                target_path = state.values.get("dataset_path")
    except Exception:
        pass

    if not target_path:
        target_path = run.get("dataset_path")

    if not target_path or not os.path.exists(target_path):
        raise HTTPException(
            status_code=404,
            detail=f"Dataset file not found at '{target_path or 'unknown'}' for run '{run_id}'.",
        )

    # 2. Read dataset via pandas
    import pandas as pd
    import numpy as np

    try:
        if target_path.endswith((".parquet", ".pq")):
            df = pd.read_parquet(target_path)
        else:
            df = pd.read_csv(target_path)
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Failed to parse dataset file '{target_path}': {exc}",
        )

    total_rows = len(df)
    total_cols = len(df.columns)
    preview_df = df.head(max(1, min(limit, 500)))

    # Convert to object dtype first so None values are not coerced back to float nan
    raw_records = (
        preview_df.astype(object)
        .where(pd.notnull(preview_df), None)
        .to_dict(orient="records")
    )
    import math
    preview_records = []
    for row in raw_records:
        clean_row = {}
        for k, v in row.items():
            if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                clean_row[k] = None
            else:
                clean_row[k] = v
        preview_records.append(clean_row)

    return {
        "run_id": run_id,
        "dataset_path": target_path,
        "is_transformed": is_transformed,
        "columns": [str(c) for c in df.columns],
        "total_rows": total_rows,
        "total_columns": total_cols,
        "preview_rows": preview_records,
    }


@app.post("/runs/{run_id}/resume")
def resume_pipeline_run(run_id: str, req: ResumeRequest):
    """
    Resume an interrupted/paused run (e.g. from human_approval node)
    using LangGraph's Command(resume=...) pattern.
    """
    run = get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run not found: '{run_id}'")

    # Double-resume protection (0c)
    if run.get("status") != "paused":
        raise HTTPException(
            status_code=409,
            detail=f"Run '{run_id}' is not currently paused (current status: '{run.get('status')}').",
        )

    # Invalid input handling (0b)
    valid_choices = {"approved", "modify", "reject"}
    if not req.approval_status or req.approval_status not in valid_choices:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid or missing approval_status '{req.approval_status}'. Allowed: {sorted(list(valid_choices))}.",
        )

    resume_payload = {"approval_status": req.approval_status}
    if req.modifications:
        resume_payload["modifications"] = req.modifications

    stream_input = Command(resume=resume_payload)
    update_run_status(run_id, status="running")
    _run_graph_in_background(stream_input=stream_input, run_id=run_id)

    return {"run_id": run_id, "status": "resumed", "decision": req.approval_status}


@app.post("/runs/{run_id}/pause")
def pause_pipeline_run(run_id: str):
    """
    Pause a running pipeline execution.
    """
    run = get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run not found: '{run_id}'")

    ctrl = get_run_control(run_id)
    ctrl.pause()
    update_run_status(run_id, status="paused", stop_reason="user_paused")
    return {"run_id": run_id, "control": "paused"}


@app.post("/runs/{run_id}/unpause")
def unpause_pipeline_run(run_id: str):
    """
    Unpause a paused pipeline execution.
    """
    run = get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run not found: '{run_id}'")

    ctrl = get_run_control(run_id)
    ctrl.resume()
    update_run_status(run_id, status="running")
    return {"run_id": run_id, "control": "unpaused"}


@app.post("/runs/{run_id}/stop")
def stop_pipeline_run(run_id: str):
    """
    Stop a running pipeline execution cleanly.
    """
    run = get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run not found: '{run_id}'")

    ctrl = get_run_control(run_id)
    ctrl.stop()
    update_run_status(run_id, status="stopped", stop_reason="user_stopped")
    return {"run_id": run_id, "control": "stopped"}


@app.post("/runs/{run_id}/escape")
def escape_pipeline_run(run_id: str):
    """
    Force-advance a stuck loop (coder retry or exploration loop) without stopping the whole run.
    Sets a one-shot escape flag on RunControl that is consumed at the next checkpoint.
    """
    run = get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run not found: '{run_id}'")

    ctrl = get_run_control(run_id)
    ctrl.escape()
    return {"run_id": run_id, "control": "escaped"}


@app.get("/runs/{run_id_a}/compare/{run_id_b}")
def compare_pipeline_runs(run_id_a: str, run_id_b: str):
    """
    Side-by-side comparison of two runs.
    """
    run_a = get_run(run_id_a)
    if not run_a:
        raise HTTPException(status_code=404, detail=f"Run not found: '{run_id_a}'")

    run_b = get_run(run_id_b)
    if not run_b:
        raise HTTPException(status_code=404, detail=f"Run not found: '{run_id_b}'")

    return compare_runs(run_id_a, run_id_b)


@app.get("/runs/{run_id}/export")
def export_pipeline_run_bundle(run_id: str):
    """
    Package run artifacts into a ZIP debug bundle and return as file download.
    """
    run = get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run not found: '{run_id}'")

    try:
        zip_path = export_run_bundle(run_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed generating export bundle: {exc}")

    if not os.path.exists(zip_path):
        raise HTTPException(status_code=500, detail="Export bundle file was not generated.")

    return FileResponse(
        path=zip_path,
        filename=os.path.basename(zip_path),
        media_type="application/zip",
    )


@app.post("/runs/{run_id}/tags")
def update_pipeline_run_tags(run_id: str, req: TagUpdateRequest):
    """
    Update or append tags to a run.
    """
    run = get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run not found: '{run_id}'")

    if req.tags is not None:
        set_run_tags(run_id, req.tags)
    elif req.tag is not None:
        add_run_tag(run_id, req.tag)
    else:
        raise HTTPException(status_code=400, detail="Must provide either 'tags' list or a single 'tag'")

    return get_run(run_id)


@app.post("/runs/{run_id}/baseline")
def set_pipeline_run_baseline(run_id: str, req: BaselineUpdateRequest):
    """
    Designate a run as baseline or clear baseline flag.
    """
    run = get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run not found: '{run_id}'")

    set_run_baseline(run_id, is_baseline=req.is_baseline, baseline_score=req.baseline_score)
    return get_run(run_id)
