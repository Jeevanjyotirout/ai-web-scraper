"""
llm/processor.py
----------------
Stage 7: Local LLM processing using TinyLlama-1.1B-Chat-v1.0.

Design
------
- Uses HuggingFace transformers pipeline for text-generation.
- Structures the prompt using TinyLlama's chat template
  (<|system|> / <|user|> / <|assistant|> tokens).
- Enforces JSON output via a strict system prompt + post-processing parser.
- Falls back gracefully: if LLM JSON parsing fails, constructs output from
  heuristics so the pipeline always returns a valid StructuredOutput.
- Lazy-loads the model on first call to keep import times fast.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

from config.settings import LLMConfig
from models.schema import RetrievedChunk, StructuredOutput
from utils.text_utils import extract_keywords, extract_title_from_text, truncate

logger = logging.getLogger(__name__)

# Regex to extract the first JSON object from a string
_JSON_RE = re.compile(r"\{[\s\S]*?\}", re.DOTALL)


class LLMProcessor:
    """
    Wraps TinyLlama (or any HuggingFace causal-LM) for RAG output generation.

    Parameters
    ----------
    config : LLMConfig
    """

    def __init__(self, config: Optional[LLMConfig] = None) -> None:
        self.config = config or LLMConfig()
        self._pipe  = None   # lazy-loaded

    # ── Lazy model loading ────────────────────────────────────────────────────

    def _load(self) -> None:
        """Load the model + tokenizer into a text-generation pipeline."""
        if self._pipe is not None:
            return

        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline

        logger.info("Loading LLM: %s (device=%s) …", self.config.model_name, self.config.device)

        dtype_map = {
            "float32": torch.float32,
            "float16": torch.float16,
            "bfloat16": torch.bfloat16,
        }
        torch_dtype = dtype_map.get(self.config.torch_dtype, torch.float32)

        tokenizer = AutoTokenizer.from_pretrained(
            self.config.model_name,
            trust_remote_code=self.config.trust_remote_code,
        )

        model_kwargs: dict[str, Any] = {
            "torch_dtype": torch_dtype,
            "low_cpu_mem_usage": True,
        }

        if self.config.load_in_4bit:
            try:
                from transformers import BitsAndBytesConfig
                model_kwargs["quantization_config"] = BitsAndBytesConfig(
                    load_in_4bit=True,
                    bnb_4bit_compute_dtype=torch.float16,
                )
                logger.info("4-bit quantisation enabled.")
            except ImportError:
                logger.warning("bitsandbytes not installed — ignoring 4-bit flag.")

        model = AutoModelForCausalLM.from_pretrained(
            self.config.model_name,
            trust_remote_code=self.config.trust_remote_code,
            **model_kwargs,
        )

        self._pipe = pipeline(
            "text-generation",
            model=model,
            tokenizer=tokenizer,
            device=self.config.device if self.config.device != "cpu" else -1,
            max_new_tokens=self.config.max_new_tokens,
            temperature=self.config.temperature,
            top_p=self.config.top_p,
            repetition_penalty=self.config.repetition_penalty,
            do_sample=self.config.do_sample,
        )
        logger.info("LLM ready.")

    # ── Public API ────────────────────────────────────────────────────────────

    def generate(
        self,
        retrieved_chunks: list[RetrievedChunk],
        source_metadata: Optional[dict] = None,
    ) -> StructuredOutput:
        """
        Generate a StructuredOutput from retrieved context chunks.

        Parameters
        ----------
        retrieved_chunks : list[RetrievedChunk]
        source_metadata  : optional dict with hints (title, author, date …)

        Returns
        -------
        StructuredOutput
        """
        self._load()

        meta  = source_metadata or {}
        context = self._build_context(retrieved_chunks)
        prompt  = self._build_prompt(context, meta)

        logger.info("Sending prompt to LLM (%d chars) …", len(prompt))

        try:
            raw = self._pipe(prompt, return_full_text=False)
            generated_text: str = raw[0]["generated_text"].strip()
            logger.debug("LLM raw output (first 300 chars): %s", generated_text[:300])
        except Exception as exc:
            logger.error("LLM generation failed: %s", exc, exc_info=True)
            generated_text = ""

        output = self._parse_output(generated_text, context, meta, retrieved_chunks)
        return output

    # ── Prompt construction ───────────────────────────────────────────────────

    def _build_context(self, chunks: list[RetrievedChunk], max_chars: int = 3500) -> str:
        parts, total = [], 0
        for r in chunks:
            t = r.chunk.text.strip()
            if total + len(t) > max_chars:
                remaining = max_chars - total
                if remaining > 80:
                    parts.append(t[:remaining] + "…")
                break
            parts.append(t)
            total += len(t)
        return "\n\n".join(parts)

    def _build_prompt(self, context: str, meta: dict) -> str:
        """
        Build a TinyLlama chat-template prompt that instructs the model
        to return *only* a JSON object with the required fields.
        """
        system = (
            "You are a precise information extraction assistant. "
            "You will be given text content and must extract structured information from it. "
            "Respond ONLY with a valid JSON object — no markdown, no explanation, no preamble. "
            "The JSON must have exactly these fields: "
            "title (string), author (string), date (string), summary (string), keywords (array of strings). "
            "If a field cannot be determined from the text, use an empty string or empty array."
        )

        hints = ""
        if meta.get("title"):
            hints += f"\nKnown title hint: {meta['title']}"
        if meta.get("author"):
            hints += f"\nKnown author hint: {meta['author']}"
        if meta.get("date"):
            hints += f"\nKnown date hint: {meta['date']}"

        user = (
            f"Extract structured information from the following text and return ONLY JSON.{hints}\n\n"
            f"TEXT:\n{context}\n\n"
            "Return ONLY the JSON object:"
        )

        # TinyLlama chat template
        prompt = (
            f"<|system|>\n{system}</s>\n"
            f"<|user|>\n{user}</s>\n"
            f"<|assistant|>\n"
        )
        return prompt

    # ── Output parsing ────────────────────────────────────────────────────────

    def _parse_output(
        self,
        generated: str,
        context: str,
        meta: dict,
        chunks: list[RetrievedChunk],
    ) -> StructuredOutput:
        """
        Parse LLM output to StructuredOutput.
        Falls back to heuristic extraction if JSON parsing fails.
        """
        # Try to extract JSON from the generated text
        parsed: Optional[dict] = None

        if generated:
            # First try direct parse
            try:
                parsed = json.loads(generated)
            except json.JSONDecodeError:
                pass

            # Try extracting first JSON object via regex
            if parsed is None:
                match = _JSON_RE.search(generated)
                if match:
                    try:
                        parsed = json.loads(match.group())
                    except json.JSONDecodeError:
                        pass

        if parsed and isinstance(parsed, dict):
            logger.info("LLM JSON parsed successfully.")
            output = StructuredOutput(
                title    = str(parsed.get("title",    "") or "").strip(),
                author   = str(parsed.get("author",   "") or "").strip(),
                date     = str(parsed.get("date",     "") or "").strip(),
                summary  = str(parsed.get("summary",  "") or "").strip(),
                keywords = [str(k).strip() for k in parsed.get("keywords", []) if k],
                source   = meta.get("source", ""),
                doc_id   = meta.get("doc_id", ""),
                chunks_used = len(chunks),
            )
        else:
            logger.warning("LLM did not return valid JSON — using heuristic fallback.")
            output = self._heuristic_fallback(context, meta, chunks)

        # Fill in blanks from metadata hints
        if not output.title  and meta.get("title"):  output.title  = meta["title"]
        if not output.author and meta.get("author"): output.author = meta["author"]
        if not output.date   and meta.get("date"):   output.date   = meta["date"]
        if not output.keywords:
            output.keywords = extract_keywords(context, top_n=8)

        return output

    def _heuristic_fallback(
        self,
        context: str,
        meta: dict,
        chunks: list[RetrievedChunk],
    ) -> StructuredOutput:
        """Construct a best-effort StructuredOutput without LLM JSON."""
        title = (
            meta.get("title")
            or extract_title_from_text(context)
            or "Untitled"
        )
        sentences = [s for s in context.split(".") if len(s.strip()) > 20]
        summary = ". ".join(sentences[:3]).strip()
        if summary and not summary.endswith("."):
            summary += "."

        return StructuredOutput(
            title       = title,
            author      = meta.get("author", ""),
            date        = meta.get("date", ""),
            summary     = truncate(summary, max_chars=500),
            keywords    = extract_keywords(context, top_n=8),
            source      = meta.get("source", ""),
            doc_id      = meta.get("doc_id", ""),
            chunks_used = len(chunks),
        )
