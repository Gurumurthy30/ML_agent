import pytest
from unittest.mock import patch, MagicMock
from agents.coder_agent import coder_agent


def test_coder_agent_logs_coder_attempt_not_attempt_result():
    run_id = "test_coder_collision_run"
    mock_llm = MagicMock()
    mock_llm.stream.return_value = ["```python\nprint('hello')\n```"]

    mock_exec_result = {
        "success": True,
        "stdout": "hello",
        "stderr": "",
        "output_path": "out.txt",
    }

    events_logged = []

    def fake_log_event(rid, agent, event_type, **payload):
        events_logged.append({"agent": agent, "event_type": event_type, **payload})

    with patch("agents.coder_agent.get_llm", return_value=mock_llm), \
         patch("agents.coder_agent._execute", return_value=mock_exec_result), \
         patch("agents.coder_agent.log_event", side_effect=fake_log_event):
        res = coder_agent(
            task_spec="print hello",
            input_paths={},
            output_path="out.txt",
            context={},
            run_id=run_id,
            parent_agent="modeler_agent",
            parent_iteration=1,
        )

    assert res["success"] is True

    # Find the attempt event logged by coder_agent
    attempt_events = [e for e in events_logged if e["agent"] == "coder_agent" and e["event_type"] in ("attempt_result", "coder_attempt")]
    assert len(attempt_events) > 0, "No attempt event was logged by coder_agent"

    event_names = [e["event_type"] for e in attempt_events]
    assert "attempt_result" not in event_names, "coder_agent emitted colliding 'attempt_result' event!"
    assert "coder_attempt" in event_names, "coder_agent did not emit 'coder_attempt' event"
