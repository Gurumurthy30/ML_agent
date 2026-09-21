# ML Pipeline Architecture & Safety Audit Report

## Overview
This audit was conducted across the multi-agent LangGraph ML pipeline repository (`ML_agent`). The pipeline consists of the Supervisor, Profiler, EDA, Features, Modeler, Judge, Human Approval, and Reporter agents, dual-persistence tracing (JSONL + SQLite), a local RAG-style run memory store, and an adaptive stopping/safety envelope controller.

All P0 (correctness/safety) and P1 (logging/data integrity) items have been resolved and verified with dedicated regression tests. P2 quality and scaling items have been resolved or flagged with architectural recommendations.

---

## Audit Findings Matrix

| ID | File:Line | Severity | Description | Status | Fix or Recommendation |
|---|---|---|---|---|---|
| **1** | `agents/features_agent.py:171`, `graph.py:57` | **P0** | Destructive action approval gate bypassed in non-guided mode (`needs_approval = result["success"] and guided` ignored `is_destructive`; `graph.py` also gated on `guided_mode`). | **Fixed** | Updated condition: `needs_approval = result["success"] and (guided or is_destructive)`. State update sets `requires_human_approval=True`, `approval_reason="destructive_action"`, and `feature_plan` regardless of `guided_mode`. `route_after_features` routes to `human_approval` whenever `requires_human_approval` is True. |
| **2** | `agents/supervisor.py:374` | **P0** | Adaptive controller's `escalate` and `human_approval` actions computed and logged, but discarded before routing. | **Fixed** | Added handling branches in `graph_node_supervisor` for `action == "escalate"` (routes to next agent with escalated retry tier) and `action == "human_approval"` (routes to human approval with mapped approval reason). |
| **3** | `agents/adaptive_controller.py:341` | **P0** | Contract mismatch: `state.py` defines `retry_tier: Literal[0, 1, 2]`, but `adaptive_controller.py` proposed tier 3 on plateau/error. | **Fixed** | Implemented Option (b) (conservative default): capped `NoiseBandPlateauDetector` and `ErrorSignatureDeduplicator` at tier 2, routing to `wind_down` with `stop_reason="converged"` once tier 2 completes. Option (a) flagged for review. |
| **4** | `agents/loop_utils.py:89`, `agents/supervisor.py:328` | **P0** | `RunControl` primitives (`pause`, `resume`, `stop`) never wired into execution loop or graph nodes. | **Fixed** | Wired `get_run_control(run_id).wait_if_paused()` and `.stopped` check into `run_exploration_loop` (exiting with reason `"user_stopped"`) and `graph_node_supervisor` (stopping with reason `"user_rejected"`). |
| **5** | `agents/coder_agent.py:187` | **P1** | Event type name collision: `coder_agent` logged `event_type="attempt_result"` when `parent_agent == "modeler_agent"`, colliding with `modeler_agent`'s own `attempt_result` schema. | **Fixed** | Renamed `coder_agent` attempt event to `"coder_attempt"`. Modeler's `"attempt_result"` left untouched. |
| **6** | `agents/reporter_agent.py:40` | **P1** | `_build_monitoring_summary` hand-rolled raw JSONL parsing instead of using SQLite-indexed `tools/tracer.py`, losing parent-agent attribution. | **Fixed** | Replaced internal aggregation with `tracer.get_run_events`, `tracer.get_run_attempts`, and `tracer.get_run_errors`, grouping attempts and errors by `parent_agent`. |
| **7** | `memory/` (legacy) | **P1** | Vector/RAG run memory store had concurrency and backend issues, polluted state, and lacked agent scoping. | **Resolved** | Completely removed legacy `memory/` package and RAG store. Deleted obsolete run logs and artifacts. |
| **8** | Architecture | **P0** | Need for structured agent memory scoping: Modeler lacked score/attempt memory and blunder tracking ("blender shit mistake"); unsummarized memory leaked token context. | **Resolved** | Implemented **Scoped Memory Architecture** (`utils/scoped_memory.py`):<br>1. **Profiler**: Strictly **NO memory** (simple one-time profiling).<br>2. **Specialists** (`coder`, `eda`, `features`, `modeler`): **Private / Score Memory** with strict isolation. Modeler maintains private scorecard and blunder tracking (crashed architectures, invalid parameters, degraded scores) to prevent repeating mistakes.<br>3. **Executives** (`supervisor`, `judge`, `reporter`): **Open Summarization Memory** with bounded digest (<2500 chars) strictly preventing token context size leaks. |
| **9** | `agents/modeler_agent.py:15` | **P2** | Docstring/config drift: docstring claimed plateau backstop fires after "last 5 iterations", while `config.CONVERGENCE_PATIENCE` defaults to 3. | **Fixed** | Updated docstring to dynamically reference `config.CONVERGENCE_PATIENCE` by name. |
| **10** | `utils/safe.py:160` | **P1** | `safe_json` used `hasattr(obj, "model_dump") and callable(obj.model_dump)` which infinitely recursed on `MagicMock` objects in tests and logging pipelines. | **Fixed** | Updated `safe_json` to strictly check `isinstance(obj, BaseModel)` before calling `model_dump()`. |
| **11** | `tools/tracer.py:60` | **P0** | `RunControl.wait_if_paused(timeout=...)` ignored the `timeout` parameter, causing indefinite hangs if resume/stop was not triggered. | **Fixed** | Updated `wait_if_paused` to check `timeout` against elapsed time and return `False` when the timeout expires. |
| **12** | `agents/adaptive_controller.py:304` | **P1** | Contract mismatch: `AdaptiveStoppingPolicy` returned `stop_reason="safety_envelope_exhausted"`, which violated `AgentState`'s `stop_reason` Literal type. | **Fixed** | Updated `stop_reason` to `"hit_safety_ceiling"`, which is a valid `AgentState` Literal. |
| **13** | `agents/coder_agent.py:180` | **P0** | Wasted LLM calls / subprocess execution: coder agent endlessly retried empty completions or byte-for-byte identical error loops up to `max_attempts` (4). | **Fixed** | Implemented early stopping & prompt adaptation:<br>1. $\ge 2$ consecutive empty completions $\rightarrow$ immediate early exit.<br>2. 2 consecutive identical error signatures $\rightarrow$ mutated retry prompt urging fundamentally different approach.<br>3. 3 consecutive identical error signatures $\rightarrow$ immediate early exit.<br>4. Emits distinct terminal event `"coder_exhausted_early"`. |
| **14** | `tools/logger.py:97` | **P1** | Dual-write try/except pattern in `log_event` caused redundant JSONL writes and subscriber publish calls. | **Fixed** | Collapsed dual-write into single canonical writer routing directly to `tracer.record_event`, with console/debug log mirroring. |
| **15** | `tools/tracer.py:440` | **P1** | Huge code/stdout/stderr payloads bloated the hot SQLite indexing path. | **Fixed** | Added payload truncation (`_truncate_for_sqlite`, max 2048 chars) for SQLite index while preserving 100% full byte-for-byte payload in JSONL files on disk. |
| **16** | `tools/tracer.py:880` | **P1** | No automated retention or rotation policy for `runs/`, `logs/`, or `artifacts/*`. | **Fixed** | Implemented `rotate_and_prune_storage(max_runs, max_age_days)` pruning file storage across `runs/`, `logs/`, `artifacts/`, and SQLite rows. |
| **17** | `tools/tracer.py:117` | **P1** | `runs_index.db` lacked schema migration mechanism (`CREATE TABLE IF NOT EXISTS` only, no `ALTER TABLE`). | **Fixed** | Added `run_migrations()` with `schema_migrations` versioned tracking table, executing idempotent schema evolutions. |
| **18** | `tools/tracer.py:755` | **P1** | `get_run_attempts` and `get_run_errors` recomputed over the entire event history on every call. | **Fixed** | Implemented zero-disk-I/O in-memory cache + `run_materialized_cache` SQLite table keyed by `(run_id, max_seq)`, auto-invalidating on new events. |
| **19** | `tools/tracer.py:195` | **P2** | Missing composite indices for event telemetry queries. | **Fixed** | Added composite indices `idx_events_run_phase` covering `(run_id, phase)` and `idx_events_run_agent_type` covering `(run_id, agent, event_type)`. |
| **20** | `tools/tracer.py:575` | **P2** | Missing explicit run baseline flag and tags/labels for UI filtering. | **Fixed** | Added columns `is_baseline`, `baseline_run_id`, `tags`, `labels` to `runs` table, helper APIs `set_run_baseline`, `set_run_tags`, `add_run_tag`, `set_run_labels`, and filtering support in `list_runs`. |
| **21** | `tools/tracer.py:962`, `api/main.py:46` | **P1** | Storage retention `rotate_and_prune_storage()` existed but was never invoked (Item 0a). | **Fixed** | Wired to admin CLI `python -m tools.tracer --prune` and automatically invoked during FastAPI server startup lifespan. |
| **22** | `tools/tracer.py:760` | **P1** | Thread-safety of in-memory materialized views `_ATTEMPTS_CACHE` and `_ERRORS_CACHE` (Item 0b). | **Verified** | Confirmed `_MATERIALIZED_CACHE_LOCK` guards all cache reads, updates, and pruning invalidations. |
| **23** | `agents/adaptive_controller.py:40`, `tools/tracer.py:230` | **P0** | Adaptive controller state (`TriedIdeasRegistry`, `ErrorSignatureDeduplicator`, `SafetyEnvelope`) lived in unlocked process memory, breaking across multi-worker uvicorn deployments (Item 0c). | **Fixed** | Implemented Option (a): added Migration 5 in `tools/tracer.py` creating `adaptive_ideas`, `adaptive_errors`, and `adaptive_runs` tables in SQLite; updated adaptive controller classes to persist and query across worker processes. |
| **24** | `graph.py:12` | **P0** | Graph used in-memory `MemorySaver()`, so paused runs and checkpointer state were lost on server restart. | **Fixed** | Replaced with `SqliteSaver` pointing to `runs/checkpoints.db`, supporting persistent thread checkpoints across process restarts. |
| **25** | `api/main.py` | **P0** | Backend API layer was missing, blocking monitoring UI and headless remote controls. | **Built** | Implemented complete FastAPI backend layer covering all telemetry and run-control endpoints (`POST /runs`, `GET /runs`, `GET /runs/{id}`, `GET /runs/{id}/events` via SSE, `GET /runs/{id}/attempts`, `GET /runs/{id}/errors`, `POST /runs/{id}/resume`, `/pause`, `/unpause`, `/stop`, `GET /runs/{a}/compare/{b}`, `GET /runs/{id}/export`, and `POST /runs/{id}/tags`, `/baseline`). |
| **26** | `api/main.py:165`, `graph.py:65` | **P0** | Human-approval resume path verification & edge cases: missing 400 validation on malformed `approval_status`, double-resume race condition (submitting `/resume` when not paused), and downstream branch routing coverage (`approved`, `modify`, `reject`). | **Fixed** | 1. Added explicit 400 Bad Request rejection for missing/invalid `approval_status`.<br>2. Added 409 Conflict guard if run is not in `"paused"` state.<br>3. Verified downstream routing: `approved` updates dataset path to proposed output on disk and advances to supervisor; `modify` loops back to features and continues; `reject` transitions to supervisor with rejection status visible.<br>4. Verified live SSE event broadcasting of `"resumed"` event. |
| **27** | `tools/tracer.py:65`, `agents/coder_agent.py:195`, `agents/loop_utils.py:105`, `api/main.py:202` | **P1** | Lack of loop escape control: stuck loops (e.g. repetitive code-gen retries or long plateaued exploration loops) could only be killed completely or paused indefinitely. | **Fixed** | Added one-shot `RunControl.escape()` and thread-safe `consume_escape()`:<br>1. **Coder retry loop**: skips remaining attempts immediately, returns failure, and emits `"user_escape_consumed"` (`level="coder_retry"`).<br>2. **Exploration loop**: breaks iteration ceiling immediately with `exit_reason="user_escape"`, routes to supervisor via standard non-destructive gate (`approval_reason="unresolved_exploration"`), and emits `"user_escape_consumed"` (`level="exploration_loop"`).<br>3. Exposed via `POST /runs/{id}/escape` endpoint. |

