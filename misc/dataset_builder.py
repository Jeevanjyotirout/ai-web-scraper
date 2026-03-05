"""
app/modules/dataset_builder.py
────────────────────────────────
Module 4 — Dataset Builder

Responsibility:
    Transform raw AI-extracted records into a clean, normalised
    Pandas DataFrame ready for export.

Operations:
    1. Schema inference — auto-detect column types from record values
    2. Type coercion   — cast strings to ints/floats/dates where possible
    3. Field transforms — strip, lower, upper, normalise whitespace
    4. Null handling   — fill missing values with sensible defaults
    5. Deduplication   — remove exact duplicate rows
    6. Column ordering — place key fields first
    7. Validation      — flag or drop rows that violate required-field rules
    8. Metadata columns — append source_url, scraped_at automatically
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from loguru import logger

from app.core.exceptions import ExportError
from app.modules.instruction_parser import ExtractionPlan, FieldDefinition, FieldType


# ── Dataset stats ──────────────────────────────────────────────────────────────

@dataclass
class DatasetStats:
    total_rows: int
    columns: List[str]
    null_counts: Dict[str, int]
    duplicate_rows_removed: int
    type_coercions: Dict[str, str]   # column → inferred type
    warnings: List[str]


@dataclass
class Dataset:
    dataframe: pd.DataFrame
    stats: DatasetStats


# ── Type coercion helpers ─────────────────────────────────────────────────────

_PRICE_RE   = re.compile(r"[$€£¥₹]?\s*(\d[\d,]*\.?\d*)")
_DATE_FMTS  = ["%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%B %d, %Y", "%b %d, %Y"]
_EMAIL_RE   = re.compile(r"\b[\w._%+\-]+@[\w.\-]+\.[a-zA-Z]{2,}\b")
_URL_RE     = re.compile(r"https?://\S+")


def _to_number(val: Any) -> Optional[float]:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip()
    # Strip currency symbols and commas
    m = _PRICE_RE.search(s)
    if m:
        try:
            return float(m.group(1).replace(",", ""))
        except ValueError:
            pass
    try:
        return float(s.replace(",", ""))
    except ValueError:
        return None


def _to_date(val: Any) -> Optional[str]:
    if val is None:
        return None
    s = str(val).strip()
    for fmt in _DATE_FMTS:
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return s   # Return as-is if unparseable


def _apply_transform(val: Any, transform: Optional[str]) -> Any:
    """Apply a named string transform to a value."""
    if val is None or transform is None:
        return val
    s = str(val)
    match transform:
        case "strip":   return s.strip()
        case "lower":   return s.strip().lower()
        case "upper":   return s.strip().upper()
        case "int":     return int(float(s.replace(",", ""))) if s else None
        case "float":   return float(s.replace(",", "")) if s else None
        case "bool":    return s.strip().lower() in {"true", "yes", "1", "on"}
        case "slug":    return re.sub(r"[^a-z0-9-]", "-", s.lower()).strip("-")
        case _:         return val


# ── Core builder ──────────────────────────────────────────────────────────────

class DatasetBuilder:
    """
    Converts a list of raw record dicts (from AI processing) into a
    clean Pandas DataFrame with type coercion and quality assurance.

    Usage:
        builder = DatasetBuilder()
        dataset = builder.build(records, plan)
    """

    def build(
        self,
        records: List[Dict[str, Any]],
        plan: ExtractionPlan,
        source_url: str = "",
        scraped_at: Optional[datetime] = None,
    ) -> Dataset:
        """
        Full pipeline: raw records → clean Dataset.
        """
        warnings: List[str] = []
        scraped_ts = (scraped_at or datetime.utcnow()).isoformat()

        if not records:
            logger.warning("No records to build dataset from")
            df = pd.DataFrame(columns=self._get_expected_columns(plan))
            return Dataset(
                dataframe=df,
                stats=DatasetStats(
                    total_rows=0,
                    columns=list(df.columns),
                    null_counts={},
                    duplicate_rows_removed=0,
                    type_coercions={},
                    warnings=["No records extracted"],
                ),
            )

        # Step 1 — Create raw DataFrame
        df = pd.DataFrame(records)
        initial_rows = len(df)
        logger.info("Building dataset", initial_rows=initial_rows, columns=list(df.columns))

        # Step 2 — Ensure all expected columns exist
        df = self._ensure_columns(df, plan)

        # Step 3 — Apply field-specific transforms and type coercion
        type_coercions: Dict[str, str] = {}
        for field_def in plan.fields:
            if field_def.name not in df.columns:
                continue
            df[field_def.name], coerced = self._coerce_column(
                df[field_def.name], field_def
            )
            if coerced:
                type_coercions[field_def.name] = field_def.field_type.value

        # Step 4 — Clean string columns
        for col in df.select_dtypes(include="object").columns:
            df[col] = df[col].apply(self._clean_string)

        # Step 5 — Drop fully empty rows
        df = df.dropna(how="all")
        after_empty_drop = len(df)
        if after_empty_drop < initial_rows:
            warnings.append(f"Removed {initial_rows - after_empty_drop} fully-null rows")

        # Step 6 — Remove duplicate rows
        before_dedup = len(df)
        df = df.drop_duplicates()
        dupes_removed = before_dedup - len(df)
        if dupes_removed:
            logger.debug("Deduplication", rows_removed=dupes_removed)

        # Step 7 — Validate required fields
        for field_def in plan.fields:
            if field_def.required and field_def.name in df.columns:
                null_mask = df[field_def.name].isna()
                if null_mask.any():
                    pct = null_mask.mean() * 100
                    warnings.append(
                        f"Required field '{field_def.name}' is null in "
                        f"{null_mask.sum()} rows ({pct:.1f}%)"
                    )

        # Step 8 — Add metadata columns
        df["_source_url"]  = source_url
        df["_scraped_at"]  = scraped_ts

        # Step 9 — Reorder columns (key fields first)
        df = self._reorder_columns(df, plan)

        # Compile null counts
        null_counts = df.isnull().sum().to_dict()

        logger.info(
            "Dataset built",
            rows=len(df),
            columns=len(df.columns),
            dupes_removed=dupes_removed,
        )

        return Dataset(
            dataframe=df,
            stats=DatasetStats(
                total_rows=len(df),
                columns=list(df.columns),
                null_counts=null_counts,
                duplicate_rows_removed=dupes_removed,
                type_coercions=type_coercions,
                warnings=warnings,
            ),
        )

    # ── Private helpers ───────────────────────────────────────────────────────

    def _get_expected_columns(self, plan: ExtractionPlan) -> List[str]:
        return [f.name for f in plan.fields] + ["_source_url", "_scraped_at"]

    def _ensure_columns(self, df: pd.DataFrame, plan: ExtractionPlan) -> pd.DataFrame:
        """Add any missing expected columns as NaN columns."""
        for field_def in plan.fields:
            if field_def.name not in df.columns:
                df[field_def.name] = np.nan
        return df

    def _coerce_column(
        self, series: pd.Series, field_def: FieldDefinition
    ) -> tuple[pd.Series, bool]:
        """
        Apply type coercion based on FieldDefinition.
        Returns (coerced_series, was_coerced).
        """
        coerced = False

        # User-specified transform takes priority
        if field_def.transform:
            series = series.apply(lambda v: _apply_transform(v, field_def.transform))
            coerced = True

        # Type-based coercion
        match field_def.field_type:
            case FieldType.NUMBER | FieldType.PRICE:
                series = series.apply(_to_number)
                coerced = True
            case FieldType.DATE:
                series = series.apply(_to_date)
            case FieldType.EMAIL:
                series = series.apply(
                    lambda v: _EMAIL_RE.search(str(v)).group(0)
                    if v and _EMAIL_RE.search(str(v))
                    else v
                )
            case FieldType.LINK:
                series = series.apply(
                    lambda v: str(v).strip() if v and str(v).startswith(("http", "/")) else v
                )
            case _:
                pass  # TEXT, HTML, BOOLEAN, CUSTOM — leave as-is

        return series, coerced

    def _clean_string(self, val: Any) -> Any:
        """Normalise string values: strip whitespace, collapse runs."""
        if val is None or (isinstance(val, float) and np.isnan(val)):
            return val
        s = str(val).strip()
        s = re.sub(r"\s+", " ", s)
        return s if s else None

    def _reorder_columns(self, df: pd.DataFrame, plan: ExtractionPlan) -> pd.DataFrame:
        """Place plan fields first, then any extras, then metadata."""
        priority = [f.name for f in plan.fields if f.name in df.columns]
        extras   = [c for c in df.columns if c not in priority and not c.startswith("_")]
        metadata = [c for c in df.columns if c.startswith("_")]
        ordered  = priority + extras + metadata
        return df[[c for c in ordered if c in df.columns]]
