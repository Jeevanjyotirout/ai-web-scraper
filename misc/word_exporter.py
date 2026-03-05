"""
word_exporter.py
----------------
Generates a professionally formatted Word (.docx) report via the docx-js
Node.js library (invoked as a subprocess).  This ensures best-in-class Word
XML generation without the limitations of python-docx.

The exported document includes:
  - Cover page
  - Table of contents
  - Dataset overview stats table
  - One full-page section per article (meta, summary, tags, metrics)
  - Running header + page-numbered footer
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

from data import Article

logger = logging.getLogger(__name__)

_JS_SCRIPT = Path(__file__).parent / "build_docx.js"


def _articles_to_json(articles: list[Article]) -> str:
    """Serialise articles to the JSON format expected by build_docx.js."""
    payload = [
        {
            "id":              a.id,
            "title":           a.title,
            "author":          a.author,
            "category":        a.category,
            "date":            a.date,
            "word_count":      a.word_count,
            "reads":           a.reads,
            "likes":           a.likes,
            "engagement_rate": a.engagement_rate,
            "status":          a.status,
            "tags":            a.tags,
            "summary":         a.summary,
        }
        for a in articles
    ]
    return json.dumps(payload)


class WordExporter:
    """
    Generates a Word (.docx) report for a list of Article objects.

    Usage
    -----
        exporter = WordExporter(articles)
        path = exporter.export("output/articles_report.docx")
    """

    def __init__(self, articles: list[Article]) -> None:
        self.articles = articles

    def export(self, output_path: str | Path) -> Path:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        articles_json = _articles_to_json(self.articles)

        result = subprocess.run(
            ["node", str(_JS_SCRIPT), articles_json, str(path)],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            logger.error("docx-js error:\n%s", result.stderr)
            raise RuntimeError(
                f"Word document generation failed.\nstderr: {result.stderr}"
            )

        logger.info("Word document saved → %s", path)
        return path
