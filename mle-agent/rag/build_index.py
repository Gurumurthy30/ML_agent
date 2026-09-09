import os
import glob
from pathlib import Path
from typing import List, Dict, Any

from config.settings import get_settings

try:
    import chromadb
    from chromadb.utils import embedding_functions
    HAS_CHROMADB = True
except ImportError:
    HAS_CHROMADB = False

def build_indices():
    settings = get_settings()
    # Validate source docs path before building
    settings.rag.validate_source_docs()

    source_dir = settings.rag.source_docs_path
    print(f"[RAG Build] Processing source documents from: '{source_dir}'")

    if not HAS_CHROMADB:
        print("[RAG Build Warning] chromadb is not installed. Indexing skipped.")
        return

    # Use CPU sentence-transformer model
    emb_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=settings.rag.embedding_model,
        device="cpu"
    )

    client = chromadb.PersistentClient(path=settings.rag.library_docs_path)
    lib_col = client.get_or_create_collection(
        name="library_docs_index",
        embedding_function=emb_fn
    )

    cs_client = chromadb.PersistentClient(path=settings.rag.technique_cheatsheet_path)
    cs_col = cs_client.get_or_create_collection(
        name="technique_cheatsheet_index",
        embedding_function=emb_fn
    )

    # Ingest text/markdown files
    doc_files = glob.glob(os.path.join(source_dir, "**", "*.md"), recursive=True) + \
                glob.glob(os.path.join(source_dir, "**", "*.txt"), recursive=True)

    if not doc_files:
        print(f"[RAG Build Warning] No .md or .txt files found in {source_dir}")
        return

    for idx, fpath in enumerate(doc_files):
        with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        fname = Path(fpath).name
        # Simple chunking
        chunks = [content[i:i+1000] for i in range(0, len(content), 1000)]
        for c_idx, chunk in enumerate(chunks):
            doc_id = f"{fname}_chunk_{c_idx}"
            if "cheatsheet" in fname.lower() or "technique" in fname.lower():
                cs_col.upsert(
                    ids=[doc_id],
                    documents=[chunk],
                    metadatas=[{"source": fname, "chunk": c_idx}]
                )
            else:
                lib_col.upsert(
                    ids=[doc_id],
                    documents=[chunk],
                    metadatas=[{"source": fname, "chunk": c_idx}]
                )

    print("[RAG Build] Collections build complete.")

if __name__ == "__main__":
    build_indices()
