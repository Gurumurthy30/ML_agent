"""
rag/sources/web_scraper.py — Curated URL scraper with local caching for RAG index

Fetches and caches curated reference documentation pages:
- LightGBM categorical features / advanced topics
- pandas What's New
- PyTorch AMP guide
- scikit-learn cross-validation guide & TargetEncoder
- Hugging Face tokenizer & Trainer guides
- timm model documentation

Features:
- Local cache in rag/sources/cache/
- Graceful offline fallback: if internet is unavailable or request fails, logs warning and skips
- HTML tag stripping and chunking into ~800-token (~3000 character) segments
"""

import hashlib
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
import urllib.request
import urllib.error


CURATED_URLS: List[Dict[str, str]] = [
    {
        "key": "lightgbm_advanced",
        "title": "LightGBM Categorical Feature Support & Advanced Topics",
        "url": "https://lightgbm.readthedocs.io/en/latest/Advanced-Topics.html",
    },
    {
        "key": "pandas_whatsnew",
        "title": "pandas What's New Latest Stable",
        "url": "https://pandas.pydata.org/docs/whatsnew/v2.2.0.html",
    },
    {
        "key": "pytorch_amp",
        "title": "PyTorch Automatic Mixed Precision (AMP) Guide",
        "url": "https://pytorch.org/docs/stable/amp.html",
    },
    {
        "key": "sklearn_cv",
        "title": "scikit-learn Cross-Validation: Evaluating Estimator Performance",
        "url": "https://scikit-learn.org/stable/modules/cross_validation.html",
    },
    {
        "key": "sklearn_target_encoder",
        "title": "scikit-learn TargetEncoder Documentation",
        "url": "https://scikit-learn.org/stable/modules/generated/sklearn.preprocessing.TargetEncoder.html",
    },
    {
        "key": "hf_tokenizer",
        "title": "Hugging Face AutoTokenizer Guide",
        "url": "https://huggingface.co/docs/transformers/main_classes/tokenizer",
    },
    {
        "key": "hf_trainer",
        "title": "Hugging Face Trainer Guide",
        "url": "https://huggingface.co/docs/transformers/main_classes/trainer",
    },
    {
        "key": "timm_models",
        "title": "timm create_model usage notes & pretrained models",
        "url": "https://huggingface.co/docs/timm/models",
    },
]

CACHE_DIR = Path(__file__).parent / "cache"


def _clean_html_text(html: str) -> str:
    """Strips HTML tags and scripts, leaving clean readable text."""
    # Try beautifulsoup if available
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
            tag.decompose()
        text = soup.get_text(separator="\n")
    except Exception:
        # Fallback regex strip
        text = re.sub(r"<(script|style).*?>.*?</\1>", "", html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)

    # Normalize whitespace
    lines = [line.strip() for line in text.splitlines()]
    non_empty = [line for line in lines if line]
    return "\n".join(non_empty)


def fetch_url(url: str, cache_key: str, timeout: int = 12) -> Optional[str]:
    """
    Fetches URL content, checking and populating local disk cache.
    Fails gracefully if offline or unreachable.
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE_DIR / f"{cache_key}.txt"

    if cache_file.exists():
        try:
            return cache_file.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            pass

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Antigravity-MLAgent/3.0"
    }
    req = urllib.request.Request(url, headers=headers)

    try:
        print(f"[WebScraper] Fetching {url}...")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
            clean_text = _clean_html_text(html)
            cache_file.write_text(clean_text, encoding="utf-8")
            return clean_text
    except urllib.error.URLError as e:
        print(f"[WebScraper Warning] Could not reach {url}: {e.reason}")
        return None
    except Exception as e:
        print(f"[WebScraper Warning] Failed to fetch {url}: {e}")
        return None


def scrape_curated_docs(chunk_size: int = 3000, overlap: int = 200) -> List[Dict[str, Any]]:
    """
    Scrapes all curated URLs, caches them, and chunks into segment documents.
    Returns list of {id, content, metadata} dicts.
    """
    documents: List[Dict[str, Any]] = []
    fetch_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    for entry in CURATED_URLS:
        key = entry["key"]
        url = entry["url"]
        title = entry["title"]

        text = fetch_url(url, key)
        if not text:
            continue

        # Chunk the text into ~800 token (~3000 character) chunks
        start = 0
        chunk_idx = 0
        while start < len(text):
            end = min(start + chunk_size, len(text))
            chunk_content = text[start:end].strip()

            if len(chunk_content) > 100:
                doc_id = f"scraped_{key}_{chunk_idx}"
                header = f"Source: {title}\nURL: {url}\nFetch Date: {fetch_date}\n\n"
                documents.append({
                    "id": doc_id,
                    "content": header + chunk_content,
                    "metadata": {
                        "source_type": "scraped",
                        "url": url,
                        "title": title,
                        "fetch_date": fetch_date,
                        "chunk_index": chunk_idx,
                    },
                })
                chunk_idx += 1

            start += chunk_size - overlap

    print(f"[WebScraper] Complete. Prepared {len(documents)} scraped chunks.")
    return documents


if __name__ == "__main__":
    docs = scrape_curated_docs()
    print(f"Total scraped chunks: {len(docs)}")