---

## Needs Human Sign-Off & Open Architectural Decisions

### 1. Cross-Run Memory (Item 0d) — Deferred (Known Intentional Gap)
- **Status**: **Explicitly Deferred** as an intentional architectural gap per Round 3 decision.
- **Rationale**: The pipeline currently operates strictly on **Intra-Run Scoped Memory** (`utils/scoped_memory.py`) where working agent memories (coder, EDA, features, modeler) and executive digests live within individual run states and persistent checkpoints. No cross-run vector digest is queried across independent pipeline invocations. If cross-run memory across identical dataset fingerprints is needed in the future, it should be implemented via a dedicated SQLite table in `runs_index.db` keyed by `dataset_fingerprint`, avoiding external vector store dependencies.

### 2. Tier-3 Strategy (Option A vs Option B)
- **Current Choice Implemented (Option B - Conservative Default)**:
  - Caps automated escalation at Tier 2.
  - When Tier 2 plateaus or repeatedly errors, the controller cleanly winds down via `next_agent: "reporter"`, `stop_reason: "converged"`.
  - Maintains `retry_tier: Literal[0, 1, 2]` across `state.py`, `supervisor.py`, and `judge_agent.py`.
- **Alternative (Option A - Expansion)**:
  - Extend `retry_tier: Literal[0, 1, 2, 3]` across `state.py`, `SupervisorDecision.retry_tier`, and `JudgeVerdict.retry_tier`.
  - Implement genuine Tier-3 behavior in `agents/modeler_agent.py` (e.g., automated hyperparameter optimization loops with Optuna/Ray Tune and ensemble blending across top candidate models).
