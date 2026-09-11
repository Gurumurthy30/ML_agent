"""
rag/sources/docstring_extractor.py — Extract docstrings from installed ML libraries

Extracts docstrings and signatures for key APIs used by the Coder agent across:
- scikit-learn (estimators, splitters, encoders, metrics)
- lightgbm, xgboost, catboost (sklearn-compatible wrappers)
- pandas (concat, merge, groupby, read_csv, read_parquet, etc.)
- numpy (array, concatenate, where, unique, argmax, stack)
- torch (nn.Linear, Conv2d, LSTM, Transformer, optimizers)
- torchvision (transforms, ImageFolder)
- timm (create_model, list_models)
- albumentations (augmentations)
- transformers (AutoTokenizer, AutoModel..., Trainer, TrainingArguments)
- datasets (load_dataset, Dataset, DatasetDict)
- librosa (load, resample, mfcc, melspectrogram)
- torchaudio (load, MelSpectrogram, MFCC)
- soundfile (read, write)

Returns a list of dicts:
[
  {
    "id": "scikit-learn_sklearn.preprocessing.TargetEncoder",
    "content": "...",
    "metadata": {
      "library": "scikit-learn",
      "symbol": "sklearn.preprocessing.TargetEncoder",
      "source_type": "docstring",
      "version": "1.5.1"
    }
  }, ...
]
"""

import importlib
import importlib.metadata
import inspect
from typing import Any, Dict, List, Optional, Tuple


TARGET_SYMBOLS: List[Tuple[str, str, str]] = [
    # (library_key, import_path, symbol_name)
    # ── scikit-learn ──
    ("scikit-learn", "sklearn.ensemble", "RandomForestClassifier"),
    ("scikit-learn", "sklearn.ensemble", "RandomForestRegressor"),
    ("scikit-learn", "sklearn.ensemble", "GradientBoostingClassifier"),
    ("scikit-learn", "sklearn.ensemble", "GradientBoostingRegressor"),
    ("scikit-learn", "sklearn.linear_model", "LogisticRegression"),
    ("scikit-learn", "sklearn.linear_model", "Ridge"),
    ("scikit-learn", "sklearn.linear_model", "Lasso"),
    ("scikit-learn", "sklearn.model_selection", "StratifiedKFold"),
    ("scikit-learn", "sklearn.model_selection", "KFold"),
    ("scikit-learn", "sklearn.model_selection", "GroupKFold"),
    ("scikit-learn", "sklearn.model_selection", "TimeSeriesSplit"),
    ("scikit-learn", "sklearn.model_selection", "cross_val_score"),
    ("scikit-learn", "sklearn.preprocessing", "StandardScaler"),
    ("scikit-learn", "sklearn.preprocessing", "OneHotEncoder"),
    ("scikit-learn", "sklearn.preprocessing", "OrdinalEncoder"),
    ("scikit-learn", "sklearn.preprocessing", "TargetEncoder"),
    ("scikit-learn", "sklearn.metrics", "roc_auc_score"),
    ("scikit-learn", "sklearn.metrics", "log_loss"),
    ("scikit-learn", "sklearn.metrics", "accuracy_score"),
    ("scikit-learn", "sklearn.metrics", "f1_score"),
    ("scikit-learn", "sklearn.metrics", "mean_squared_error"),

    # ── LightGBM, XGBoost, CatBoost ──
    ("lightgbm", "lightgbm", "LGBMClassifier"),
    ("lightgbm", "lightgbm", "LGBMRegressor"),
    ("lightgbm", "lightgbm", "early_stopping"),
    ("xgboost", "xgboost", "XGBClassifier"),
    ("xgboost", "xgboost", "XGBRegressor"),
    ("catboost", "catboost", "CatBoostClassifier"),
    ("catboost", "catboost", "CatBoostRegressor"),

    # ── pandas ──
    ("pandas", "pandas", "concat"),
    ("pandas", "pandas", "merge"),
    ("pandas", "pandas", "read_csv"),
    ("pandas", "pandas", "read_parquet"),
    ("pandas", "pandas", "get_dummies"),
    ("pandas", "pandas", "pivot_table"),
    ("pandas", "pandas.DataFrame", "groupby"),

    # ── numpy ──
    ("numpy", "numpy", "array"),
    ("numpy", "numpy", "concatenate"),
    ("numpy", "numpy", "where"),
    ("numpy", "numpy", "unique"),
    ("numpy", "numpy", "argmax"),
    ("numpy", "numpy", "stack"),

    # ── PyTorch ──
    ("torch", "torch.nn", "Linear"),
    ("torch", "torch.nn", "Conv2d"),
    ("torch", "torch.nn", "LSTM"),
    ("torch", "torch.nn", "Transformer"),
    ("torch", "torch.optim", "Adam"),
    ("torch", "torch.optim", "AdamW"),

    # ── torchvision ──
    ("torchvision", "torchvision.datasets", "ImageFolder"),

    # ── timm ──
    ("timm", "timm", "create_model"),
    ("timm", "timm", "list_models"),

    # ── transformers ──
    ("transformers", "transformers", "AutoTokenizer"),
    ("transformers", "transformers", "AutoModelForSequenceClassification"),
    ("transformers", "transformers", "AutoModelForImageClassification"),
    ("transformers", "transformers", "Trainer"),
    ("transformers", "transformers", "TrainingArguments"),

    # ── datasets ──
    ("datasets", "datasets", "load_dataset"),
    ("datasets", "datasets", "Dataset"),
    ("datasets", "datasets", "DatasetDict"),

    # ── audio libraries ──
    ("librosa", "librosa", "load"),
    ("librosa", "librosa", "resample"),
    ("librosa", "librosa.feature", "mfcc"),
    ("librosa", "librosa.feature", "melspectrogram"),
    ("torchaudio", "torchaudio", "load"),
    ("torchaudio", "torchaudio.transforms", "MelSpectrogram"),
    ("torchaudio", "torchaudio.transforms", "MFCC"),
    ("soundfile", "soundfile", "read"),
    ("soundfile", "soundfile", "write"),
]


