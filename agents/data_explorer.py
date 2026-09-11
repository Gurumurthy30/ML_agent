import json
import wave
from pathlib import Path
from typing import Dict, Any, List, Optional

import numpy as np
import pandas as pd

from graph.state import AgentState
from config.settings import get_settings
from agents.utils import push_event

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


# ---------------------------------------------------------------------- #
# Shared helpers (unchanged from v1)
# ---------------------------------------------------------------------- #

def _compute_class_balance(df: pd.DataFrame, target_column: str) -> Dict[str, Any]:
    """Deterministic target distribution check — flags imbalance if minority class < 20%."""
    if target_column not in df.columns:
        return {}
    value_counts = df[target_column].value_counts(dropna=False)
    proportions = df[target_column].value_counts(normalize=True, dropna=False)
    minority_ratio = float(proportions.min()) if len(proportions) else None
    return {
        "value_counts": {str(k): int(v) for k, v in value_counts.items()},
        "proportions": {str(k): round(float(v), 4) for k, v in proportions.items()},
        "is_imbalanced": bool(minority_ratio is not None and minority_ratio < 0.2),
    }


def _numeric_summary(series: pd.Series) -> Dict[str, Any]:
    clean = series.dropna()
    if clean.empty:
        return {"mean": None, "median": None, "std": None, "min": None, "max": None}
    return {
        "mean": round(float(clean.mean()), 4),
        "median": round(float(clean.median()), 4),
        "std": round(float(clean.std()), 4),
        "min": round(float(clean.min()), 4),
        "max": round(float(clean.max()), 4),
    }


# ---------------------------------------------------------------------- #
# Tabular EDA (unchanged computations)
# ---------------------------------------------------------------------- #

def _compute_column_stats(df: pd.DataFrame) -> Dict[str, Any]:
    """Deterministic per-column stats: mean, median, std, NaN count/pct, IQR outlier count."""
    stats: Dict[str, Any] = {}
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    for col in numeric_cols:
        series = df[col]
        clean = series.dropna()
        nan_count = int(series.isna().sum())
        is_binary_like = clean.nunique() <= 2
        outlier_count = None
        if not clean.empty and not is_binary_like:
            q1, q3 = clean.quantile(0.25), clean.quantile(0.75)
            iqr = q3 - q1
            lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
            outlier_count = int(((clean < lower) | (clean > upper)).sum())
        stats[col] = {
            "mean": round(float(clean.mean()), 4) if not clean.empty else None,
            "median": round(float(clean.median()), 4) if not clean.empty else None,
            "std": round(float(clean.std()), 4) if not clean.empty else None,
            "nan_count": nan_count,
            "nan_pct": round(float(nan_count / len(series) * 100), 2) if len(series) else 0.0,
            "outlier_count_iqr": outlier_count,
        }
    return stats


def _compute_target_correlations(df: pd.DataFrame, target_column: str, top_k: int = 10) -> List[Dict[str, Any]]:
    """Pearson correlation of each numeric feature with the target — top-k by |corr|."""
    if target_column not in df.columns or not pd.api.types.is_numeric_dtype(df[target_column]):
        return []
    numeric_df = df.select_dtypes(include=[np.number])
    if target_column not in numeric_df.columns or len(numeric_df.columns) < 2:
        return []
    corr = numeric_df.corr(numeric_only=True)[target_column].drop(target_column, errors="ignore")
    corr = corr.dropna().sort_values(key=lambda s: s.abs(), ascending=False)
    return [{"feature": feat, "corr": round(float(val), 4)} for feat, val in corr.head(top_k).items()]


def _check_leakage_candidates(df: pd.DataFrame, target_column: str) -> List[str]:
    """Flags numeric columns near-perfectly correlated (>0.95) with a numeric target."""
    if target_column not in df.columns or not pd.api.types.is_numeric_dtype(df[target_column]):
        return []
    numeric_df = df.select_dtypes(include=[np.number])
    if target_column not in numeric_df.columns or len(numeric_df.columns) < 2:
        return []
    corr = numeric_df.corr(numeric_only=True)[target_column].drop(target_column, errors="ignore")
    return corr[corr.abs() > 0.95].index.tolist()


