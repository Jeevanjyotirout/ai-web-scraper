import faiss
import numpy as np
from typing import Optional
from app.core.config import settings
from app.services.ai.embeddings import embed_texts, embed_query
from loguru import logger


class VectorStore:
    """FAISS-backed vector store for semantic chunk retrieval."""

    def __init__(self):
        self._index: Optional[faiss.Index] = None
        self._chunks: list[str] = []
        self._metadata: list[dict] = []

    def build(self, chunks: list[str], metadata: Optional[list[dict]] = None):
        """Embed and index all text chunks."""
        if not chunks:
            logger.warning("No chunks to index")
            return

        logger.info(f"Building FAISS index for {len(chunks)} chunks")
        embeddings = embed_texts(chunks)
        dim = embeddings.shape[1]

        if settings.FAISS_INDEX_TYPE == "IVF":
            nlist = min(len(chunks), 100)
            quantizer = faiss.IndexFlatL2(dim)
            self._index = faiss.IndexIVFFlat(quantizer, dim, nlist)
            self._index.train(embeddings)
        elif settings.FAISS_INDEX_TYPE == "HNSW":
            self._index = faiss.IndexHNSWFlat(dim, 32)
        else:
            self._index = faiss.IndexFlatL2(dim)

        self._index.add(embeddings)
        self._chunks = chunks
        self._metadata = metadata or [{} for _ in chunks]
        logger.info(f"FAISS index built: {self._index.ntotal} vectors, dim={dim}")

    def search(self, query: str, top_k: Optional[int] = None) -> list[dict]:
        """Return top-k most relevant chunks for query."""
        if self._index is None or self._index.ntotal == 0:
            return []

        k = min(top_k or settings.FAISS_TOP_K, self._index.ntotal)
        q_vec = embed_query(query).reshape(1, -1)
        distances, indices = self._index.search(q_vec, k)

        results = []
        for dist, idx in zip(distances[0], indices[0]):
            if idx < 0:
                continue
            results.append({
                "chunk": self._chunks[idx],
                "score": float(dist),
                "metadata": self._metadata[idx],
            })

        return results

    def is_ready(self) -> bool:
        return self._index is not None and self._index.ntotal > 0
