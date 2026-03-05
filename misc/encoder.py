"""
src/embeddings/encoder.py
Encodes text chunks → float32 vectors via sentence-transformers.

Model: all-MiniLM-L6-v2  (384-dim, L2-normalised)
The SentenceTransformer instance is cached as a module-level singleton.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Union

import numpy as np
from sentence_transformers import SentenceTransformer

from config.settings import cfg
from src.tokenizer.chunker import Chunk
from src.utils.logger import get_logger

log = get_logger(__name__)

# ── singleton ──────────────────────────────────────────────────────────────────
_MODEL: Optional[SentenceTransformer] = None


def _get_model() -> SentenceTransformer:
    global _MODEL
    if _MODEL is None:
        log.info(f"Loading embedding model: {cfg.embedding_model}")
        _MODEL = SentenceTransformer(cfg.embedding_model, device=cfg.embed_device)
        log.info(f"Embedding model ready  dim={_MODEL.get_sentence_embedding_dimension()}")
    return _MODEL


# ── result container ───────────────────────────────────────────────────────────

@dataclass
class EncodedChunks:
    vectors: np.ndarray   # float32  (N, 384)
    chunks:  List[Chunk]

    @property
    def n(self) -> int:
        return len(self.vectors)

    @property
    def dim(self) -> int:
        return self.vectors.shape[1] if self.n else 0

    def __post_init__(self) -> None:
        assert len(self.vectors) == len(self.chunks), "vectors / chunks length mismatch"


# ── core class ─────────────────────────────────────────────────────────────────

class Encoder:
    """
    Wraps sentence-transformers for batch-efficient encoding.

    Usage
    -----
    enc = Encoder()
    result = enc.encode(chunks)         # List[Chunk]  →  EncodedChunks
    qvec   = enc.encode_query("…")      # str          →  np.ndarray (1, 384)
    """

    def __init__(self) -> None:
        self._m = _get_model()

    def encode(self, chunks: List[Chunk], show_progress: bool = False) -> EncodedChunks:
        if not chunks:
            empty = np.zeros((0, cfg.embed_dim), dtype=np.float32)
            return EncodedChunks(empty, [])

        texts = [c.text for c in chunks]
        log.info(f"Encoding {len(texts)} chunks …")

        vecs = self._m.encode(
            texts,
            batch_size=cfg.embed_batch,
            show_progress_bar=show_progress and len(texts) > cfg.embed_batch,
            convert_to_numpy=True,
            normalize_embeddings=True,   # L2-normalise for cosine similarity
        ).astype(np.float32)

        log.info(f"Encoded  shape={vecs.shape}")
        return EncodedChunks(vecs, chunks)

    def encode_query(self, query: str) -> np.ndarray:
        """Returns shape (1, 384) — ready for FAISS search."""
        vec = self._m.encode([query], normalize_embeddings=True,
                             convert_to_numpy=True).astype(np.float32)
        return vec   # already (1, 384)

    def encode_text(self, text: Union[str, List[str]]) -> np.ndarray:
        """Encode raw string(s). Returns (N, 384) or (384,) for single string."""
        single = isinstance(text, str)
        texts  = [text] if single else text
        vecs   = self._m.encode(texts, normalize_embeddings=True,
                                convert_to_numpy=True).astype(np.float32)
        return vecs[0] if single else vecs
