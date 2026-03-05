"""
models/schema.py
----------------
Pydantic-free dataclass models used throughout the RAG pipeline.
No external validation library required — keeps dependencies minimal.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Optional
import numpy as np


@dataclass
class Document:
    """
    A single input document entering the pipeline.

    Attributes
    ----------
    text        : Raw (possibly scraped) text content.
    source      : URL, filename, or other provenance string.
    metadata    : Arbitrary key/value pairs (author, date, title hints …).
    doc_id      : Unique identifier (set automatically if not provided).
    """
    text: str
    source: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    doc_id: str = field(default_factory=lambda: _new_id())

    def __post_init__(self) -> None:
        if not self.text or not self.text.strip():
            raise ValueError("Document.text must not be empty.")

    def __repr__(self) -> str:
        return f"Document(source={self.source!r}, chars={len(self.text)})"


@dataclass
class Chunk:
    """
    A text chunk produced by the chunking stage.

    Attributes
    ----------
    text        : The chunk content.
    doc_id      : Parent document ID.
    chunk_index : Position within the parent document (0-based).
    token_count : Number of tokens in this chunk (set by tokenizer).
    metadata    : Inherited + chunk-specific metadata.
    """
    text: str
    doc_id: str
    chunk_index: int = 0
    token_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    chunk_id: str = field(default_factory=lambda: _new_id())

    def __repr__(self) -> str:
        return f"Chunk(doc={self.doc_id[:8]}, idx={self.chunk_index}, tokens={self.token_count})"


@dataclass
class EmbeddedChunk:
    """A Chunk paired with its embedding vector."""
    chunk: Chunk
    embedding: np.ndarray   # shape: (embedding_dim,)

    def __repr__(self) -> str:
        return f"EmbeddedChunk(chunk={self.chunk!r}, dim={self.embedding.shape})"


@dataclass
class RetrievedChunk:
    """A chunk returned by a vector similarity search with its score."""
    chunk: Chunk
    score: float            # cosine similarity ∈ [0, 1] (higher = more similar)

    def __repr__(self) -> str:
        return f"RetrievedChunk(score={self.score:.4f}, chunk={self.chunk!r})"


@dataclass
class StructuredOutput:
    """
    The final JSON-serialisable output produced by the LLM stage.

    Required fields match the specification:
        { "title", "author", "date", "summary", "keywords" }
    """
    title: str = ""
    author: str = ""
    date: str = ""
    summary: str = ""
    keywords: list[str] = field(default_factory=list)

    # ── Extra provenance fields (not in spec output but useful internally) ──
    source: str = ""
    doc_id: str = ""
    chunks_used: int = 0
    pipeline_version: str = "1.0.0"
    generated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        """Return the spec-required subset as a plain dict."""
        return {
            "title":    self.title,
            "author":   self.author,
            "date":     self.date,
            "summary":  self.summary,
            "keywords": self.keywords,
        }

    def to_json(self, indent: int = 2) -> str:
        """Serialise to JSON string (spec fields only)."""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def to_full_dict(self) -> dict[str, Any]:
        """Return all fields including provenance."""
        return asdict(self)

    def __repr__(self) -> str:
        return f"StructuredOutput(title={self.title!r}, keywords={self.keywords})"


# ── Helpers ───────────────────────────────────────────────────────────────────
import hashlib, time

def _new_id() -> str:
    """Generate a short deterministic-ish unique ID."""
    raw = f"{time.time_ns()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:12]
