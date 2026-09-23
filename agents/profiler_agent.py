"""
Profiler does NOT use the Coder sub-agent — it's explicitly low-stakes enough to
hand-code. Ground-truth stats computed in pandas; LLM only interprets/flags, never
invents numbers.

Modality detection (new): Kaggle-style CV/NLP/audio tasks are still delivered as a
table — a CSV with columns that are image/audio *file paths*, or columns of raw free
text, alongside ordinary numeric/categorical columns. Rather than requiring a whole
separate ingestion path per modality, the Profiler flags each column's modality here;
everything downstream (Coder's prompts, EDA/Features/Modeler) reads that flag out of
`profile["features"][*]["modality"]` and reacts accordingly, while Features' existing
structural-diff hard-block keeps working unchanged since the table (paths + labels)
is still what's being diffed, not decoded pixels/audio.
"""
import os
import json
from typing import Optional, Dict, Any, List
import pandas as pd
from tools.llm import get_llm
from langchain_core.messages import SystemMessage, HumanMessage

from state import AgentState
from tools.streaming import stream_text
from tools.logger import get_logger, log_event, step_timer
from utils.safe import safe_round, safe_json
from utils.exceptions import LLMParseError

_make_llm = get_llm

_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tiff", ".webp")
_AUDIO_EXTS = (".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aac")
_FREE_TEXT_MIN_WORDS = 8          # average word count above this suggests prose, not a label
_FREE_TEXT_MIN_UNIQUE_RATIO = 0.5  # most rows distinct suggests free text, not categorical


def load_dataset(dataset_path: str) -> pd.DataFrame:
    if dataset_path.endswith(".csv"):
        return pd.read_csv(dataset_path)
    elif dataset_path.endswith((".parquet", ".pq")):
        return pd.read_parquet(dataset_path)
    raise ValueError(f"Unsupported dataset format: {dataset_path}")


def _path_extension_hit_rate(series: pd.Series, extensions: tuple) -> float:
    sample = series.dropna().astype(str).head(200)
    if sample.empty:
        return 0.0
    hits = sample.str.lower().str.endswith(extensions)
    return float(hits.mean())


def _looks_like_free_text(series: pd.Series) -> bool:
    sample = series.dropna().astype(str).head(500)
    if sample.empty:
        return False
    avg_words = sample.str.split().map(len).mean()
    unique_ratio = sample.nunique() / len(sample)
    return avg_words >= _FREE_TEXT_MIN_WORDS and unique_ratio >= _FREE_TEXT_MIN_UNIQUE_RATIO


def _detect_modality(series: pd.Series, is_numeric: bool) -> str:
    """Best-effort column-modality detection for Kaggle-style tables. Falls back to
    the plain numerical/categorical split when nothing more specific matches."""
    if is_numeric:
        return "numerical"
    if _path_extension_hit_rate(series, _IMAGE_EXTS) >= 0.5:
        return "image_path"
    if _path_extension_hit_rate(series, _AUDIO_EXTS) >= 0.5:
        return "audio_path"
    if _looks_like_free_text(series):
        return "free_text"
    return "categorical"


def compute_data_profile(df: pd.DataFrame, target_column: str = None) -> dict:
    profile = {"rows": len(df), "columns": len(df.columns),
               "target_column": target_column, "features": []}
    modality_counts = {}

    for col in df.columns:
        series = df[col]
        is_numeric = pd.api.types.is_numeric_dtype(series)
        modality = _detect_modality(series, is_numeric)
        modality_counts[modality] = modality_counts.get(modality, 0) + 1

        feature = {
            "name": col,
            "type": "numerical" if is_numeric else "categorical",
            "modality": modality,
            "null_count": int(series.isnull().sum()),
            "null_pct": safe_round(series.isnull().mean() * 100, 2, default=0.0),
            "cardinality": int(series.nunique()),
        }
        if is_numeric and len(series.dropna()) > 0:
            q1, q3 = series.quantile(0.25), series.quantile(0.75)
            iqr = q3 - q1
            lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
            feature["outliers"] = int(((series < lower) | (series > upper)).sum())
            feature["mean"] = safe_round(series.mean(), 3, default=None)
            feature["std"] = safe_round(series.std(), 3, default=None)
        elif modality == "free_text":
            word_counts = series.dropna().astype(str).str.split().map(len)
            feature["avg_word_count"] = safe_round(float(word_counts.mean()), 1, default=0.0) if len(word_counts) else 0
        profile["features"].append(feature)

    non_tabular = {k: v for k, v in modality_counts.items()
                   if k in ("image_path", "audio_path", "free_text")}
    profile["modality_summary"] = modality_counts
    profile["detected_modalities"] = (
        sorted(non_tabular.keys()) if non_tabular else ["tabular"]
    )
    return safe_json(profile)


def _parse_json(text: str) -> Optional[dict]:
    clean = (text or "").strip()
    if clean.startswith("```json"):
        clean = clean[7:]
    elif clean.startswith("```"):
        clean = clean[3:]
    if clean.endswith("```"):
        clean = clean[:-3]
    clean = clean.strip()
    try:
        d = json.loads(clean)
        return d if isinstance(d, dict) else None
    except Exception:
        return None


