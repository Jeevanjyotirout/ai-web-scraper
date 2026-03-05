"""
src/pipeline/pipeline.py
End-to-end RAG pipeline orchestrator.

Stage map
─────────
  1. Chunker          raw text → List[Chunk]
  2. Encoder          List[Chunk] → EncodedChunks (float32 vectors)
  3. VectorStore      add EncodedChunks; search(query_vec) → List[Hit]
  4. LLMEngine        List[Hit] + query → RAGOutput (JSON)

Public API
──────────
  pipeline = RAGPipeline()
  result   = pipeline.run(text, query)         # full pipeline, one call
  pipeline.index(text)                         # build index only
  result   = pipeline.query(query)             # query existing index
  pipeline.save() / pipeline.load()            # persist FAISS index
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import List, Optional

from config.settings import cfg
from src.embeddings.encoder import Encoder
from src.llm.engine import LLMEngine, RAGOutput
from src.tokenizer.chunker import Chunk, Chunker
from src.utils.logger import get_logger
from src.vector_store.store import Hit, VectorStore

log = get_logger(__name__)


# ── stats container ────────────────────────────────────────────────────────────

@dataclass
class Stats:
    chunks:    int   = 0
    vectors:   int   = 0
    hits:      int   = 0
    chunk_ms:  float = 0.0
    embed_ms:  float = 0.0
    store_ms:  float = 0.0
    query_ms:  float = 0.0
    llm_ms:    float = 0.0

    @property
    def total_ms(self) -> float:
        return self.chunk_ms + self.embed_ms + self.store_ms + self.query_ms + self.llm_ms

    def __str__(self) -> str:
        return (
            f"Stats | chunks={self.chunks}  vectors={self.vectors}  hits={self.hits} | "
            f"chunk={self.chunk_ms:.0f}ms  embed={self.embed_ms:.0f}ms  "
            f"store={self.store_ms:.0f}ms  query={self.query_ms:.0f}ms  "
            f"llm={self.llm_ms:.0f}ms  total={self.total_ms:.0f}ms"
        )


@dataclass
class PipelineResult:
    output: RAGOutput
    stats:  Stats
    hits:   List[Hit] = field(default_factory=list)

    def to_json(self, indent: int = 2) -> str:
        return self.output.to_json(indent)

    def to_dict(self) -> dict:
        return self.output.to_dict()


# ── main class ─────────────────────────────────────────────────────────────────

class RAGPipeline:
    """
    Single entry-point for the local RAG system.

    Quick start
    -----------
    pipeline = RAGPipeline()
    result   = pipeline.run("Your article text here …",
                            query="What is this article about?")
    print(result.to_json())
    """

    def __init__(self) -> None:
        log.info("Initialising RAG pipeline …")
        self.chunker = Chunker()
        self.encoder = Encoder()
        self.store   = VectorStore()
        self.llm     = LLMEngine()
        log.info("Pipeline ready")

    # ── convenience: full pipeline in one call ─────────────────────────────────

    def run(
        self,
        text:  str,
        query: str = "What is the main topic, who is the author, and when was this published?",
        meta:  Optional[dict] = None,
    ) -> PipelineResult:
        """
        Index `text` then immediately query it.
        Resets the store first so each call is independent.
        """
        self.store.reset()
        stats = Stats()

        # ── Stage 1: chunk ────────────────────────────────────────────────────
        t = time.perf_counter()
        chunks = self.chunker.chunk(text, meta=meta or {})
        stats.chunk_ms = _ms(t)
        stats.chunks   = len(chunks)

        if not chunks:
            log.warning("No chunks produced — returning empty output")
            return PipelineResult(RAGOutput(), stats)

        # ── Stage 2: embed ────────────────────────────────────────────────────
        t = time.perf_counter()
        encoded = self.encoder.encode(chunks)
        stats.embed_ms = _ms(t)

        # ── Stage 3: store ────────────────────────────────────────────────────
        t = time.perf_counter()
        self.store.add(encoded)
        stats.store_ms = _ms(t)
        stats.vectors  = self.store.size

        # ── Stage 4: retrieve ─────────────────────────────────────────────────
        t = time.perf_counter()
        hits = self._retrieve(query)
        stats.query_ms = _ms(t)
        stats.hits     = len(hits)

        # ── Stage 5: LLM extraction ───────────────────────────────────────────
        t = time.perf_counter()
        output = self.llm.extract(hits, query=query)
        stats.llm_ms = _ms(t)

        log.info(str(stats))
        return PipelineResult(output=output, stats=stats, hits=hits)

    # ── separate index / query workflow ────────────────────────────────────────

    def index(self, text: str, meta: Optional[dict] = None) -> List[Chunk]:
        """
        Tokenise + embed + store `text` without querying.
        Call multiple times to build a multi-document index.
        """
        chunks  = self.chunker.chunk(text, meta=meta or {})
        if not chunks:
            return []
        encoded = self.encoder.encode(chunks)
        self.store.add(encoded)
        return chunks

    def query(
        self,
        query: str,
        top_k: Optional[int] = None,
    ) -> PipelineResult:
        """Query the existing index (must call index() first)."""
        stats = Stats()
        if self.store.is_empty:
            log.warning("Store is empty — index documents first")
            return PipelineResult(RAGOutput(summary="No documents indexed."), stats)

        t = time.perf_counter()
        hits = self._retrieve(query, top_k)
        stats.query_ms = _ms(t)
        stats.hits     = len(hits)

        t = time.perf_counter()
        output = self.llm.extract(hits, query=query)
        stats.llm_ms = _ms(t)

        log.info(str(stats))
        return PipelineResult(output=output, stats=stats, hits=hits)

    def batch(self, texts: List[str], query: str) -> PipelineResult:
        """Index multiple documents then query across all of them."""
        self.store.reset()
        for i, t in enumerate(texts):
            self.index(t, meta={"doc_index": i})
        return self.query(query)

    def save(self) -> None:
        self.store.save()

    def load(self) -> bool:
        return self.store.load()

    def reset(self) -> None:
        self.store.reset()

    # ── private ────────────────────────────────────────────────────────────────

    def _retrieve(self, query: str, top_k: Optional[int] = None) -> List[Hit]:
        qvec = self.encoder.encode_query(query)
        hits = self.store.search(qvec, top_k=top_k)
        for h in hits:
            log.debug(str(h))
        return hits


def _ms(t: float) -> float:
    return (time.perf_counter() - t) * 1000