def _compute_categorical_cardinality(df: pd.DataFrame) -> Dict[str, int]:
    """Unique-value counts for object/category columns."""
    cat_cols = df.select_dtypes(include=["object", "category", "string"]).columns.tolist()
    return {col: int(df[col].nunique(dropna=True)) for col in cat_cols}


try:
    from scipy import stats as scipy_stats
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False


def _compute_anova_stats(df: pd.DataFrame, target_column: str, top_k: int = 5) -> List[Dict[str, Any]]:
    """One-way ANOVA F-statistic & p-value for numeric features across target groups."""
    if target_column not in df.columns or not HAS_SCIPY:
        return []
    groups = [group.dropna() for _, group in df.groupby(target_column)]
    if len(groups) < 2:
        return []
    results = []
    numeric_cols = [c for c in df.select_dtypes(include=[np.number]).columns if c != target_column]
    for col in numeric_cols:
        col_groups = [g[col].dropna() for g in groups if not g[col].dropna().empty]
        if len(col_groups) >= 2:
            try:
                f_stat, p_val = scipy_stats.f_oneway(*col_groups)
                if not np.isnan(f_stat) and not np.isnan(p_val):
                    results.append({
                        "feature": col,
                        "f_statistic": round(float(f_stat), 4),
                        "p_value": float(f"{p_val:.4e}")
                    })
            except Exception:
                pass
    results.sort(key=lambda x: x["f_statistic"], reverse=True)
    return results[:top_k]


def _compute_tabular_eda(train_df: pd.DataFrame, target_column: str) -> Dict[str, Any]:
    column_stats = _compute_column_stats(train_df)
    class_balance = _compute_class_balance(train_df, target_column)
    leakage_candidates = _check_leakage_candidates(train_df, target_column)
    target_correlations = _compute_target_correlations(train_df, target_column)
    categorical_cardinality = _compute_categorical_cardinality(train_df)
    anova_results = _compute_anova_stats(train_df, target_column)
    numeric_df = train_df.select_dtypes(include=[np.number])
    skewness = {col: round(float(numeric_df[col].skew()), 4) for col in numeric_df.columns if not numeric_df[col].dropna().empty}

    return {
        "missing_values_flag": any(s["nan_count"] > 0 for s in column_stats.values()),
        "class_imbalance_flag": class_balance.get("is_imbalanced", False),
        "potential_leakage_notes": (
            f"Columns highly correlated (>0.95) with target: {leakage_candidates}"
            if leakage_candidates else "None detected via correlation check."
        ),
        "column_stats": column_stats,
        "class_balance": class_balance,
        "target_correlations": target_correlations,
        "categorical_cardinality": categorical_cardinality,
        "anova_stats": anova_results,
        "skewness": skewness,
    }


# ---------------------------------------------------------------------- #
# Computer vision EDA
# ---------------------------------------------------------------------- #

def _sample_image_stats(manifest_df: pd.DataFrame, sample_size: int = 200) -> Dict[str, Any]:
    if not HAS_PIL:
        return {"note": "Pillow not installed — image stats skipped.", "corrupted_count": None}
    if "file_path" not in manifest_df.columns:
        return {"note": "No file_path column in manifest.", "corrupted_count": None}
    sample = manifest_df["file_path"].head(sample_size)
    widths, heights, aspect_ratios, channel_counts, formats = [], [], [], [], []
    corrupted_count = 0
    for fpath in sample:
        try:
            with Image.open(fpath) as img:
                w, h = img.size
                widths.append(w); heights.append(h)
                aspect_ratios.append(round(w / h, 4) if h else None)
                channel_counts.append(len(img.getbands()))
                formats.append(img.format)
        except Exception:
            corrupted_count += 1
    fmt_counts: Dict[str, int] = {}
    for f in formats:
        fmt_counts[str(f)] = fmt_counts.get(str(f), 0) + 1
    ch_counts: Dict[str, int] = {}
    for c in channel_counts:
        ch_counts[str(c)] = ch_counts.get(str(c), 0) + 1
    return {
        "sampled_count": len(sample),
        "corrupted_count": corrupted_count,
        "width_stats": _numeric_summary(pd.Series(widths)),
        "height_stats": _numeric_summary(pd.Series(heights)),
        "aspect_ratio_stats": _numeric_summary(pd.Series(aspect_ratios)),
        "channel_count_distribution": ch_counts,
        "file_format_distribution": fmt_counts,
    }