from utils.run_context import detect_label_duplicate_columns, format_run_context, sync_run_context_env


def profiler_agent(state: AgentState) -> dict:
    run_id = state.get("run_id") or state.get("dataset_fingerprint", "run")
    logger = get_logger(run_id)

    with step_timer(run_id, "profiler_agent", "load_and_compute_stats"):
        df = load_dataset(state["dataset_path"])
        target_column = state.get("target_column")
        if not target_column and "target" in df.columns:
            target_column = "target"

        # First-class leakage detection at pipeline start
        detected_leakage = detect_label_duplicate_columns(df, target_column)
        user_excludes = list(state.get("exclude_columns") or [])
        exclude_columns = list(user_excludes)
        for col in detected_leakage:
            if col not in exclude_columns:
                exclude_columns.append(col)

        feature_columns = [str(c) for c in df.columns if c != target_column and c not in exclude_columns]
        sync_run_context_env(target_column, exclude_columns)
        computed_profile = compute_data_profile(df, target_column)

    llm = _make_llm()

    run_context_block = format_run_context(target_column, exclude_columns, feature_columns)

    system_prompt = f"""{run_context_block}

You are the Profiler agent in a multi-agent ML pipeline.
Interpret pre-computed dataset statistics; never invent numbers yourself.
Flag data quality issues (high nulls, high-cardinality categoricals, likely leakage,
class imbalance if target given, notable outliers). If detected_modalities includes
"image_path", "audio_path", or "free_text", note that as a modeling consideration
(e.g. "this is an image classification task with tabular metadata") rather than
treating it as an ordinary categorical column. Recommend a metric.
Output ONLY valid JSON: {{"dataset_name": str, "modality": str, "rows": int,
"target_column": str|null, "recommended_metric": str, "data_quality_flags": [str],
"features": [{{"name": str, "type": str, "modality": str, "null_pct": float,
"cardinality": int, "outliers": int|null, "notes": str}}]}}"""

    human_prompt = f"""Computed dataset profile:
{json.dumps(computed_profile, indent=2)}

Agent state context:
{json.dumps({k: v for k, v in state.items() if k not in ("dataset_path", "messages")}, default=str)}"""

    messages = [SystemMessage(content=system_prompt), HumanMessage(content=human_prompt)]
    with step_timer(run_id, "profiler_agent", "llm_interpret"):
        response_text = stream_text(llm, messages, run_id=run_id, agent="profiler_agent")

    result = _parse_json(response_text)
    if result is None:
        logger.warning("profiler_agent: first response was not valid JSON, retrying once")
        messages += [
            SystemMessage(content=response_text),
            HumanMessage(content="Your last response was not valid JSON. Return ONLY the JSON object."),
        ]
        retry_text = stream_text(llm, messages, run_id=run_id, agent="profiler_agent(retry)")
        result = _parse_json(retry_text)

    if result is None:
        logger.warning("profiler_agent: LLM JSON parsing failed after retry; constructing fallback profile from statistics")
        result = {
            "dataset_name": "dataset",
            "modality": computed_profile.get("detected_modalities", ["tabular"])[0],
            "rows": computed_profile.get("rows", 0),
            "target_column": target_column,
            "recommended_metric": "accuracy",
            "data_quality_flags": [],
            "features": computed_profile.get("features", []),
        }

    # The LLM's JSON is the "interpreted" profile handed downstream, but the
    # ground-truth modality_summary/detected_modalities came straight from pandas —
    # keep those exact values rather than trusting the LLM to have echoed them back.
    result["modality_summary"] = computed_profile["modality_summary"]
    result["detected_modalities"] = computed_profile["detected_modalities"]

    # Target column from state is authoritative
    target_col = target_column or result.get("target_column")
    result["target_column"] = target_col
    result["exclude_columns"] = exclude_columns
    result["feature_columns"] = feature_columns

    if detected_leakage:
        if not isinstance(result.get("data_quality_flags"), list):
            result["data_quality_flags"] = []
        leakage_flag = f"Target leakage alert: column(s) {detected_leakage} are 1:1 duplicate encodings of target '{target_col}' and are excluded from features."
        if leakage_flag not in result["data_quality_flags"]:
            result["data_quality_flags"].append(leakage_flag)

    inferred_task_type = result.get("task_type")
    if not inferred_task_type and target_col and target_col in df.columns:
        series = df[target_col]
        inferred_task_type = "classification" if (not pd.api.types.is_numeric_dtype(series) or series.nunique() <= 10) else "regression"
    if inferred_task_type:
        result["task_type"] = inferred_task_type

    log_event(run_id, "profiler_agent", "profile_ready",
              flags=result.get("data_quality_flags"), metric=result.get("recommended_metric"),
              detected_modalities=result["detected_modalities"],
              target_column=target_col, task_type=inferred_task_type or "classification",
              exclude_columns=exclude_columns, feature_columns=feature_columns,
              profile=result)

    return {
        "profile": result,
        "target_column": target_col,
        "exclude_columns": exclude_columns,
        "feature_columns": feature_columns,
        "task_type": inferred_task_type or "classification",
    }

