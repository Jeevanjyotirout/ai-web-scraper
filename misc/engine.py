"""
src/llm/engine.py
TinyLlama-1.1B-Chat GGUF inference via llama-cpp-python.

Responsibilities
  1. Build a TinyLlama chat-format prompt from retrieved context chunks
  2. Run local inference (temperature=0.1 for deterministic extraction)
  3. Parse JSON from raw LLM output with three fallback strategies
  4. Return a validated RAGOutput dataclass

Output schema
  { "title": str, "author": str, "date": str,
    "summary": str, "keywords": list[str] }
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from config.settings import cfg
from src.utils.logger import get_logger
from src.utils.text_cleaner import truncate

log = get_logger(__name__)

# ────────────────────────────────────────────────────────────────────────────────
# Output dataclass
# ────────────────────────────────────────────────────────────────────────────────

@dataclass
class RAGOutput:
    title:    str       = "Unknown"
    author:   str       = "Unknown"
    date:     str       = "Unknown"
    summary:  str       = ""
    keywords: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "title":    self.title,
            "author":   self.author,
            "date":     self.date,
            "summary":  self.summary,
            "keywords": self.keywords,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def __repr__(self) -> str:  # noqa: D105
        return (
            f"RAGOutput(\n"
            f"  title   = {self.title!r}\n"
            f"  author  = {self.author!r}\n"
            f"  date    = {self.date!r}\n"
            f"  summary = {self.summary[:80]!r}…\n"
            f"  keywords= {self.keywords}\n"
            ")"
        )


# ────────────────────────────────────────────────────────────────────────────────
# Prompt builder
# ────────────────────────────────────────────────────────────────────────────────

_SYSTEM = (
    "You are a precise information-extraction assistant. "
    "Output ONLY valid JSON — no explanations, no markdown."
)

_TEMPLATE = """\
Extract information from the context below and return this JSON object:
{{
  "title":    "<main title or topic, max 120 chars>",
  "author":   "<full author name or 'Unknown'>",
  "date":     "<YYYY-MM-DD or 'Unknown'>",
  "summary":  "<2-3 factual sentences>",
  "keywords": ["<kw1>","<kw2>","<kw3>","<kw4>","<kw5>"]
}}

Rules:
- Return ONLY the JSON object shown above.
- keywords must be a JSON array of exactly 5 strings.
- date must be YYYY-MM-DD format or the string "Unknown".
- Do NOT add any text before or after the JSON.

CONTEXT:
{context}

QUESTION: {query}

