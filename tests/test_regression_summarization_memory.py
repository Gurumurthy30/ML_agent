"""
Regression tests for Open Memory with Summarization:
1. Executive agents (Supervisor, Judge, Reporter) have open visibility via summarized pipeline state.
2. Token / Size Leak Prevention:
   - open_summary_memory is strictly bounded in characters/tokens.
   - Large raw datasets or long agent histories do not cause context window blowup.
   - Reducer merge_open_summary truncates phase summaries to prevent size leaks.
3. Supervisor routing with Open Summarization Memory.
"""
import pytest
import json
from unittest.mock import patch, MagicMock
from state import build_initial_state
from utils.scoped_memory import merge_open_summary, format_open_memory_digest
from agents.supervisor import graph_node_supervisor, SupervisorDecision
from agents.judge_agent import judge_agent, JudgeVerdict
from agents.reporter_agent import reporter_agent


def test_open_memory_digest_strictly_prevents_size_leaks():
    """Verify format_open_memory_digest bounds the summary length to prevent token leaks."""
    # Simulate a huge, bloated open_summary_memory
    giant_string = "A" * 10000
    huge_summary = {
        "profiler": f"Profiler facts: {giant_string}",
        "eda": f"EDA findings: {giant_string}",
        "features": f"Feature engineering steps: {giant_string}",
        "modeler": f"Modeler candidates: {giant_string}",
        "judge": f"Judge critique: {giant_string}",
    }

    # Reducer truncates each phase
    merged = merge_open_summary({}, huge_summary)
    for k, v in merged.items():
        assert len(v) <= 600, f"Phase {k} exceeded 600 characters"

    # Digest formatting stays strictly under max_chars limit (default 2500)
    digest = format_open_memory_digest(merged, max_chars=2500)
    assert len(digest) <= 2500
    assert "[Profiler]" in digest
    assert "[EDA]" in digest
    assert "[Features]" in digest
    assert "[Modeler]" in digest
    assert "[Judge]" in digest


def test_open_memory_digest_auto_synthesizes_from_state():
    """Verify format_open_memory_digest extracts concise facts from state if summary is empty."""
    state = build_initial_state("test.csv")
    state["profile"] = {
        "rows": 5000,
        "features": [{"name": f"col_{i}"} for i in range(30)],
        "target_column": "target",
        "recommended_metric": "roc_auc",
        "data_quality_flags": ["high_cardinality"],
    }
    state["task_type"] = "classification"
    state["target_column"] = "target"
    state["candidate_models"] = [
        {"model_family": "LightGBM", "cv_score": 0.912},
        {"model_family": "RandomForest", "cv_score": 0.884},
    ]
    state["best_metric"] = 0.912

    digest = format_open_memory_digest({}, state=state)
    assert "[Profiler]: Dataset: 5000 rows x 30 cols" in digest
    assert "Target: 'target'" in digest
    assert "[Modeler]: Trained 2 candidate models" in digest
    assert "Best score: 0.9120" in digest
    assert len(digest) < 1500  # Stays compact


def test_supervisor_routes_with_open_summarization_memory():
    """Verify supervisor passes open summarization memory to LLM without raw state size leak."""
    state = build_initial_state("test.csv")
    state["open_summary_memory"] = {
        "profiler": "Dataset profiled: 1000 rows, 10 cols. Target: churn. Metric: roc_auc.",
        "eda": "Exploration complete. No collinear features found.",
    }
    state["profile"] = {"target_column": "churn"}
    state["eda_findings"] = {"iterations_run": 2}

    captured_prompt = {}

    def mock_invoke(llm, schema, messages, **kwargs):
        captured_prompt["content"] = messages[1].content
        return SupervisorDecision(
            next_agent="features",
            reasoning="EDA is complete; route to feature engineering.",
            task_instructions="Engineer features.",
        )

    with patch("agents.supervisor.invoke_structured_robust", side_effect=mock_invoke), \
         patch("agents.adaptive_controller.adaptive_controller.evaluate_next_action", return_value={"action": "proceed"}):
        res = graph_node_supervisor(state)

    assert res["next_agent"] == "features"
    prompt_text = captured_prompt["content"]
    assert "Pipeline Summary (Open Summarization Memory):" in prompt_text
    assert "[Profiler]: Dataset profiled" in prompt_text
    assert "[EDA]: Exploration complete" in prompt_text
    # Ensure it's not a massive 20,000-char raw json dump
    assert len(prompt_text) < 2000


def test_judge_and_reporter_update_open_summary_memory(tmp_path):
    """Verify judge and reporter populate open_summary_memory with concise verdicts and status."""
    csv_file = tmp_path / "data.csv"
    csv_file.write_text("a,b\n1,0\n2,1\n")
    state = build_initial_state(str(csv_file))
    state["profile"] = {"recommended_metric": "accuracy"}
    state["task_type"] = "classification"
    state["candidate_models"] = [{"model_family": "RandomForest", "cv_score": 0.88}]
    state["best_metric"] = 0.88

    # 1. Judge
    mock_verdict = JudgeVerdict(
        verdict="accept",
        feedback="Model accuracy of 0.88 exceeds baseline.",
        reasoning="Acceptable performance.",
    )
    with patch("agents.judge_agent.invoke_structured_robust", return_value=mock_verdict):
        judge_res = judge_agent(state)

    assert "open_summary_memory" in judge_res
    assert "judge" in judge_res["open_summary_memory"]
    assert "accept" in judge_res["open_summary_memory"]["judge"]

    # 2. Reporter
    state_for_reporter = {**state, **judge_res}
    with patch("agents.reporter_agent.stream_text", return_value="Final Executive Report Content"):
        reporter_res = reporter_agent(state_for_reporter)

    assert "open_summary_memory" in reporter_res
    assert "reporter" in reporter_res["open_summary_memory"]
    assert "Final report generated" in reporter_res["open_summary_memory"]["reporter"]