def get_pkg_version(lib_name: str) -> str:
    """Gets version from package metadata or __version__ attribute."""
    # Mapping for packages whose import name differs from metadata name
    pkg_meta_names = {
        "scikit-learn": "scikit-learn",
        "sklearn": "scikit-learn",
        "lightgbm": "lightgbm",
        "xgboost": "xgboost",
        "catboost": "catboost",
        "pandas": "pandas",
        "numpy": "numpy",
        "torch": "torch",
        "torchvision": "torchvision",
        "timm": "timm",
        "transformers": "transformers",
        "datasets": "datasets",
        "librosa": "librosa",
        "torchaudio": "torchaudio",
        "soundfile": "soundfile",
        "albumentations": "albumentations",
    }
    meta_name = pkg_meta_names.get(lib_name, lib_name)
    try:
        return importlib.metadata.version(meta_name)
    except Exception:
        try:
            mod = importlib.import_module(lib_name)
            return getattr(mod, "__version__", "unknown")
        except Exception:
            return "unknown"


def extract_symbol_doc(lib_name: str, mod_path: str, sym_name: str) -> Optional[Dict[str, Any]]:
    """Imports symbol and extracts its docstring and signature."""
    try:
        if "." in mod_path and not mod_path.startswith("pandas.DataFrame"):
            mod = importlib.import_module(mod_path)
            obj = getattr(mod, sym_name, None)
        elif mod_path == "pandas.DataFrame":
            import pandas as pd
            obj = getattr(pd.DataFrame, sym_name, None)
        else:
            mod = importlib.import_module(mod_path)
            obj = getattr(mod, sym_name, None)

        if obj is None:
            return None

        version = get_pkg_version(lib_name)
        full_symbol = f"{mod_path}.{sym_name}"

        # Signature
        sig_str = ""
        try:
            sig = inspect.signature(obj)
            sig_str = str(sig)
        except Exception:
            pass

        # Main docstring
        doc = inspect.getdoc(obj) or ""
        if not doc.strip():
            return None

        # Format content
        lines = [
            f"Library: {lib_name} (version {version})",
            f"Symbol: {full_symbol}{sig_str}",
            "",
            doc,
        ]

        # For estimators or classes, also inspect key methods if available
        if inspect.isclass(obj):
            for method_name in ("fit", "predict", "predict_proba", "transform", "forward"):
                method = getattr(obj, method_name, None)
                if method and inspect.isfunction(method) or inspect.ismethod(method):
                    m_doc = inspect.getdoc(method)
                    if m_doc:
                        try:
                            m_sig = str(inspect.signature(method))
                        except Exception:
                            m_sig = "()"
                        lines.append(f"\n--- Method: {method_name}{m_sig} ---\n{m_doc[:1000]}")

        content = "\n".join(lines)
        doc_id = f"{lib_name}_{full_symbol}".replace(".", "_").replace(" ", "_")

        return {
            "id": doc_id,
            "content": content,
            "metadata": {
                "library": lib_name,
                "symbol": full_symbol,
                "source_type": "docstring",
                "version": version,
            },
        }
    except ImportError:
        # Package not installed — skip gracefully
        return None
    except Exception as e:
        print(f"[DocstringExtractor Warning] Could not extract {mod_path}.{sym_name}: {e}")
        return None