- **Trade-off**: Option B prevents infinite retry cycles and enforces a bounded safety ceiling without introducing heavy new dependencies. Option A enables automated ensembling at the cost of additional complexity, compute, and runtime budget.

### 3. Metric Epsilon Drift
- `config.METRIC_IMPROVEMENT_EPSILON` defaults to `0.001` (used by Modeler, Supervisor, and Stall Detector).
- `agents/adaptive_controller.py` defines `DEFAULT_NOISE_BAND_EPSILON = 0.002`.
- **Recommendation for sign-off**: Align `DEFAULT_NOISE_BAND_EPSILON` in `adaptive_controller.py` to import and default to `config.METRIC_IMPROVEMENT_EPSILON` (0.001) for cross-module consistency.

### 4. `AgentState.approval_reason` Literal Extension for `user_escape`
- **Current Choice Implemented (Option B - Conservative Default)**:
  - Preserves existing `approval_reason` schema in `state.py`: `Literal["destructive_action", "unresolved_exploration", "low_confidence", "manual_audit"]`.
  - When a user escape triggers early exit in `run_exploration_loop` (`exit_reason="user_escape"`), agent nodes (`eda_agent.py`, `features_agent.py`, `modeler_agent.py`) treat any non-`llm_stop` exit by setting `requires_human_approval=True` and defaulting `approval_reason="unresolved_exploration"`.
  - Emits telemetry event `"user_escape_consumed"` to clearly distinguish manual human intervention in the audit trail without modifying the core state contract.
