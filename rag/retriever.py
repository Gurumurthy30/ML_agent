import os
from typing import List, Dict, Any
from config.settings import get_settings

try:
    import chromadb
    from chromadb.utils import embedding_functions
    HAS_CHROMADB = True
except ImportError:
    HAS_CHROMADB = False

def query_library_docs(query: str, top_k: int = 3) -> List[str]:
    """Queries the library_docs_index Chroma collection or returns fallback hints."""
    settings = get_settings()
    path = settings.rag.library_docs_path

    if HAS_CHROMADB and os.path.exists(path):
        try:
            emb_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name=settings.rag.embedding_model,
                device="cpu"
            )
            client = chromadb.PersistentClient(path=path)
            col = client.get_collection(name="library_docs_index", embedding_function=emb_fn)
            res = col.query(query_texts=[query], n_results=top_k)
            if res and "documents" in res and res["documents"]:
                return res["documents"][0]
        except Exception as e:
            pass

    # Fallback response for offline/mock execution
    return [
        "LightGBM documentation: use EarlyStopping callback, set num_leaves=31, learning_rate=0.05, n_estimators=1000.",
        "Scikit-Learn documentation: use StratifiedKFold(n_splits=5, shuffle=True, random_state=42) for classification targets.",
        "Pandas documentation: handle missing values with SimpleImputer or median fill before feature scaling."
    ]

def query_technique_cheatsheet(query: str, top_k: int = 3) -> List[str]:
    """Queries the technique_cheatsheet_index Chroma collection or returns fallback hints."""
    settings = get_settings()
    path = settings.rag.technique_cheatsheet_path

    if HAS_CHROMADB and os.path.exists(path):
        try:
            emb_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name=settings.rag.embedding_model,
                device="cpu"
            )
            client = chromadb.PersistentClient(path=path)
            col = client.get_collection(name="technique_cheatsheet_index", embedding_function=emb_fn)
            res = col.query(query_texts=[query], n_results=top_k)
            if res and "documents" in res and res["documents"]:
                return res["documents"][0]
        except Exception as e:
            pass

    # Fallback response for offline/mock execution
    return [
        "Tabular Cheatsheet: Create interaction terms (numerical ratio/product), target encoding for high-cardinality categoricals, frequency encoding.",
        "Ensemble Cheatsheet: Rank-average or weighted blend of LightGBM + XGBoost + CatBoost predictions across out-of-fold predictions."
    ]
