import os
import json
import pytest
from pathlib import Path
from fastapi.testclient import TestClient

from app.main import app
from app.db.session import init_db
from app.config import BASE_DIR

client = TestClient(app)


def test_phase2_endpoints():
    # 1. Initialize DB
    init_db()

    # 2. Health check
    res = client.get("/")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"

    # 3. Create Project
    proj_payload = {
        "name": "Phase2 Test Project",
        "description": "Verification project for Phase 2 FastAPI backend",
    }
    res = client.post("/projects", json=proj_payload)
    assert res.status_code == 200
    project = res.json()
    project_id = project["id"]
    assert "phase2_test_project" in project_id

    # 4. Get Project
    res = client.get(f"/projects/{project_id}")
    assert res.status_code == 200
    assert res.json()["name"] == proj_payload["name"]

    # 5. List Projects
    res = client.get("/projects")
    assert res.status_code == 200
    assert any(p["id"] == project_id for p in res.json())

    # 6. Upload Dataset
    sample_csv = BASE_DIR / "sample_data" / "titanic.csv"
    assert sample_csv.exists()

    with open(sample_csv, "rb") as f:
        res = client.post(
            f"/projects/{project_id}/datasets",
            files={"file": ("titanic.csv", f, "text/csv")},
        )
    assert res.status_code == 200
    dataset = res.json()
    assert dataset["version"] == "dataset_v1"
    assert dataset["row_count"] == 60
    assert dataset["col_count"] == 9

    # 7. List Datasets
    res = client.get(f"/projects/{project_id}/datasets")
    assert res.status_code == 200
    assert len(res.json()) >= 1

    # 8. Start Workflow Run with missing target -> should land in NEEDS_INPUT
    res = client.post(
        f"/projects/{project_id}/runs",
        json={"target_column": None, "target_metric": "f1"},
    )
    assert res.status_code == 200
    missing_run = res.json()
    run_id_missing = missing_run["id"]

    # Allow background task to process
    import time
    time.sleep(1)

    res = client.get(f"/projects/{project_id}/runs/{run_id_missing}")
    assert res.status_code == 200
    assert res.json()["status"] == "NEEDS_INPUT"

    # 9. Verify Models / Leaderboard Endpoint returns valid direction and MLflow runs
    # Check demo_titanic leaderboard
    res = client.get("/projects/demo_titanic/models?metric=f1")
    assert res.status_code == 200
    lb_data = res.json()
    assert lb_data["direction"] == "max"
    assert len(lb_data["leaderboard"]) >= 1

    # Check demo_housing leaderboard (lower is better for rmse)
    res = client.get("/projects/demo_housing/models?metric=rmse")
    assert res.status_code == 200
    lb_housing = res.json()
    assert lb_housing["direction"] == "min"
    assert len(lb_housing["leaderboard"]) >= 1

    # 10. Verify Report endpoint
    demo_rep_dir = BASE_DIR / "projects" / "demo_titanic" / "reports"
    demo_rep_dir.mkdir(parents=True, exist_ok=True)
    if not (demo_rep_dir / "final_report.md").exists():
        (demo_rep_dir / "final_report.md").write_text("# Final Report\nAutonomous ML Run Report", encoding="utf-8")

    res = client.get("/projects/demo_titanic/report")
    assert res.status_code == 200
    rep_data = res.json()
    assert "markdown" in rep_data
    assert "summary" in rep_data
    assert "Final Report" in rep_data["markdown"]

    # 11. Verify Evaluation endpoint
    res = client.get("/projects/demo_titanic/evaluation")
    assert res.status_code == 200
    eval_data = res.json()
    assert "json" in eval_data

    # 12. Verify Artifacts endpoint
    res = client.get("/projects/demo_titanic/artifacts")
    assert res.status_code == 200
    assert isinstance(res.json(), list)

    # 13. Verify Events endpoint streaming
    with client.stream("GET", f"/projects/{project_id}/events?run_id={run_id_missing}") as stream_res:
        assert stream_res.status_code == 200
        assert "text/event-stream" in stream_res.headers["content-type"]
        lines = []
        for line in stream_res.iter_lines():
            if line:
                lines.append(line)
            if len(lines) >= 1:
                break
        assert len(lines) >= 1
        assert "data:" in lines[0] or "ping" in lines[0]

    print("ALL PHASE 2 BACKEND ENDPOINT TESTS PASSED SUCCESSFULLY!")


if __name__ == "__main__":
    test_phase2_endpoints()