def _compute_cv_eda(train_df: pd.DataFrame, target_column: str) -> Dict[str, Any]:
    class_balance = _compute_class_balance(train_df, target_column)
    image_stats = _sample_image_stats(train_df)
    return {
        "class_imbalance_flag": class_balance.get("is_imbalanced", False),
        "class_balance": class_balance,
        "missing_values_flag": image_stats.get("corrupted_count", 0) not in (0, None),
        "image_stats": image_stats,
    }


# ---------------------------------------------------------------------- #
# NLP EDA
# ---------------------------------------------------------------------- #

def _compute_nlp_eda(train_df: pd.DataFrame, target_column: str, text_column: str = "text") -> Dict[str, Any]:
    if text_column not in train_df.columns:
        # Try to find a text-like column
        for col in train_df.select_dtypes(include=["object"]).columns:
            if col != target_column:
                text_column = col
                break
        else:
            return {"note": f"No text column found in dataset."}
    text = train_df[text_column].astype(str)
    char_lengths = text.str.len()
    word_lengths = text.str.split().apply(lambda x: len(x) if isinstance(x, list) else 0)
    empty_count = int((text.str.strip() == "").sum())
    duplicate_count = int(text.duplicated().sum())
    vocab = set()
    for tokens in text.str.lower().str.findall(r"[a-z0-9']+"):
        vocab.update(tokens)
    class_balance = _compute_class_balance(train_df, target_column)
    return {
        "missing_values_flag": empty_count > 0,
        "class_imbalance_flag": class_balance.get("is_imbalanced", False),
        "class_balance": class_balance,
        "char_length_stats": _numeric_summary(char_lengths),
        "word_count_stats": _numeric_summary(word_lengths),
        "vocab_size": len(vocab),
        "empty_text_count": empty_count,
        "duplicate_text_count": duplicate_count,
    }


# ---------------------------------------------------------------------- #
# Audio EDA
# ---------------------------------------------------------------------- #

def _sample_audio_stats(manifest_df: pd.DataFrame, sample_size: int = 200) -> Dict[str, Any]:
    if "file_path" not in manifest_df.columns:
        return {"note": "No file_path column in manifest.", "corrupted_or_unsupported_count": None}
    sample = manifest_df["file_path"].head(sample_size)
    durations, sample_rates, channels = [], [], []
    corrupted_or_unsupported = 0
    for fpath in sample:
        try:
            with wave.open(str(fpath), "rb") as wf:
                n_frames = wf.getnframes()
                rate = wf.getframerate()
                durations.append(n_frames / rate if rate else None)
                sample_rates.append(rate)
                channels.append(wf.getnchannels())
        except (wave.Error, EOFError, FileNotFoundError, OSError):
            corrupted_or_unsupported += 1
    sr_counts: Dict[str, int] = {}
    for r in sample_rates:
        sr_counts[str(r)] = sr_counts.get(str(r), 0) + 1
    ch_counts: Dict[str, int] = {}
    for c in channels:
        ch_counts[str(c)] = ch_counts.get(str(c), 0) + 1
    return {
        "sampled_count": len(sample),
        "corrupted_or_unsupported_count": corrupted_or_unsupported,
        "duration_seconds_stats": _numeric_summary(pd.Series(durations)),
        "sample_rate_distribution": sr_counts,
        "channel_count_distribution": ch_counts,
    }


def _compute_audio_eda(train_df: pd.DataFrame, target_column: str) -> Dict[str, Any]:
    class_balance = _compute_class_balance(train_df, target_column)
    audio_stats = _sample_audio_stats(train_df)
    return {
        "class_imbalance_flag": class_balance.get("is_imbalanced", False),
        "class_balance": class_balance,
        "missing_values_flag": bool(audio_stats.get("corrupted_or_unsupported_count") not in (0, None)),
        "audio_stats": audio_stats,
    }


# ---------------------------------------------------------------------- #
# EDA → Markdown report (for UI eda_report block + Planner TASK_CONTEXT)
# ---------------------------------------------------------------------- #

