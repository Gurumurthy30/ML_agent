"""
Run Memory / RAG — real implementation.

Replaces the previous stub (`lookup_run_memory` returning None). Per the diagram,
Reporter writes into Run Memory/RAG at the end of a run, and EDA/Features/Modeler/
Judge each "check first" against it near the start of their own work.

This is a small, dependency-light local vector store — a JSONL file of
{text, embedding, metadata} records plus brute-force cosine similarity. That's the
right scale here (a handful of past runs, not millions of documents); a real vector
DB would be a drop-in replacement behind the same two functions if this ever needs to
scale up.

Embeddings prefer Ollama's embedding endpoint (`OllamaEmbeddings`, consistent with the
rest of the project's model config) and transparently fall back to a small local
hashing-trick vectorizer if Ollama isn't reachable (e.g. no network, or the embedding
model isn't pulled) — so lookups/stores never hard-fail a run over an embedding
service being unavailable.
"""
import os
import json
import math
import hashlib
from typing import Optional

from tools.logger import get_logger, log_event

_STORE_DIR = os.environ.get("PIPELINE_MEMORY_DIR", "memory/store")
os.makedirs(_STORE_DIR, exist_ok=True)
_STORE_PATH = os.path.join(_STORE_DIR, "run_memory.jsonl")

_EMBED_MODEL = "nomic-embed-text"
_FALLBACK_DIM = 256


def _hashing_embed(text: str, dim: int = _FALLBACK_DIM) -> list:
    """Zero-dependency, no-network fallback: a normalized hashing-trick bag-of-words
    vector. Not as good as a real embedding model, but keeps RAG functional offline
    and gives sane behavior for exact/near-exact repeated phrasing."""
    vec = [0.0] * dim
    for token in text.lower().split():
        idx = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16) % dim
        vec[idx] += 1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def _embed(text: str, run_id: str = None) -> list:
    try:
        from langchain_ollama import OllamaEmbeddings
        embedder = OllamaEmbeddings(
            model=_EMBED_MODEL, base_url="https://ollama.com",
            client_kwargs={"headers": {"Authorization": f"Bearer {os.getenv('OLLAMA_API_KEY')}"}},
        )
        return embedder.embed_query(text)
    except Exception as exc:
        if run_id:
            get_logger(run_id).debug("run_memory: Ollama embedding unavailable (%s), using local fallback", exc)
        return _hashing_embed(text)


def _cosine(a: list, b: list) -> float:
    if len(a) != len(b):
        # Different embedding backends/dimensions were used across records —
        # can't compare meaningfully, treat as unrelated rather than erroring.
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a)) or 1.0
    norm_b = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (norm_a * norm_b)


def _read_all() -> list:
    if not os.path.exists(_STORE_PATH):
        return []
    records = []
    with open(_STORE_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def store_run_memory(dataset_fingerprint: str, run_id: str, text: str, metadata: dict) -> None:
    """Persist one run's summary for future retrieval. Called by the Reporter agent
    at the end of a run."""
    record = {
        "dataset_fingerprint": dataset_fingerprint,
        "run_id": run_id,
        "text": text,
        "embedding": _embed(text, run_id=run_id),
        "metadata": metadata,
    }
    with open(_STORE_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, default=str) + "\n")
    log_event(run_id, "run_memory", "stored", dataset_fingerprint=dataset_fingerprint,
              text_len=len(text))


def lookup_run_memory(dataset_fingerprint: str, query: str, top_k: int = 3,
                       run_id: str = None) -> Optional[list]:
    """Return up to `top_k` past-run records most similar to `query`, ranked by
    cosine similarity, or None if the store is empty. Runs for the SAME dataset
    fingerprint are ranked first (exact match on "we've literally seen this dataset
    before"), then similarity search covers everything else."""
    records = _read_all()
    if not records:
        return None

    query_vec = _embed(query, run_id=run_id)
    scored = []
    for rec in records:
        score = _cosine(query_vec, rec.get("embedding", []))
        if rec.get("dataset_fingerprint") == dataset_fingerprint:
            score += 1.0  # exact-dataset bonus, keeps same-dataset history on top
        scored.append((score, rec))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    top = [
        {"run_id": rec["run_id"], "text": rec["text"], "metadata": rec.get("metadata", {}),
         "similarity": round(score, 4)}
        for score, rec in scored[:top_k]
    ]
    if run_id:
        log_event(run_id, "run_memory", "lookup", query=query[:200], n_results=len(top), results=top)
    return top or None
