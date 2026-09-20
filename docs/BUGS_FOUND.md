# Audit: Runtime Bugs Identified & Resolved in Phase 1

This document tracks the error classes, root causes, targeted fixes, and verification status across backend agents, safe utilities, and event logging in `ML_agent`.

| # | File:Line | Symptom | Root Cause | Fix | Verification |
|---|-----------|---------|------------|-----|--------------|
| **1** | `agents/loop_utils.py:103` | `TypeError: log_event() got multiple values for argument 'agent'` | `log_event(agent_name, ...)` was called with both positional `agent_name` and unpack `**payload` containing `agent=agent_name`. | Removed redundant `agent=agent_name` keyword parameter from payload dictionary. | `smoke_test.py` and `pytest tests/test_stall_detector.py` passed. |
| **2** | `agents/modeler_agent.py:144, 203` | `ValueError: could not convert string to float: 'None'` / `TypeError: '>' not supported between instances of 'NoneType' and 'float'` / `NaN` crashes | Direct conversion `float(parsed["cv_score"])` and direct comparison `candidate > current_best` without null, NaN, or non-numeric validation. | Replaced raw float casting and `_better()` with `to_float(..., allow_nan=False)` and `is_better(cand, best, higher_is_better)` from `utils.safe`. Replaced raw delta with `safe_diff()`. | `tests/test_safe_utils.py` unit tests and `smoke_test.py` pass cleanly. |
| **3** | `agents/profiler_agent.py:127, 240` | `TypeError: type numpy.float64 doesn't define __round__ method` or `NaN` serialization crash; `json.loads` JSONDecodeError when LLM outputs markdown fences | `round(series.std(), 3)` on single-element/null columns produces `NaN` or unroundable types; LLM output enclosed in ````json ... ```` fences fails raw `json.loads()`. | Applied `safe_round()`, implemented `_parse_json()` to strip markdown fences, and added schema-safe fallbacks if LLM returns invalid JSON. | `smoke_test.py` mock profiler and parser validation passes. |
| **4** | `agents/supervisor.py:180, 218` | `TypeError: unsupported operand type(s) for -: 'float' and 'NoneType'` | Candidate scores and baseline scores subtracted directly in supervisor decision loop without verifying numeric types. | Routed all score comparisons and deltas through `to_float()`, `safe_diff()`, and `safe_round()`. | `pytest tests/test_supervisor_retry_cap.py` and `test_stalled_retry_escalation.py` pass. |
| **5** | `tools/logger.py:46` | Browser `SyntaxError: Unexpected token 'N', "NaN" is not valid JSON` in SSE stream | Standard library `json.dumps(record)` converts Python `float('nan')` to raw `NaN` (invalid JSON per RFC 8259), crashing browser `JSON.parse()`. | Filtered all event payloads through `safe_json()` before disk persistence and SSE broadcast, mapping `NaN`/`Infinity` to `None`/`null`. | SSE stream verified with valid JSON payloads. |
| **6** | `agents/features_agent.py`, `coder_agent.py`, `judge_agent.py`, `reporter_agent.py` | `AttributeError: module 'agents.coder_agent' has no attribute '_make_llm'` during test mocking / unit tests | Modules directly invoked `get_llm()` without exposing `_make_llm` hook expected by test suites and smoke tests. | Exported `_make_llm = get_llm` at module level in each agent and dynamically resolved `_make_llm()` on invocation. | `smoke_test.py` (60 passed, 0 failed). |

---

## Error Hardening Infrastructure Added

- `utils/exceptions.py`: Typed hierarchy (`PipelineError`, `LLMParseError`, `CodeExecutionError`, `MetricUnavailableError`, `StateError`) with structured context (`step`, `details`, `error_signature`).
- `utils/safe.py`: Safe mathematical and serialization primitives:
  - `to_float(val, default=None, allow_nan=False)`
  - `is_better(candidate, baseline, higher_is_better=True, min_delta=1e-5)`
  - `safe_diff(candidate, baseline, higher_is_better=True)`
  - `safe_round(val, ndigits=4, default=None)`
  - `safe_div(num, denom, default=0.0)`
  - `safe_json(data)`
  - `require(condition, exc_class, message, **context)`
- `tests/test_safe_utils.py`: 16 comprehensive unit tests covering edge cases (NaN, Inf, strings, None, dictionary recursion, division by zero).
