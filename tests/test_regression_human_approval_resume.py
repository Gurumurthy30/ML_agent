"""
Regression and end-to-end tests for human-approval resume path (0a - 0d):
  0a: Individual routing tests for 'approved', 'modify', and 'reject'.
  0b: Invalid input validation (missing, null, or unknown approval_status returns 400).
  0c: Double-resume protection (subsequent resume returns 409 Conflict).
  0d: Live visibility: 'resumed' event reaches the SSE stream subscribers in real-time.
"""
import os
import json
import tempfile
import time
import pytest
from fastapi.testclient import TestClient

from api.main import app
from graph import human_approval_node, route_after_human_approval
from tools.tracer import register_run, update_run_status
from tools.logger import subscribe, unsubscribe, log_event


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


# ---------------------------------------------------------------------------
# 0a. Downstream Routing Verification for Each approval_status
# ---------------------------------------------------------------------------
def test_resume_routing_approved(monkeypatch, tmp_path):
    """
    approved -> updates transformed_dataset_path to feature_plan['proposed_output_path']
    when the file exists on disk; route_after_human_approval returns 'supervisor'.
    """
    proposed_file = tmp_path / "transformed_dataset.parquet"
    proposed_file.write_text("dummy transformed data")
    proposed_path = str(proposed_file)

    run_id = f"test_apprv_{int(time.time()*1000)}"
    register_run(run_id, dataset_path="dummy.csv")

    state = {
        "run_id": run_id,
        "requires_human_approval": True,
        "approval_reason": "destructive_action",
        "feature_plan": {
            "description": "Drop correlated column",
            "proposed_output_path": proposed_path,
        },
    }

    # Simulate LangGraph interrupt returning resume payload
    monkeypatch.setattr("graph.interrupt", lambda x: {"approval_status": "approved"})

    update = human_approval_node(state)

    assert update["approval_status"] == "approved"
    assert update["requires_human_approval"] is False
    assert update["transformed_dataset_path"] == proposed_path

    # Merge update into state and verify downstream routing
    state.update(update)
    next_route = route_after_human_approval(state)
    assert next_route == "supervisor"


def test_resume_routing_modify(monkeypatch):
    """
    modify -> route_after_human_approval sends execution back to 'features' agent.
    """
    run_id = f"test_mod_{int(time.time()*1000)}"
    register_run(run_id, dataset_path="dummy.csv")

    state = {
        "run_id": run_id,
        "requires_human_approval": True,
        "approval_reason": "guided_mode",
        "feature_plan": {"description": "Try PCA instead"},
    }

    monkeypatch.setattr("graph.interrupt", lambda x: {"approval_status": "modify"})

    update = human_approval_node(state)

    assert update["approval_status"] == "modify"
    assert update["requires_human_approval"] is False
    assert "transformed_dataset_path" not in update

    state.update(update)
    next_route = route_after_human_approval(state)
    assert next_route == "features"


def test_resume_routing_reject(monkeypatch):
    """
    reject -> routes to 'supervisor'; approval_status 'reject' is preserved in state.
    """
    run_id = f"test_rej_{int(time.time()*1000)}"
    register_run(run_id, dataset_path="dummy.csv")

    state = {
        "run_id": run_id,
        "requires_human_approval": True,
        "approval_reason": "destructive_action",
    }

    monkeypatch.setattr("graph.interrupt", lambda x: {"approval_status": "reject"})

    update = human_approval_node(state)

    assert update["approval_status"] == "reject"
    assert update["requires_human_approval"] is False

    state.update(update)
    next_route = route_after_human_approval(state)
    assert next_route == "supervisor"
    assert state.get("approval_status") == "reject"


# ---------------------------------------------------------------------------
# 0b. Invalid Input Handling (Missing, Null, or Unknown approval_status)
# ---------------------------------------------------------------------------
def test_resume_invalid_input_rejected_at_api_layer(client):
    run_id = f"test_inv_{int(time.time()*1000)}"
    register_run(run_id, dataset_path="dummy.csv")
    update_run_status(run_id, status="paused", stop_reason="human_approval_required")

    # 1. Unknown status string
    res_bad = client.post(f"/runs/{run_id}/resume", json={"approval_status": "invalid_choice"})
    assert res_bad.status_code == 400
    assert "Invalid or missing approval_status" in res_bad.json()["detail"]

    # 2. Null status
    res_null = client.post(f"/runs/{run_id}/resume", json={"approval_status": None})
    assert res_null.status_code == 400
    assert "Invalid or missing approval_status" in res_null.json()["detail"]

    # 3. Missing key
    res_empty = client.post(f"/runs/{run_id}/resume", json={})
    assert res_empty.status_code == 400
    assert "Invalid or missing approval_status" in res_empty.json()["detail"]


# ---------------------------------------------------------------------------
# 0c. Double-Resume Protection (409 Conflict)
# ---------------------------------------------------------------------------
def test_double_resume_returns_409_conflict(client, monkeypatch):
    run_id = f"test_dbl_{int(time.time()*1000)}"
    register_run(run_id, dataset_path="dummy.csv")
    update_run_status(run_id, status="paused", stop_reason="human_approval_required")

    monkeypatch.setattr("api.main._run_graph_in_background", lambda stream_input, run_id: None)

    # First resume succeeds
    res1 = client.post(f"/runs/{run_id}/resume", json={"approval_status": "approved"})
    assert res1.status_code == 200
    assert res1.json()["status"] == "resumed"

    # Second resume returns 409 Conflict (not paused)
    res2 = client.post(f"/runs/{run_id}/resume", json={"approval_status": "approved"})
    assert res2.status_code == 409
    assert "not currently paused" in res2.json()["detail"]


# ---------------------------------------------------------------------------
# 0d. Resume Live Visibility via SSE
# ---------------------------------------------------------------------------
def test_resume_emits_live_sse_event():
    run_id = f"test_sse_res_{int(time.time()*1000)}"
    register_run(run_id, dataset_path="dummy.csv")

    # Subscribe queue
    sub_queue = subscribe(run_id)
    try:
        # Simulate node resuming and emitting event
        log_event(
            run_id, "human_approval", "resumed",
            decision={"approval_status": "approved", "note": "user confirmed"}
        )

        # Confirm event was pushed to subscriber queue
        assert not sub_queue.empty()
        rec = sub_queue.get_nowait()
        assert rec["agent"] == "human_approval"
        assert rec["event"] == "resumed"
        assert rec["decision"]["approval_status"] == "approved"
    finally:
        unsubscribe(run_id, sub_queue)
