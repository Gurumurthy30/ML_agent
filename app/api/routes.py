import asyncio
import json
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Any

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlmodel import Session, select

from app.db.session import get_session
from app.db.models import Project, Dataset, WorkflowRun, ArtifactIndex
from app.api.runner import execute_workflow_async
from app.core.events import event_manager
from app.tools.mlflow_tools import MLflowTools, is_higher_better
from app.config import PROJECTS_DIR

router = APIRouter()


# --- Pydantic Schemas ---

class ProjectCreate(BaseModel):
    name: str
    description: Optional[str] = None


class RunCreate(BaseModel):
    target_column: Optional[str] = None
    target_metric: Optional[str] = None
    dataset_version: Optional[str] = None
    constraints: Optional[dict[str, Any]] = None


# --- Project Endpoints ---

@router.post("/projects", response_model=Project)
def create_project(data: ProjectCreate, session: Session = Depends(get_session)):
    slug = re.sub(r"[^a-zA-Z0-9_\-]", "_", data.name).strip("_").lower()
    project_id = slug or f"proj_{uuid.uuid4().hex[:8]}"

    # Check existence
    existing = session.get(Project, project_id)
    if existing:
        project_id = f"{slug}_{uuid.uuid4().hex[:4]}"

    now = datetime.now(timezone.utc)
    project = Project(
        id=project_id,
        name=data.name,
        description=data.description,
        created_at=now,
        updated_at=now,
    )
    session.add(project)
    session.commit()
    session.refresh(project)

    # Prepare project directory structure
    p_dir = PROJECTS_DIR / project_id
    p_dir.mkdir(parents=True, exist_ok=True)
    for sub in ["datasets", "profile", "eda", "features", "models", "evaluations", "reports", "memory", "workspace"]:
        (p_dir / sub).mkdir(parents=True, exist_ok=True)

    return project


@router.get("/projects", response_model=list[Project])
def list_projects(session: Session = Depends(get_session)):
    return session.exec(select(Project).order_by(Project.created_at.desc())).all()


@router.get("/projects/{project_id}", response_model=Project)
def get_project(project_id: str, session: Session = Depends(get_session)):
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")
    return project


# --- Dataset Endpoints ---