JSON:"""


def _build_prompt(context: str, query: str) -> str:
    ctx = truncate(context, 1600)
    body = _TEMPLATE.format(context=ctx, query=query)
    # TinyLlama ChatML template
    return (
        f"<|system|>\n{_SYSTEM}</s>\n"
        f"<|user|>\n{body}</s>\n"
        f"<|assistant|>\n"
    )


def _build_context(hits: list) -> str:
    parts = []
    for i, h in enumerate(hits, 1):
        text = h.text if hasattr(h, "text") else str(h)
        parts.append(f"[{i}] {text.strip()}")
    return "\n\n".join(parts)


# ────────────────────────────────────────────────────────────────────────────────
# JSON parser (three fallback strategies)
# ────────────────────────────────────────────────────────────────────────────────

def _parse_json(raw: str) -> Optional[dict]:
    raw = raw.strip()

    # Strategy 1 — direct parse
    try:
        d = json.loads(raw)
        if isinstance(d, dict):
            return d
    except json.JSONDecodeError:
        pass

    # Strategy 2 — find outermost { … }
    m = re.search(r"\{[\s\S]*\}", raw)
    if m:
        try:
            d = json.loads(m.group(0))
            if isinstance(d, dict):
                return d
        except json.JSONDecodeError:
            pass

    # Strategy 3 — strip markdown fences + repair trailing commas
    cleaned = re.sub(r"```(?:json)?\s*", "", raw).strip().strip("`")
    cleaned = re.sub(r",\s*([}\]])", r"\1", cleaned)  # trailing commas
    brace = cleaned.find("{")
    if brace >= 0:
        cleaned = cleaned[brace:]
        if cleaned.count("{") > cleaned.count("}"):
            cleaned += "}"
        try:
            d = json.loads(cleaned)
            if isinstance(d, dict):
                return d
        except json.JSONDecodeError:
            pass

    log.warning("All JSON-parse strategies failed")
    return None


def _dict_to_output(d: dict) -> RAGOutput:
    kw = d.get("keywords", [])
    if isinstance(kw, str):
        kw = [k.strip() for k in re.split(r"[,;]", kw) if k.strip()]
    elif isinstance(kw, list):
        kw = [str(k).strip() for k in kw if k][:10]

    date = str(d.get("date", "Unknown")).strip()
    if date.lower() in ("", "none", "null", "n/a"):
        date = "Unknown"

    return RAGOutput(
        title    = str(d.get("title",   "Unknown"))[:200].strip() or "Unknown",
        author   = str(d.get("author",  "Unknown"))[:100].strip() or "Unknown",
        date     = date,
        summary  = str(d.get("summary", ""))[:1000].strip(),
        keywords = kw,
    )


# ────────────────────────────────────────────────────────────────────────────────
# TinyLlama engine
# ────────────────────────────────────────────────────────────────────────────────

class LLMEngine:
    """
    Lazy-loads TinyLlama GGUF on first call to extract().

    Usage
    -----
    engine = LLMEngine()
    output = engine.extract(hits, query="What is this document about?")
    print(output.to_json())
    """

    def __init__(self) -> None:
        self._llm = None   # loaded lazily

    # ── public ─────────────────────────────────────────────────────────────────

    def extract(self, hits: list, query: str = "What is this document about?") -> RAGOutput:
        context = _build_context(hits)
        if not context.strip():
            log.warning("Empty context — returning default RAGOutput")
            return RAGOutput()

        prompt = _build_prompt(context, query)
        log.debug(f"Prompt length: {len(prompt)} chars")

        raw = self._infer(prompt)
        log.debug(f"Raw LLM output: {raw[:300]}")

        parsed = _parse_json(raw)
        if parsed is None:
            log.warning("Returning RAGOutput defaults (JSON parse failed)")
            return RAGOutput()

        out = _dict_to_output(parsed)
        log.info(f"Extracted  title={out.title!r}  keywords={out.keywords}")
        return out

    def model_exists(self) -> bool:
        return Path(cfg.model_path).exists()

    # ── private ────────────────────────────────────────────────────────────────

    def _load(self) -> None:
        if self._llm is not None:
            return

        mp = Path(cfg.model_path)
        if not mp.exists():
            raise FileNotFoundError(
                f"Model not found: {mp}\n"
                "Download with:\n"
                "  bash scripts/download_model.sh\n"
                "or:\n"
                "  huggingface-cli download TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF "
                "tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf --local-dir ./models"
            )

        try:
            from llama_cpp import Llama
        except ImportError:
            raise ImportError(
                "llama-cpp-python not installed.\n"
                "Run: pip install llama-cpp-python --prefer-binary"
            )

        log.info(f"Loading TinyLlama: {mp}")
        self._llm = Llama(
            model_path   = str(mp),
            n_ctx        = cfg.llm_ctx,
            n_threads    = cfg.llm_threads,
            n_gpu_layers = cfg.llm_gpu,
            verbose      = cfg.llm_verbose,
            chat_format  = "chatml",
        )
        log.info("TinyLlama ready")

    def _infer(self, prompt: str) -> str:
        self._load()
        try:
            resp = self._llm(
                prompt,
                max_tokens  = cfg.llm_tokens,
                temperature = cfg.llm_temp,
                top_p       = cfg.llm_top_p,
                stop        = ["</s>", "<|user|>", "<|system|>"],
                echo        = False,
            )
            return resp["choices"][0]["text"].strip()
        except Exception as exc:
            raise RuntimeError(f"LLM inference failed: {exc}") from exc
