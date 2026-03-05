"""
extracted_data.py
-----------------
Structured data model for content extracted from a scraped page.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class ExtractedData:
    """
    Fully structured representation of a scraped page's content.

    Attributes
    ----------
    title : str
        Page title (<title> or first <h1>).
    meta : dict[str, str]
        Common <meta> tag values (description, keywords, etc.).
    headings : dict[str, list[str]]
        Mapping of heading level (h1–h6) → list of heading texts.
    paragraphs : list[str]
        Body paragraphs filtered of noise and short captions.
    links : list[dict[str, str]]
        All page links as {"href": ..., "text": ...}.
    tables : list[list[list[str]]]
        All tables as 3-D arrays: table → row → cell.
    images : list[dict[str, str]]
        All images as {"src": ..., "alt": ...}.
    raw_text : str
        Full visible text of the page (for FTS / NLP pipelines).
    open_graph : dict[str, str]
        Open Graph and Twitter Card meta properties.
    extracted_at : datetime
        UTC timestamp of extraction.
    """

    title: str = ""
    meta: dict[str, str] = field(default_factory=dict)
    headings: dict[str, list[str]] = field(default_factory=dict)
    paragraphs: list[str] = field(default_factory=list)
    links: list[dict[str, str]] = field(default_factory=list)
    tables: list[list[list[str]]] = field(default_factory=list)
    images: list[dict[str, str]] = field(default_factory=list)
    raw_text: str = ""
    open_graph: dict[str, str] = field(default_factory=dict)
    extracted_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable dictionary representation."""
        return {
            "title": self.title,
            "meta": self.meta,
            "headings": self.headings,
            "paragraphs": self.paragraphs,
            "links": self.links,
            "tables": self.tables,
            "images": self.images,
            "raw_text": self.raw_text,
            "open_graph": self.open_graph,
            "extracted_at": self.extracted_at.isoformat(),
        }

    # ------------------------------------------------------------------
    # Convenience properties
    # ------------------------------------------------------------------

    @property
    def word_count(self) -> int:
        """Approximate word count of the raw visible text or paragraphs."""
        if self.raw_text:
            return len(self.raw_text.split())
        return sum(len(p.split()) for p in self.paragraphs)

    @property
    def description(self) -> str:
        """Best-effort page description from meta tags or first paragraph."""
        if self.meta.get("description"):
            return self.meta["description"]
        if self.open_graph.get("og:description"):
            return self.open_graph["og:description"]
        if self.paragraphs:
            return self.paragraphs[0]
        return ""

    def __repr__(self) -> str:
        return (
            f"ExtractedData(title={self.title!r}, "
            f"paragraphs={len(self.paragraphs)}, "
            f"links={len(self.links)}, "
            f"words≈{self.word_count})"
        )
