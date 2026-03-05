"""
orchestrator.py
---------------
High-level orchestrator that composes the ScrapingEngine, ContentExtractor,
and PaginationHandler into a single easy-to-use interface.

Typical usage
-------------
    async with Orchestrator() as orch:
        results = await orch.scrape(
            urls=["https://example.com/articles"],
            follow_pagination=True,
        )
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import Optional

from config.settings import ScraperConfig
from models.extracted_data import ExtractedData
from models.page_result import PageResult
from scraper.engine import ScrapingEngine
from scraper.extractor import ContentExtractor
from scraper.paginator import PaginationHandler

logger = logging.getLogger(__name__)


class Orchestrator:
    """
    Unified pipeline: fetch → extract → paginate → store.

    Can be used as an async context manager to cleanly release resources.
    """

    def __init__(self, config: Optional[ScraperConfig] = None):
        self.config = config or ScraperConfig()
        self.engine = ScrapingEngine(self.config)
        self.extractor = ContentExtractor()
        self.paginator = PaginationHandler(max_pages=self.config.max_pages)

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        pass  # Engine manages browser lifecycle per-request

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def scrape(
        self,
        urls: list[str],
        follow_pagination: bool = False,
        save_output: bool = True,
    ) -> list[ExtractedData]:
        """
        Scrape a list of seed URLs, optionally following pagination,
        and return structured ExtractedData objects.

        Parameters
        ----------
        urls : list[str]
            Seed URLs to scrape.
        follow_pagination : bool
            If True, automatically follow next-page links up to
            config.max_pages per seed URL.
        save_output : bool
            If True, write results as JSON to config.output_dir.

        Returns
        -------
        list[ExtractedData]
            One entry per successfully scraped page.
        """
        all_results: list[ExtractedData] = []

        for seed_url in urls:
            page_urls = [seed_url]

            if follow_pagination:
                # Fetch the first page to discover pagination links
                first_page = await self.engine.scrape_page(seed_url)
                if first_page is None:
                    logger.warning("Failed to fetch seed URL: %s", seed_url)
                    continue

                extracted_first = self.extractor.extract_content(
                    first_page.html, base_url=first_page.final_url
                )
                all_results.append(extracted_first)

                # Gather additional page URLs from pagination
                pagination_urls = list(
                    self.paginator.iter_pages(seed_url, first_page.html)
                )[1:]  # skip index 0 (already fetched)

                page_urls = pagination_urls
            
            # Fetch all remaining pages concurrently
            scraped_pages = await self.engine.scrape_pages(page_urls)

            for page in scraped_pages:
                extracted = self.extractor.extract_content(
                    page.html, base_url=page.final_url
                )
                all_results.append(extracted)

        if save_output:
            self._save_results(all_results)

        logger.info("Scraping complete. Total pages extracted: %d", len(all_results))
        return all_results

    async def scrape_single(self, url: str) -> Optional[ExtractedData]:
        """
        Convenience method to scrape a single URL without pagination.

        Parameters
        ----------
        url : str
            Target URL.

        Returns
        -------
        ExtractedData | None
        """
        page = await self.engine.scrape_page(url)
        if page is None:
            return None
        return self.extractor.extract_content(page.html, base_url=page.final_url)

    # ------------------------------------------------------------------
    # Output helpers
    # ------------------------------------------------------------------

    def _save_results(self, results: list[ExtractedData]) -> None:
        """Persist extracted data as newline-delimited JSON (JSONL)."""
        output_dir = Path(self.config.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "results.jsonl"

        with open(output_path, "w", encoding="utf-8") as f:
            for item in results:
                f.write(json.dumps(item.to_dict(), ensure_ascii=False) + "\n")

        logger.info("Results saved to %s", output_path)
