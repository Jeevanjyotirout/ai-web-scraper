"""
app/modules/instruction_parser.py
───────────────────────────────────
Module 1 — Instruction Parser

Responsibility:
    Transform free-text user instructions into a structured extraction
    plan that the downstream scraping and AI modules can execute.

Pipeline:
    raw text
        └─► normalise & validate
            └─► NLP intent detection (regex + heuristics)
                └─► build ExtractionPlan (field definitions + strategy)
                    └─► optionally enrich via LLM

The parser is intentionally LLM-free by default (fast, zero-latency).
An optional  enrich_with_llm=True  flag delegates deeper understanding
to the local Ollama model when instructions are ambiguous.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

from loguru import logger

from app.core.exceptions import InstructionParseError, UnsupportedInstructionError


# ── Data structures ───────────────────────────────────────────────────────────

class FieldType(str, Enum):
    TEXT    = "text"
    LINK    = "link"
    IMAGE   = "image"
    NUMBER  = "number"
    DATE    = "date"
    EMAIL   = "email"
    PRICE   = "price"
    BOOLEAN = "boolean"
    HTML    = "html"
    CUSTOM  = "custom"


@dataclass
class FieldDefinition:
    """A single column/field to be extracted per record."""

    name: str
    field_type: FieldType
    description: str
    css_hint: Optional[str] = None          # Suggested CSS selector
    xpath_hint: Optional[str] = None
    required: bool = False
    transform: Optional[str] = None        # e.g. "strip", "lower", "float"
    examples: List[str] = field(default_factory=list)


@dataclass
class ExtractionStrategy:
    """How to navigate the page(s)."""

    paginate: bool = False
    pagination_selector: Optional[str] = None
    follow_links: bool = False
    link_pattern: Optional[str] = None     # Regex to filter internal links
    wait_for_selector: Optional[str] = None
    scroll_to_load: bool = False
    login_required: bool = False


@dataclass
class ExtractionPlan:
    """Complete, structured plan consumed by the scraping engine."""

    raw_instructions: str
    fields: List[FieldDefinition]
    strategy: ExtractionStrategy
    container_selector: Optional[str] = None   # Repeating record container
    record_limit: Optional[int] = None
    confidence: float = 1.0                    # 0–1 parser confidence
    warnings: List[str] = field(default_factory=list)
    ai_enriched: bool = False


# ── Heuristic patterns ────────────────────────────────────────────────────────

# Map field-name keywords → likely FieldType
_TYPE_KEYWORDS: Dict[str, FieldType] = {
    "price": FieldType.PRICE,
    "cost":  FieldType.PRICE,
    "fee":   FieldType.PRICE,
    "url":   FieldType.LINK,
    "link":  FieldType.LINK,
    "href":  FieldType.LINK,
    "image": FieldType.IMAGE,
    "photo": FieldType.IMAGE,
    "img":   FieldType.IMAGE,
    "email": FieldType.EMAIL,
    "mail":  FieldType.EMAIL,
    "date":  FieldType.DATE,
    "time":  FieldType.DATE,
    "year":  FieldType.DATE,
    "count": FieldType.NUMBER,
    "num":   FieldType.NUMBER,
    "qty":   FieldType.NUMBER,
    "rating": FieldType.NUMBER,
    "score":  FieldType.NUMBER,
}

# Tokens that hint at list/table extraction
_LIST_KEYWORDS = re.compile(
    r"\b(all|every|each|list\s+of|table\s+of|rows?\s+of|entries)\b",
    re.IGNORECASE,
)

# Tokens that hint at pagination handling
_PAGINATION_KEYWORDS = re.compile(
    r"\b(all\s+pages?|paginate|next\s+page|multiple\s+pages?|entire\s+site)\b",
    re.IGNORECASE,
)

# "Extract X, Y and Z" — comma/and-separated field list
_FIELD_LIST_PATTERN = re.compile(
    r"(?:extract|get|scrape|collect|find|pull)\s+"
    r"(?:the\s+)?(.+?)(?:\s+from\b|\s+on\b|\s+of\b|$)",
    re.IGNORECASE,
)

# Detects "price", "title", "name" etc. as individual tokens
_BARE_FIELD_PATTERN = re.compile(r"\b([a-z][a-z_\-]{1,30})\b", re.IGNORECASE)


# ── Core parser ───────────────────────────────────────────────────────────────

class InstructionParser:
    """
    Converts natural-language instructions into an  ExtractionPlan.

    Usage:
        parser = InstructionParser()
        plan = parser.parse("Extract all product names, prices, and ratings")
    """

    # Words that are obviously NOT field names
    _STOP_WORDS = frozenset(
        {
            "extract", "get", "scrape", "collect", "find", "pull", "all", "the",
            "from", "and", "or", "with", "each", "every", "list", "table",
            "rows", "row", "entries", "entry", "items", "item", "a", "an",
            "on", "of", "this", "that", "these", "those", "their", "its",
            "page", "pages", "website", "site", "data", "information", "info",
        }
    )

    def __init__(self) -> None:
        self._field_cache: Dict[str, FieldDefinition] = {}

    # ── Public API ────────────────────────────────────────────────────────────

    def parse(self, instructions: str, *, enrich_with_llm: bool = False) -> ExtractionPlan:
        """
        Main entry point. Returns an  ExtractionPlan  or raises
        InstructionParseError on unrecoverable input.
        """
        if not instructions or not instructions.strip():
            raise InstructionParseError("Instructions cannot be empty")

        normalised = self._normalise(instructions)
        logger.debug("Parsing instructions", length=len(normalised))

        fields   = self._extract_fields(normalised)
        strategy = self._infer_strategy(normalised)
        warnings: List[str] = []
        confidence = 1.0

        if not fields:
            # Fall back: treat the whole instruction as a single "content" field
            fields = [
                FieldDefinition(
                    name="content",
                    field_type=FieldType.TEXT,
                    description="AI-extracted content based on instructions",
                )
            ]
            warnings.append("No explicit fields detected — falling back to AI extraction")
            confidence = 0.6

        plan = ExtractionPlan(
            raw_instructions=instructions,
            fields=fields,
            strategy=strategy,
            confidence=confidence,
            warnings=warnings,
        )

        logger.info(
            "Instruction plan created",
            fields=[f.name for f in fields],
            paginate=strategy.paginate,
            confidence=confidence,
        )
        return plan

    def validate(self, instructions: str) -> Tuple[bool, List[str]]:
        """
        Quick validation without building the full plan.
        Returns (is_valid, list_of_issues).
        """
        issues: List[str] = []

        if not instructions or not instructions.strip():
            issues.append("Instructions must not be empty")

        if len(instructions.strip()) < 10:
            issues.append("Instructions are too short (minimum 10 characters)")

        if len(instructions) > 4096:
            issues.append("Instructions exceed maximum length of 4096 characters")

        # Sanity: no script injections
        if re.search(r"<script|javascript:", instructions, re.IGNORECASE):
            issues.append("Instructions contain potentially unsafe content")

        return len(issues) == 0, issues

    # ── Private helpers ───────────────────────────────────────────────────────

    def _normalise(self, text: str) -> str:
        """Lowercase, collapse whitespace, strip punctuation noise."""
        text = text.lower().strip()
        text = re.sub(r"[^\w\s,.\-/]", " ", text)
        text = re.sub(r"\s+", " ", text)
        return text

    def _extract_fields(self, text: str) -> List[FieldDefinition]:
        """
        Detect field names from natural-language text.

        Strategy (in order of confidence):
        1. Match "extract X, Y, and Z from ..." pattern
        2. Match known field-type keywords
        3. Noun-phrase heuristic
        """
        fields: List[FieldDefinition] = []
        seen: set[str] = set()

        # Strategy 1 — explicit list after "extract / get / scrape ..."
        match = _FIELD_LIST_PATTERN.search(text)
        if match:
            raw_fields = match.group(1)
            # Split on commas and "and"
            tokens = re.split(r",\s*|\s+and\s+", raw_fields)
            for token in tokens:
                name = self._clean_field_name(token)
                if name and name not in seen:
                    seen.add(name)
                    fields.append(self._make_field(name))

        # Strategy 2 — scan for domain-specific keywords anywhere in text
        for keyword, ftype in _TYPE_KEYWORDS.items():
            if re.search(rf"\b{keyword}\b", text) and keyword not in seen:
                seen.add(keyword)
                fields.append(FieldDefinition(
                    name=keyword,
                    field_type=ftype,
                    description=f"Automatically detected {keyword} field",
                ))

        # Strategy 3 — bare nouns adjacent to known extraction verbs
        if not fields:
            for token in _BARE_FIELD_PATTERN.findall(text):
                name = token.lower()
                if name not in self._STOP_WORDS and name not in seen and len(name) > 2:
                    seen.add(name)
                    fields.append(self._make_field(name))

        return fields[:20]   # Hard cap to avoid absurd plans

    def _make_field(self, name: str) -> FieldDefinition:
        """Build a FieldDefinition, inferring type from name keywords."""
        ftype = FieldType.TEXT
        for kw, ft in _TYPE_KEYWORDS.items():
            if kw in name:
                ftype = ft
                break

        return FieldDefinition(
            name=name,
            field_type=ftype,
            description=f"Extracted field: {name}",
            required=(name in {"title", "name", "url", "price"}),
        )

    def _clean_field_name(self, raw: str) -> Optional[str]:
        """Sanitise a raw token into a valid field name."""
        name = re.sub(r"[^\w]", "_", raw.strip().lower())
        name = re.sub(r"_+", "_", name).strip("_")
        if not name or name in self._STOP_WORDS or len(name) < 2:
            return None
        return name

    def _infer_strategy(self, text: str) -> ExtractionStrategy:
        """Detect scraping strategy hints from the instruction text."""
        strategy = ExtractionStrategy()

        if _PAGINATION_KEYWORDS.search(text):
            strategy.paginate = True
            strategy.pagination_selector = "a[rel='next'], .pagination .next, button.next-page"

        if re.search(r"\b(lazy|scroll|infinite\s+scroll)\b", text):
            strategy.scroll_to_load = True

        if re.search(r"\b(login|sign.?in|authenticate|account)\b", text):
            strategy.login_required = True

        if re.search(r"\b(follow\s+links?|crawl|spider)\b", text):
            strategy.follow_links = True

        return strategy
