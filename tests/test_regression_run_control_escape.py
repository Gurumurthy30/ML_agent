"""
Regression tests for RunControl escape functionality:
  1. RunControl.escape() one-shot flag behavior.
  2. Escape mid coder-retry exits before max_attempts, returns failure, logs 'user_escape_consumed'.
  3. Escape mid exploration-loop exits before ceiling, sets exit_reason='user_escape', logs event.
  4. POST /runs/{id}/escape endpoint sets escape flag and returns 200/404.
"""
import time
import pytest
from fastapi.testclient import TestClient

from api.main import app
from tools.tracer import RunControl, get_run_control, register_run, get_run_events
from agents.coder_agent import coder_agent
from agents.loop_utils import run_exploration_loop


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_run_control_escape_one_shot():
    run_id = f"test_ctrl_esc_{int(time.time()*1000)}"
    ctrl = RunControl(run_id)

    assert ctrl.escaped is False
    assert ctrl.consume_escape() is False

    # Set escape
    ctrl.escape()
    assert ctrl.escaped is True

    # First consume returns True and resets flag
    assert ctrl.consume_escape() is True
    assert ctrl.escaped is False

    # Second consume returns False (one-shot)
    assert ctrl.consume_escape() is False


def test_escape_mid_coder_retry(monkeypatch, tmp_path):
    run_id = f"test_coder_esc_{int(time.time()*1000)}"
    register_run(run_id, dataset_path="dummy.csv")

    output_p = str(tmp_path / "out.json")

    # Mock stream_text to return valid-looking code on attempt 1
    # Mock _execute to fail attempt 1, triggering a retry
    attempts_called = 0
    def mock_stream(llm, messages, run_id=None, agent=None):
        nonlocal attempts_called
        attempts_called += 1
        return "import sys; print('attempt')"

    def mock_exec(code, input_paths, output_path, timeout, run_id):
        # Trigger escape right before attempt 2 executes
        get_run_control(run_id).escape()
        return {
            "success": False,
            "stdout": "",
            "stderr": "ValueError: mock error",
            "output_path": None,
        }

    monkeypatch.setattr("agents.coder_agent.stream_text", mock_stream)
    monkeypatch.setattr("agents.coder_agent._execute", mock_exec)

    result = coder_agent(
        task_spec="Failing task",
        input_paths={},
        output_path=output_p,
        context={},
        max_attempts=4,
        run_id=run_id,
    )

    # Must exit early due to escape on attempt 2, not burning all 4 attempts
    assert result["success"] is False
    assert result.get("escaped") is True
    assert result.get("exit_reason") == "user_escape"
    assert attempts_called < 4

    # Verify event was logged
    events = get_run_events(run_id)
    esc_events = [e for e in events if e.get("event") == "user_escape_consumed"]
    assert len(esc_events) >= 1
    assert esc_events[0]["level"] == "coder_retry"


def test_escape_mid_exploration_loop():
    run_id = f"test_loop_esc_{int(time.time()*1000)}"
    register_run(run_id, dataset_path="dummy.csv")

    class MockDecision:
        decision = "continue"
        reasoning = "keep exploring"
        task_spec = "explore features"

    iterations_run = 0

    def decide_step(condensed_history):
        return MockDecision()

    def execute_step(decision, iteration):
        nonlocal iterations_run
        iterations_run += 1
        if iteration == 2:
            # User presses escape during/after iteration 2
            get_run_control(run_id).escape()
        return {
            "condensed": f"step_{iteration}",
            "record": {"iter": iteration},
            "metric": 0.5,
        }

    loop_res = run_exploration_loop(
        run_id=run_id,
        agent_name="features_agent",
        ceiling=10,
        decide_next_step=decide_step,
        execute_step=execute_step,
    )

    # Must exit early at iteration 3 with user_escape, not running to ceiling 10
    assert loop_res["exit_reason"] == "user_escape"
    assert loop_res["iterations"] == 2

    # Verify event was logged
    events = get_run_events(run_id)
    esc_events = [e for e in events if e.get("event") == "user_escape_consumed"]
    assert len(esc_events) >= 1
    assert esc_events[0]["level"] == "exploration_loop"


def test_post_escape_api_endpoint(client):
    run_id = f"test_api_esc_{int(time.time()*1000)}"
    register_run(run_id, dataset_path="dummy.csv")

    ctrl = get_run_control(run_id)
    assert ctrl.escaped is False

    # Successful escape
    res = client.post(f"/runs/{run_id}/escape")
    assert res.status_code == 200
    assert res.json()["control"] == "escaped"
    assert ctrl.escaped is True

    # 404 on nonexistent run
    res_404 = client.post("/runs/nonexistent_run_esc/escape")
    assert res_404.status_code == 404
