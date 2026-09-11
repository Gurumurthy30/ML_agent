"""
rag/build_index.py — Build Chroma RAG indexes for library docs and technique cheatsheets

CLI usage:
    python rag/build_index.py --source docstrings   # Re-index library_docs_index from installed Python APIs
    python rag/build_index.py --source scraped      # Re-index library_docs_index from cached/fetched web guides
    python rag/build_index.py --source cheatsheet   # Re-index technique_cheatsheet_index from technique_cheatsheet.json
    python rag/build_index.py --source docs         # Legacy markdown file ingestion from source_docs_path
    python rag/build_index.py                       # Runs docstrings, scraped, and cheatsheet (default: all)
"""

import argparse
import glob
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure project root in sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import get_settings

try:
    import chromadb
    from chromadb.utils import embedding_functions
    HAS_CHROMADB = True
except ImportError:
    HAS_CHROMADB = False


def get_embedding_function(model_name: str):
    """Initializes sentence-transformers embedding function with fallback to local cached model."""
    if not HAS_CHROMADB:
        return None

    # First try configured model
    try:
        return embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=model_name,
            device="cpu",
        )
    except Exception as e:
        print(f"[RAG Build Warning] Could not load '{model_name}': {e}. Falling back to 'sentence-transformers/all-MiniLM-L6-v2'.")
        return embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="sentence-transformers/all-MiniLM-L6-v2",
            device="cpu",
        )


def _batch_upsert(collection, ids: List[str], documents: List[str], metadatas: List[Dict[str, Any]], batch_size: int = 100):
    """Upserts items in batches to respect Chroma batch limits."""
    total = len(ids)
    for i in range(0, total, batch_size):
        chunk_ids = ids[i:i + batch_size]
        chunk_docs = documents[i:i + batch_size]
        chunk_metas = metadatas[i:i + batch_size]
        collection.upsert(
            ids=chunk_ids,
            documents=chunk_docs,
            metadatas=chunk_metas,
        )


def index_docstrings(lib_col) -> int:
    """Extracts and indexes docstrings from installed Python libraries into library_docs_index."""
    from rag.sources.docstring_extractor import extract_all_docstrings

    print("\n[RAG Build] ---> Indexing library docstrings...")
    docs = extract_all_docstrings()
    if not docs:
        print("[RAG Build Warning] No docstrings extracted.")
        return 0

    ids = [d["id"] for d in docs]
    documents = [d["content"] for d in docs]
    metadatas = [d["metadata"] for d in docs]

    _batch_upsert(lib_col, ids, documents, metadatas)
    print(f"[RAG Build] Successfully indexed {len(docs)} library docstrings.")
    return len(docs)


def index_scraped_docs(lib_col) -> int:
    """Scrapes curated documentation and indexes chunks into library_docs_index."""
    from rag.sources.web_scraper import scrape_curated_docs

    print("\n[RAG Build] ---> Indexing scraped web documentation...")
    docs = scrape_curated_docs()
    if not docs:
        print("[RAG Build Warning] No scraped chunks available.")
        return 0

    ids = [d["id"] for d in docs]
    documents = [d["content"] for d in docs]
    metadatas = [d["metadata"] for d in docs]

    _batch_upsert(lib_col, ids, documents, metadatas)
    print(f"[RAG Build] Successfully indexed {len(docs)} scraped doc chunks.")
    return len(docs)


def index_technique_cheatsheet(cs_col) -> int:
    """Indexes technique cheatsheet entries from technique_cheatsheet.json into technique_cheatsheet_index."""
    cheatsheet_path = Path(__file__).parent / "sources" / "technique_cheatsheet.json"
    print(f"\n[RAG Build] ---> Indexing technique cheatsheet from '{cheatsheet_path}'...")

    if not cheatsheet_path.exists():
        print(f"[RAG Build Error] Cheatsheet file not found: {cheatsheet_path}")
        return 0

    with open(cheatsheet_path, "r", encoding="utf-8") as f:
        entries = json.load(f)

    if not entries:
        print("[RAG Build Warning] Cheatsheet file is empty.")
        return 0

    ids: List[str] = []
    documents: List[str] = []
    metadatas: List[Dict[str, Any]] = []

    for idx, item in enumerate(entries):
        modality = item.get("modality", "tabular")
        tech_name = item.get("technique_name", f"tech_{idx}")
        slug = tech_name.lower().replace(" ", "_").replace("/", "_").replace("(", "").replace(")", "")
        doc_id = f"cheatsheet_{modality}_{slug}"

        when_to_use = item.get("when_to_use", "")
        tradeoffs = item.get("tradeoffs", "")
        common_pitfalls = item.get("common_pitfalls", "")
        related = item.get("related_techniques", [])
        confidence = item.get("confidence", "seed_draft")

        content_lines = [
            f"Technique: {tech_name} (Modality: {modality})",
            f"When to use: {when_to_use}",
            f"Tradeoffs: {tradeoffs}",
            f"Common pitfalls: {common_pitfalls}",
            f"Related techniques: {', '.join(related) if isinstance(related, list) else related}",
            f"Confidence: {confidence}",
        ]
        doc_text = "\n".join(content_lines)

        ids.append(doc_id)
        documents.append(doc_text)
        metadatas.append({
            "modality": modality,
            "technique_name": tech_name,
            "confidence": confidence,
            "source_type": "cheatsheet",
        })

    _batch_upsert(cs_col, ids, documents, metadatas)
    print(f"[RAG Build] Successfully indexed {len(ids)} technique cheatsheet entries.")
    return len(ids)


