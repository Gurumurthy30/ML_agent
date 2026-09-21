import time
import threading
import pytest
from unittest.mock import MagicMock
from tools.tracer import get_run_control
from agents.loop_utils import run_exploration_loop
from agents.supervisor import graph_node_supervisor
from state import build_initial_state


def test_loop_utils_honors_run_control_stop():
    run_id = "test_run_control_stop_loop"
    ctrl = get_run_control(run_id)
    ctrl.stop()

    iterations_called = []

    def fake_decide(condensed):
        return MagicMock(decision="continue", reasoning="continue", task_spec="task")

    def fake_execute(decision, iteration):
        iterations_called.append(iteration)
        return {"condensed": f"iter {iteration}", "record": {}}

    res = run_exploration_loop(
        run_id=run_id,
        agent_name="eda_agent",
        ceiling=10,
        decide_next_step=fake_decide,
        execute_step=fake_execute,
    )

    assert res["exit_reason"] == "user_stopped"
    assert len(iterations_called) == 0


def test_loop_utils_honors_run_control_pause_resume():
    run_id = "test_run_control_pause_loop"
    ctrl = get_run_control(run_id)
    ctrl.resume()  # clean state
    ctrl.pause()

    step_executed = []

    def fake_decide(condensed):
        return MagicMock(decision="stop", reasoning="done")

    def fake_execute(decision, iteration):
        step_executed.append(iteration)
        return {"condensed": "done", "record": {}}

    res_box = {}

    def worker():
        res_box["res"] = run_exploration_loop(
            run_id=run_id,
            agent_name="eda_agent",
            ceiling=5,
            decide_next_step=fake_decide,
            execute_step=fake_execute,
        )

    t = threading.Thread(target=worker)
    t.start()

    # Worker must be blocked while paused
    time.sleep(0.3)
    assert t.is_alive()
    assert "res" not in res_box

    # Resume must unblock worker
    ctrl.resume()
    t.join(timeout=2.0)
    assert not t.is_alive()
    assert res_box.get("res") is not None
    assert res_box["res"]["exit_reason"] == "llm_stop"


def test_supervisor_honors_run_control_stop():
    run_id = "test_run_control_stop_supervisor"
    ctrl = get_run_control(run_id)
    ctrl.stop()

    state = build_initial_state(dataset_path="test.csv", run_id=run_id)
    res = graph_node_supervisor(state)

    assert res["next_agent"] == "reporter"
    assert res["stop_reason"] == "user_rejected"