def format_eda_as_markdown(info: Dict[str, Any], eda: Dict[str, Any]) -> str:
    """
    Renders the EDA results as a rich markdown report.
    This is what flows to both the UI (eda_report event) and Planner's TASK_CONTEXT.
    Includes target_confidence prominently so Planner can decide whether to trust it.
    """
    modality = info.get("modality", "tabular")
    target_col = info.get("target_column", "target")
    target_confidence = info.get("target_confidence", "defaulted")
    metric = info.get("metric", "roc_auc")
    train_shape = info.get("train_shape", [0, 0])
    task_type = info.get("task_type", "binary_classification")

    confidence_labels = {
        "explicit": "✅ Explicit — user named this column in their message",
        "name_matched": "🟡 Name-matched — column name matches known target patterns (target/label/y/class)",
        "defaulted": "🔴 Defaulted — last column used; no explicit or name-matched signal found",
    }
    confidence_label = confidence_labels.get(target_confidence, target_confidence)

    lines = [
        f"## Data Exploration Report",
        f"",
        f"| Property | Value |",
        f"|---|---|",
        f"| **Modality** | {modality.upper()} |",
        f"| **Task Type** | {task_type} |",
        f"| **Target Column** | `{target_col}` |",
        f"| **Target Confidence** | {confidence_label} |",
        f"| **Primary Metric** | `{metric}` |",
        f"| **Train Shape** | {train_shape[0] if train_shape else '?'} rows × {train_shape[1] if len(train_shape or []) > 1 else '?'} cols |",
        f"| **Missing Values** | {'⚠️ Yes' if eda.get('missing_values_flag') else '✅ None detected'} |",
        f"| **Class Imbalance** | {'⚠️ Yes (minority class < 20%)' if eda.get('class_imbalance_flag') else '✅ Balanced'} |",
        f"| **Leakage Risk** | {eda.get('potential_leakage_notes', 'Not checked')} |",
        f"",
    ]

    # Class balance
    cb = eda.get("class_balance", {})
    if cb and "proportions" in cb:
        lines.append("### Class Distribution")
        for cls, prop in cb.get("proportions", {}).items():
            count = cb.get("value_counts", {}).get(cls, 0)
            bar_len = int(prop * 20)
            bar = "█" * bar_len + "░" * (20 - bar_len)
            lines.append(f"- `{cls}`: {bar} {prop*100:.1f}% ({count:,} samples)")
        lines.append("")

    if modality == "tabular":
        col_stats = eda.get("column_stats", {})
        if col_stats:
            lines.append("### Feature Statistics")
            lines.append("| Column | Mean | Std | Nulls | IQR Outliers |")
            lines.append("|---|---|---|---|---|")
            for col, s in col_stats.items():
                outlier_str = str(s.get("outlier_count_iqr", "—")) if s.get("outlier_count_iqr") is not None else "—"
                lines.append(
                    f"| `{col}` | {s.get('mean', '—')} | {s.get('std', '—')} "
                    f"| {s.get('nan_count', 0)} ({s.get('nan_pct', 0)}%) | {outlier_str} |"
                )
            lines.append("")

        corrs = eda.get("target_correlations", [])
        if corrs:
            lines.append("### Top Feature–Target Correlations (Pearson r)")
            for c in corrs:
                sign = "+" if c["corr"] >= 0 else ""
                lines.append(f"- `{c['feature']}`: {sign}{c['corr']}")
            lines.append("")

        anova = eda.get("anova_stats", [])
        if anova:
            lines.append("### ANOVA — Top Statistically Significant Features")
            lines.append("| Feature | F-stat | p-value |")
            lines.append("|---|---|---|")
            for a in anova:
                lines.append(f"| `{a['feature']}` | {a['f_statistic']} | {a['p_value']} |")
            lines.append("")

        cards = eda.get("categorical_cardinality", {})
        if cards:
            lines.append("### Categorical Cardinality")
            for cat_col, n_uniq in cards.items():
                enc_hint = "→ target-encode" if n_uniq > 15 else "→ one-hot"
                lines.append(f"- `{cat_col}`: {n_uniq} unique values {enc_hint}")
            lines.append("")

    elif modality == "cv":
        img = eda.get("image_stats", {})
        if img:
            lines.append("### Image Dataset Profile")
            lines.append(f"- Sampled: {img.get('sampled_count')} images")
            lines.append(f"- Corrupted: {img.get('corrupted_count')}")
            lines.append(f"- Width: {img.get('width_stats')}")
            lines.append(f"- Height: {img.get('height_stats')}")
            lines.append(f"- Channels: {img.get('channel_count_distribution')}")
            lines.append(f"- Formats: {img.get('file_format_distribution')}")
            lines.append("")

    elif modality == "nlp":
        lines.append("### Text Corpus Profile")
        lines.append(f"- Word count stats: {eda.get('word_count_stats')}")
        lines.append(f"- Char length stats: {eda.get('char_length_stats')}")
        lines.append(f"- Vocabulary size: {eda.get('vocab_size')} unique tokens")
        lines.append(f"- Empty texts: {eda.get('empty_text_count')}")
        lines.append(f"- Duplicate texts: {eda.get('duplicate_text_count')}")
        lines.append("")

    elif modality == "audio":
        aud = eda.get("audio_stats", {})
        if aud:
            lines.append("### Audio Signal Profile")
            lines.append(f"- Sampled: {aud.get('sampled_count')} files")
            lines.append(f"- Duration (s): {aud.get('duration_seconds_stats')}")
            lines.append(f"- Sample rates: {aud.get('sample_rate_distribution')}")
            lines.append(f"- Channels: {aud.get('channel_count_distribution')}")
            lines.append(f"- Corrupted/unsupported: {aud.get('corrupted_or_unsupported_count')}")
            lines.append("")

    return "\n".join(lines)