def extract_albumentations_docs() -> List[Dict[str, Any]]:
    """Introspects albumentations top-level augmentations."""
    results = []
    try:
        import albumentations as A
        version = get_pkg_version("albumentations")
        for sym_name in getattr(A, "__all__", []):
            if sym_name.startswith("_"):
                continue
            obj = getattr(A, sym_name, None)
            if obj and inspect.isclass(obj):
                doc = inspect.getdoc(obj)
                if doc:
                    try:
                        sig = str(inspect.signature(obj))
                    except Exception:
                        sig = "()"
                    content = (
                        f"Library: albumentations (version {version})\n"
                        f"Symbol: albumentations.{sym_name}{sig}\n\n"
                        f"{doc}"
                    )
                    results.append({
                        "id": f"albumentations_{sym_name}",
                        "content": content,
                        "metadata": {
                            "library": "albumentations",
                            "symbol": f"albumentations.{sym_name}",
                            "source_type": "docstring",
                            "version": version,
                        },
                    })
    except ImportError:
        pass
    return results


def extract_torchvision_transforms() -> List[Dict[str, Any]]:
    """Introspects torchvision.transforms classes."""
    results = []
    try:
        import torchvision.transforms as T
        version = get_pkg_version("torchvision")
        for name in dir(T):
            if name.startswith("_"):
                continue
            obj = getattr(T, name, None)
            if inspect.isclass(obj) and not name.startswith("_"):
                doc = inspect.getdoc(obj)
                if doc and len(doc) > 40:
                    try:
                        sig = str(inspect.signature(obj))
                    except Exception:
                        sig = "()"
                    content = (
                        f"Library: torchvision (version {version})\n"
                        f"Symbol: torchvision.transforms.{name}{sig}\n\n"
                        f"{doc}"
                    )
                    results.append({
                        "id": f"torchvision_transforms_{name}",
                        "content": content,
                        "metadata": {
                            "library": "torchvision",
                            "symbol": f"torchvision.transforms.{name}",
                            "source_type": "docstring",
                            "version": version,
                        },
                    })
    except ImportError:
        pass
    return results


def extract_all_docstrings() -> List[Dict[str, Any]]:
    """
    Main entry point. Extracts docstrings across all configured libraries.
    Returns list of documents with {id, content, metadata}.
    """
    documents: List[Dict[str, Any]] = []
    print("[DocstringExtractor] Starting library docstring extraction...")

    extracted_count = 0
    skipped_count = 0

    for lib_name, mod_path, sym_name in TARGET_SYMBOLS:
        doc_entry = extract_symbol_doc(lib_name, mod_path, sym_name)
        if doc_entry:
            documents.append(doc_entry)
            extracted_count += 1
        else:
            skipped_count += 1

    # Add albumentations & torchvision transforms
    albu_docs = extract_albumentations_docs()
    documents.extend(albu_docs)
    extracted_count += len(albu_docs)

    tv_docs = extract_torchvision_transforms()
    documents.extend(tv_docs)
    extracted_count += len(tv_docs)

    print(f"[DocstringExtractor] Complete. Extracted {extracted_count} docstrings ({skipped_count} skipped/not installed).")
    return documents


if __name__ == "__main__":
    docs = extract_all_docstrings()
    print(f"Total extracted: {len(docs)}")
    if docs:
        print(f"Sample snippet:\n{docs[0]['content'][:300]}")
