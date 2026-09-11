"""
Session Init — pure-code, no-LLM step that runs once when the user sends
their first chat message with attached files.

Responsibilities (per brief §2):
1. Save uploaded file(s) to state/sessions/{session_id}/data/
2. Light file inspection — columns/dtypes for tabular, file listing for others
3. Modality detection — from file type/structure
4. Target column guess — keyword proximity match on user message, with confidence tag
5. Metric auto-pick — by ML best-practice defaults, never asked from user
6. Return SessionContext typed dict consumed by Data Explorer and the rest of the graph
"""

import re
import shutil
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, TypedDict


# ─────────────────────────────────────────────────────────────────────────────
# Supported upload formats
# ─────────────────────────────────────────────────────────────────────────────

TABULAR_EXTENSIONS = {".csv", ".parquet", ".json", ".jsonl", ".tsv", ".xlsx", ".arrow"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".tiff", ".tif"}
AUDIO_EXTENSIONS = {".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aac"}

# Keyword proximity matching for target column extraction
_TARGET_INTENT_WORDS = {
    "predict", "predicting", "predicted",
    "classify", "classifying", "classification",
    "estimate", "estimating", "forecast",
    "target", "label", "outcome", "output",
    "target is", "label is", "predict the",
}

# Name-match columns for target detection
_TARGET_NAME_PATTERNS = {
    "target", "label", "y", "class", "outcome",
    "labels", "classes", "target_col", "class_label",
}

# Metric defaults per task type (brief §2, table)
_METRIC_DEFAULTS = {
    "binary_classification": "roc_auc",
    "multiclass_classification": "macro_f1",
    "multilabel_classification": "macro_f1",
    "regression": "rmse",
}


# ─────────────────────────────────────────────────────────────────────────────
# SessionContext — typed dict handed off to AgentState.task_context
# ─────────────────────────────────────────────────────────────────────────────

class SessionContext(TypedDict):
    session_id: str
    user_message: str
    session_data_dir: str           # absolute path to state/sessions/{id}/data/
    modality: Literal["tabular", "cv", "nlp", "audio"]
    target_column: Optional[str]
    target_confidence: Literal["explicit", "name_matched", "defaulted"]
    task_type: str                  # binary_classification | multiclass_classification | regression | etc.
    metric: str
    metric_direction: Literal["maximize", "minimize"]
    metrics_to_track: List[str]
    column_names: List[str]         # for tabular: column names from first uploaded file
    file_listing: List[str]         # for non-tabular: list of discovered files
    train_shape: Optional[List[int]]
    task_id: str
    task_name: str
    sample_submission_format: Dict[str, str]


# ─────────────────────────────────────────────────────────────────────────────
# Core helpers
# ─────────────────────────────────────────────────────────────────────────────

def _detect_modality(files: List[Path]) -> Literal["tabular", "cv", "nlp", "audio"]:
    """
    Detect data modality from the uploaded files.
    Priority: extension-based grouping → majority type.
    NLP-in-CSV detection happens separately in _detect_nlp_csv().
    """
    tabular_count = sum(1 for f in files if f.suffix.lower() in TABULAR_EXTENSIONS)
    image_count = sum(1 for f in files if f.suffix.lower() in IMAGE_EXTENSIONS)
    audio_count = sum(1 for f in files if f.suffix.lower() in AUDIO_EXTENSIONS)

    if image_count >= max(tabular_count, audio_count, 1) and image_count > 0:
        return "cv"
    if audio_count >= max(tabular_count, image_count, 1) and audio_count > 0:
        return "audio"
    if tabular_count > 0:
        return "tabular"
    return "nlp"


def _detect_nlp_csv(df_head: Any, col_names: List[str]) -> bool:
    """
    Cheap heuristic: if any string column has avg word count > 20 tokens,
    this is likely NLP-in-a-CSV rather than pure tabular.
    """
    try:
        import pandas as pd
        string_cols = [c for c in col_names if df_head[c].dtype == object]
        for col in string_cols:
            avg_words = df_head[col].dropna().astype(str).str.split().apply(len).mean()
            if avg_words > 20:
                return True
    except Exception:
        pass
    return False