# Alias for backward-compat with planner.py
format_eda_as_prompt = format_eda_as_markdown


# ---------------------------------------------------------------------- #
# Modality EDA dispatch
# ---------------------------------------------------------------------- #

_MODALITY_EDA_FUNCS = {
    "tabular": _compute_tabular_eda,
    "cv": _compute_cv_eda,
    "nlp": _compute_nlp_eda,
    "audio": _compute_audio_eda,
}


# ---------------------------------------------------------------------- #
# Dataset loader — session-aware
# ---------------------------------------------------------------------- #

def _load_dataset_from_session(session_data_dir: str, modality: str) -> Optional[pd.DataFrame]:
    """
    Loads the primary training DataFrame from the session data directory.
    Supports: CSV, TSV, Parquet, JSON, JSONL.
    For CV/audio, returns a manifest DataFrame with file_path + label columns.
    """
    data_dir = Path(session_data_dir)
    if not data_dir.exists():
        return None

    # Tabular: find first train-like file
    tabular_extensions = [".csv", ".parquet", ".json", ".jsonl", ".tsv"]
    for fname in ["train.csv", "train.parquet", "train.json", "data.csv", "dataset.csv"]:
        f = data_dir / fname
        if f.exists():
            return _read_tabular_file(f)

    # Fallback: first file with tabular extension
    for ext in tabular_extensions:
        matches = list(data_dir.glob(f"*{ext}"))
        if matches:
            return _read_tabular_file(matches[0])

    # For CV/audio: build a manifest from discovered files
    from session.init import IMAGE_EXTENSIONS, AUDIO_EXTENSIONS
    if modality == "cv":
        exts = IMAGE_EXTENSIONS
    elif modality == "audio":
        exts = AUDIO_EXTENSIONS
    else:
        return None

    files = [p for p in data_dir.rglob("*") if p.suffix.lower() in exts]
    if files:
        return pd.DataFrame({"file_path": [str(f) for f in files]})

    return None


def _read_tabular_file(file_path: Path) -> Optional[pd.DataFrame]:
    """Read a single tabular file into a DataFrame."""
    try:
        import pandas as pd
        suffix = file_path.suffix.lower()
        if suffix == ".csv":
            return pd.read_csv(file_path)
        elif suffix == ".tsv":
            return pd.read_csv(file_path, sep="\t")
        elif suffix == ".parquet":
            return pd.read_parquet(file_path)
        elif suffix in (".json", ".jsonl"):
            try:
                return pd.read_json(file_path, lines=(suffix == ".jsonl"))
            except Exception:
                return pd.read_json(file_path)
    except Exception as e:
        print(f"[DataExplorer] Could not read {file_path.name}: {e}")
    return None


# ---------------------------------------------------------------------- #
# Node
# ---------------------------------------------------------------------- #

