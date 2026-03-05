"""
src/vector_store/store.py
FAISS-backed vector store with metadata persistence.

Stores:
  • FAISS IndexFlatL2 binary  (.faiss)
  • Parallel Chunk list        (.pkl)

IndexFlatL2 gives exact nearest-neighbour search which is reliable for
corpora up to ~500 k vectors.  Switch to IndexIVFFlat for larger corpora
(see _build_index).
"""
from __future__ import annotations

import pickle
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import faiss
import numpy as np

from config.settings import cfg
from src.embeddings.encoder import EncodedChunks
from src.tokenizer.chunker import Chunk
from src.utils.logger import get_logger

log = get_logger(__name__)


# ── result type ────────────────────────────────────────────────────────────────

@dataclass
class Hit:
    rank:    int
    score:   float       # L2 distance  (lower = more similar)
    chunk:   Chunk

    @property
    def similarity(self) -> float:
        """Approximate cosine similarity from L2 distance (normalised vecs)."""
        return max(0.0, 1.0 - self.score / 2.0)

    @property
    def text(self) -> str:
        return self.chunk.text

    def __repr__(self) -> str:
        return (f"Hit(rank={self.rank}, sim={self.similarity:.3f}, "
                f"'{self.text[:70].replace(chr(10),' ')}…')")


# ── core class ─────────────────────────────────────────────────────────────────

class VectorStore:
    """
    Thin FAISS wrapper that keeps vectors and their source Chunks in sync.

    Usage
    -----
    store = VectorStore()
    store.add(encoded_chunks)
    hits  = store.search(query_vec, top_k=5)
    store.save()          # persist to disk
    store.load()          # reload on next run
    """

    def __init__(
        self,
        index_dir:  Optional[Path] = None,
        index_name: Optional[str]  = None,
        dim:        int            = cfg.embed_dim,
    ) -> None:
        self.dim        = dim
        self._idx:    Optional[faiss.Index] = None
        self._chunks: List[Chunk]           = []

        d = Path(index_dir or cfg.index_dir)
        d.mkdir(parents=True, exist_ok=True)
        n = index_name or cfg.index_name
        self._idx_path  = d / f"{n}.faiss"
        self._meta_path = d / f"{n}.pkl"

    # ── public ─────────────────────────────────────────────────────────────────

    def add(self, encoded: EncodedChunks) -> None:
        """Add all vectors + chunks from an EncodedChunks to the index."""
        if encoded.n == 0:
            log.warning("add() called with empty EncodedChunks — skipping")
            return
        if self._idx is None:
            self._idx = self._build_index(encoded.dim)
        self._idx.add(encoded.vectors)
        self._chunks.extend(encoded.chunks)
        log.info(f"Index now holds {self._idx.ntotal:,} vectors")

    def search(self, query_vec: np.ndarray, top_k: Optional[int] = None) -> List[Hit]:
        """
        Find the top-k nearest neighbours for a query vector.

        Args
        ----
        query_vec : float32 array  (1, dim) or (dim,)
        top_k     : number of results; defaults to cfg.top_k
        """
        if self._idx is None or self._idx.ntotal == 0:
            log.warning("search() called on empty store")
            return []

        k   = min(top_k or cfg.top_k, self._idx.ntotal)
        qv  = self._prep(query_vec)
        D, I = self._idx.search(qv, k)

        hits: List[Hit] = []
        for rank, (dist, idx) in enumerate(zip(D[0], I[0]), 1):
            if 0 <= idx < len(self._chunks):
                hits.append(Hit(rank=rank, score=float(dist), chunk=self._chunks[idx]))
        return hits

    def save(self) -> None:
        if self._idx is None:
            log.warning("Nothing to save (empty index)")
            return
        faiss.write_index(self._idx, str(self._idx_path))
        with open(self._meta_path, "wb") as f:
            pickle.dump(self._chunks, f)
        log.info(f"Index saved  → {self._idx_path}  ({self._idx.ntotal:,} vectors)")

    def load(self) -> bool:
        """Load from disk. Returns True on success, False if no file found."""
        if not self._idx_path.exists():
            return False
        self._idx    = faiss.read_index(str(self._idx_path))
        with open(self._meta_path, "rb") as f:
            self._chunks = pickle.load(f)
        log.info(f"Index loaded ← {self._idx_path}  ({self._idx.ntotal:,} vectors)")
        return True

    def reset(self) -> None:
        self._idx    = None
        self._chunks = []

    @property
    def size(self) -> int:
        return self._idx.ntotal if self._idx else 0

    @property
    def is_empty(self) -> bool:
        return self.size == 0

    # ── private ────────────────────────────────────────────────────────────────

    @staticmethod
    def _build_index(dim: int) -> faiss.Index:
        """IndexFlatL2 — exact, no training required."""
        log.debug(f"Creating IndexFlatL2  dim={dim}")
        return faiss.IndexFlatL2(dim)

    @staticmethod
    def _prep(v: np.ndarray) -> np.ndarray:
        v = v.astype(np.float32)
        return v.reshape(1, -1) if v.ndim == 1 else v