def _guess_target_column(
    col_names: List[str],
    user_message: str,
) -> tuple[Optional[str], Literal["explicit", "name_matched", "defaulted"]]:
    """
    Three-level target column heuristic per brief §2 step 4.
    Returns (column_name, confidence_tag).

    Priority order:
      a) Explicit: user message mentions a column name near task-intent keywords
      b) Name match: column is named target/label/y/class/outcome (case-insensitive)
      c) Fallback: last column
    """
    col_lower_map = {c.lower(): c for c in col_names}
    msg_lower = user_message.lower()

    # (a) Explicit — column name appears near intent words in message
    # Tokenise message; look within a window of 5 tokens around each intent word
    tokens = re.findall(r"[\w']+|[^\\w\\s]", msg_lower)
    intent_positions = []
    for i, tok in enumerate(tokens):
        for kw in _TARGET_INTENT_WORDS:
            kw_tokens = kw.split()
            if tokens[i : i + len(kw_tokens)] == kw_tokens:
                intent_positions.append(i)
                break

    if intent_positions:
        window = 5
        for pos in intent_positions:
            start = max(0, pos - window)
            end = min(len(tokens), pos + window + 1)
            nearby_tokens = tokens[start:end]
            for tok in nearby_tokens:
                tok_clean = tok.strip("'\".,;:!?()")
                if tok_clean in col_lower_map:
                    return col_lower_map[tok_clean], "explicit"

    # (b) Name match — well-known target column names
    for col_l, col_orig in col_lower_map.items():
        if col_l in _TARGET_NAME_PATTERNS:
            return col_orig, "name_matched"

    # (c) Fallback — last column
    if col_names:
        return col_names[-1], "defaulted"

    return None, "defaulted"


def _infer_task_type(df_head: Any, target_col: str) -> str:
    """
    Infer task type from target column dtype and cardinality.
    Returns one of: binary_classification, multiclass_classification,
                    multilabel_classification, regression
    """
    try:
        import pandas as pd
        import numpy as np

        if target_col not in df_head.columns:
            return "binary_classification"

        series = df_head[target_col].dropna()

        # Multilabel: list-like values
        if series.apply(lambda x: isinstance(x, (list, tuple))).any():
            return "multilabel_classification"

        # Numeric target
        if pd.api.types.is_numeric_dtype(series):
            n_unique = series.nunique()
            if n_unique == 2:
                return "binary_classification"
            elif n_unique <= 20:
                return "multiclass_classification"
            else:
                # check if integer-labeled (likely classification despite high cardinality)
                if pd.api.types.is_integer_dtype(series) and n_unique <= 100:
                    return "multiclass_classification"
                return "regression"

        # String/object target — always classification
        n_unique = series.nunique()
        if n_unique == 2:
            return "binary_classification"
        return "multiclass_classification"

    except Exception:
        return "binary_classification"


_MINIMIZE_METRICS = {"rmse", "mse", "mae", "logloss", "log_loss", "loss"}


def get_metric_direction(metric_name: str) -> Literal["maximize", "minimize"]:
    """Returns 'minimize' for error/loss metrics, 'maximize' otherwise."""
    m_clean = (metric_name or "").lower().replace("-", "_")
    return "minimize" if m_clean in _MINIMIZE_METRICS else "maximize"


def _auto_pick_metric(task_type: str, user_message: str) -> tuple[str, Literal["maximize", "minimize"]]:
    """
    Auto-pick default metric and its optimization direction per brief §2 step 5 table.
    If the user explicitly names a metric in their message, honour it.
    Otherwise use the ML-best-practice default — never ask the user.
    Returns (metric_name, direction).
    """
    known_metrics = {
        "roc_auc", "auc", "auc-roc",
        "f1", "macro_f1", "micro_f1", "weighted_f1",
        "rmse", "mse", "mae", "r2",
        "accuracy", "logloss", "log_loss",
        "map", "ndcg",
    }
    msg_lower = user_message.lower()
    chosen_metric = None
    for m in known_metrics:
        # word-boundary search
        if re.search(r"\b" + re.escape(m.replace("-", "[_-]?")) + r"\b", msg_lower):
            canonical = {
                "auc": "roc_auc",
                "auc-roc": "roc_auc",
                "f1": "macro_f1",
                "micro_f1": "macro_f1",
                "weighted_f1": "macro_f1",
                "mse": "rmse",
                "log_loss": "logloss",
            }.get(m, m)
            chosen_metric = canonical
            break

    if not chosen_metric:
        chosen_metric = _METRIC_DEFAULTS.get(task_type, "roc_auc")

    direction = get_metric_direction(chosen_metric)
    return chosen_metric, direction


# ─────────────────────────────────────────────────────────────────────────────
# Main Session Init entry point
# ─────────────────────────────────────────────────────────────────────────────