def data_explorer_node(state: AgentState) -> AgentState:
    """
    Data Explorer Agent Node (v2).

    Purely deterministic — no LLM call. Runs once at session start.
    Reads session context from state (populated by Session Init via task_context),
    loads the uploaded dataset, computes modality-specific EDA, and produces:
      - state["task_context"]  enriched with eda_summary and eda_prompt_summary
      - state["eda_report_markdown"]  — rendered markdown for the UI eda_report block
      - node_start / eda_report / node_end events pushed to state["event_queue"]
    """
    push_event(state, {"type": "node_start", "node": "data_explorer"})

    task_ctx = state.get("task_context", {})
    modality = task_ctx.get("modality", "tabular")
    target_column = task_ctx.get("target_column", "target")
    target_confidence = task_ctx.get("target_confidence", "defaulted")
    session_data_dir = state.get("session_data_dir", task_ctx.get("session_data_dir", ""))

    # Budget from initial state (session init doesn't override budget)
    settings = get_settings()

    # Load dataset from session data dir
    eda_summary: Dict[str, Any] = {
        "missing_values_flag": False,
        "class_imbalance_flag": False,
        "potential_leakage_notes": "Dataset not available for direct inspection.",
    }

    eda_func = _MODALITY_EDA_FUNCS.get(modality)
    train_df = None

    if eda_func is not None:
        try:
            train_df = _load_dataset_from_session(session_data_dir, modality)
            if train_df is not None:
                eda_summary = eda_func(train_df, target_column)
            else:
                eda_summary["note"] = "No dataset found in session data dir — EDA skipped."
                print(f"[DataExplorer] No dataset found in {session_data_dir}")
        except Exception as e:
            print(f"[DataExplorer] EDA computation failed, continuing with info-only: {e}")
    else:
        eda_summary["note"] = f"No EDA implemented for modality '{modality}'."

    # Shape info
    train_shape = task_ctx.get("train_shape")
    if train_df is not None and train_shape is None:
        train_shape = [len(train_df), len(train_df.columns)]

    info = {
        "modality": modality,
        "target_column": target_column,
        "target_confidence": target_confidence,
        "metric": task_ctx.get("metric", "roc_auc"),
        "task_type": task_ctx.get("task_type", "binary_classification"),
        "train_shape": train_shape or [0, 0],
        "task_id": task_ctx.get("task_id", "session_unknown"),
        "task_name": task_ctx.get("task_name", "Chat Session Task"),
    }

    # Render full markdown report
    eda_report_md = format_eda_as_markdown(info, eda_summary)

    # Write session-scoped task_context.json
    if session_data_dir:
        session_dir = Path(session_data_dir).parent
        task_ctx_path = session_dir / "task_context.json"
        try:
            full_ctx = {**task_ctx, "eda_summary": eda_summary, "train_shape": train_shape}
            with open(task_ctx_path, "w", encoding="utf-8") as f:
                json.dump(full_ctx, f, indent=2, default=str)
        except Exception as e:
            print(f"[DataExplorer] Could not write task_context.json: {e}")

    # Emit eda_report event (UI renders as collapsed expandable block)
    n_cols = len(train_df.columns) if train_df is not None else 0
    n_flagged = sum([
        int(eda_summary.get("missing_values_flag", False)),
        int(eda_summary.get("class_imbalance_flag", False)),
        int(bool(eda_summary.get("potential_leakage_notes", "None") != "None detected via correlation check.")),
    ])
    push_event(state, {
        "type": "eda_report",
        "content_markdown": eda_report_md,
        "summary": f"Explored the data — {n_cols} columns, {n_flagged} issue(s) flagged",
    })

    push_event(state, {"type": "node_end", "node": "data_explorer"})

    print(
        f"[DataExplorer] modality={modality} | target={target_column!r} ({target_confidence}) | "
        f"missing={eda_summary.get('missing_values_flag')} | imbalanced={eda_summary.get('class_imbalance_flag')}"
    )

    state["task_context"] = {
        **task_ctx,
        "eda_summary": eda_summary,
        "eda_prompt_summary": eda_report_md,
        "train_shape": train_shape,
    }
    state["eda_report_markdown"] = eda_report_md
    state["target_confidence"] = target_confidence
    state["status"] = "planning"
    return state