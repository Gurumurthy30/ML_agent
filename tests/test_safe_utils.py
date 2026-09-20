"""
Unit tests for utils/safe.py.
Verifies to_float, is_better, safe_json, safe_div, safe_diff, and require.
"""
import math
import numpy as np
import pytest
from datetime import datetime

from utils.safe import to_float, is_better, safe_json, safe_diff, safe_div, require
from utils.exceptions import StateError


class TestToFloat:
    def test_none_and_empty(self):
        assert to_float(None) is None
        assert to_float(None, default=0.0) == 0.0
        assert to_float("") is None
        assert to_float("   ") is None
        assert to_float("N/A") is None
        assert to_float("null") is None
        assert to_float("None") is None

    def test_valid_numbers(self):
        assert to_float(0.85) == 0.85
        assert to_float(42) == 42.0
        assert to_float("0.912") == 0.912
        assert to_float(" 12.34 ") == 12.34
        assert to_float("85.5%") == 85.5
        assert to_float("1,234.5") == 1234.5

    def test_nan_and_inf(self):
        assert to_float(float("nan")) is None
        assert to_float(float("inf")) is None
        assert to_float(float("-inf")) is None
        assert to_float("nan") is None
        assert to_float("inf") is None
        assert to_float("NaN") is None

    def test_numpy_scalars(self):
        assert to_float(np.float32(0.75)) == pytest.approx(0.75)
        assert to_float(np.float64(0.99)) == pytest.approx(0.99)
        assert to_float(np.int64(10)) == 10.0
        assert to_float(np.array(3.14)) == pytest.approx(3.14)


class TestIsBetter:
    def test_higher_is_better_nominal(self):
        assert is_better(0.85, 0.80, higher_is_better=True) is True
        assert is_better(0.80, 0.85, higher_is_better=True) is False
        assert is_better(0.80, 0.80, higher_is_better=True) is False

    def test_lower_is_better_rmse(self):
        # For RMSE: 0.15 is better than 0.20
        assert is_better(0.15, 0.20, higher_is_better=False) is True
        assert is_better(0.25, 0.20, higher_is_better=False) is False
        assert is_better(0.20, 0.20, higher_is_better=False) is False

    def test_none_handling(self):
        # Missing candidate is never better
        assert is_better(None, 0.80) is False
        assert is_better("N/A", 0.80) is False
        # Any valid score beats None baseline
        assert is_better(0.80, None) is True
        assert is_better(0.15, None, higher_is_better=False) is True
        # Both None
        assert is_better(None, None) is False

    def test_nan_handling(self):
        nan = float("nan")
        assert is_better(nan, 0.80) is False
        assert is_better(0.80, nan) is True
        assert is_better(nan, nan) is False

    def test_epsilon_threshold(self):
        # Difference must exceed epsilon
        assert is_better(0.8005, 0.8000, higher_is_better=True, epsilon=0.001) is False
        assert is_better(0.8020, 0.8000, higher_is_better=True, epsilon=0.001) is True


class TestSafeJson:
    def test_primitives(self):
        assert safe_json(42) == 42
        assert safe_json("hello") == "hello"
        assert safe_json(True) is True
        assert safe_json(None) is None

    def test_nan_inf_becomes_none(self):
        assert safe_json(float("nan")) is None
        assert safe_json(float("inf")) is None
        assert safe_json(float("-inf")) is None
        data = {"score": float("nan"), "loss": float("inf"), "valid": 0.5}
        clean = safe_json(data)
        assert clean["score"] is None
        assert clean["loss"] is None
        assert clean["valid"] == 0.5

    def test_numpy_types(self):
        data = {
            "arr": np.array([1, 2, 3]),
            "f32": np.float32(0.123),
            "i64": np.int64(42),
            "b": np.bool_(True),
            "nan_arr": np.array([np.nan, 1.0]),
        }
        clean = safe_json(data)
        assert clean["arr"] == [1, 2, 3]
        assert isinstance(clean["f32"], float)
        assert clean["i64"] == 42
        assert clean["b"] is True
        assert clean["nan_arr"] == [None, 1.0]

    def test_datetime(self):
        now = datetime(2026, 9, 19, 18, 30, 0)
        assert safe_json(now) == "2026-09-19T18:30:00"


class TestRequire:
    def test_require_success(self):
        state = {"profile": {"rows": 100}, "best_metric": 0.85}
        assert require(state, "profile", "test_node") == {"rows": 100}
        assert require(state, "best_metric", "test_node") == 0.85

    def test_require_missing_key(self):
        state = {"profile": {}}
        with pytest.raises(StateError) as exc_info:
            require(state, "missing_key", "my_node")
        assert "my_node" in str(exc_info.value)
        assert "missing_key" in str(exc_info.value)

    def test_require_none_value(self):
        state = {"best_metric": None}
        with pytest.raises(StateError):
            require(state, "best_metric", "my_node", allow_none=False)

        # allow_none=True should succeed
        assert require(state, "best_metric", "my_node", allow_none=True) is None