@router.post("/projects/{project_id}/datasets", response_model=Dataset)
async def upload_dataset(project_id: str, file: UploadFile = File(...), session: Session = Depends(get_session)):
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")

    # Determine next dataset version (e.g. dataset_v1, dataset_v2) without overwriting
    existing_datasets = session.exec(
        select(Dataset).where(Dataset.project_id == project_id).order_by(Dataset.created_at.asc())
    ).all()
    next_ver_num = len(existing_datasets) + 1
    version_tag = f"dataset_v{next_ver_num}"

    dest_dir = PROJECTS_DIR / project_id / "datasets" / version_tag
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_file = dest_dir / "data.csv"

    # Save uploaded file
    with open(dest_file, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # Inspect shape
    row_count = 0
    col_count = 0
    try:
        df = pd.read_csv(dest_file)
        row_count, col_count = df.shape
    except Exception:
        pass

    dataset_record = Dataset(
        id=f"ds_{uuid.uuid4().hex[:8]}",
        project_id=project_id,
        version=version_tag,
        filename=file.filename or "data.csv",
        file_path=str(dest_file),
        row_count=row_count,
        col_count=col_count,
        created_at=datetime.now(timezone.utc),
    )
    session.add(dataset_record)
    session.commit()
    session.refresh(dataset_record)

    return dataset_record


@router.get("/projects/{project_id}/datasets", response_model=list[Dataset])
def list_datasets(project_id: str, session: Session = Depends(get_session)):
    return session.exec(
        select(Dataset).where(Dataset.project_id == project_id).order_by(Dataset.created_at.desc())
    ).all()


# --- Workflow Run Endpoints ---

@router.post("/projects/{project_id}/runs", response_model=WorkflowRun)
def trigger_run(
    project_id: str,
    payload: RunCreate,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
):
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")

    # Resolve dataset version
    dataset_version = payload.dataset_version
    if not dataset_version:
        latest_dataset = session.exec(
            select(Dataset).where(Dataset.project_id == project_id).order_by(Dataset.created_at.desc())
        ).first()
        if not latest_dataset:
            raise HTTPException(status_code=400, detail="No dataset uploaded for this project yet. Please upload a CSV first.")
        dataset_version = latest_dataset.version

    run_id = f"run_{uuid.uuid4().hex[:8]}"
    workflow_run = WorkflowRun(
        id=run_id,
        project_id=project_id,
        dataset_version=dataset_version,
        target_column=payload.target_column,
        target_metric=payload.target_metric,
        status="PENDING",
        current_stage="start",
        created_at=datetime.now(timezone.utc),
    )
    session.add(workflow_run)
    session.commit()
    session.refresh(workflow_run)

    # Launch in background
    background_tasks.add_task(
        execute_workflow_async,
        project_id=project_id,
        run_id=run_id,
        dataset_version=dataset_version,
        target_column=payload.target_column,
        target_metric=payload.target_metric,
        constraints=payload.constraints or {},
    )

    return workflow_run


@router.get("/projects/{project_id}/runs", response_model=list[WorkflowRun])
def list_runs(project_id: str, session: Session = Depends(get_session)):
    return session.exec(
        select(WorkflowRun).where(WorkflowRun.project_id == project_id).order_by(WorkflowRun.created_at.desc())
    ).all()


@router.get("/projects/{project_id}/runs/{run_id}", response_model=WorkflowRun)
def get_run(project_id: str, run_id: str, session: Session = Depends(get_session)):
    run = session.get(WorkflowRun, run_id)
    if not run or run.project_id != project_id:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found for project '{project_id}'")
    return run


# --- SSE Event Stream ---

@router.get("/projects/{project_id}/events")
async def stream_events(project_id: str, run_id: str = Query(...)):
    """Server-Sent Events (SSE) endpoint streaming real-time pipeline events."""
    past_events = event_manager.get_past_events(project_id, run_id)
    queue = event_manager.subscribe(project_id, run_id)

    async def event_generator():
        try:
            # Replay historical events
            for ev in past_events:
                yield f"data: {json.dumps(ev)}\n\n"

            # If past events already reached completion or pause, terminate stream cleanly
            if any(ev.get("event_type") == "WORKFLOW_COMPLETED" for ev in past_events):
                return
            if past_events and past_events[-1].get("data", {}).get("status") in ["NEEDS_INPUT", "FAILED"]:
                return

            # Stream live events
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=20.0)
                    yield f"data: {json.dumps(event)}\n\n"
                    if event.get("event_type") == "WORKFLOW_COMPLETED" or event.get("data", {}).get("status") == "NEEDS_INPUT":
                        break
                except asyncio.TimeoutError:
                    # Keep-alive heartbeat
                    yield ": ping\n\n"
        finally:
            event_manager.unsubscribe(project_id, run_id, queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# --- Artifacts Endpoints ---

@router.get("/projects/{project_id}/artifacts")
def get_artifacts(project_id: str, session: Session = Depends(get_session)):
    return session.exec(
        select(ArtifactIndex).where(ArtifactIndex.project_id == project_id).order_by(ArtifactIndex.created_at.desc())
    ).all()


@router.get("/projects/{project_id}/artifacts/{artifact_id}/content")
def get_artifact_content(project_id: str, artifact_id: str, session: Session = Depends(get_session)):
    """Fetches the content of an artifact (markdown rendered, JSON pretty-printed, parquet/csv table preview)."""
    artifact = session.get(ArtifactIndex, artifact_id)
    if not artifact or artifact.project_id != project_id:
        raise HTTPException(status_code=404, detail=f"Artifact '{artifact_id}' not found for project '{project_id}'")

    file_path = Path(artifact.file_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"Artifact file not found on disk: {file_path.name}")

    ext = file_path.suffix.lower()
    try:
        if ext == ".json":
            content = json.loads(file_path.read_text(encoding="utf-8"))
            return {"type": "json", "data": content, "raw": file_path.read_text(encoding="utf-8")}
        elif ext in [".md", ".markdown"]:
            return {"type": "markdown", "content": file_path.read_text(encoding="utf-8")}
        elif ext in [".py", ".sh"]:
            return {"type": "code", "content": file_path.read_text(encoding="utf-8"), "language": "python" if ext == ".py" else "bash"}
        elif ext == ".parquet":
            df = pd.read_parquet(file_path)
            preview_df = df.head(100).fillna("")
            return {
                "type": "table",
                "columns": list(df.columns),
                "rows": preview_df.to_dict(orient="records"),
                "total_rows": len(df),
                "total_columns": len(df.columns),
            }
        elif ext == ".csv":
            df = pd.read_csv(file_path)
            preview_df = df.head(100).fillna("")
            return {
                "type": "table",
                "columns": list(df.columns),
                "rows": preview_df.to_dict(orient="records"),
                "total_rows": len(df),
                "total_columns": len(df.columns),
            }
        else:
            return {"type": "text", "content": file_path.read_text(encoding="utf-8", errors="replace")}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read artifact content: {str(e)}")


@router.get("/projects/{project_id}/datasets/{version}/preview")
def preview_dataset(project_id: str, version: str, session: Session = Depends(get_session)):
    """Returns a table preview of the requested dataset version."""
    dataset = session.exec(
        select(Dataset).where(Dataset.project_id == project_id, Dataset.version == version)
    ).first()
    if not dataset:
        raise HTTPException(status_code=404, detail=f"Dataset version '{version}' not found for project '{project_id}'")

    file_path = Path(dataset.file_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"Dataset file '{dataset.filename}' does not exist on disk")

    try:
        df = pd.read_csv(file_path)
        preview_df = df.head(100).fillna("")
        return {
            "version": version,
            "filename": dataset.filename,
            "columns": list(df.columns),
            "rows": preview_df.to_dict(orient="records"),
            "total_rows": len(df),
            "total_columns": len(df.columns),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to preview dataset: {str(e)}")


# --- Models & Leaderboard Endpoints ---

@router.get("/projects/{project_id}/models")
def get_leaderboard(project_id: str, metric: str = Query("f1")):
    """Returns ranked MLflow runs sorted by target metric with direction awareness."""
    try:
        tools = MLflowTools(project_id)
        runs = tools.get_leaderboard(metric)
        return {
            "project_id": project_id,
            "target_metric": metric,
            "direction": "max" if is_higher_better(metric) else "min",
            "leaderboard": runs,
        }
    except Exception as e:
        return {"project_id": project_id, "target_metric": metric, "leaderboard": [], "error": str(e)}


@router.get("/projects/{project_id}/experiments")
def get_experiments(project_id: str):
    """Raw MLflow experiment runs."""
    try:
        tools = MLflowTools(project_id)
        runs = tools.get_leaderboard("f1")
        return {"project_id": project_id, "runs": runs}
    except Exception as e:
        return {"project_id": project_id, "runs": [], "error": str(e)}


# --- Evaluation & Report Endpoints ---

@router.get("/projects/{project_id}/evaluation")
def get_evaluation(project_id: str):
    """Returns latest evaluation json and markdown report."""
    eval_dir = PROJECTS_DIR / project_id / "evaluations"
    if not eval_dir.exists():
        raise HTTPException(status_code=404, detail="No evaluation found for this project")

    # Get latest evaluation file
    json_files = sorted(eval_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not json_files:
        raise HTTPException(status_code=404, detail="No evaluation found for this project")

    latest_json = json_files[0]
    data = json.loads(latest_json.read_text(encoding="utf-8"))
    md_file = latest_json.with_suffix(".md")
    md_content = md_file.read_text(encoding="utf-8") if md_file.exists() else ""

    return {"json": data, "markdown": md_content}


@router.get("/projects/{project_id}/report")
def get_report(project_id: str):
    """Returns the final markdown and JSON report."""
    reports_dir = PROJECTS_DIR / project_id / "reports"
    json_path = reports_dir / "summary.json"
    md_path = reports_dir / "final_report.md"

    if not md_path.exists() and not json_path.exists():
        raise HTTPException(status_code=404, detail="No report generated for this project yet")

    summary_data = {}
    if json_path.exists():
        summary_data = json.loads(json_path.read_text(encoding="utf-8"))

    md_content = ""
    if md_path.exists():
        md_content = md_path.read_text(encoding="utf-8")

    return {"summary": summary_data, "markdown": md_content}
