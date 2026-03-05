"""
output/formatter.py
-------------------
Stage 8: Structured output formatting and persistence.

Writes results as:
- Validated JSON to stdout
- Per-document JSON files to output/
- A consolidated JSONL file for batch runs
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from config.settings import OutputConfig
from models.schema import StructuredOutput

logger = logging.getLogger(__name__)

# Required output fields per specification
_REQUIRED_FIELDS = {"title", "author", "date", "summary", "keywords"}


class OutputFormatter:
    """
    Validates and persists StructuredOutput objects.

    Parameters
    ----------
    config : OutputConfig
    """

    def __init__(self, config: Optional[OutputConfig] = None) -> None:
        self.config = config or OutputConfig()
        self.config.output_dir.mkdir(parents=True, exist_ok=True)

    # ── Public API ────────────────────────────────────────────────────────────

    def format(self, output: StructuredOutput) -> dict[str, Any]:
        """
        Validate and return the spec-compliant dict.

        Parameters
        ----------
        output : StructuredOutput

        Returns
        -------
        dict with exactly: title, author, date, summary, keywords
        """
        data = output.to_dict()
        self._validate(data)
        logger.info("Output validated: title=%r, keywords=%s", data["title"], data["keywords"])
        return data

    def format_json(self, output: StructuredOutput) -> str:
        """Return the spec-compliant JSON string."""
        data = self.format(output)
        return json.dumps(data, indent=self.config.json_indent, ensure_ascii=False)

    def save(self, output: StructuredOutput, filename: Optional[str] = None) -> Path:
        """
        Persist the structured output to a JSON file.

        Parameters
        ----------
        output   : StructuredOutput
        filename : optional file stem (auto-generated if None)

        Returns
        -------
        Path  of the written file
        """
        data = self.format(output)

        if filename is None:
            ts    = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
            safe  = _safe_stem(output.title or output.doc_id or "output")
            filename = f"{ts}_{safe}.json"

        path = self.config.output_dir / filename
        path.write_text(
            json.dumps(data, indent=self.config.json_indent, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.info("Output saved → %s", path)
        return path

    def append_jsonl(
        self,
        output: StructuredOutput,
        filename: str = "results.jsonl",
    ) -> None:
        """Append a single JSON line to the consolidated JSONL file."""
        data = self.format(output)
        path = self.config.output_dir / filename
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(data, ensure_ascii=False) + "\n")
        logger.debug("Appended to %s", path)

    # ── Validation ────────────────────────────────────────────────────────────

    def _validate(self, data: dict[str, Any]) -> None:
        """Raise ValueError if required fields are missing or have wrong types."""
        for field in _REQUIRED_FIELDS:
            if field not in data:
                raise ValueError(f"Output missing required field: {field!r}")

        if not isinstance(data["keywords"], list):
            raise TypeError(f"'keywords' must be a list, got {type(data['keywords'])}")

        for f in ("title", "author", "date", "summary"):
            if not isinstance(data[f], str):
                raise TypeError(f"'{f}' must be a string, got {type(data[f])}")


def _safe_stem(text: str, max_len: int = 40) -> str:
    """Convert text to a filesystem-safe stem."""
    import re
    stem = re.sub(r"[^\w\s-]", "", text).strip().lower()
    stem = re.sub(r"[\s-]+", "_", stem)
    return stem[:max_len] or "output"
