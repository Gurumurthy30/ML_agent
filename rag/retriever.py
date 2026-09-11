"""
rag/retriever.py — Query Chroma RAG collections for library docs and technique cheatsheets

Returns lists of structured dicts:
[
  {
    "content": "...",
    "metadata": {
      "library": "...",
      "symbol": "...",
      "source_type": "...",
      ...
    }
  }
]

Features:
- Returns dicts with content and metadata
- Supports modality filtering for technique cheatsheets
- Graceful empty-collection or offline handling with structured domain fallbacks
"""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from config.settings import get_settings

from functools import lru_cache

try:
    import chromadb
    from chromadb.utils import embedding_functions
    HAS_CHROMADB = True
except ImportError:
    HAS_CHROMADB = False

_CLIENT_CACHE = {}


@lru_cache(maxsize=4)
def _get_embedding_function(model_name: str):
    """Initializes sentence-transformers embedding function with fallback (cached)."""
    if not HAS_CHROMADB:
        return None
    try:
        return embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=model_name,
            device="cpu",
        )
    except Exception:
        return embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="sentence-transformers/all-MiniLM-L6-v2",
            device="cpu",
        )


def _get_chroma_client(path: str):
    if path not in _CLIENT_CACHE:
        _CLIENT_CACHE[path] = chromadb.PersistentClient(path=path)
    return _CLIENT_CACHE[path]


_FALLBACK_LIBRARY_DOCS = [
    {
        "content": "LightGBM: Prefer LGBMClassifier/LGBMRegressor sklearn API. Pass categoricals as category dtype. Use early_stopping callback, tune num_leaves (default 31) and learning_rate (0.05).",
        "metadata": {"library": "lightgbm", "symbol": "lightgbm.LGBMClassifier", "source_type": "fallback"},
    },
    {
        "content": "Scikit-Learn: StratifiedKFold(n_splits=5, shuffle=True, random_state=42) preserves class balance. TargetEncoder must be computed strictly out-of-fold to prevent leakage.",
        "metadata": {"library": "scikit-learn", "symbol": "sklearn.model_selection.StratifiedKFold", "source_type": "fallback"},
    },
    {
        "content": "Pandas: pd.concat([df1, df2], axis=0), never .append() (removed in pandas 2.0). Group aggregations: df.groupby('id')['val'].agg(['mean', 'std']).",
        "metadata": {"library": "pandas", "symbol": "pandas.concat", "source_type": "fallback"},
    },
]

_FALLBACK_CHEATSHEET = [
    {
        "content": "Technique: LightGBM Baseline (Modality: tabular)\nWhen to use: Standard baseline for structured tabular data.\nTradeoffs: Fast training, handles NaNs natively.\nCommon pitfalls: Setting num_leaves too high causing rapid overfit.\nRelated techniques: XGBoost Baseline, CatBoost Baseline",
        "metadata": {"modality": "tabular", "technique_name": "LightGBM Baseline", "source_type": "fallback", "confidence": "seed_draft"},
    },
    {
        "content": "Technique: Rank-Average Blending (Modality: tabular)\nWhen to use: Ensembling distinct tree models (LightGBM + XGBoost + CatBoost) on ranking metrics (ROC-AUC).\nTradeoffs: Robust to probability calibration differences.\nCommon pitfalls: Applying to log-loss or MSE.\nRelated techniques: Weighted Probability Blending, OOF Stacking",
        "metadata": {"modality": "tabular", "technique_name": "Rank-Average Blending", "source_type": "fallback", "confidence": "seed_draft"},
    },
]


def query_library_docs(query: str, top_k: int = 3, dry_run: bool = False) -> List[Dict[str, Any]]:
    """
    Queries the library_docs_index Chroma collection.
    Returns top_k results as dicts: [{"content": str, "metadata": dict}, ...]
    Gracefully falls back if Chroma is missing, unindexed, or empty.
    """
    if dry_run or os.environ.get("DRY_RUN", "").lower() == "true":
        return _FALLBACK_LIBRARY_DOCS[:top_k]

    settings = get_settings()
    path = str(Path(settings.rag.library_docs_path).resolve())

    if HAS_CHROMADB and os.path.exists(path):
        try:
            emb_fn = _get_embedding_function(settings.rag.embedding_model)
            client = _get_chroma_client(path)
            col = client.get_collection(name="library_docs_index", embedding_function=emb_fn)
            count = col.count()

            if count > 0:
                n_results = min(top_k, count)
                res = col.query(query_texts=[query], n_results=n_results)

                if res and "documents" in res and res["documents"] and res["documents"][0]:
                    docs = res["documents"][0]
                    metas = res["metadatas"][0] if ("metadatas" in res and res["metadatas"]) else [{}] * len(docs)
                    return [{"content": doc, "metadata": meta or {}} for doc, meta in zip(docs, metas)]
        except Exception:
            pass

    return _FALLBACK_LIBRARY_DOCS[:top_k]


def query_technique_cheatsheet(
    query: str, modality: Optional[str] = None, top_k: int = 3, dry_run: bool = False
) -> List[Dict[str, Any]]:
    """
    Queries the technique_cheatsheet_index Chroma collection, optionally filtered by modality.
    Returns top_k results as dicts: [{"content": str, "metadata": dict}, ...]
    Gracefully falls back if Chroma is missing, unindexed, or empty.
    """
    if dry_run or os.environ.get("DRY_RUN", "").lower() == "true":
        if modality:
            filtered = [f for f in _FALLBACK_CHEATSHEET if f.get("metadata", {}).get("modality") == modality]
            if filtered:
                return filtered[:top_k]
        return _FALLBACK_CHEATSHEET[:top_k]

    settings = get_settings()
    path = str(Path(settings.rag.technique_cheatsheet_path).resolve())

    if HAS_CHROMADB and os.path.exists(path):
        try:
            emb_fn = _get_embedding_function(settings.rag.embedding_model)
            client = _get_chroma_client(path)
            col = client.get_collection(name="technique_cheatsheet_index", embedding_function=emb_fn)
            count = col.count()

            if count > 0:
                n_results = min(top_k, count)
                query_kwargs: Dict[str, Any] = {
                    "query_texts": [query],
                    "n_results": n_results,
                }
                if modality:
                    query_kwargs["where"] = {"modality": modality}

                res = None
                try:
                    res = col.query(**query_kwargs)
                except Exception:
                    # If modality filter produced 0 matches or failed, query without where clause
                    query_kwargs.pop("where", None)
                    res = col.query(**query_kwargs)

                if res and "documents" in res and res["documents"] and res["documents"][0]:
                    docs = res["documents"][0]
                    metas = res["metadatas"][0] if ("metadatas" in res and res["metadatas"]) else [{}] * len(docs)
                    return [{"content": doc, "metadata": meta or {}} for doc, meta in zip(docs, metas)]
        except Exception:
            pass

    # Filter fallback by modality if matching
    if modality:
        filtered = [f for f in _FALLBACK_CHEATSHEET if f.get("metadata", {}).get("modality") == modality]
        if filtered:
            return filtered[:top_k]

    return _FALLBACK_CHEATSHEET[:top_k]
