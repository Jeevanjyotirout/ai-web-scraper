"""
app/modules/ai_processing.py
──────────────────────────────
Module 3 — AI Processing Engine

Responsibility:
    Apply local AI to understand scraped content and extract
    structured records that match the user's instructions.

Pipeline:
    raw page text
        └─► chunk into overlapping segments
            └─► embed via sentence-transformers
                └─► build FAISS index per job
                    └─► semantic search with instruction as query
                        └─► pass top-k chunks + instruction to Ollama LLM
                            └─► parse JSON response → List[Dict]

All AI is 100% local — no external API calls.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any, Dict, Iterator, List, Optional

import faiss
import numpy as np
import ollama
from loguru import logger
from sentence_transformers import SentenceTransformer
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import settings
from app.core.exceptions import (
    AIProcessingError,
    EmbeddingError,
    OllamaUnavailableError,
)
from app.modules.instruction_parser import ExtractionPlan
from app.modules.scraping_engine import PageResult


# ── Models (loaded lazily and cached) ─────────────────────────────────────────

_embedding_model: Optional[SentenceTransformer] = None


def _get_embedding_model() -> SentenceTransformer:
    global _embedding_model
    if _embedding_model is None:
        logger.info("Loading embedding model", model=settings.EMBEDDING_MODEL)
        _embedding_model = SentenceTransformer(settings.EMBEDDING_MODEL)
        logger.info("Embedding model loaded")
    return _embedding_model


# ── Data structures ────────────────────────────────────────────────────────────

@dataclass
class TextChunk:
    """A single text segment ready for embedding."""

    text: str
    source_url: str
    page_index: int
    chunk_index: int
    metadata: Dict[str, Any]


@dataclass
class AIProcessingResult:
    """Structured records extracted by the AI pipeline."""

    records: List[Dict[str, Any]]
    total_chunks_processed: int
    total_chunks_indexed: int
    top_k_retrieved: int
    llm_calls: int
    elapsed_seconds: float
    warnings: List[str]


# ── Text chunker ───────────────────────────────────────────────────────────────

class TextChunker:
    """
    Splits page content into overlapping token windows.
    Handles very large pages safely.
    """

    def __init__(self, chunk_size: int = 512, overlap: int = 64) -> None:
        self.chunk_size = chunk_size
        self.overlap    = overlap

    def chunk_page(self, page: PageResult) -> List[TextChunk]:
        chunks: List[TextChunk] = []

        # Combine headings + paragraphs + table text as primary content
        sections = []
        if page.title:
            sections.append(f"Title: {page.title}")
        sections.extend(page.headings[:10])
        sections.extend(page.paragraphs)
        for table in page.tables:
            for row in table:
                sections.append(" | ".join(row))

        full_text = " ".join(sections)
        words     = full_text.split()

        for i, chunk_words in enumerate(self._sliding_window(words)):
            chunk_text = " ".join(chunk_words).strip()
            if not chunk_text:
                continue
            chunks.append(TextChunk(
                text=chunk_text,
                source_url=page.url,
                page_index=page.page_index,
                chunk_index=i,
                metadata={
                    "title": page.title,
                    "url":   page.url,
                    "fetch_time_ms": page.fetch_time_ms,
                },
            ))

        return chunks

    def _sliding_window(self, words: List[str]) -> Iterator[List[str]]:
        start = 0
        while start < len(words):
            yield words[start : start + self.chunk_size]
            start += self.chunk_size - self.overlap
            if start + self.overlap >= len(words):
                break


# ── FAISS vector store ────────────────────────────────────────────────────────

class VectorStore:
    """
    In-memory FAISS index for a single scraping job.
    Created fresh per job — not shared across jobs.
    """

    def __init__(self) -> None:
        self._index: Optional[faiss.Index] = None
        self._chunks: List[TextChunk] = []

    def build(self, chunks: List[TextChunk]) -> None:
        """Embed and index all chunks."""
        if not chunks:
            logger.warning("No chunks to index")
            return

        texts = [c.text for c in chunks]
        try:
            model      = _get_embedding_model()
            embeddings = model.encode(
                texts,
                show_progress_bar=False,
                convert_to_numpy=True,
                batch_size=64,
            ).astype("float32")
        except Exception as exc:
            raise EmbeddingError(f"Embedding failed: {exc}") from exc

        dim = embeddings.shape[1]
        # Use IVF index for large corpora, flat for small
        if len(chunks) > 1000:
            nlist = min(int(len(chunks) ** 0.5), 256)
            quantizer = faiss.IndexFlatL2(dim)
            self._index = faiss.IndexIVFFlat(quantizer, dim, nlist)
            self._index.train(embeddings)
        else:
            self._index = faiss.IndexFlatL2(dim)

        self._index.add(embeddings)
        self._chunks = chunks
        logger.debug("FAISS index built", vectors=self._index.ntotal, dim=dim)

    def search(self, query: str, top_k: int = 25) -> List[TextChunk]:
        """Return top-k chunks most relevant to the query."""
        if self._index is None or self._index.ntotal == 0:
            return []

        model  = _get_embedding_model()
        q_vec  = model.encode([query], convert_to_numpy=True).astype("float32")
        k      = min(top_k, self._index.ntotal)
        _, ids = self._index.search(q_vec, k)

        return [self._chunks[i] for i in ids[0] if 0 <= i < len(self._chunks)]


# ── Ollama LLM client ─────────────────────────────────────────────────────────

class LLMClient:
    """
    Wrapper around the Ollama Python SDK.
    Handles prompt construction, response parsing, and retries.
    """

    def __init__(self) -> None:
        self._client = ollama.Client(host=settings.OLLAMA_HOST)

    def is_available(self) -> bool:
        """Check if Ollama is running and the configured model is available."""
        try:
            models = self._client.list()
            available = [m.model for m in models.models]
            logger.debug("Ollama models available", models=available)
            return any(settings.OLLAMA_MODEL in m for m in available)
        except Exception as exc:
            logger.warning("Ollama health check failed", error=str(exc))
            return False

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=20),
        reraise=True,
    )
    def extract(
        self,
        context_chunks: List[str],
        instructions: str,
        field_names: List[str],
        source_url: str,
    ) -> List[Dict[str, Any]]:
        """
        Ask the LLM to extract structured records from context text.

        Returns a list of dicts, one per detected record.
        """
        context_text = self._build_context(context_chunks)
        prompt       = self._build_prompt(
            context_text, instructions, field_names, source_url
        )

        try:
            response = self._client.chat(
                model=settings.OLLAMA_MODEL,
                messages=[{"role": "user", "content": prompt}],
                options={
                    "temperature": 0.05,
                    "num_ctx": 4096,
                    "top_p": 0.9,
                },
            )
            raw_output = response.message.content
            return self._parse_json_response(raw_output, field_names)

        except json.JSONDecodeError as exc:
            logger.warning("LLM returned non-JSON, attempting repair", error=str(exc))
            return []
        except Exception as exc:
            raise AIProcessingError(f"LLM call failed: {exc}") from exc

    def _build_context(self, chunks: List[str], max_chars: int = 3800) -> str:
        """Join chunks, truncating to fit the model's context window."""
        joined = "\n\n---\n\n".join(chunks)
        if len(joined) > max_chars:
            joined = joined[:max_chars] + "\n\n[... content truncated ...]"
        return joined

    def _build_prompt(
        self,
        context: str,
        instructions: str,
        field_names: List[str],
        url: str,
    ) -> str:
        fields_json = json.dumps(field_names)
        return f"""You are a precise data extraction assistant. Extract structured data from web page content.

SOURCE URL: {url}

USER INSTRUCTIONS:
{instructions}

REQUIRED FIELDS (extract these exact keys):
{fields_json}

WEB PAGE CONTENT:
{context}

TASK:
- Extract ALL matching records as a JSON array
- Each record must be a JSON object with the required field keys
- Use null for missing fields — never invent data
- If multiple records exist (e.g. a list of products), return all of them
- Return ONLY the JSON array, no explanations or markdown

JSON OUTPUT:"""

    def _parse_json_response(
        self, raw: str, field_names: List[str]
    ) -> List[Dict[str, Any]]:
        """Extract and validate the JSON array from LLM output."""
        # Strip markdown code fences
        text = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("`").strip()

        # Try to find a JSON array
        match = re.search(r"\[[\s\S]*\]", text)
        if match:
            text = match.group(0)

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            # Try to repair by closing unclosed brackets
            text = text.rstrip(",") + "]" if not text.endswith("]") else text
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                logger.warning("Could not parse LLM JSON response", raw_snippet=raw[:200])
                return []

        if isinstance(data, dict):
            data = [data]

        if not isinstance(data, list):
            return []

        # Validate and normalise each record
        records = []
        for item in data:
            if not isinstance(item, dict):
                continue
            # Ensure all required fields exist (set None if absent)
            record = {fn: item.get(fn) for fn in field_names}
            # Add any bonus fields the LLM included
            for k, v in item.items():
                if k not in record:
                    record[k] = v
            records.append(record)

        return records


