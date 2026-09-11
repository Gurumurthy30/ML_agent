"""
tests/test_multi_metric.py — Multi-metric and Direction-Aware Evaluation Tests
"""

import pytest
from session.init import get_metric_direction, _auto_pick_metric
from agents.selector import check_plateau_and_variance, _select_best_exp, _format_exp_metrics
from tools.local_env_mcp.server import LocalEnvMCP


def test_metric_direction_mapping():
    assert get_metric_direction("rmse") == "minimize"
    assert get_metric_direction("mae") == "minimize"
    assert get_metric_direction("log_loss") == "minimize"
    assert get_metric_direction("mse") == "minimize"
    assert get_metric_direction("roc_auc") == "maximize"
    assert get_metric_direction("f1") == "maximize"
    assert get_metric_direction("accuracy") == "maximize"
    assert get_metric_direction("r2") == "maximize"
    assert get_metric_direction("unknown_metric") == "maximize"


def test_session_init_auto_pick_metric():
    metric, direction = _auto_pick_metric("regression", "train a regression model")
    assert metric == "rmse"
    assert direction == "minimize"

    metric, direction = _auto_pick_metric("binary_classification", "predict the target column with roc_auc")
    assert metric == "roc_auc"
    assert direction == "maximize"

    metric, direction = _auto_pick_metric("binary_classification", "predict outcome")
    assert metric == "roc_auc"
    assert direction == "maximize"


def test_select_best_exp_direction():
    entries = [
        {"experiment_id": "exp_001", "cv_mean": 0.45, "status": "success"},
        {"experiment_id": "exp_002", "cv_mean": 0.12, "status": "success"},
        {"experiment_id": "exp_003", "cv_mean": 0.88, "status": "success"},
    ]
    # Minimize should choose exp_002 (lowest error)
    best_min = _select_best_exp(entries, direction="minimize")
    assert best_min["experiment_id"] == "exp_002"
    assert best_min["cv_mean"] == 0.12

    # Maximize should choose exp_003 (highest score)
    best_max = _select_best_exp(entries, direction="maximize")
    assert best_max["experiment_id"] == "exp_003"
    assert best_max["cv_mean"] == 0.88


def test_format_exp_metrics():
    exp = {
        "experiment_id": "exp_001",
        "primary_metric": "rmse",
        "cv_mean": 0.1234,
        "metrics": {"rmse": 0.1234, "mae": 0.0987, "r2": 0.8543}
    }
    s = _format_exp_metrics(exp)
    assert "rmse: 0.1234" in s
    assert "mae: 0.0987" in s
    assert "r2: 0.8543" in s


def test_check_plateau_and_variance_minimize_worse_than_baseline():
    entries = [
        {"experiment_id": "exp_001", "cv_mean": 0.20, "cv_std": 0.01, "status": "success", "primary_metric_direction": "minimize"},
        {"experiment_id": "exp_002", "cv_mean": 0.25, "cv_std": 0.01, "status": "success", "primary_metric_direction": "minimize"},
    ]
    # In minimization, 0.25 > 0.20 + 0.01, so exp_002 is worse than baseline
    res = check_plateau_and_variance(entries, direction="minimize")
    assert res["status"] == "redirect"
    assert res["reason"] == "worse_than_baseline"


def test_check_plateau_and_variance_maximize_worse_than_baseline():
    entries = [
        {"experiment_id": "exp_001", "cv_mean": 0.85, "cv_std": 0.01, "status": "success", "primary_metric_direction": "maximize"},
        {"experiment_id": "exp_002", "cv_mean": 0.80, "cv_std": 0.01, "status": "success", "primary_metric_direction": "maximize"},
    ]
    # In maximization, 0.80 < 0.85 - 0.01, so exp_002 is worse than baseline
    res = check_plateau_and_variance(entries, direction="maximize")
    assert res["status"] == "redirect"
    assert res["reason"] == "worse_than_baseline"


def test_check_plateau_and_variance_near_tied_minimize():
    entries = [
        {"experiment_id": "exp_001", "cv_mean": 0.1205, "cv_std": 0.01, "status": "success", "model_type": "LightGBM"},
        {"experiment_id": "exp_002", "cv_mean": 0.1209, "cv_std": 0.01, "status": "success", "model_type": "XGBoost"},
    ]
    res = check_plateau_and_variance(entries, direction="minimize")
    assert res["status"] == "redirect"
    assert res["reason"] == "near_tied"


def test_parse_cv_metrics_json():
    mcp = LocalEnvMCP(session_id="test_session", dry_run=True)
    stdout = """
    Training fold 1...
    Training fold 2...
    CV_RESULT: {"cv_mean": 0.1425, "cv_std": 0.0031, "metrics": {"rmse": 0.1425, "mae": 0.1012, "r2": 0.892}}
    Done.
    """
    mean, std, metrics = mcp._parse_cv_metrics(stdout)
    assert mean == 0.1425
    assert std == 0.0031
    assert metrics["rmse"] == 0.1425
    assert metrics["mae"] == 0.1012
    assert metrics["r2"] == 0.892


def test_parse_cv_metrics_regex_fallback():
    mcp = LocalEnvMCP(session_id="test_session", dry_run=True)
    stdout = "Model finished. CV_MEAN=0.8765 CV_STD=0.0123"
    mean, std, metrics = mcp._parse_cv_metrics(stdout)
    assert mean == 0.8765
    assert std == 0.0123
    assert metrics == {"primary": 0.8765}


def test_local_env_mcp_dry_run_returns_metrics():
    mcp = LocalEnvMCP(session_id="test_session", dry_run=True)
    res = mcp.execute_code("print('hello')")
    assert res["status"] == "success"
    assert "metrics" in res
    assert isinstance(res["metrics"], dict)
    assert len(res["metrics"]) > 0