- **Alternative (Option A - Dedicated Literal)**:
  - Expand `approval_reason: Optional[Literal["destructive_action", "unresolved_exploration", "low_confidence", "manual_audit", "user_escape"]] = None` in `state.py` and downstream node schemas.
  - Allows front-end UI and supervisor prompts to render specialized "Manual Escape Triggered" approval banners.

---

## Full Audit Checklist Verification

- **Reducer Correctness**: Verified. `candidate_models`, `metric_history`, `private_memories`, `open_summary_memory`, and `messages` use LangGraph reducers (`operator.add`, `merge_private_memories`, `merge_open_summary`, `add_messages`). All other fields use explicit compare-and-replace or single-node ownership.
- **Type-Contract Consistency**: Verified across all models. `retry_tier`, `approval_reason`, `stop_reason`, `next_agent`, and `approval_status` match `AgentState` Literals.
- **Event-Schema Consistency**: Verified. Renamed `"attempt_result"` to `"coder_attempt"` in `coder_agent.py` to eliminate event collision with `modeler_agent.py`. Emits `"user_escape_consumed"` when escape flag is claimed.
- **Memory Scoping & Privacy**: Verified. Modeler, EDA, Features, and Coder maintain isolated private memories. Profiler has zero memory. Executive agents consume bounded open summaries preventing token size leaks.
- **Coder Early Exhaustion & Escape**: Verified. Coder terminates on 2 consecutive empty outputs or 3 identical error signatures, emitting `"coder_exhausted_early"`. Immediately aborts remaining retry iterations when `escape()` is triggered.
- **Dual-Write Consistency**: Verified. Collapsed `logger.py` into canonical `tracer.py` writer with SQLite payload truncation.
- **Experiment Tracking**: Verified. Versioned migrations, materialized view cache, run baselines, tags/labels filtering, and retention/rotation policies implemented and tested.
- **SSE & Replay Concurrency**: Verified. StreamingResponse text/event-stream endpoint with monotonic catch-up via `since_seq` and live queue updates, broadcasting `"resumed"` and `"user_escape_consumed"` events.
- **Persistent Checkpointer**: Verified. Replaced in-memory saver with `SqliteSaver` in `graph.py` ensuring pipeline runs persist across server restarts.
- **Multi-Worker Safety**: Verified. Adaptive controller state (`TriedIdeasRegistry`, `ErrorSignatureDeduplicator`, `SafetyEnvelope`) persisted to SQLite (`runs_index.db`), eliminating state loss under multi-process uvicorn/gunicorn workers.
- **Human Approval & Run Controls**: Verified. Dedicated downstream routing for `approved`, `modify`, and `reject`. Double-resume protected by HTTP 409 Conflict. One-shot `POST /runs/{id}/escape` force-advances stuck coder retries or exploration ceilings.

