"""
Comprehensive integration tests for the FastAPI backend layer (api/main.py).

Covers all 11 required endpoints:
  1. POST /runs (validation, creation, background execution)
  2. GET  /runs (filtering by tag and is_baseline)
  3. GET  /runs/{id} (metadata & 404 handling)
  4. GET  /runs/{id}/events (SSE catchup & streaming)
  5. GET  /runs/{id}/attempts (attempt ledger)
  6. GET  /runs/{id}/errors (grouped error ledger)
  7. POST /runs/{id}/resume (LangGraph Command resume)
  8. POST /runs/{id}/pause, /unpause, /stop (run controls)
  9. GET  /runs/{a}/compare/{b} (side-by-side comparison)
  10. GET /runs/{id}/export (ZIP debug bundle download)
  11. POST /runs/{id}/tags, POST /runs/{id}/baseline (metadata updating)
"""
import io
import json
import os
import time
import zipfile
import pytest
from fastapi.testclient import TestClient

from api.main import app
from tools.tracer import (
    register_run,
    record_event,
    update_run_status,
    get_run_control,
)


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="module")
def sample_csv(tmp_path_factory):
    csv_dir = tmp_path_factory.mktemp("data")
    csv_file = csv_dir / "dataset.csv"
    csv_file.write_text("feature1,feature2,target\n1,2,0\n3,4,1\n5,6,0\n7,8,1\n")
    return str(csv_file)


# ---------------------------------------------------------------------------
# 1. POST /runs (Validation & Creation)
# ---------------------------------------------------------------------------
def test_create_run_validation_missing_file(client):
    response = client.post("/runs", json={
        "dataset_path": "nonexistent_file_path_12345.csv",
        "mode": "full_pipeline",
    })
    assert response.status_code == 400
    assert "Dataset file not found" in response.json()["detail"]


def test_create_run_validation_invalid_mode(client, sample_csv):
    response = client.post("/runs", json={
        "dataset_path": sample_csv,
        "mode": "invalid_mode_xyz",
    })
    assert response.status_code == 400
    assert "Invalid pipeline mode" in response.json()["detail"]


