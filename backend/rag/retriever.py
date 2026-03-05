"""
retrieval/retriever.py
-----------------------
Stage 6: Query-time retrieval — embeds the query and fetches the most
relevant chunks from the FAISS vector store.
"""

from __future__ import annotations

import logging
from typing import Optional

from config.settings import RetrievalConfig
from models.schema import RetrievedChunk
from pipeline.embedder import EmbeddingGenerator
from storage.vector_store import FAISSVectorStore

logger = logging.getLogger(__name__)


class Retriever:
    """
    Retrieves the most semantically relevant chunks for a query.

    Parameters
    ----------
    embedder    : EmbeddingGenerator — shared instance (already loaded)
    vector_store: FAISSVectorStore   — shared instance (already loaded)
    config      : RetrievalConfig
    """

    def __init__(
        self,
        embedder: EmbeddingGenerator,
        vector_store: FAISSVectorStore,
        config: Optional[RetrievalConfig] = None,
    ) -> None:
        self.embedder     = embedder
        self.vector_store = vector_store
        self.config       = config or RetrievalConfig()

    # ── Public API ────────────────────────────────────────────────────────────

    def retrieve(
        self,
        query: str,
        top_k: Optional[int] = None,
        score_threshold: Optional[float] = None,
    ) -> list[RetrievedChunk]:
        """
        Embed *query* and return the *top_k* closest stored chunks.

        Parameters
        ----------
        query           : str
        top_k           : int  (defaults to RetrievalConfig.top_k)
        score_threshold : float (defaults to RetrievalConfig.score_threshold)

        Returns
        -------
        list[RetrievedChunk]  sorted by score descending
        """
        if not query or not query.strip():
            logger.warning("Empty query passed to retriever.")
            return []

        k         = top_k          if top_k          is not None else self.config.top_k
        threshold = score_threshold if score_threshold is not None else self.config.score_threshold

        logger.info("Retrieving top-%d chunks for query: %r …", k, query[:80])

        query_vec = self.embedder.embed_query(query)
        results   = self.vector_store.search(query_vec, top_k=k, score_threshold=threshold)

        logger.info(
            "Retrieved %d chunks (scores: %s)",
            len(results),
            [f"{r.score:.3f}" for r in results],
        )
        return results

    def build_context(self, retrieved: list[RetrievedChunk], max_chars: int = 4000) -> str:
        """
        Concatenate retrieved chunk texts into a single context string
        for the LLM prompt, respecting a character budget.

        Parameters
        ----------
        retrieved : list[RetrievedChunk]
        max_chars : int

        Returns
        -------
        str
        """
        parts: list[str] = []
        total = 0
        for r in retrieved:
            snippet = r.chunk.text.strip()
            if total + len(snippet) > max_chars:
                remaining = max_chars - total
                if remaining > 100:
                    parts.append(snippet[:remaining] + "…")
                break
            parts.append(snippet)
            total += len(snippet)

        context = "\n\n---\n\n".join(parts)
        logger.debug("Context assembled: %d chars from %d chunks.", len(context), len(parts))
        return context
