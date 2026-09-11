"""
agents/data_explorer.py — Data Explorer Agent (minimal skeleton)

Loads the dataset, computes basic EDA stats, and enriches the task context.
Purely deterministic — no LLM call.
"""

from pathlib import Path
from typing import Dict, Any, Optional

import pandas as pd

from graph.state import AgentState
from agents.utils import push_event


def _load_csv(data_dir: str) -> Optional[pd.DataFrame]:
    """Finds and loads the first CSV file from the data directory."""
    path = Path(data_dir)
    if not path.exists():
        return None
    for name in ["train.csv", "data.csv", "dataset.csv"]:
        f = path / name
        if f.exists():
            return pd.read_csv(f)
    # Fallback: first CSV found
    csvs = list(path.glob("*.csv"))
    return pd.read_csv(csvs[0]) if csvs else None


def _basic_stats(df: pd.DataFrame, target_column: str) -> Dict[str, Any]:
    """Computes minimal EDA: shape, missing values, class balance."""
    stats: Dict[str, Any] = {
        "shape": list(df.shape),
        "columns": list(df.columns),
        "missing_values_flag": bool(df.isnull().any().any()),
    }

    # Class balance (for classification targets)
    if target_column in df.columns:
        counts = df[target_column].value_counts()
        proportions = df[target_column].value_counts(normalize=True)
        minority = float(proportions.min()) if len(proportions) else 1.0
        stats["class_balance"] = {
            "counts": {str(k): int(v) for k, v in counts.items()},
            "is_imbalanced": minority < 0.2,
        }

    return stats


def data_explorer_node(state: AgentState) -> AgentState:
    """
    Data Explorer Agent: loads data and computes basic stats.

    Flow: load CSV → compute stats → enrich task_context → set state
    """
    task_ctx = state.get("task_context", {})
    target_column = task_ctx.get("target_column", "target")
    session_data_dir = state.get("session_data_dir", task_ctx.get("session_data_dir", ""))

    # Load dataset
    df = _load_csv(session_data_dir)

    eda_summary = {}
    if df is not None:
        eda_summary = _basic_stats(df, target_column)
        print(f"[DataExplorer] Loaded {df.shape[0]} rows × {df.shape[1]} cols")
    else:
        eda_summary["note"] = "No dataset found."
        print(f"[DataExplorer] No dataset found in {session_data_dir}")

    # TODO: add more EDA (correlations, outliers, etc.) as needed
    # TODO: generate markdown report for UI

    # Enrich task context
    state["task_context"] = {
        **task_ctx,
        "eda_summary": eda_summary,
        "train_shape": eda_summary.get("shape", [0, 0]),
    }
    state["status"] = "planning"
    return state