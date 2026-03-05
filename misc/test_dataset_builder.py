"""
tests/test_dataset_builder.py
───────────────────────────────
Unit tests for DatasetBuilder.
"""

from __future__ import annotations

import pytest
import pandas as pd
import numpy as np

from app.modules.dataset_builder import DatasetBuilder, _to_number, _to_date
from app.modules.instruction_parser import (
    ExtractionPlan,
    ExtractionStrategy,
    FieldDefinition,
    FieldType,
)


def _make_plan(field_specs: list[tuple[str, FieldType]]) -> ExtractionPlan:
    fields = [
        FieldDefinition(name=name, field_type=ftype, description=name)
        for name, ftype in field_specs
    ]
    return ExtractionPlan(
        raw_instructions="test",
        fields=fields,
        strategy=ExtractionStrategy(),
    )


@pytest.fixture
def builder() -> DatasetBuilder:
    return DatasetBuilder()


class TestToNumber:
    def test_plain_int(self):           assert _to_number("42") == 42.0
    def test_float(self):               assert _to_number("3.14") == 3.14
    def test_with_currency(self):       assert _to_number("$9.99") == 9.99
    def test_with_commas(self):         assert _to_number("1,234.56") == 1234.56
    def test_none(self):                assert _to_number(None) is None
    def test_non_numeric(self):         assert _to_number("N/A") is None


class TestToDate:
    def test_iso_format(self):          assert _to_date("2024-03-15") == "2024-03-15"
    def test_slash_format(self):        assert _to_date("15/03/2024") == "2024-03-15"
    def test_none(self):                assert _to_date(None) is None


class TestDatasetBuilder:
    def test_empty_records_returns_empty_df(self, builder):
        plan    = _make_plan([("name", FieldType.TEXT)])
        dataset = builder.build([], plan)
        assert len(dataset.dataframe) == 0
        assert "name" in dataset.dataframe.columns

    def test_basic_build(self, builder):
        plan    = _make_plan([("name", FieldType.TEXT), ("price", FieldType.PRICE)])
        records = [
            {"name": "Widget A", "price": "$12.99"},
            {"name": "Widget B", "price": "€24.50"},
        ]
        dataset = builder.build(records, plan, source_url="http://example.com")
        df = dataset.dataframe

        assert len(df) == 2
        assert df["price"].dtype == float
        assert df["price"].iloc[0] == 12.99
        assert "_source_url" in df.columns
        assert "_scraped_at" in df.columns

    def test_duplicate_rows_removed(self, builder):
        plan    = _make_plan([("name", FieldType.TEXT)])
        records = [{"name": "A"}, {"name": "A"}, {"name": "B"}]
        dataset = builder.build(records, plan)
        assert len(dataset.dataframe) == 2
        assert dataset.stats.duplicate_rows_removed == 1

    def test_missing_columns_added_as_null(self, builder):
        plan    = _make_plan([("name", FieldType.TEXT), ("price", FieldType.PRICE)])
        records = [{"name": "X"}]   # no price
        dataset = builder.build(records, plan)
        assert "price" in dataset.dataframe.columns
        assert pd.isna(dataset.dataframe["price"].iloc[0])

    def test_column_order(self, builder):
        plan = _make_plan([("title", FieldType.TEXT), ("url", FieldType.LINK)])
        records = [{"url": "http://x.com", "title": "Page", "extra": "bonus"}]
        dataset = builder.build(records, plan)
        cols = list(dataset.dataframe.columns)
        # Plan fields should come before extras
        assert cols.index("title") < cols.index("extra")
