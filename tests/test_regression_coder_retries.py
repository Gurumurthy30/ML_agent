"""
Regression tests for coder_agent retry loop optimizations:
- 2 consecutive empty code responses -> early stop at attempt 2
- 2 consecutive identical error signatures -> modified retry directive
- 3 consecutive identical error signatures -> early stop at attempt 3
- Diverse errors -> exhausts all 4 attempts normally without coder_exhausted_early
"""
from unittest.mock import patch, MagicMock
from agents.coder_agent import coder_agent


def test_two_consecutive_empty_codes_stops_at_attempt_2():
    """Verify coder_agent halts immediately on 2 consecutive empty completions."""
    events_logged = []

    def mock_log_event(run_id, agent, event_name, **kwargs):
        events_logged.append({"event": event_name, **kwargs})

    # Return empty strings (e.g. empty fences or whitespace)
    with patch("agents.coder_agent._make_llm") as mock_llm_factory, \
         patch("agents.coder_agent.stream_text", return_value="   ```python\n\n```   "), \
         patch("agents.coder_agent.log_event", side_effect=mock_log_event):

        res = coder_agent(
            task_spec="print hello",
            input_paths={"dataset": "dummy.csv"},
            output_path="out.json",
            context={},
            max_attempts=4,
            run_id="test_run_empty",
        )

        assert res["success"] is False
        assert res["attempts"] == 2
        assert res.get("exhausted_early") is True
        assert res.get("exit_reason") == "consecutive_empty_code"

        exhausted_events = [e for e in events_logged if e["event"] == "coder_exhausted_early"]
        assert len(exhausted_events) == 1
        assert exhausted_events[0]["reason"] == "consecutive_empty_code"
        assert exhausted_events[0]["attempts"] == 2


def test_three_consecutive_identical_errors_stops_at_attempt_3():
    """Verify coder_agent prompts for fundamentally different approach on 2nd repeat,
    and terminates early on 3rd repeat."""
    events_logged = []
    stream_calls = []

    def mock_log_event(run_id, agent, event_name, **kwargs):
        events_logged.append({"event": event_name, **kwargs})

    def mock_stream_text(llm, messages, run_id=None, agent=None):
        stream_calls.append([m.content for m in messages])
        return "print('attempt')"

    def mock_execute(code, input_paths, output_path, timeout, run_id):
        # Same error on each attempt
        return {
            "success": False,
            "stdout": "",
            "stderr": "ZeroDivisionError: division by zero at line 42",
            "output_path": None,
        }

    with patch("agents.coder_agent._make_llm"), \
         patch("agents.coder_agent.stream_text", side_effect=mock_stream_text), \
         patch("agents.coder_agent._execute", side_effect=mock_execute), \
         patch("agents.coder_agent.log_event", side_effect=mock_log_event):

        res = coder_agent(
            task_spec="compute division",
            input_paths={"dataset": "dummy.csv"},
            output_path="out.json",
            context={},
            max_attempts=4,
            run_id="test_run_repeated_err",
        )

        assert res["success"] is False
        assert res["attempts"] == 3
        assert res.get("exhausted_early") is True
        assert res.get("exit_reason") == "repeated_identical_error"

        # Check that attempt 2 (which is passed in stream_calls[1] as the prompt before generation 2)
        # did not yet have the fundamental directive, but attempt 3 prompt (stream_calls[2]) DID have it!
        # stream_calls[0]: initial call (1 message)
        # stream_calls[1]: retry 1 (after 1st error)
        # stream_calls[2]: retry 2 (after 2nd consecutive error) -> MUST contain "fundamentally different approach"
        assert len(stream_calls) == 3
        attempt_2_messages = stream_calls[1]
        assert "fundamentally different approach" not in attempt_2_messages[-1]

        attempt_3_messages = stream_calls[2]
        assert "Your last fix produced the identical error — try a fundamentally different approach" in attempt_3_messages[-1]

        exhausted_events = [e for e in events_logged if e["event"] == "coder_exhausted_early"]
        assert len(exhausted_events) == 1
        assert exhausted_events[0]["reason"] == "repeated_identical_error"
        assert exhausted_events[0]["attempts"] == 3


def test_four_differing_errors_exhausts_normally():
    """Verify coder_agent uses all max_attempts if each failure is different,
    without firing coder_exhausted_early."""
    events_logged = []
    error_counter = [0]

    def mock_log_event(run_id, agent, event_name, **kwargs):
        events_logged.append({"event": event_name, **kwargs})

    def mock_execute(code, input_paths, output_path, timeout, run_id):
        error_counter[0] += 1
        return {
            "success": False,
            "stdout": "",
            "stderr": f"ErrorType{error_counter[0]}: Unique failure details {error_counter[0]}",
            "output_path": None,
        }

    with patch("agents.coder_agent._make_llm"), \
         patch("agents.coder_agent.stream_text", return_value="x = 1"), \
         patch("agents.coder_agent._execute", side_effect=mock_execute), \
         patch("agents.coder_agent.log_event", side_effect=mock_log_event):

        res = coder_agent(
            task_spec="compute something",
            input_paths={"dataset": "dummy.csv"},
            output_path="out.json",
            context={},
            max_attempts=4,
            run_id="test_run_diverse_err",
        )

        assert res["success"] is False
        assert res["attempts"] == 4
        assert res.get("exhausted_early") is not True

        exhausted_events = [e for e in events_logged if e["event"] == "coder_exhausted_early"]
        assert len(exhausted_events) == 0