# ── Main AI processing engine ─────────────────────────────────────────────────

class AIProcessingEngine:
    """
    Orchestrates chunking → embedding → retrieval → LLM extraction.

    One instance per scraping job.
    """

    def __init__(self) -> None:
        self._chunker   = TextChunker(settings.CHUNK_SIZE, settings.CHUNK_OVERLAP)
        self._llm       = LLMClient()
        self._llm_available: Optional[bool] = None

    def process(
        self,
        pages: List[PageResult],
        plan: ExtractionPlan,
    ) -> AIProcessingResult:
        """
        Main synchronous entry point (called from Celery worker thread).

        Returns structured records extracted from all pages.
        """
        start    = time.time()
        warnings = list(plan.warnings)

        if not pages:
            return AIProcessingResult(
                records=[], total_chunks_processed=0,
                total_chunks_indexed=0, top_k_retrieved=0,
                llm_calls=0, elapsed_seconds=0.0, warnings=["No pages to process"],
            )

        # Step 1 — Chunk all pages
        all_chunks: List[TextChunk] = []
        for page in pages:
            chunks = self._chunker.chunk_page(page)
            all_chunks.extend(chunks)
            logger.debug("Chunked page", url=page.url, chunks=len(chunks))

        total_chunks = len(all_chunks)
        logger.info("All pages chunked", total_chunks=total_chunks, pages=len(pages))

        if not all_chunks:
            return AIProcessingResult(
                records=[], total_chunks_processed=0,
                total_chunks_indexed=0, top_k_retrieved=0,
                llm_calls=0, elapsed_seconds=0.0, warnings=["No text extracted from pages"],
            )

        # Step 2 — Build FAISS index
        vs = VectorStore()
        vs.build(all_chunks)

        # Step 3 — Semantic search using instructions as query
        field_names = [f.name for f in plan.fields]
        query       = self._build_search_query(plan)
        top_chunks  = vs.search(query, top_k=settings.FAISS_TOP_K)
        logger.info("Vector search done", retrieved=len(top_chunks))

        # Step 4 — LLM extraction
        records:  List[Dict[str, Any]] = []
        llm_calls = 0

        if not self._check_llm():
            warnings.append("Ollama not available — falling back to raw chunk extraction")
            records = self._fallback_extract(top_chunks, field_names)
        else:
            # Batch top-k chunks into LLM call windows
            batch_size = 10
            for batch_start in range(0, len(top_chunks), batch_size):
                batch = top_chunks[batch_start : batch_start + batch_size]
                try:
                    batch_records = self._llm.extract(
                        context_chunks=[c.text for c in batch],
                        instructions=plan.raw_instructions,
                        field_names=field_names,
                        source_url=batch[0].source_url if batch else "",
                    )
                    records.extend(batch_records)
                    llm_calls += 1
                except AIProcessingError as exc:
                    logger.error("LLM extraction batch failed", error=str(exc))
                    warnings.append(f"LLM batch {llm_calls + 1} failed: {exc}")

        # Deduplicate records
        records = self._deduplicate(records, field_names)

        elapsed = time.time() - start
        logger.info(
            "AI processing complete",
            records=len(records),
            llm_calls=llm_calls,
            elapsed_s=round(elapsed, 2),
        )

        return AIProcessingResult(
            records=records,
            total_chunks_processed=total_chunks,
            total_chunks_indexed=len(all_chunks),
            top_k_retrieved=len(top_chunks),
            llm_calls=llm_calls,
            elapsed_seconds=elapsed,
            warnings=warnings,
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _check_llm(self) -> bool:
        if self._llm_available is None:
            self._llm_available = self._llm.is_available()
        return self._llm_available

    def _build_search_query(self, plan: ExtractionPlan) -> str:
        """Combine raw instructions + field names for richer semantic query."""
        field_hint = " ".join(f.name for f in plan.fields[:10])
        return f"{plan.raw_instructions} {field_hint}"

    def _fallback_extract(
        self, chunks: List[TextChunk], field_names: List[str]
    ) -> List[Dict[str, Any]]:
        """When LLM is unavailable, return raw chunk text as records."""
        return [
            {fn: (chunk.text[:200] if fn == "content" else None) for fn in field_names}
            | {"raw_text": chunk.text[:500], "source": chunk.source_url}
            for chunk in chunks[:100]
        ]

    def _deduplicate(
        self, records: List[Dict[str, Any]], key_fields: List[str]
    ) -> List[Dict[str, Any]]:
        """Remove duplicate records by hashing their key fields."""
        seen:   set[str]         = set()
        unique: List[Dict[str, Any]] = []
        for rec in records:
            fingerprint = "|".join(str(rec.get(f, "")) for f in key_fields[:3])
            h = hashlib.md5(fingerprint.encode()).hexdigest() if fingerprint else None
            if h and h not in seen:
                seen.add(h)
                unique.append(rec)
            elif not h:
                unique.append(rec)
        return unique


import hashlib  # noqa: E402 (needed for _deduplicate)
