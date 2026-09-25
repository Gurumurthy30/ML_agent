import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select
from app.main import app
from app.db.session import engine
from app.db.models import Project, WorkflowRun, Event
from app.config import PROJECTS_DIR

client = TestClient(app)


def test_code_executions_and_delete_project():
    # 1. Create a temporary project
    proj_name = "Test Delete And Coder Project"
    resp = client.post("/projects", json={"name": proj_name, "description": "Test cleanup and coder executions"})
    assert resp.status_code == 200
    data = resp.json()
    project_id = data["id"]

    # 2. Check code executions endpoint (initially empty)
    resp = client.get(f"/projects/{project_id}/code-executions")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)

    # 3. Simulate an execution manager write
    from app.tools.execution_manager import ExecutionManager
    exec_mgr = ExecutionManager(project_id)
    script = "print('Hello from Coder Agent')\nx = 10 + 20\nprint(f'Computed: {x}')"
    res = exec_mgr.run_script(
        script_content=script,
        script_name="test_script.py",
        stage="features",
        task_description="Test execution recording",
    )
    assert res.success is True
    assert "Computed: 30" in res.stdout

    # 4. Check code executions endpoint again
    resp = client.get(f"/projects/{project_id}/code-executions")
    assert resp.status_code == 200
    records = resp.json()
    assert len(records) >= 1
    assert records[0]["stage"] == "features"
    assert "Computed: 30" in records[0]["stdout"]
    assert records[0]["exit_code"] == 0
    assert records[0]["success"] is True

    # 5. Delete the project via DELETE /projects/{project_id}
    del_resp = client.delete(f"/projects/{project_id}")
    assert del_resp.status_code == 200
    del_data = del_resp.json()
    assert del_data["status"] == "success"

    # 6. Verify project is removed from DB and filesystem
    with Session(engine) as session:
        proj_in_db = session.get(Project, project_id)
        assert proj_in_db is None

    p_dir = PROJECTS_DIR / project_id
    assert not p_dir.exists()

    # 7. Check 404 after deletion
    get_resp = client.get(f"/projects/{project_id}")
    assert get_resp.status_code == 404