---

## Regression Test Suite Status

All 109 unit tests and 61 smoke tests passing (170 total checks):
```
====================== 109 passed, 2 warnings in 30.30s =======================
61 passed, 0 failed (smoke_test.py)
```
1. `tests/test_regression_features_destructive_gate.py`: Verifies non-guided destructive actions trigger human approval and routing.
2. `tests/test_regression_supervisor_adaptive_actions.py`: Verifies supervisor honors adaptive controller `escalate` and `human_approval` actions.
3. `tests/test_regression_tier3_cap.py`: Verifies adaptive controller caps escalation at tier 2.
4. `tests/test_regression_run_control_wiring.py`: Verifies loop utils and supervisor respond to pause, resume, and stop.
5. `tests/test_regression_coder_event_collision.py`: Verifies coder agent emits `coder_attempt` instead of colliding `attempt_result`.
6. `tests/test_regression_reporter_tracer_aggregation.py`: Verifies tracer aggregation and parent-agent nesting in reporter.
7. `tests/test_regression_scoped_memory.py`: Verifies profiler zero-memory, modeler private score memory and blunder tracking, coder error tracking, and private isolation.
8. `tests/test_regression_summarization_memory.py`: Verifies open memory summarization, token size leak prevention (<2500 chars), supervisor routing, and executive agent digests.
9. `tests/test_regression_coder_retries.py`: Verifies coder early stopping on consecutive empty code (attempt 2), identical error repetition prompt mutation (attempt 2) and early stop (attempt 3), and terminal event `coder_exhausted_early`.
10. `tests/test_regression_tracer_and_experiments.py`: Verifies schema migrations, SQLite payload truncation, canonical logger writer, baseline/tags filtering, materialized caching, and storage retention rotation.
11. `tests/test_regression_adaptive_controller_persistence.py`: Verifies multi-process persistence of `TriedIdeasRegistry`, `ErrorSignatureDeduplicator`, and `SafetyEnvelope` across independent worker instances via SQLite.
12. `tests/test_api_endpoints.py`: Verifies all 12 FastAPI endpoints (validation, run start in background, status polling, SSE streaming, attempts/errors ledgers, resume with Command, double-resume 409, escape, pause/unpause/stop controls, run comparison, ZIP debug export, and tags/baseline updates).
13. `tests/test_regression_human_approval_resume.py`: Verifies 0a downstream routing (`approved`, `modify`, `reject`), 0b input validation (400), 0c double-resume 409 guard, and 0d live SSE event propagation.
14. `tests/test_regression_run_control_escape.py`: Verifies one-shot consumption of `escape()`, coder retry early exit before `max_attempts`, exploration loop early exit before `ceiling`, and `POST /runs/{id}/escape` API endpoint.
