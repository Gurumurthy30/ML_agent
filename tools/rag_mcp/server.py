"""
rag_mcp/server.py — RAG MCP Server

Wraps existing rag/retriever.py as MCP tools:
- search_library_docs(query, top_k)
- search_technique_cheatsheet(query, modality, top_k)
"""

from typing import Any, Dict, List


class RagMCP:
    """In-process RAG MCP server. Agents import and call directly."""

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run

    def search_library_docs(self, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """
        Search the library_docs_index (sklearn/pytorch/pandas/etc API docs).
        Returns top_k document snippets with content and source metadata.
        """
        try:
            from rag import query_library_docs
            results = query_library_docs(query, top_k=top_k, dry_run=self.dry_run)
            return results if results else []
        except Exception as e:
            return [{"content": f"[RAG unavailable: {e}]", "source": "error"}]

    def search_technique_cheatsheet(
        self, query: str, modality: str = "tabular", top_k: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Search the curated technique cheat-sheet, filtered by modality.
        Returns top_k technique snippets.
        """
        try:
            from rag import query_technique_cheatsheet
            results = query_technique_cheatsheet(query, modality=modality, top_k=top_k, dry_run=self.dry_run)
            return results if results else []
        except Exception as e:
            return [{"content": f"[RAG unavailable: {e}]", "source": "error"}]
        except Exception as e:
            return [{"content": f"[RAG unavailable: {e}]", "source": "error"}]
