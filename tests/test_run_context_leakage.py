"""
Unit tests for Run Context injection, Leakage Detection, and Convergence at 1.0.
"""
import os
import pandas as pd
import pytest
from utils.run_context import detect_label_duplicate_columns, format_run_context, sync_run_context_env
from state import build_initial_state
from agents.judge_agent import judge_agent
from agents.modeler_agent import modeler_agent


def test_detect_label_duplicate_columns_iris_style():
    # Synthetic Iris-like DataFrame
    df = pd.DataFrame({
        "sepal_length": [5.1, 4.9, 7.0, 6.4, 6.3, 5.8],
        "sepal_width": [3.5, 3.0, 3.2, 3.2, 3.3, 2.7],
        "species": ["setosa", "setosa", "versicolor", "versicolor", "virginica", "virginica"],
        "target": [0, 0, 1, 1, 2, 2],
    })

    suspects = detect_label_duplicate_columns(df, "target")
    assert suspects == ["species"], f"Expected ['species'], got {suspects}"

    # Non-leaking column should not be flagged
    no_suspects = detect_label_duplicate_columns(df, "sepal_length")
    assert "species" not in no_suspects
    assert "target" not in no_suspects


def test_detect_label_duplicate_columns_no_leakage():
    df = pd.DataFrame({
        "feat_a": [1.0, 2.0, 3.0, 4.0, 5.0],
        "feat_b": ["x", "y", "z", "w", "v"],
        "target": [0, 1, 0, 1, 0],
    })
    # feat_b has 5 unique, target has 2 unique -> cannot be 1:1 duplicate
    suspects = detect_label_duplicate_columns(df, "target")
    assert suspects == []


def test_format_run_context():
    block = format_run_context("target", ["species", "id"], ["feat1", "feat2"])
    assert 'target_column: "target"' in block
    assert "exclude_columns: ['species', 'id']" in block
    assert "feature_columns: ['feat1', 'feat2']" in block
    assert "TARGET_COLUMN and EXCLUDE_COLUMNS" in block
    assert "X = df.drop(columns=" in block


def test_sync_run_context_env():
    sync_run_context_env("label_col", ["col_a", "col_b"])
    assert os.environ["TARGET_COLUMN"] == "label_col"
    assert os.environ["EXCLUDE_COLUMNS"] == "col_a,col_b"


def test_judge_immediate_acceptance_at_perfect_score():
    state = build_initial_state("test.csv")
    state["best_metric"] = 1.0
    state["candidate_models"] = [{"model_family": "RandomForest", "cv_score": 1.0}]
    state["task_type"] = "classification"

    result = judge_agent(state)
    assert result["last_verdict"] == "accept"
    assert "maximum" in result["judge_feedback"][0].lower() or "perfect" in result["judge_feedback"][0].lower()


def test_dataset_inspect_endpoint(tmp_path):
    from fastapi.testclient import TestClient
    from api.main import app

    csv_path = tmp_path / "iris_leak.csv"
    df = pd.DataFrame({
        "sepal_length": [5.1, 4.9, 7.0, 6.4, 6.3, 5.8],
        "species": ["setosa", "setosa", "versicolor", "versicolor", "virginica", "virginica"],
        "target": [0, 0, 1, 1, 2, 2],
    })
    df.to_csv(csv_path, index=False)

    client = TestClient(app)
    response = client.post("/datasets/inspect", json={
        "dataset_path": str(csv_path),
        "target_column": "target",
    })
    assert response.status_code == 200
    data = response.json()
    assert data["rows"] == 6
    assert data["columns"] == ["sepal_length", "species", "target"]
    assert data["leakage_candidates"] == ["species"]

