"""
Fault-Injection & Hardening Test Suite (12 Scenarios):
  1. test_fault_nan_metric: float('nan') safely handled
  2. test_fault_none_metric: None metric safely handled
  3. test_fault_string_score: Strings ("0.852", "N/A", "None") safely converted
  4. test_fault_div_zero: Safe division by zero returns default
  5. test_fault_malformed_llm_json: Markdown fences and broken json safely recovered
  6. test_fault_syntax_error_code: Coder syntax error captured and signed
  7. test_fault_missing_column: KeyError / missing feature caught
  8. test_fault_infinite_retry_modeler: Modeler plateau triggers tier escalation
  9. test_fault_duplicate_error_loop: 2+ repeats trigger mutation/escalation
  10. test_fault_safety_envelope_time: Wall-clock limit winds down cleanly
  11. test_fault_safety_envelope_tokens: Token limit winds down cleanly
  12. test_fault_run_controls: Pause, resume, and stop controls function as expected
"""
import math
import pytest
from utils.safe import to_float, is_better, safe_diff, safe_div, safe_round, safe_json
from utils.exceptions import PipelineError, LLMParseError, CodeExecutionError
from agents.profiler_agent import _parse_json
from agents.adaptive_controller import (
    TriedIdeasRegistry,
    ErrorSignatureDeduplicator,
    NoiseBandPlateauDetector,
    SafetyEnvelope,
    AdaptiveStoppingPolicy,
)
from tools.tracer import compute_error_signature, RunControl


# 1. NaN Metric Handling
def test_fault_nan_metric():
    nan_val = float('nan')
    res = to_float(nan_val, default=None, allow_nan=False)
    assert res is None

    # is_better should never crash on NaN
    assert is_better(nan_val, 0.8) is False
    assert is_better(0.8, nan_val) is True

    # safe_json maps NaN to None
    clean = safe_json({"metric": nan_val})
    assert clean["metric"] is None


# 2. None Metric Handling
def test_fault_none_metric():
    res = to_float(None, default=0.0)
    assert res == 0.0

    delta = safe_diff(None, 0.8, default=None)
    assert delta is None

    delta2 = safe_diff(0.85, None, default=None)
    assert delta2 is None


# 3. String Score Parsing
def test_fault_string_score():
    assert to_float("0.852") == 0.852
    assert to_float("  0.9123  ") == 0.9123
    assert to_float("N/A", default=None) is None
    assert to_float("None", default=None) is None
    assert to_float("error_code_500", default=0.0) == 0.0


# 4. Safe Division by Zero
def test_fault_div_zero():
    assert safe_div(10, 0) == 0.0
    assert safe_div(10, 0, default=None) is None
    assert safe_div(0, 0) == 0.0
    assert safe_div(15, 3) == 5.0


# 5. Malformed LLM JSON with Markdown Fences
def test_fault_malformed_llm_json():
    # Markdown fence wrapped
    raw_fenced = "```json\n{\"target_column\": \"churn\", \"task_type\": \"binary\"}\n```"
    parsed = _parse_json(raw_fenced)
    assert parsed["target_column"] == "churn"
    assert parsed["task_type"] == "binary"

    # Fences without json tag
    raw_bare = "```\n{\"cv_score\": 0.88}\n```"
    parsed_bare = _parse_json(raw_bare)
    assert parsed_bare["cv_score"] == 0.88

    # Broken json returns None safely without throwing
    broken = "Here is your output: {bad json without quotes}"
    parsed_broken = _parse_json(broken)
    assert parsed_broken is None


# 6. Syntax Error Code Signature
def test_fault_syntax_error_code():
    err_msg = "File \"<string>\", line 12, in <module>\nSyntaxError: invalid syntax"
    sig = compute_error_signature("SyntaxError", err_msg)
    assert sig.startswith("SyntaxError:")
    assert len(sig) > len("SyntaxError:")


# 7. Missing Column KeyError Handling
def test_fault_missing_column():
    err_msg = "KeyError: 'Age_engineered_x2'"
    sig = compute_error_signature("KeyError", err_msg)
    assert "KeyError:" in sig


# 8. Modeler Infinite Plateau Triggers Tier Escalation
def test_fault_infinite_retry_modeler():
    policy = AdaptiveStoppingPolicy()
    run_id = "run_plateau_fault"
    policy.safety_envelope.start_run(run_id)

    stagnant_state = {
        "iteration": 4,
        "metric_history": [0.8100, 0.8102, 0.8101, 0.8103],
    }
    rec = policy.evaluate_next_action(run_id, stagnant_state, proposed_tier=1)
    assert rec["action"] == "escalate"
    assert rec["tier"] == 2
    assert rec["next_agent"] == "features"


# 9. Duplicate Error Loop Detection
def test_fault_duplicate_error_loop():
    dedup = ErrorSignatureDeduplicator()
    run_id = "run_loop_fault"

    # Repeat same error 2 times
    dedup.record_error(run_id, "LightGBMError", "Check failed at 0x7ffd9820")
    dedup.record_error(run_id, "LightGBMError", "Check failed at 0x7ffd9999")

    assert dedup.should_force_escalate(run_id, max_consecutive=2) is True


# 10. Safety Envelope Wall Clock Limit
def test_fault_safety_envelope_time():
    env = SafetyEnvelope(max_wall_time_s=1)
    env.start_run("run_time_fault")
    import time
    time.sleep(1.1)

    status, msg = env.check_envelope("run_time_fault", current_iteration=1)
    assert status == "exhausted"
    assert "Wall-clock" in msg


# 11. Safety Envelope Token Limit
def test_fault_safety_envelope_tokens():
    env = SafetyEnvelope(max_tokens=100000)
    env.start_run("run_tokens_fault")

    status, msg = env.check_envelope("run_tokens_fault", current_iteration=1, total_tokens=100001)
    assert status == "exhausted"
    assert "Token safety limit" in msg


# 12. Run Controls (Pause, Resume, Stop)
def test_fault_run_controls():
    ctrl = RunControl("run_ctrl_test")
    assert ctrl.is_paused() is False

    ctrl.pause()
    assert ctrl.is_paused() is True

    ctrl.resume()
    assert ctrl.is_paused() is False

    assert ctrl.stopped is False
    ctrl.stop()
    assert ctrl.stopped is True
