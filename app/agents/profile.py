import json
from pathlib import Path
from typing import Any
import pandas as pd
import numpy as np

from app.core.state import ProjectState, TaskType, ProfileSummary, ColumnProfile
from app.tools.registry import ToolRegistry
from app.config import PROJECTS_DIR


def profile_dataset(state: ProjectState, registry: ToolRegistry) -> dict[str, Any]:
    """Deterministic, plain Python dataset profiling node (NO LLM call)."""
    project_id = state["project_id"]
    tools = registry.get_tools_for_role("profile")
    dataset_version = state.get("dataset_version", "dataset_v1")

    # Load dataset
    df: pd.DataFrame = tools.dataset.load_dataset(dataset_version)
    target_col = state.get("target_column")

    row_count, col_count = df.shape
    duplicates_count = int(df.duplicated().sum())
    total_cells = row_count * col_count
    total_missing = int(df.isna().sum().sum())
    missing_total_pct = round((total_missing / total_cells * 100) if total_cells > 0 else 0.0, 2)

    columns_profile: list[ColumnProfile] = []
    for col in df.columns:
        series = df[col]
        missing_cnt = int(series.isna().sum())
        missing_pct = round((missing_cnt / row_count * 100) if row_count > 0 else 0.0, 2)
        n_unique = int(series.nunique(dropna=True))
        is_const = bool(n_unique <= 1)
        samples = series.dropna().head(3).tolist()

        columns_profile.append(
            ColumnProfile(
                name=col,
                dtype=str(series.dtype),
                missing_count=missing_cnt,
                missing_pct=missing_pct,
                unique_count=n_unique,
                is_constant=is_const,
                sample_values=samples,
            )
        )

    # Analyze target column & guess task type
    task_guess = TaskType.AMBIGUOUS
    target_dist: dict[str, Any] = {}
    notes = []

    if target_col and target_col in df.columns:
        t_series = df[target_col].dropna()
        t_unique = int(t_series.nunique())

        if t_unique == 2:
            task_guess = TaskType.BINARY_CLASSIFICATION
            val_counts = t_series.value_counts().to_dict()
            target_dist = {str(k): int(v) for k, v in val_counts.items()}
            notes.append(f"Target '{target_col}' has exactly 2 unique values: Binary Classification detected.")
        elif 2 < t_unique <= 20 and (t_series.dtype == "object" or pd.api.types.is_categorical_dtype(t_series) or pd.api.types.is_integer_dtype(t_series)):
            task_guess = TaskType.MULTICLASS_CLASSIFICATION
            val_counts = t_series.value_counts().head(20).to_dict()
            target_dist = {str(k): int(v) for k, v in val_counts.items()}
            notes.append(f"Target '{target_col}' has {t_unique} unique discrete values: Multiclass Classification detected.")
        elif pd.api.types.is_numeric_dtype(t_series) and t_unique > 20:
            task_guess = TaskType.REGRESSION
            target_dist = {
                "min": float(t_series.min()),
                "max": float(t_series.max()),
                "mean": float(round(t_series.mean(), 4)),
                "std": float(round(t_series.std(), 4)),
                "median": float(round(t_series.median(), 4)),
            }
            notes.append(f"Target '{target_col}' is continuous numeric with {t_unique} unique values: Regression detected.")
        else:
            task_guess = TaskType.AMBIGUOUS
            notes.append(f"Target '{target_col}' could not be definitively classified.")
    else:
        notes.append("No valid target column found in dataset.")

    profile_summary = ProfileSummary(
        row_count=row_count,
        column_count=col_count,
        columns=columns_profile,
        target_column=target_col,
        task_type_guess=task_guess,
        duplicates_count=duplicates_count,
        missing_total_pct=missing_total_pct,
        target_distribution=target_dist,
        notes=notes,
    )

    # Save artifacts on disk
    profile_dir = PROJECTS_DIR / project_id / "profile"
    profile_dir.mkdir(parents=True, exist_ok=True)
    json_path = profile_dir / "profile.json"
    summary_md_path = profile_dir / "summary.md"

    summary_dict = profile_summary.model_dump()
    tools.files.write_file("profile/profile.json", json.dumps(summary_dict, indent=2))

    # Generate Markdown Summary (NO plots)
    md_lines = [
        f"# Dataset Profile: Project `{project_id}`",
        f"- **Rows:** {row_count}",
        f"- **Columns:** {col_count}",
        f"- **Duplicates:** {duplicates_count}",
        f"- **Total Missing Cells:** {missing_total_pct}%",
        f"- **Guessed Task Type:** `{task_guess.value}`",
        f"- **Target Column:** `{target_col}`",
        "",
        "## Target Distribution",
        json.dumps(target_dist, indent=2),
        "",
        "## Columns Overview",
        "| Column | Dtype | Missing Count | Missing % | Unique Count | Constant? |",
        "|---|---|---|---|---|---|",
    ]
    for col in columns_profile:
        md_lines.append(
            f"| {col.name} | {col.dtype} | {col.missing_count} | {col.missing_pct}% | {col.unique_count} | {col.is_constant} |"
        )

    tools.files.write_file("profile/summary.md", "\n".join(md_lines))

    # Register artifacts
    art_json = tools.artifacts.register_artifact(
        project_id=project_id,
        artifact_type="profile_json",
        path=str(json_path),
        run_id=state.get("run_id"),
        version=dataset_version,
    )
    art_md = tools.artifacts.register_artifact(
        project_id=project_id,
        artifact_type="profile_summary_md",
        path=str(summary_md_path),
        run_id=state.get("run_id"),
        version=dataset_version,
    )

    artifacts_list = list(state.get("artifacts", []))
    artifacts_list.extend([art_json, art_md])

    # If task_type is not locked in state, use profile guess
    assigned_task_type = state.get("task_type") or task_guess

    return {
        "profile_summary": summary_dict,
        "task_type": assigned_task_type,
        "current_stage": "profile",
        "artifacts": artifacts_list,
        "status": "SUCCESS",
    }
