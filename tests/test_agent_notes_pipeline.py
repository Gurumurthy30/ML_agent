"""
Regression and round-trip tests for the Agent Notes -> Backend API -> Frontend pipeline.
Tests reproduction and fix verification for:
1. Judge feedback overwrite-vs-append during retries
2. Judge rejected_family contract and propagation to state
3. Features operator modification acknowledgment
4. Final report persistence into runs table and non-truncation in SQLite
5. best_metric propagation to runs.best_score
6. Judge verdict telemetry columns (decision, tier, rejected_family)
"""
import os
import json
import time
import pytest
from pydantic import BaseModel
from state import build_initial_state, AgentState
from agents.judge_agent import JudgeVerdict, judge_agent
from tools.tracer import (
    register_run,
    get_run,
    get_run_events,
    update_run_status,
    record_event,
    _truncate_for_sqlite,
)


def test_reproduce_judge_feedback_accumulates_across_retries(monkeypatch, tmp_path):
    """
    Test that judge_feedback is an append-only list across retry rounds,
    so previous rejection feedback is never overwritten when a subsequent verdict accepts.
    """
    data_file = tmp_path / "tiny.csv"
    data_file.write_text("a,b,target\n1,2,0\n3,4,1\n")
    run_id = f"test_fb_acc_{int(time.time() * 1000)}"
    register_run(run_id, dataset_path=str(data_file))

    state = build_initial_state(dataset_path=str(data_file), run_id=run_id)

    # Round 1: Judge Rejects
    verdict1 = JudgeVerdict(
        verdict="reject",
        retry_tier=1,
        feedback="Model accuracy 0.62 is too low; try gradient boosting instead of logistic regression.",
        reasoning="Baseline accuracy fails threshold.",
    )
    monkeypatch.setattr(
        "agents.judge_agent.invoke_structured_robust",
        lambda *args, **kwargs: verdict1,
    )
    update1 = judge_agent(state)

    # Merge into state
    state["last_verdict"] = update1["last_verdict"]
    # If judge_feedback is a list reducer, state["judge_feedback"] += update1["judge_feedback"]
    if isinstance(update1.get("judge_feedback"), list):
        state["judge_feedback"] = (state.get("judge_feedback") or []) + update1["judge_feedback"]
    else:
        state["judge_feedback"] = update1.get("judge_feedback")

    # Round 2: Judge Accepts
    verdict2 = JudgeVerdict(
        verdict="accept",
        retry_tier=None,
        feedback="GradientBoosting achieved 0.84 accuracy, exceeding baseline threshold.",
        reasoning="All convergence criteria satisfied.",
    )
    monkeypatch.setattr(
        "agents.judge_agent.invoke_structured_robust",
        lambda *args, **kwargs: verdict2,
    )
    update2 = judge_agent(state)

    if isinstance(update2.get("judge_feedback"), list):
        state["judge_feedback"] = (state.get("judge_feedback") or []) + update2["judge_feedback"]
    else:
        state["judge_feedback"] = update2.get("judge_feedback")

    # Assert that BOTH feedback messages are preserved in history
    feedbacks = state.get("judge_feedback")
    assert isinstance(feedbacks, list), f"judge_feedback should be a list, got {type(feedbacks)}"
    assert len(feedbacks) == 2, f"Expected 2 feedback entries, got {len(feedbacks)}"
    assert "0.62 is too low" in feedbacks[0]
    assert "achieved 0.84 accuracy" in feedbacks[1]


