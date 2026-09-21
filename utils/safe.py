"""
utils.safe — Defensive, fault-tolerant numeric normalization, comparison,
and JSON sanitization primitives.

All cross-boundary metric comparisons, coercions, and JSON emissions
MUST route through this module to guarantee:
1. No TypeError from None or NaN comparisons.
2. No JSON.parse crashes from NaN/Infinity or numpy types in SSE/API.
3. Explicit metric direction semantics (higher-is-better vs lower-is-better).
"""
import math
from datetime import date, datetime, time
from typing import Any, Optional, Union

from utils.exceptions import StateError

try:
    import numpy as np
    _HAS_NUMPY = True
except ImportError:
    _HAS_NUMPY = False


def to_float(value: Any, default: Optional[float] = None, allow_nan: bool = False) -> Optional[float]:
    """
    Safely convert an arbitrary value to a Python float.
    Handles:
      - None, empty string, "N/A", "none", "null" -> default
      - Strings like " 0.85 ", "0.85%", "1,234.56"
      - numpy scalars (float32, float64, int64, etc.)
      - NaN and Inf -> default (unless allow_nan is explicitly True)
    """
    if value is None:
        return default

    # Handle numpy scalars
    if _HAS_NUMPY:
        if isinstance(value, (np.floating, np.integer)):
            value = value.item()
        elif isinstance(value, np.ndarray) and value.size == 1:
            value = value.item()

    if isinstance(value, (int, float)):
        try:
            val_float = float(value)
            if not allow_nan and (math.isnan(val_float) or math.isinf(val_float)):
                return default
            return val_float
        except (ValueError, OverflowError):
            return default

    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned or cleaned.lower() in ("none", "null", "n/a", "na"):
            return default
        if not allow_nan and cleaned.lower() in ("nan", "inf", "-inf"):
            return default
        # Strip trailing % or currency/comma
        cleaned = cleaned.rstrip("%").replace(",", "")
        try:
            val_float = float(cleaned)
            if not allow_nan and (math.isnan(val_float) or math.isinf(val_float)):
                return default
            return val_float
        except (ValueError, OverflowError):
            return default

    # Fallback attempt
    try:
        val_float = float(value)
        if math.isnan(val_float) or math.isinf(val_float):
            return default
        return val_float
    except (TypeError, ValueError, OverflowError):
        return default


def is_better(
    new_val: Any,
    best_val: Any,
    higher_is_better: bool = True,
    epsilon: float = 0.0,
) -> bool:
    """
    None-safe, NaN-safe metric comparison that strictly respects metric direction.

    Rules:
      1. If new_val cannot be coerced to a finite float -> False (a missing/broken metric is never better).
      2. If best_val cannot be coerced to a finite float -> True (any valid metric beats missing/NaN baseline).
      3. If higher_is_better is True:
           returns (new_float - best_float) > epsilon
      4. If higher_is_better is False (e.g. RMSE, MSE, MAE, loss):
           returns (best_float - new_float) > epsilon
    """
    new_f = to_float(new_val)
    if new_f is None:
        return False

    best_f = to_float(best_val)
    if best_f is None:
        return True

    diff = (new_f - best_f) if higher_is_better else (best_f - new_f)
    return diff > epsilon


def safe_diff(
    new_val: Any,
    old_val: Any,
    higher_is_better: bool = True,
    default: float = 0.0,
) -> float:
    """
    Safely compute delta between two metrics without throwing TypeError or returning NaN.
    Positive delta always signifies improvement if higher_is_better logic is aligned,
    or raw difference if higher_is_better is standard.
    """
    new_f = to_float(new_val)
    old_f = to_float(old_val)
    if new_f is None or old_f is None:
        return default

    return round(new_f - old_f, 6)


def safe_round(value: Any, digits: int = 4, default: Any = "—") -> Any:
    """Safely round a numeric value. If None or NaN, returns default."""
    val_f = to_float(value)
    if val_f is None:
        return default
    return round(val_f, digits)


def safe_div(numerator: Any, denominator: Any, default: float = 0.0) -> float:
    """Safely divide two numbers, guarding against ZeroDivisionError and empty collections."""
    num_f = to_float(numerator, default=0.0)
    den_f = to_float(denominator, default=0.0)
    if den_f == 0.0:
        return default
    return float(num_f / den_f)


def safe_json(obj: Any) -> Any:
    """
    Recursively sanitize an object for strict JSON serialization:
      - Numpy arrays -> list
      - Numpy scalars -> int, float, bool
      - NaN / Infinity -> None (becomes JSON null, preventing JS syntax error)
      - Datetime / date / time -> ISO 8601 string
      - Sets / tuples -> list
      - Dicts -> keys to str, values sanitized recursively
      - Pydantic models -> model_dump() then sanitized
      - Unknown objects -> repr(obj) or str(obj)
    Never raises an exception; guaranteed to produce JSON-serializable structures.
    """
    if obj is None:
        return None

    # Handle Pydantic models
    try:
        from pydantic import BaseModel
        if isinstance(obj, BaseModel):
            return safe_json(obj.model_dump())
    except Exception:
        pass

    # Handle Numpy types
    if _HAS_NUMPY:
        if isinstance(obj, np.ndarray):
            return [safe_json(x) for x in obj.tolist()]
        if isinstance(obj, np.bool_):
            return bool(obj)
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            val = float(obj)
            return None if (math.isnan(val) or math.isinf(val)) else val

    # Primitive floats (check NaN/inf)
    if isinstance(obj, float):
        return None if (math.isnan(obj) or math.isinf(obj)) else obj

    # Ints, strings, booleans
    if isinstance(obj, (int, str, bool)):
        return obj

    # Datetimes
    if isinstance(obj, (datetime, date, time)):
        return obj.isoformat()

    # Collections
    if isinstance(obj, dict):
        return {str(k): safe_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [safe_json(x) for x in obj]

    # Fallback to string repr
    try:
        return str(obj)
    except Exception:
        return repr(obj)


def require(state: dict, key: str, node_name: str, allow_none: bool = False) -> Any:
    """
    Assert that a required key exists in state and is non-None.
    Raises StateError with explicit node and key context instead of
    letting downstream code crash with NoneType or KeyError.
    """
    if not isinstance(state, dict):
        raise StateError(key=key, node=node_name, message=f"Node '{node_name}' expected dict state, got {type(state)}")

    if key not in state:
        raise StateError(
            key=key,
            node=node_name,
            message=f"Node '{node_name}' requires state key '{key}', but it was not found in state."
        )

    val = state[key]
    if val is None and not allow_none:
        raise StateError(
            key=key,
            node=node_name,
            message=f"Node '{node_name}' requires non-None state key '{key}', but value is None."
        )

    return val
