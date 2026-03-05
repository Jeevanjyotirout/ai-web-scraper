"""
main.py
-------
File Export System — production entry point.

Generates both an Excel workbook and a Word document from the article dataset
and places them in the output/ directory.

Usage
-----
    python main.py                     # export all articles, all formats
    python main.py --format excel      # Excel only
    python main.py --format word       # Word only
    python main.py --output ./reports  # custom output directory
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

from data import ARTICLES, Article
from excel_exporter import ExcelExporter
from word_exporter import WordExporter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def export_excel(articles: list[Article], output_dir: Path) -> Path:
    logger.info("Building Excel workbook …")
    t0   = time.perf_counter()
    path = ExcelExporter(articles).export(output_dir / "articles_report.xlsx")
    logger.info("Excel done in %.2fs → %s", time.perf_counter() - t0, path)
    return path


def export_word(articles: list[Article], output_dir: Path) -> Path:
    logger.info("Building Word document …")
    t0   = time.perf_counter()
    path = WordExporter(articles).export(output_dir / "articles_report.docx")
    logger.info("Word done in %.2fs → %s", time.perf_counter() - t0, path)
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Article Dataset File Exporter")
    parser.add_argument("--format", choices=["excel", "word", "both"], default="both")
    parser.add_argument("--output", default="output", help="Output directory")
    args = parser.parse_args()

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info("=" * 55)
    logger.info("  File Export System  |  %d articles", len(ARTICLES))
    logger.info("=" * 55)

    exported: list[Path] = []

    try:
        if args.format in ("excel", "both"):
            exported.append(export_excel(ARTICLES, output_dir))

        if args.format in ("word", "both"):
            exported.append(export_word(ARTICLES, output_dir))
    except Exception as exc:
        logger.error("Export failed: %s", exc, exc_info=True)
        sys.exit(1)

    logger.info("=" * 55)
    logger.info("  Export complete. Files written:")
    for p in exported:
        logger.info("    ✓  %s  (%s)", p.name, _human_size(p))
    logger.info("=" * 55)


def _human_size(path: Path) -> str:
    size = path.stat().st_size
    for unit in ("B", "KB", "MB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


if __name__ == "__main__":
    main()