def test_reproduce_judge_rejected_family_contract(monkeypatch, tmp_path):
    """
    Test that JudgeVerdict schema and judge_agent return rejected_family
    matching the agent prompt's documented output contract.
    """
    data_file = tmp_path / "tiny.csv"
    data_file.write_text("a,b,target\n1,2,0\n3,4,1\n")
    run_id = f"test_rej_fam_{int(time.time() * 1000)}"
    register_run(run_id, dataset_path=str(data_file))

    state = build_initial_state(dataset_path=str(data_file), run_id=run_id)

    # JudgeVerdict must accept rejected_family per documented contract
    verdict = JudgeVerdict(
        verdict="reject",
        retry_tier=1,
        rejected_family="logisticregression",
        feedback="Logistic regression underfit the data.",
        reasoning="Underfitting detected.",
    )
    assert verdict.rejected_family == "logisticregression"

    monkeypatch.setattr(
        "agents.judge_agent.invoke_structured_robust",
        lambda *args, **kwargs: verdict,
    )
    update = judge_agent(state)
    assert update.get("rejected_family") == "logisticregression"


def test_reproduce_judge_verdict_telemetry_columns(monkeypatch, tmp_path):
    """
    Test that when judge_agent logs verdict event, SQLite events table
    has decision and tier columns cleanly populated.
    """
    data_file = tmp_path / "tiny.csv"
    data_file.write_text("a,b,target\n1,2,0\n3,4,1\n")
    run_id = f"test_judge_telem_{int(time.time() * 1000)}"
    register_run(run_id, dataset_path=str(data_file))

    state = build_initial_state(dataset_path=str(data_file), run_id=run_id)
    verdict = JudgeVerdict(
        verdict="reject",
        retry_tier=1,
        feedback="Underperforming model.",
        reasoning="Failed metric gate.",
    )
    monkeypatch.setattr(
        "agents.judge_agent.invoke_structured_robust",
        lambda *args, **kwargs: verdict,
    )
    judge_agent(state)

    evs = get_run_events(run_id)
    verdict_evs = [e for e in evs if e.get("event") == "verdict" or e.get("event_type") == "verdict"]
    assert len(verdict_evs) >= 1
    ev = verdict_evs[0]
    assert ev.get("decision") == "reject"
    assert ev.get("tier") == 1


def test_reproduce_report_persistence_and_no_truncation(tmp_path):
    """
    Test that report text is preserved in full in runs table and not truncated
    by SQLite payload indexing.
    """
    run_id = f"test_rep_trunc_{int(time.time() * 1000)}"
    data_path = str(tmp_path / "data.csv")
    register_run(run_id, dataset_path=data_path)

    # 3500-char markdown report
    long_report = "# Comprehensive ML Pipeline Report\n\n" + ("Detailed analysis paragraph.\n" * 150)
    assert len(long_report) > 3000

    # 1. Update run status with report
    update_run_status(run_id, status="completed", report=long_report, best_score=0.91)

    run = get_run(run_id)
    assert run is not None
    assert run.get("report") == long_report, "Full report should be retrievable from get_run"

    # 2. Test _truncate_for_sqlite preserves report field
    event_payload = {
        "report": long_report,
        "stdout": "A" * 3000,
    }
    truncated = _truncate_for_sqlite(event_payload)
    assert truncated["report"] == long_report, "report field should not be truncated"
    assert "TRUNCATED" in truncated["stdout"], "stdout should still be truncated"


def test_reproduce_features_operator_modification_acknowledgment(monkeypatch, tmp_path):
    """
    Test that when modifications are passed to features_agent, it logs an
    operator_modification_acknowledged event and preserves human instructions.
    """
    data_file = tmp_path / "data.csv"
    data_file.write_text("age,fare,survived\n22,7.25,0\n38,71.28,1\n")
    run_id = f"test_op_ack_{int(time.time() * 1000)}"
    register_run(run_id, dataset_path=str(data_file))

    state = build_initial_state(dataset_path=str(data_file), run_id=run_id)
    op_text = "Keep column 'age' and use median imputation."
    state["modifications"] = op_text
    state["feature_plan"] = {"description": "Proposed drop age", "modifications": op_text}

    from agents.features_agent import FeatureStepDecision, features_agent

    monkeypatch.setattr(
        "agents.features_agent.invoke_structured_robust",
        lambda *args, **kwargs: FeatureStepDecision(
            decision="stop",
            reasoning="Operator instructions followed.",
            destructive_self_assessment=False,
        ),
    )

    update = features_agent(state)
    evs = get_run_events(run_id)
    ack_evs = [e for e in evs if e.get("event") == "operator_modification_acknowledged" or e.get("event_type") == "operator_modification_acknowledged"]
    assert len(ack_evs) >= 1, "features_agent must log operator_modification_acknowledged event"
    assert ack_evs[0].get("modifications") == op_text