class SessionInit:
    """
    Deterministic, no-LLM session initialiser.
    Call .run() with staged file paths and the user's message.
    """

    def __init__(self, session_id: str, storage_root: str = "state/sessions/"):
        self.session_id = session_id
        self.session_dir = Path(storage_root) / session_id
        self.data_dir = self.session_dir / "data"

    def run(
        self,
        staged_files: List[Path],
        user_message: str,
    ) -> SessionContext:
        """
        Steps 1-6 of brief §2. Returns a SessionContext dict.
        """

        # ── Step 1: Save uploads to session data dir ─────────────────────────
        self.data_dir.mkdir(parents=True, exist_ok=True)
        (self.session_dir / "exec_workspace").mkdir(parents=True, exist_ok=True)

        saved_files: List[Path] = []
        for src in staged_files:
            dest = self.data_dir / src.name
            shutil.copy2(src, dest)
            saved_files.append(dest)

        if not saved_files:
            default_data = Path("data")
            if default_data.exists():
                for src in default_data.iterdir():
                    if src.is_file() and not src.name.startswith("."):
                        dest = self.data_dir / src.name
                        shutil.copy2(src, dest)
                        saved_files.append(dest)

        # ── Step 2 & 3: Light inspection + modality detection ─────────────────
        modality = _detect_modality(saved_files)
        col_names: List[str] = []
        file_listing: List[str] = [f.name for f in saved_files]
        train_shape: Optional[List[int]] = None
        df_head = None

        if modality == "tabular":
            # Read first tabular file for column inspection
            primary_file = next(
                (f for f in saved_files if f.suffix.lower() in TABULAR_EXTENSIONS),
                None
            )
            if primary_file is not None:
                df_head, col_names, train_shape = self._inspect_tabular(primary_file)
                # NLP-in-CSV override
                if df_head is not None and _detect_nlp_csv(df_head, col_names):
                    modality = "nlp"

        elif modality in ("cv", "audio"):
            # Recursively list all relevant files in subdirectories too
            all_files: List[str] = []
            for f in saved_files:
                if f.is_dir():
                    exts = IMAGE_EXTENSIONS if modality == "cv" else AUDIO_EXTENSIONS
                    all_files.extend(
                        str(p.name) for p in f.rglob("*") if p.suffix.lower() in exts
                    )
                else:
                    all_files.append(f.name)
            file_listing = all_files

        # ── Step 4: Target column guess ──────────────────────────────────────
        target_col, target_confidence = _guess_target_column(col_names, user_message)

        # ── Step 5: Infer task type + auto-pick metric ───────────────────────
        task_type = _infer_task_type(df_head, target_col) if (df_head is not None and target_col) else "binary_classification"
        metric, metric_direction = _auto_pick_metric(task_type, user_message)
        default_metrics_to_track = (
            ["rmse", "mae", "r2"] if task_type == "regression" or metric_direction == "minimize"
            else ["roc_auc", "f1", "accuracy"]
        )
        if metric not in default_metrics_to_track:
            default_metrics_to_track = [metric] + default_metrics_to_track

        # ── Step 6: Assemble SessionContext ──────────────────────────────────
        ctx: SessionContext = {
            "session_id": self.session_id,
            "user_message": user_message,
            "session_data_dir": str(self.data_dir.resolve()),
            "modality": modality,
            "target_column": target_col,
            "target_confidence": target_confidence,
            "task_type": task_type,
            "metric": metric,
            "metric_direction": metric_direction,
            "metrics_to_track": default_metrics_to_track,
            "column_names": col_names,
            "file_listing": file_listing,
            "train_shape": train_shape,
            "task_id": f"session_{self.session_id[:8]}",
            "task_name": f"Chat Session — {modality.upper()} Task",
            "sample_submission_format": {
                "id_column": "id",
                "pred_column": target_col or "target",
            },
        }

        print(
            f"[SessionInit] session={self.session_id[:8]} | modality={modality} | "
            f"target={target_col!r} ({target_confidence}) | metric={metric} [{metric_direction}] | "
            f"files={len(saved_files)}"
        )

        return ctx

    def _inspect_tabular(self, file_path: Path):
        """
        Light inspection of a tabular file. Returns (df_head, col_names, shape).
        Supports CSV, TSV, Parquet, JSON, JSONL, XLSX, Arrow.
        """
        try:
            import pandas as pd

            suffix = file_path.suffix.lower()

            if suffix == ".csv":
                df = pd.read_csv(file_path, nrows=500)
            elif suffix == ".tsv":
                df = pd.read_csv(file_path, sep="\t", nrows=500)
            elif suffix == ".parquet":
                df = pd.read_parquet(file_path)
                df = df.head(500)
            elif suffix in (".json", ".jsonl"):
                try:
                    df = pd.read_json(file_path, lines=(suffix == ".jsonl"), nrows=500)
                except Exception:
                    df = pd.read_json(file_path, nrows=500)
            elif suffix == ".xlsx":
                df = pd.read_excel(file_path, nrows=500)
            elif suffix == ".arrow":
                import pyarrow.feather as feather
                df = feather.read_feather(file_path)
                df = df.head(500)
            else:
                return None, [], None

            # Full row count (cheap estimate for large files)
            try:
                full_count = len(pd.read_csv(file_path) if suffix == ".csv" else df)
            except Exception:
                full_count = len(df)

            return df, df.columns.tolist(), [full_count, len(df.columns)]

        except Exception as e:
            print(f"[SessionInit] Could not inspect {file_path.name}: {e}")
            return None, [], None


def run_session_init(
    session_id: str,
    staged_files: List[Path],
    user_message: str,
    storage_root: str = "state/sessions/",
) -> SessionContext:
    """Top-level convenience function."""
    return SessionInit(session_id, storage_root).run(staged_files, user_message)
