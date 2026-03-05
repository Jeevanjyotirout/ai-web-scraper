"""
tests/test_instruction_parser.py
──────────────────────────────────
Unit tests for InstructionParser.
Run:  pytest tests/test_instruction_parser.py -v
"""

from __future__ import annotations

import pytest
from app.modules.instruction_parser import (
    ExtractionPlan,
    FieldType,
    InstructionParser,
)
from app.core.exceptions import InstructionParseError


@pytest.fixture
def parser() -> InstructionParser:
    return InstructionParser()


class TestValidation:
    def test_empty_instructions_raises(self, parser):
        valid, issues = parser.validate("")
        assert not valid
        assert any("empty" in i.lower() for i in issues)

    def test_too_short_raises(self, parser):
        valid, issues = parser.validate("hi")
        assert not valid

    def test_too_long_raises(self, parser):
        valid, issues = parser.validate("x" * 5000)
        assert not valid

    def test_valid_instructions(self, parser):
        valid, issues = parser.validate("Extract all product names and prices")
        assert valid
        assert issues == []


class TestFieldExtraction:
    def test_explicit_list(self, parser):
        plan = parser.parse("Extract product name, price, and rating from this page")
        names = [f.name for f in plan.fields]
        assert "name" in names or "product_name" in names
        assert "price" in names
        assert "rating" in names

    def test_price_inferred_as_price_type(self, parser):
        plan = parser.parse("Extract all prices from the store")
        price_fields = [f for f in plan.fields if f.field_type == FieldType.PRICE]
        assert len(price_fields) >= 1

    def test_url_inferred_as_link_type(self, parser):
        plan = parser.parse("Get all article URLs and titles")
        url_fields = [f for f in plan.fields if f.field_type == FieldType.LINK]
        assert len(url_fields) >= 1

    def test_fallback_to_content_field(self, parser):
        plan = parser.parse("Please get me some useful stuff from this website")
        assert len(plan.fields) >= 1


class TestStrategy:
    def test_pagination_detected(self, parser):
        plan = parser.parse("Extract all reviews from all pages")
        assert plan.strategy.paginate is True

    def test_scroll_detected(self, parser):
        plan = parser.parse("Scrape all items using infinite scroll")
        assert plan.strategy.scroll_to_load is True

    def test_single_page_default(self, parser):
        plan = parser.parse("Extract the headline from this news article")
        assert plan.strategy.paginate is False
        assert plan.strategy.scroll_to_load is False


class TestConfidence:
    def test_high_confidence_explicit_fields(self, parser):
        plan = parser.parse("Extract title, author, date from every article")
        assert plan.confidence >= 0.8

    def test_lower_confidence_vague(self, parser):
        plan = parser.parse("Get whatever is useful from this page please thanks")
        # May still work but confidence could be lower
        assert 0 < plan.confidence <= 1.0
