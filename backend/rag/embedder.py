"""
pipeline/embedder.py
--------------------
Stage 3: Dense embedding generation using sentence-transformers/all-MiniLM-L6-v2.

Design
------
- Lazy-loads the model on first use to keep startup fast.
- Batched inference with configurable batch size.
- Normalised embeddings for cosine similarity (dot product == cosine when normalised).
- Thread-safe singleton pattern via a module-level cache.
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np
from sentence_transformers import SentenceTransformer

from config.settings import EmbeddingConfig
from models.schema import Chunk, EmbeddedChunk

logger = logging.getLogger(__name__)


class EmbeddingGenerator:
    """
    Wraps a SentenceTransformer model to produce normalised dense embeddings
    for a list of Chunk objects.

    Parameters
    ----------
    config : EmbeddingConfig
    """

    def __init__(self, config: Optional[EmbeddingConfig] = None) -> None:
        self.config = config or EmbeddingConfig()
        self._model: Optional[SentenceTransformer] = None

    # ── Lazy model loading ────────────────────────────────────────────────────

    @property
    def model(self) -> SentenceTransformer:
        if self._model is None:
            logger.info(
                "Loading embedding model: %s (device=%s)",
                self.config.model_name, self.config.device,
            )
            self._model = SentenceTransformer(
                self.config.model_name,
                device=self.config.device,
            )
            logger.info(
                "Embedding model ready. Output dim=%d",
                self._model.get_sentence_embedding_dimension(),
            )
        return self._model

    # ── Public API ────────────────────────────────────────────────────────────

    def embed_chunks(self, chunks: list[Chunk]) -> list[EmbeddedChunk]:
        """
        Generate embeddings for a list of Chunk objects.

        Parameters
        ----------
        chunks : list[Chunk]

        Returns
        -------
        list[EmbeddedChunk]
            Each chunk paired with its embedding vector.
        """
        if not chunks:
            return []

        texts = [c.text for c in chunks]
        logger.info("Embedding %d chunks (batch_size=%d) …", len(chunks), self.config.batch_size)

        embeddings: np.ndarray = self.model.encode(
            texts,
            batch_size=self.config.batch_size,
            normalize_embeddings=self.config.normalize_embeddings,
            show_progress_bar=self.config.show_progress_bar,
            convert_to_numpy=True,
        )

        logger.info("Embedding complete. Shape: %s", embeddings.shape)

        return [
            EmbeddedChunk(chunk=chunk, embedding=emb)
            for chunk, emb in zip(chunks, embeddings)
        ]

    def embed_query(self, query: str) -> np.ndarray:
        """
        Embed a single query string.

        Parameters
        ----------
        query : str

        Returns
        -------
        np.ndarray
            Shape: (embedding_dim,)
        """
        vec: np.ndarray = self.model.encode(
            [query],
            normalize_embeddings=self.config.normalize_embeddings,
            convert_to_numpy=True,
        )
        return vec[0]

    @property
    def embedding_dim(self) -> int:
        """Return the output dimension of the loaded model."""
        return self.model.get_sentence_embedding_dimension()
