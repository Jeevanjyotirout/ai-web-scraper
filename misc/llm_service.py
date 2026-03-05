import json
import ollama
from typing import Optional
from app.core.config import settings
from app.utils.text_utils import extract_json_from_llm, truncate_text
from loguru import logger


class LLMService:
    """Local LLM inference via Ollama (TinyLlama / Phi)."""

    def __init__(self):
        self._client = ollama.Client(host=settings.OLLAMA_HOST)

    def health_check(self) -> bool:
        try:
            models = self._client.list()
            available = [m.model for m in models.models]
            logger.info(f"Ollama models available: {available}")
            return settings.OLLAMA_MODEL in " ".join(available)
        except Exception as e:
            logger.warning(f"Ollama health check failed: {e}")
            return False

    def extract_structured_data(
        self,
        context_chunks: list[str],
        instructions: str,
        source_url: str,
    ) -> list[dict]:
        """
        Use LLM to extract structured rows from context chunks
        according to user instructions.
        Returns a list of dicts (rows).
        """
        context_text = "\n\n---\n\n".join(context_chunks)
        context_text = truncate_text(context_text, max_chars=3500)

        prompt = f"""You are a data extraction assistant. Your task is to extract structured data from web page content.

SOURCE URL: {source_url}

USER INSTRUCTIONS:
{instructions}

WEB PAGE CONTENT:
{context_text}

TASK: Extract all relevant data items as a JSON array. Each item should be an object (dict) with consistent keys.
- Follow the user instructions exactly
- If the user asks for a table, return rows as objects
- Use clear, descriptive keys (e.g. "name", "price", "description", "url", "date")
- If a field is missing for an item, use null
- Return ONLY valid JSON, no explanation or markdown

JSON OUTPUT:"""

        try:
            response = self._client.chat(
                model=settings.OLLAMA_MODEL,
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": 0.1, "num_ctx": 4096},
            )
            raw = response.message.content
            json_str = extract_json_from_llm(raw)
            data = json.loads(json_str)

            if isinstance(data, dict):
                data = [data]
            elif not isinstance(data, list):
                logger.warning(f"LLM returned unexpected type: {type(data)}")
                return []

            return [row for row in data if isinstance(row, dict)]

        except json.JSONDecodeError as e:
            logger.warning(f"LLM JSON parse error: {e} | raw: {raw[:300]}")
            return self._fallback_extract(context_chunks, instructions)
        except Exception as e:
            logger.error(f"LLM extraction failed: {e}")
            return []

    def _fallback_extract(self, chunks: list[str], instructions: str) -> list[dict]:
        """Fallback: return raw chunks as plain rows."""
        return [{"content": chunk, "source": "raw_extract"} for chunk in chunks[:20]]

    def infer_columns(self, sample_rows: list[dict]) -> list[str]:
        """Ask LLM to suggest clean column names from sample data."""
        if not sample_rows:
            return []
        keys = set()
        for row in sample_rows[:5]:
            keys.update(row.keys())
        return sorted(keys)