def test_create_run_success(client, sample_csv, monkeypatch):
    # Avoid spawning long background worker during unit test
    called_with = []
    def mock_bg(stream_input, run_id):
        called_with.append(run_id)
        return None

    monkeypatch.setattr("api.main._run_graph_in_background", mock_bg)

    payload = {
        "dataset_path": sample_csv,
        "mode": "full_pipeline",
        "guided_mode": True,
        "tags": ["unit-test", "v1"],
        "metric_name": "f1",
    }
    response = client.post("/runs", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert "run_id" in data
    assert data["mode"] == "full_pipeline"
    assert data["guided_mode"] == 1
    assert data["metric_name"] == "f1"
    assert called_with == [data["run_id"]]


# ---------------------------------------------------------------------------
# 2. GET /runs & Query Filters
# ---------------------------------------------------------------------------
def test_list_runs_and_filters(client):
    tag_val = f"filter_test_{int(time.time()*1000)}"
    r1 = f"run_filt_1_{int(time.time()*1000)}"
    r2 = f"run_filt_2_{int(time.time()*1000)}"

    register_run(r1, dataset_path="data.csv", tags=[tag_val], is_baseline=True)
    register_run(r2, dataset_path="data.csv", tags=["other"], is_baseline=False)

    # Filter by tag
    res_tag = client.get(f"/runs?tag={tag_val}")
    assert res_tag.status_code == 200
    runs = res_tag.json()
    assert any(r["run_id"] == r1 for r in runs)
    assert not any(r["run_id"] == r2 for r in runs)

    # Filter by is_baseline
    res_base = client.get("/runs?is_baseline=true")
    assert res_base.status_code == 200
    base_runs = res_base.json()
    assert any(r["run_id"] == r1 for r in base_runs)


# ---------------------------------------------------------------------------
# 3. GET /runs/{id}
# ---------------------------------------------------------------------------
def test_get_run_success_and_404(client):
    run_id = f"run_get_{int(time.time()*1000)}"
    register_run(run_id, dataset_path="data.csv")

    res_ok = client.get(f"/runs/{run_id}")
    assert res_ok.status_code == 200
    assert res_ok.json()["run_id"] == run_id

    res_404 = client.get("/runs/nonexistent_run_id_99999")
    assert res_404.status_code == 404
    assert "Run not found" in res_404.json()["detail"]


# ---------------------------------------------------------------------------
# 4. GET /runs/{id}/attempts & /errors
# ---------------------------------------------------------------------------
def test_get_run_attempts_and_errors(client):
    run_id = f"run_att_err_{int(time.time()*1000)}"
    register_run(run_id, dataset_path="data.csv")

    # Record mock attempts & error
    record_event(
        run_id, "modeler_agent", "candidate_evaluated",
        attempt=1, tier=1, metric_value=0.82, model_name="RandomForestClassifier",
    )
    record_event(
        run_id, "coder_agent", "step_error",
        error="ValueError: Expected 2D array, got 1D array instead",
        error_type="ValueError",
    )

    res_att = client.get(f"/runs/{run_id}/attempts")
    assert res_att.status_code == 200
    attempts = res_att.json()
    assert len(attempts) >= 1
    assert attempts[0]["model_name"] == "RandomForestClassifier"

    res_err = client.get(f"/runs/{run_id}/errors")
    assert res_err.status_code == 200
    errors = res_err.json()
    assert len(errors) >= 1
    assert "ValueError" in errors[0]["error_signature"]

    # 404 checks
    assert client.get("/runs/bad_run/attempts").status_code == 404
    assert client.get("/runs/bad_run/errors").status_code == 404


# ---------------------------------------------------------------------------
# 5. POST /runs/{id}/pause, /unpause, /stop
# ---------------------------------------------------------------------------
def test_run_controls(client):
    run_id = f"run_ctrl_{int(time.time()*1000)}"
    register_run(run_id, dataset_path="data.csv")

    ctrl = get_run_control(run_id)
    assert not ctrl.is_paused()
    assert not ctrl.stopped

    # Pause
    res_p = client.post(f"/runs/{run_id}/pause")
    assert res_p.status_code == 200
    assert res_p.json()["control"] == "paused"
    assert ctrl.is_paused()

    # Unpause
    res_u = client.post(f"/runs/{run_id}/unpause")
    assert res_u.status_code == 200
    assert res_u.json()["control"] == "unpaused"
    assert not ctrl.is_paused()

    # Stop
    res_s = client.post(f"/runs/{run_id}/stop")
    assert res_s.status_code == 200
    assert res_s.json()["control"] == "stopped"
    assert ctrl.stopped

    # Escape
    res_e = client.post(f"/runs/{run_id}/escape")
    assert res_e.status_code == 200
    assert res_e.json()["control"] == "escaped"
    assert ctrl.escaped is True

    # 404 checks
    assert client.post("/runs/bad_run/pause").status_code == 404
    assert client.post("/runs/bad_run/unpause").status_code == 404
    assert client.post("/runs/bad_run/stop").status_code == 404
    assert client.post("/runs/bad_run/escape").status_code == 404


# ---------------------------------------------------------------------------
# 6. POST /runs/{id}/tags & /baseline
# ---------------------------------------------------------------------------
def test_run_tags_and_baseline(client):
    run_id = f"run_meta_{int(time.time()*1000)}"
    register_run(run_id, dataset_path="data.csv")

    # Set tags
    res_tags1 = client.post(f"/runs/{run_id}/tags", json={"tags": ["exp1", "dev"]})
    assert res_tags1.status_code == 200
    tags = json.loads(res_tags1.json()["tags"]) if isinstance(res_tags1.json()["tags"], str) else res_tags1.json()["tags"]
    assert "exp1" in tags
    assert "dev" in tags

    # Append tag
    res_tags2 = client.post(f"/runs/{run_id}/tags", json={"tag": "prod"})
    assert res_tags2.status_code == 200
    tags2 = json.loads(res_tags2.json()["tags"]) if isinstance(res_tags2.json()["tags"], str) else res_tags2.json()["tags"]
    assert "prod" in tags2

    # Set baseline
    res_base = client.post(f"/runs/{run_id}/baseline", json={"is_baseline": True, "baseline_score": 0.885})
    assert res_base.status_code == 200
    assert res_base.json()["is_baseline"] == 1
    assert res_base.json()["baseline_score"] == 0.885


# ---------------------------------------------------------------------------
# 7. GET /runs/{a}/compare/{b}
# ---------------------------------------------------------------------------
def test_compare_runs_endpoint(client):
    r_a = f"run_cmp_a_{int(time.time()*1000)}"
    r_b = f"run_cmp_b_{int(time.time()*1000)}"

    register_run(r_a, dataset_path="data.csv")
    register_run(r_b, dataset_path="data.csv")

    record_event(r_a, "modeler_agent", "candidate_evaluated", attempt=1, metric_value=0.80)
    record_event(r_b, "modeler_agent", "candidate_evaluated", attempt=1, metric_value=0.85)

    res = client.get(f"/runs/{r_a}/compare/{r_b}")
    assert res.status_code == 200
    data = res.json()
    assert "run_a" in data
    assert "run_b" in data
    assert data["run_a"]["best_score"] == 0.80
    assert data["run_b"]["best_score"] == 0.85
    assert data["delta_best_score"] == pytest.approx(0.05)


# ---------------------------------------------------------------------------
# 8. GET /runs/{id}/export (ZIP bundle)
# ---------------------------------------------------------------------------
def test_export_run_bundle_endpoint(client):
    run_id = f"run_exp_{int(time.time()*1000)}"
    register_run(run_id, dataset_path="data.csv")
    record_event(run_id, "profiler_agent", "completed", intent="dataset profiling")

    res = client.get(f"/runs/{run_id}/export")
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/zip"

    # Verify returned bytes form a valid zip file
    zf = zipfile.ZipFile(io.BytesIO(res.content))
    namelist = zf.namelist()
    assert "events.jsonl" in namelist or "metrics.csv" in namelist


# ---------------------------------------------------------------------------
# 9. GET /runs/{id}/events (SSE catchup & streaming)
# ---------------------------------------------------------------------------
def test_sse_events_catchup(client):
    run_id = f"run_sse_{int(time.time()*1000)}"
    register_run(run_id, dataset_path="data.csv")

    # Record two events
    e1 = record_event(run_id, "profiler_agent", "step_start", step="profile_dataset")
    e2 = record_event(run_id, "profiler_agent", "step_end", step="profile_dataset")

    # Stream starting from seq=0 with live=false for deterministic response
    response = client.get(f"/runs/{run_id}/events?since_seq=0&live=false")
    assert response.status_code == 200
    lines = [line for line in response.text.split("\n") if line.startswith("data:")]
    assert len(lines) >= 2
    ev1 = json.loads(lines[0].replace("data:", "").strip())
    assert ev1["seq"] == e1["seq"]
    assert ev1["event"] == "step_start"


# ---------------------------------------------------------------------------
# 10. POST /runs/{id}/resume (Command resume flow)
# ---------------------------------------------------------------------------
def test_resume_flow_endpoint(client, monkeypatch):
    run_id = f"run_resume_{int(time.time()*1000)}"
    register_run(run_id, dataset_path="data.csv")
    update_run_status(run_id, status="paused", stop_reason="human_approval_required")

    resumed_runs = []
    def mock_bg(stream_input, run_id):
        resumed_runs.append((stream_input, run_id))
        return None

    monkeypatch.setattr("api.main._run_graph_in_background", mock_bg)

    # Invalid choice check
    res_bad = client.post(f"/runs/{run_id}/resume", json={"approval_status": "invalid_choice"})
    assert res_bad.status_code == 400

    # Successful resume
    res_ok = client.post(f"/runs/{run_id}/resume", json={
        "approval_status": "approved",
        "modifications": "keep column age",
    })
    assert res_ok.status_code == 200
    assert res_ok.json()["status"] == "resumed"
    assert res_ok.json()["decision"] == "approved"
    assert len(resumed_runs) == 1
    assert resumed_runs[0][1] == run_id

    # Second resume returns 409 Conflict
    res_dbl = client.post(f"/runs/{run_id}/resume", json={"approval_status": "approved"})
    assert res_dbl.status_code == 409
    assert "not currently paused" in res_dbl.json()["detail"]


# ---------------------------------------------------------------------------
# 11. Full End-to-End Guided Lifecycle Test
# ---------------------------------------------------------------------------
def test_end_to_end_guided_run_lifecycle(client, sample_csv, monkeypatch):
    """
    Simulates complete client flow:
    start run -> poll status -> handle pause -> resume -> confirm completion
    """
    lifecycle_states = []

    def mock_worker(stream_input, run_id):
        # 1. Pipeline starts running
        update_run_status(run_id, status="running")
        # 2. Features triggers human approval pause
        update_run_status(run_id, status="paused", stop_reason="human_approval_required")

    monkeypatch.setattr("api.main._run_graph_in_background", mock_worker)

    # Step 1: Start guided run
    start_res = client.post("/runs", json={
        "dataset_path": sample_csv,
        "mode": "full_pipeline",
        "guided_mode": True,
        "tags": ["e2e-guided"],
    })
    assert start_res.status_code == 201
    run_id = start_res.json()["run_id"]

    # Step 2: Poll status -> confirm paused for human approval
    poll_res = client.get(f"/runs/{run_id}")
    assert poll_res.status_code == 200
    assert poll_res.json()["status"] == "paused"
    assert poll_res.json()["stop_reason"] == "human_approval_required"

    # Step 3: Resume guided run with approved decision
    def mock_resume_worker(stream_input, run_id):
        # Pipeline finishes
        record_event(run_id, "modeler_agent", "candidate_evaluated", attempt=1, metric_value=0.89)
        update_run_status(run_id, status="completed", best_score=0.89)

    monkeypatch.setattr("api.main._run_graph_in_background", mock_resume_worker)

    resume_res = client.post(f"/runs/{run_id}/resume", json={
        "approval_status": "approved",
    })
    assert resume_res.status_code == 200
    assert resume_res.json()["status"] == "resumed"

    # Step 4: Poll status -> confirm completed
    final_res = client.get(f"/runs/{run_id}")
    assert final_res.status_code == 200
    assert final_res.json()["status"] == "completed"
    assert final_res.json()["best_score"] == 0.89

    # Step 5: Check attempts ledger and export
    attempts_res = client.get(f"/runs/{run_id}/attempts")
    assert attempts_res.status_code == 200
    assert len(attempts_res.json()) >= 1

    export_res = client.get(f"/runs/{run_id}/export")
    assert export_res.status_code == 200
    assert export_res.headers["content-type"] == "application/zip"