def test_modeler_handles_none_task_spec_and_parquet_dataset(tmp_path, monkeypatch):
    """
    Regression test: verify that when ModelStepDecision has task_spec=None,
    modeler_agent does not raise TypeError ('NoneType' object is not subscriptable)
    and that Parquet file paths generate parquet loading instructions.
    """
    parquet_file = tmp_path / "data.parquet"
    parquet_file.write_bytes(b"dummy parquet bytes")
    run_id = f"test_modeler_none_{int(time.time() * 1000)}"
    register_run(run_id, dataset_path=str(parquet_file))

    state = build_initial_state(dataset_path=str(parquet_file), run_id=run_id)
    state["transformed_dataset_path"] = str(parquet_file)
    state["target_column"] = "target"
    state["task_type"] = "classification"
    state["profile"] = {"recommended_metric": "f1"}

    from agents.modeler_agent import ModelStepDecision, modeler_agent

    # First call: continue with task_spec=None; second call: stop
    call_count = 0
    def mock_decide(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return ModelStepDecision(decision="continue", task_spec=None, reasoning="Initial step")
        return ModelStepDecision(decision="stop", reasoning="Done")

    monkeypatch.setattr("agents.modeler_agent.invoke_structured_robust", mock_decide)

    coder_specs_received = []
    def mock_coder(task_spec, **kwargs):
        coder_specs_received.append(task_spec)
        return {
            "success": True,
            "stdout": "RESULT_JSON: {\"model_family\": \"RandomForest\", \"cv_score\": 0.85, \"metric\": \"f1\"}",
            "stderr": "",
            "output_path": str(tmp_path / "model.joblib"),
            "attempts": 1,
        }

    monkeypatch.setattr("agents.modeler_agent.coder_agent", mock_coder)

    # Must complete without throwing TypeError
    update = modeler_agent(state)
    assert update["last_executed_agent"] == "modeler"
    assert len(coder_specs_received) == 1
    # Verify parquet loading instruction was supplied
    assert "pd.read_parquet" in coder_specs_received[0]
    assert update["best_metric"] == 0.85


def test_coder_attempt_1_contains_human_message(tmp_path, monkeypatch):
    """
    Regression test: verify that coder_agent provides a HumanMessage on attempt 1
    so chat LLMs don't return empty completions due to missing user turn.
    """
    from agents.coder_agent import coder_agent
    from langchain_core.messages import HumanMessage, SystemMessage

    captured_messages = []
    def mock_stream_text(llm, messages, **kwargs):
        captured_messages.extend(messages)
        return "import os\nprint('hello')"

    monkeypatch.setattr("agents.coder_agent.stream_text", mock_stream_text)
    monkeypatch.setattr("agents.coder_agent._execute", lambda *args, **kwargs: {
        "success": True, "stdout": "hello", "stderr": "", "output_path": None
    })

    result = coder_agent(
        task_spec="Print hello",
        input_paths={"dataset": "data.csv"},
        output_path="out.json",
        context={},
        max_attempts=1,
    )

    assert result["success"] is True
    has_system = any(isinstance(m, SystemMessage) for m in captured_messages)
    has_human = any(isinstance(m, HumanMessage) for m in captured_messages)
    assert has_system, "coder_agent must provide a SystemMessage"
    assert has_human, "coder_agent must provide a HumanMessage on Attempt 1"

