"""
rag_pipeline.py
---------------
Master orchestrator that wires together all eight pipeline stages:

    Scraped text
        ↓  Stage 1  TokenizerChunker  — HuggingFace tokenization
        ↓  Stage 2  TokenizerChunker  — overlapping token-window chunking
        ↓  Stage 3  EmbeddingGenerator — sentence-transformers embeddings
        ↓  Stage 4  FAISSVectorStore   — vector indexing
        ↓  Stage 5  FAISSVectorStore   — persist to disk
        ↓  Stage 6  Retriever          — semantic query retrieval
        ↓  Stage 7  LLMProcessor       — TinyLlama structured generation
        ↓  Stage 8  OutputFormatter    — validated JSON output

Usage
-----
    from rag_pipeline import RAGPipeline
    from models.schema import Document

    pipeline = RAGPipeline()
    pipeline.index(documents)                     # build the index
    result = pipeline.query("Summarise the text") # retrieve + generate
    print(result.to_json())
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from config.settings import PipelineConfig
from llm.processor import LLMProcessor
from models.schema import Document, StructuredOutput
from output.formatter import OutputFormatter
from pipeline.embedder import EmbeddingGenerator
from pipeline.tokenizer_chunker import TokenizerChunker
from retrieval.retriever import Retriever
from storage.vector_store import FAISSVectorStore
from utils.logging_config import setup_logging

logger = logging.getLogger(__name__)


class RAGPipeline:
    """
    End-to-end local RAG pipeline.

    The pipeline is designed to be used in two phases:

    **Indexing phase**  (run once per document corpus)
        ``pipeline.index(documents)``

    **Query phase**     (run as many times as needed)
        ``result = pipeline.query("your question here")``

    A persisted FAISS index is loaded automatically on startup if it exists,
    so re-indexing is only needed when the corpus changes.

    Parameters
    ----------
    config : PipelineConfig  (uses defaults if not provided)
    """

    def __init__(self, config: Optional[PipelineConfig] = None) -> None:
        self.config = config or PipelineConfig()
        setup_logging(self.config.log_level)

        logger.info("=" * 60)
        logger.info("Initialising RAG Pipeline: %s", self.config.pipeline_name)
        logger.info("=" * 60)

        # Instantiate all components
        self.chunker      = TokenizerChunker(self.config.tokenizer, self.config.chunking)
        self.embedder     = EmbeddingGenerator(self.config.embedding)
        self.vector_store = FAISSVectorStore(self.config.faiss, self.config.embedding)
        self.retriever    = Retriever(self.embedder, self.vector_store, self.config.retrieval)
        self.llm          = LLMProcessor(self.config.llm)
        self.formatter    = OutputFormatter(self.config.output)

        # Try to restore a previously built index
        loaded = self.vector_store.load()
        if loaded:
            logger.info("Restored existing index (%d vectors).", self.vector_store.total_vectors)
        else:
            logger.info("No existing index found — run index() to build one.")

    # ── Indexing ──────────────────────────────────────────────────────────────

    def index(self, documents: list[Document]) -> None:
        """
        Full indexing pipeline: tokenize → chunk → embed → store.

        Parameters
        ----------
        documents : list[Document]
        """
        logger.info("── Indexing %d document(s) ──", len(documents))

        # Stage 1 & 2: Tokenize + chunk
        all_chunks = self.chunker.process_batch(documents)
        logger.info("Total chunks produced: %d", len(all_chunks))

        if not all_chunks:
            logger.warning("No chunks produced — check document content.")
            return

        # Stage 3: Embed
        embedded = self.embedder.embed_chunks(all_chunks)
        logger.info("Embeddings generated: %d", len(embedded))

        # Stage 4 & 5: Store + persist
        self.vector_store.add(embedded)
        logger.info("Indexing complete. Vector store: %s", self.vector_store)

    def index_text(self, text: str, source: str = "", metadata: Optional[dict] = None) -> None:
        """
        Convenience wrapper to index a single raw text string.

        Parameters
        ----------
        text     : str  raw scraped text
        source   : str  provenance URL / filename
        metadata : dict optional hints (title, author, date …)
        """
        doc = Document(text=text, source=source, metadata=metadata or {})
        self.index([doc])

    # ── Query ─────────────────────────────────────────────────────────────────

    def query(
        self,
        query: str,
        top_k: Optional[int] = None,
        source_metadata: Optional[dict] = None,
        save_output: bool = True,
    ) -> StructuredOutput:
        """
        Full query pipeline: embed query → retrieve → LLM → format.

        Parameters
        ----------
        query           : str  the user query
        top_k           : int  number of chunks to retrieve
        source_metadata : dict optional hints for the LLM
        save_output     : bool persist result to output/ directory

        Returns
        -------
        StructuredOutput
        """
        logger.info("── Query: %r ──", query[:80])

        if self.vector_store.total_vectors == 0:
            logger.warning("Vector store is empty — call index() first.")
            return StructuredOutput(summary="No documents indexed yet.")

        # Stage 6: Retrieve
        retrieved = self.retriever.retrieve(query, top_k=top_k)
        if not retrieved:
            logger.warning("No chunks retrieved for query: %r", query)
            return StructuredOutput(summary="No relevant content found.")

        # Stage 7: LLM generation
        output = self.llm.generate(retrieved, source_metadata=source_metadata)

        # Stage 8: Format + persist
        if save_output:
            self.formatter.save(output)
            self.formatter.append_jsonl(output)

        logger.info("Query complete: %s", output)
        return output

    def process(
        self,
        text: str,
        query: str = "Extract title, author, date, summary and keywords from this text.",
        source: str = "",
        metadata: Optional[dict] = None,
        save_output: bool = True,
    ) -> StructuredOutput:
        """
        One-shot convenience method: index a single text then immediately query it.

        Parameters
        ----------
        text        : str  raw scraped text
        query       : str  extraction prompt
        source      : str  provenance
        metadata    : dict optional hints
        save_output : bool

        Returns
        -------
        StructuredOutput
        """
        self.index_text(text, source=source, metadata=metadata or {})
        meta = {"source": source, **(metadata or {})}
        return self.query(query, source_metadata=meta, save_output=save_output)

    # ── Status ────────────────────────────────────────────────────────────────

    def status(self) -> dict:
        """Return a dict summarising the current pipeline state."""
        return {
            "pipeline_name":   self.config.pipeline_name,
            "total_vectors":   self.vector_store.total_vectors,
            "embedding_model": self.config.embedding.model_name,
            "llm_model":       self.config.llm.model_name,
            "index_type":      self.config.faiss.index_type,
            "top_k":           self.config.retrieval.top_k,
        }
