"""
src/tokenizer/chunker.py
HuggingFace AutoTokenizer + sliding-window chunking.

Pipeline step:  raw text  →  List[Chunk]
Each Chunk carries its decoded text, token count, and position offsets.
The tokenizer is cached after first load (singleton).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterator, List, Optional

from transformers import AutoTokenizer, PreTrainedTokenizerBase

from config.settings import cfg
from src.utils.logger import get_logger
from src.utils.text_cleaner import clean

log = get_logger(__name__)

# ── singleton cache ────────────────────────────────────────────────────────────
_TOKENIZER_CACHE: dict[str, PreTrainedTokenizerBase] = {}


def _get_tokenizer(model: str) -> PreTrainedTokenizerBase:
    if model not in _TOKENIZER_CACHE:
        log.info(f"Loading tokenizer: {model}")
        _TOKENIZER_CACHE[model] = AutoTokenizer.from_pretrained(
            model, use_fast=True, clean_up_tokenization_spaces=True
        )
        log.info(f"Tokenizer ready  vocab={_TOKENIZER_CACHE[model].vocab_size:,}")
    return _TOKENIZER_CACHE[model]


# ── data model ─────────────────────────────────────────────────────────────────

@dataclass
class Chunk:
    text:        str
    chunk_id:    int
    token_count: int
    start_tok:   int
    end_tok:     int
    meta:        dict = field(default_factory=dict)

    def __repr__(self) -> str:
        return (f"Chunk(id={self.chunk_id}, toks={self.token_count}, "
                f"'{self.text[:60].replace(chr(10),' ')}…')")


# ── core class ─────────────────────────────────────────────────────────────────

class Chunker:
    """
    Tokenise raw text with a HuggingFace tokenizer, then split
    into overlapping windows of `chunk_size` tokens.

    Usage
    -----
    chunks = Chunker().chunk("Your long article here …")
    """

    def __init__(
        self,
        model:   Optional[str] = None,
        size:    Optional[int] = None,
        overlap: Optional[int] = None,
    ) -> None:
        self._tok     = _get_tokenizer(model or cfg.tokenizer_model)
        self.size     = size    or cfg.chunk_size
        self.overlap  = overlap or cfg.chunk_overlap
        self.stride   = max(1, self.size - self.overlap)

    # ── public ─────────────────────────────────────────────────────────────────

    def chunk(self, text: str, meta: Optional[dict] = None) -> List[Chunk]:
        """Clean → tokenise → chunk. Returns [] for empty / whitespace input."""
        cleaned = clean(text)
        if not cleaned:
            return []

        ids = self._tok.encode(cleaned, add_special_tokens=False, truncation=False)
        if not ids:
            return []

        log.debug(f"Tokenised → {len(ids):,} tokens")
        chunks = list(self._windows(ids, meta or {}))
        log.info(f"Chunked into {len(chunks)} pieces  (size={self.size}, overlap={self.overlap})")
        return chunks

    def token_count(self, text: str) -> int:
        return len(self._tok.encode(text, add_special_tokens=False, truncation=False))

    # ── private ────────────────────────────────────────────────────────────────

    def _windows(self, ids: list[int], meta: dict) -> Iterator[Chunk]:
        cid = 0
        pos = 0
        while pos < len(ids):
            end    = min(pos + self.size, len(ids))
            window = ids[pos:end]
            text   = self._tok.decode(window, skip_special_tokens=True).strip()
            if text:
                yield Chunk(
                    text=text, chunk_id=cid, token_count=len(window),
                    start_tok=pos, end_tok=end,
                    meta={"total_tokens": len(ids), **meta},
                )
                cid += 1
            if end >= len(ids):
                break
            pos += self.stride