def index_legacy_docs(lib_col, cs_col, source_dir: str) -> int:
    """Legacy ingest of .md and .txt files from source_docs_path."""
    print(f"\n[RAG Build] ---> Ingesting legacy source documents from: '{source_dir}'")
    if not os.path.exists(source_dir):
        print(f"[RAG Build Warning] source_docs_path does not exist: {source_dir}")
        return 0

    doc_files = glob.glob(os.path.join(source_dir, "**", "*.md"), recursive=True) + \
                glob.glob(os.path.join(source_dir, "**", "*.txt"), recursive=True)

    if not doc_files:
        print(f"[RAG Build Warning] No .md or .txt files found in {source_dir}")
        return 0

    indexed = 0
    for fpath in doc_files:
        with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        fname = Path(fpath).name
        chunks = [content[i:i+1000] for i in range(0, len(content), 1000)]
        for c_idx, chunk in enumerate(chunks):
            doc_id = f"legacy_{fname}_chunk_{c_idx}"
            meta = {"source": fname, "chunk": c_idx, "source_type": "legacy_doc"}
            if "cheatsheet" in fname.lower() or "technique" in fname.lower():
                cs_col.upsert(ids=[doc_id], documents=[chunk], metadatas=[meta])
            else:
                lib_col.upsert(ids=[doc_id], documents=[chunk], metadatas=[meta])
            indexed += 1

    print(f"[RAG Build] Indexed {indexed} legacy chunks.")
    return indexed


def build_indices(source: str = "all") -> None:
    settings = get_settings()

    if not HAS_CHROMADB:
        print("[RAG Build Error] chromadb is not installed. Indexing skipped.")
        return

    emb_fn = get_embedding_function(settings.rag.embedding_model)

    lib_path = str(Path(settings.rag.library_docs_path).resolve())
    cs_path = str(Path(settings.rag.technique_cheatsheet_path).resolve())

    Path(lib_path).mkdir(parents=True, exist_ok=True)
    Path(cs_path).mkdir(parents=True, exist_ok=True)

    lib_client = chromadb.PersistentClient(path=lib_path)
    lib_col = lib_client.get_or_create_collection(
        name="library_docs_index",
        embedding_function=emb_fn,
    )

    cs_client = chromadb.PersistentClient(path=cs_path)
    cs_col = cs_client.get_or_create_collection(
        name="technique_cheatsheet_index",
        embedding_function=emb_fn,
    )

    print("=" * 80)
    print(f"RAG BUILD PIPELINE — source mode: '{source}'")
    print(f"  library_docs_path: {lib_path}")
    print(f"  technique_cheatsheet_path: {cs_path}")
    print("=" * 80)

    if source in ("docstrings", "all"):
        index_docstrings(lib_col)

    if source in ("scraped", "all"):
        index_scraped_docs(lib_col)

    if source in ("cheatsheet", "all"):
        index_technique_cheatsheet(cs_col)

    if source == "docs":
        index_legacy_docs(lib_col, cs_col, settings.rag.source_docs_path)

    print("\n" + "=" * 80)
    print(f"RAG Build Complete!")
    print(f"  library_docs_index count: {lib_col.count()}")
    print(f"  technique_cheatsheet_index count: {cs_col.count()}")
    print("=" * 80)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build Chroma RAG indexes for ML Agent.")
    parser.add_argument(
        "--source",
        choices=["docstrings", "scraped", "cheatsheet", "all", "docs"],
        default="all",
        help="Source of content to index: docstrings, scraped, cheatsheet, docs, or all (default: all)",
    )
    args = parser.parse_args()
    build_indices(source=args.source)
