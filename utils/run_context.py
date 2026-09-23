"""
Authoritative Run Context & Leakage Detection Module.

Enforces pipeline-wide single source of truth for:
  - target_column: explicitly provided target column name
  - exclude_columns: label-duplicate / ID columns to exclude
  - feature_columns: all remaining valid predictor columns

Provides:
  - detect_label_duplicate_columns(df, target_col): flags 1:1 bijective encodings of target
  - format_run_context(target_column, exclude_columns, feature_columns): builds authoritative prompt block
  - sync_run_context_env(target_column, exclude_columns): exports TARGET_COLUMN and EXCLUDE_COLUMNS to os.environ
"""
import os
import json
from typing import List, Optional
import pandas as pd


def detect_label_duplicate_columns(df: pd.DataFrame, target_col: Optional[str]) -> List[str]:
    """
    Flag columns that are a 1:1 encoding of the target (leakage risk).
    For example, in Iris CSV where target is integer 0, 1, 2 and species is
    'setosa', 'versicolor', 'virginica', this returns ['species'] automatically.
    """
    if not target_col or target_col not in df.columns:
        return []

    suspects = []
    target_nunique = df[target_col].nunique(dropna=False)
    if target_nunique <= 1:
        return []

    for col in df.columns:
        if col == target_col:
            continue
        if df[col].nunique(dropna=False) != target_nunique:
            continue
        # Bijective check: each value of col maps to exactly one target value
        try:
            mapping = df.groupby(col, dropna=False)[target_col].nunique(dropna=False)
            if (mapping == 1).all():
                suspects.append(col)
        except Exception:
            continue

    return suspects


def format_run_context(
    target_column: Optional[str],
    exclude_columns: Optional[List[str]] = None,
    feature_columns: Optional[List[str]] = None,
) -> str:
    """
    Build the authoritative RUN CONTEXT block injected into every agent's system prompt.
    """
    target_str = target_column or ""
    clean_excludes = [str(c).strip() for c in (exclude_columns or []) if str(c).strip()]
    clean_features = [str(c).strip() for c in (feature_columns or []) if str(c).strip()]

    return f"""RUN CONTEXT (authoritative — do not re-derive):
- target_column: "{target_str}"
- exclude_columns: {clean_excludes}   # label-duplicate / ID columns, never usable as features
- feature_columns: {clean_features}   # = all columns minus target_column minus exclude_columns

RULES FOR ALL GENERATED CODE:
1. Always load target_column and exclude_columns from the environment variables
   TARGET_COLUMN and EXCLUDE_COLUMNS (comma-separated) — never hardcode "target"
   or re-detect the target column yourself.
2. Before building X, drop BOTH target_column and every column in exclude_columns:
       target_col = os.environ.get("TARGET_COLUMN", "target")
       exclude_cols = [c.strip() for c in os.environ.get("EXCLUDE_COLUMNS", "").split(",") if c.strip()]
       X = df.drop(columns=[c for c in [target_col] + exclude_cols if c in df.columns])
3. Never include exclude_columns in correlation matrices, feature importance,
   or model inputs of any kind — they exist only for reference/EDA labeling.
4. If a new column is discovered during your step that appears to be a
   near-duplicate of target_column (e.g. same cardinality, 1:1 mapping),
   do not silently use it as a feature — report it back as a flag instead."""


def sync_run_context_env(
    target_column: Optional[str],
    exclude_columns: Optional[List[str]] = None,
) -> None:
    """
    Synchronizes the authoritative target_column and exclude_columns to the OS environment.
    """
    if target_column:
        os.environ["TARGET_COLUMN"] = str(target_column).strip()
    if exclude_columns is not None:
        clean_excludes = [str(c).strip() for c in exclude_columns if str(c).strip()]
        os.environ["EXCLUDE_COLUMNS"] = ",".join(clean_excludes)
