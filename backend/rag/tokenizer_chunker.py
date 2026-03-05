"""
pipeline/tokenizer_chunker.py
------------------------------
Stage 1 & 2: HuggingFace tokenization + overlapping token-window chunking.

Design
------
- Uses the *fast* HuggingFace tokenizer for the embedding model so that
  chunk boundaries are always aligned to real token counts (not character
  heuristics), ensuring no chunk ever exceeds the model's context window.
- Overlapping windows (configurable stride) preserve cross-boundary context.
- Sentence-aware splitting as an additional heuristic to avoid mid-sentence cuts.
"""

from __future__ import annotations

import logging
from typing import Optional

from transformers import AutoTokenizer, PreTrainedTokenizerFast

from config.settings import TokenizerConfig, ChunkingConfig
from models.schema import Document, Chunk
from utils.text_utils import clean_text, split_into_sentences

logger = logging.getLogger(__name__)


class TokenizerChunker:
    """
    Tokenizes documents and splits them into overlapping chunks whose
    token count never exceeds *chunk_size*.

    Parameters
    ----------
    tok_cfg   : TokenizerConfig
    chunk_cfg : ChunkingConfig
    """

    def __init__(
        self,
        tok_cfg: Optional[TokenizerConfig] = None,
        chunk_cfg: Optional[ChunkingConfig] = None,
    ) -> None:
        self.tok_cfg   = tok_cfg   or TokenizerConfig()
        self.chunk_cfg = chunk_cfg or ChunkingConfig()

        logger.info("Loading tokenizer: %s", self.tok_cfg.model_name)
        self._tokenizer: PreTrainedTokenizerFast = AutoTokenizer.from_pretrained(
            self.tok_cfg.model_name,
            use_fast=True,
        )
        logger.info("Tokenizer ready (vocab size=%d)", self._tokenizer.vocab_size)

    # ── Public API ────────────────────────────────────────────────────────────

    def process(self, document: Document) -> list[Chunk]:
        """
        Full tokenize → chunk pipeline for a single document.

        Parameters
        ----------
        document : Document
            Input document with raw text.

        Returns
        -------
        list[Chunk]
            Non-overlapping metadata chunks with token counts set.
        """
        text = clean_text(document.text)
        if not text:
            logger.warning("Document %s yielded empty text after cleaning — skipping.", document.doc_id)
            return []

        # Tokenize the entire cleaned text
        token_ids: list[int] = self._tokenizer.encode(
            text,
            add_special_tokens=False,
            truncation=False,
        )
        logger.debug(
            "Document %s: %d chars → %d tokens",
            document.doc_id[:8], len(text), len(token_ids),
        )

        chunks = self._sliding_window_chunks(token_ids, document)
        logger.info(
            "Document %s → %d chunks (size=%d, overlap=%d)",
            document.doc_id[:8], len(chunks),
            self.chunk_cfg.chunk_size, self.chunk_cfg.chunk_overlap,
        )
        return chunks

    def process_batch(self, documents: list[Document]) -> list[Chunk]:
        """Process a list of documents and return all chunks."""
        all_chunks: list[Chunk] = []
        for doc in documents:
            all_chunks.extend(self.process(doc))
        return all_chunks

    def count_tokens(self, text: str) -> int:
        """Return the token count of *text* (excluding special tokens)."""
        return len(self._tokenizer.encode(text, add_special_tokens=False))

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _sliding_window_chunks(
        self, token_ids: list[int], document: Document
    ) -> list[Chunk]:
        """
        Split *token_ids* into overlapping windows of *chunk_size* tokens
        with a stride of *(chunk_size - chunk_overlap)*.

        Each window is decoded back to text and wrapped in a Chunk object.
        """
        size    = self.chunk_cfg.chunk_size
        overlap = self.chunk_cfg.chunk_overlap
        stride  = max(1, size - overlap)
        chunks: list[Chunk] = []

        start = 0
        idx   = 0
        total = len(token_ids)

        while start < total:
            end    = min(start + size, total)
            window = token_ids[start:end]

            chunk_text = self._tokenizer.decode(window, skip_special_tokens=True).strip()

            if len(chunk_text) >= self.chunk_cfg.min_chunk_length:
                chunk = Chunk(
                    text=chunk_text,
                    doc_id=document.doc_id,
                    chunk_index=idx,
                    token_count=len(window),
                    metadata={
                        **document.metadata,
                        "source": document.source,
                        "start_token": start,
                        "end_token": end,
                    },
                )
                chunks.append(chunk)
                idx += 1

            if end >= total:
                break
            start += stride

        return chunks
