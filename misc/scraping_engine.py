"""
app/modules/scraping_engine.py
────────────────────────────────
Module 2 — Scraping Engine

Responsibility:
    Crawl one or many web pages and return raw structured page data.

Features:
    - Playwright for JS-rendered SPA / dynamic pages
    - BeautifulSoup for static DOM parsing
    - Automatic robots.txt compliance
    - Polite crawl delays
    - Depth-limited BFS crawler for multi-page jobs
    - Retry logic with exponential back-off
    - Deduplication of visited URLs
    - Rate-limit detection & back-off
    - Large-site support (async concurrent fetching)
"""

from __future__ import annotations

import asyncio
import hashlib
import random
import re
import time
from collections import deque
from dataclasses import dataclass, field
from typing import AsyncIterator, Dict, List, Optional, Set
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import aiohttp
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
from loguru import logger
from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    async_playwright,
)
from tenacity import (
    AsyncRetrying,
    RetryError,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import settings
from app.core.exceptions import (
    MaxPagesReachedError,
    PageRenderError,
    RateLimitedError,
    RobotsBlockedError,
    ScrapingError,
)
from app.modules.instruction_parser import ExtractionPlan


# ── Page result ────────────────────────────────────────────────────────────────

@dataclass
class PageResult:
    """Parsed output for a single fetched page."""

    url: str
    title: str
    html: str
    text: str                           # Cleaned plaintext
    headings: List[str]
    paragraphs: List[str]
    tables: List[List[List[str]]]       # [table][row][cell]
    links: List[Dict[str, str]]         # [{"text": ..., "href": ...}]
    images: List[Dict[str, str]]
    metadata: Dict[str, str]
    status_code: int
    fetch_time_ms: int
    page_index: int = 0


@dataclass
class ScrapeResult:
    """Aggregate result returned to the pipeline after crawling."""

    seed_url: str
    pages: List[PageResult]
    total_pages: int
    failed_urls: List[str] = field(default_factory=list)
    elapsed_seconds: float = 0.0


# ── Robots.txt helper ──────────────────────────────────────────────────────────

class RobotsChecker:
    """Cache-enabled robots.txt checker."""

    def __init__(self) -> None:
        self._cache: Dict[str, RobotFileParser] = {}

    async def is_allowed(self, url: str, user_agent: str = "*") -> bool:
        if not settings.SCRAPE_RESPECT_ROBOTS:
            return True

        parsed = urlparse(url)
        base = f"{parsed.scheme}://{parsed.netloc}"
        robots_url = f"{base}/robots.txt"

        if base not in self._cache:
            rp = RobotFileParser()
            rp.set_url(robots_url)
            try:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, rp.read)
            except Exception as exc:
                logger.debug("Could not fetch robots.txt", url=robots_url, error=str(exc))
                # If we can't fetch it, assume allowed
                self._cache[base] = RobotFileParser()
            else:
                self._cache[base] = rp

        return self._cache[base].can_fetch(user_agent, url)


# ── HTML parser ────────────────────────────────────────────────────────────────

class HTMLParser:
    """Extracts structured data from raw HTML using BeautifulSoup."""

    _NOISE_TAGS = {"script", "style", "noscript", "svg", "iframe", "nav", "footer", "header"}

    def parse(self, html: str, url: str) -> dict:
        soup = BeautifulSoup(html, "lxml")

        # Remove noise
        for tag in soup(_noise_tag for _noise_tag in self._NOISE_TAGS):
            tag.decompose()

        return {
            "title":      self._get_title(soup),
            "text":       self._get_text(soup),
            "headings":   self._get_headings(soup),
            "paragraphs": self._get_paragraphs(soup),
            "tables":     self._get_tables(soup),
            "links":      self._get_links(soup, url),
            "images":     self._get_images(soup, url),
            "metadata":   self._get_metadata(soup),
        }

    def _get_title(self, soup: BeautifulSoup) -> str:
        tag = soup.find("title")
        return tag.get_text(strip=True) if tag else ""

    def _get_text(self, soup: BeautifulSoup) -> str:
        text = soup.get_text(separator=" ", strip=True)
        return re.sub(r"\s+", " ", text).strip()

    def _get_headings(self, soup: BeautifulSoup) -> List[str]:
        return [
            tag.get_text(strip=True)
            for level in range(1, 7)
            for tag in soup.find_all(f"h{level}")
            if tag.get_text(strip=True)
        ]

    def _get_paragraphs(self, soup: BeautifulSoup) -> List[str]:
        return [
            p.get_text(strip=True)
            for p in soup.find_all("p")
            if len(p.get_text(strip=True)) > 30
        ]

    def _get_tables(self, soup: BeautifulSoup) -> List[List[List[str]]]:
        tables = []
        for table in soup.find_all("table"):
            rows = []
            for tr in table.find_all("tr"):
                cells = [
                    cell.get_text(strip=True)
                    for cell in tr.find_all(["td", "th"])
                ]
                if cells:
                    rows.append(cells)
            if rows:
                tables.append(rows)
        return tables

    def _get_links(self, soup: BeautifulSoup, base_url: str) -> List[Dict[str, str]]:
        links = []
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if href.startswith(("javascript:", "#", "mailto:")):
                continue
            absolute = urljoin(base_url, href)
            text = a.get_text(strip=True)
            links.append({"text": text, "href": absolute})
        return links[:200]

    def _get_images(self, soup: BeautifulSoup, base_url: str) -> List[Dict[str, str]]:
        images = []
        for img in soup.find_all("img"):
            src = img.get("src", "").strip()
            if src:
                images.append({
                    "src":   urljoin(base_url, src),
                    "alt":   img.get("alt", ""),
                    "title": img.get("title", ""),
                })
        return images[:100]

    def _get_metadata(self, soup: BeautifulSoup) -> Dict[str, str]:
        meta: Dict[str, str] = {}
        for tag in soup.find_all("meta"):
            name  = tag.get("name") or tag.get("property") or ""
            content = tag.get("content") or ""
            if name and content:
                meta[name.lower()] = content
        return meta


# ── Main scraping engine ───────────────────────────────────────────────────────

class ScrapingEngine:
    """
    Async scraping engine supporting single-page, crawl, and sitemap modes.

    Manages a Playwright browser instance per-job and shuts it down cleanly.
    """

    def __init__(self) -> None:
        self._ua = UserAgent()
        self._robots = RobotsChecker()
        self._html_parser = HTMLParser()
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def __aenter__(self) -> "ScrapingEngine":
        await self._start_browser()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self._stop_browser()

    async def _start_browser(self) -> None:
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=settings.SCRAPE_BROWSER_HEADLESS,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
            ],
        )
        logger.debug("Playwright browser started")

    async def _stop_browser(self) -> None:
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        logger.debug("Playwright browser stopped")

    # ── Public API ────────────────────────────────────────────────────────────

    async def scrape(
        self,
        url: str,
        plan: ExtractionPlan,
        max_pages: int,
        max_depth: int,
        progress_callback=None,
    ) -> ScrapeResult:
        """
        Orchestrate the full scrape based on the extraction plan.

        Args:
            url:               Seed URL
            plan:              ExtractionPlan from InstructionParser
            max_pages:         Hard page cap
            max_depth:         BFS depth for crawl mode
            progress_callback: Optional async callable(pages_done, total_est)
        """
        start = time.time()
        results: List[PageResult] = []
        failed: List[str] = []

        strategy = plan.strategy
        max_pages = min(max_pages, settings.SCRAPE_MAX_PAGES)

        if strategy.paginate or strategy.follow_links or max_pages > 1:
            # Multi-page BFS crawl
            results, failed = await self._crawl(
                seed_url=url,
                max_pages=max_pages,
                max_depth=max_depth,
                pagination_selector=strategy.pagination_selector,
                link_pattern=strategy.link_pattern,
                progress_callback=progress_callback,
            )
        else:
            # Single page
            page_result = await self._fetch_page(url, page_index=0)
            if page_result:
                results.append(page_result)
            else:
                failed.append(url)

        elapsed = time.time() - start
        logger.info(
            "Scrape complete",
            url=url,
            pages=len(results),
            failed=len(failed),
            elapsed_s=round(elapsed, 2),
        )

        return ScrapeResult(
            seed_url=url,
            pages=results,
            total_pages=len(results),
            failed_urls=failed,
            elapsed_seconds=elapsed,
        )

    # ── Single-page fetch ─────────────────────────────────────────────────────

    async def _fetch_page(self, url: str, page_index: int = 0) -> Optional[PageResult]:
        """Fetch and parse a single URL with retry logic."""

        # robots.txt check
        if not await self._robots.is_allowed(url):
            raise RobotsBlockedError(f"robots.txt blocks access to {url}")

        user_agent = self._ua.random
        t_start = time.time()

        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(3),
                wait=wait_exponential(multiplier=1, min=2, max=10),
                retry=retry_if_exception_type((PageRenderError, aiohttp.ClientError)),
                reraise=True,
            ):
                with attempt:
                    html = await self._render_page(url, user_agent)

        except RetryError as exc:
            logger.warning("Page fetch failed after retries", url=url, error=str(exc))
            return None
        except RateLimitedError:
            logger.warning("Rate limited — waiting 30s", url=url)
            await asyncio.sleep(30)
            return None
        except Exception as exc:
            logger.error("Unexpected error fetching page", url=url, error=str(exc))
            return None

        fetch_ms = int((time.time() - t_start) * 1000)
        parsed   = self._html_parser.parse(html, url)

        return PageResult(
            url=url,
            title=parsed["title"],
            html=html,
            text=parsed["text"],
            headings=parsed["headings"],
            paragraphs=parsed["paragraphs"],
            tables=parsed["tables"],
            links=parsed["links"],
            images=parsed["images"],
            metadata=parsed["metadata"],
            status_code=200,
            fetch_time_ms=fetch_ms,
            page_index=page_index,
        )

    async def _render_page(self, url: str, user_agent: str) -> str:
        """Use Playwright to fully render a page (handles JS, lazy loading)."""
        assert self._browser is not None, "Browser not started"

        context: BrowserContext = await self._browser.new_context(
            user_agent=user_agent,
            viewport={"width": 1280, "height": 800},
            locale="en-US",
        )
        page: Page = await context.new_page()

        try:
            response = await page.goto(
                url,
                wait_until="networkidle",
                timeout=settings.SCRAPE_TIMEOUT * 1000,
            )

            if response and response.status == 429:
                raise RateLimitedError(f"Target returned 429 for {url}")

            if response and response.status >= 400:
                raise PageRenderError(
                    f"HTTP {response.status} for {url}",
                    context={"url": url, "status": response.status},
                )

            # Auto-scroll for lazy-loaded content
            await self._auto_scroll(page)
            html = await page.content()
            return html

        except (RateLimitedError, PageRenderError):
            raise
        except Exception as exc:
            raise PageRenderError(f"Render failed for {url}: {exc}") from exc
        finally:
            await page.close()
            await context.close()

    async def _auto_scroll(self, page: Page) -> None:
        """Scroll to bottom to trigger infinite-scroll / lazy images."""
        await page.evaluate("""
            async () => {
                await new Promise(resolve => {
                    let h = 0;
                    const step = 400;
                    const timer = setInterval(() => {
                        window.scrollBy(0, step);
                        h += step;
                        if (h >= document.body.scrollHeight - window.innerHeight) {
                            clearInterval(timer);
                            resolve();
                        }
                    }, 120);
                    setTimeout(() => { clearInterval(timer); resolve(); }, 10000);
                });
            }
        """)

    # ── BFS crawler ───────────────────────────────────────────────────────────

    async def _crawl(
        self,
        seed_url: str,
        max_pages: int,
        max_depth: int,
        pagination_selector: Optional[str],
        link_pattern: Optional[str],
        progress_callback=None,
    ) -> tuple[List[PageResult], List[str]]:
        """
        Breadth-first crawl from seed_url.
        Stays within the same origin (scheme + netloc).
        """
        origin = "{0.scheme}://{0.netloc}".format(urlparse(seed_url))
        visited: Set[str]        = set()
        failed: List[str]        = []
        results: List[PageResult] = []
        queue: deque              = deque([(seed_url, 0)])
        semaphore = asyncio.Semaphore(settings.SCRAPE_CONCURRENCY)

        async def _process(url: str, depth: int) -> None:
            nonlocal results

            if len(results) >= max_pages:
                raise MaxPagesReachedError(f"Reached max_pages limit of {max_pages}")

            url_hash = hashlib.md5(url.encode()).hexdigest()
            if url_hash in visited:
                return
            visited.add(url_hash)

            async with semaphore:
                # Polite delay
                await asyncio.sleep(
                    random.uniform(settings.SCRAPE_DELAY_MIN, settings.SCRAPE_DELAY_MAX)
                )
                result = await self._fetch_page(url, page_index=len(results))

            if result is None:
                failed.append(url)
                return

            results.append(result)

            if progress_callback:
                await progress_callback(len(results), max_pages)

            # Enqueue next-page / child links
            if depth < max_depth:
                for link in result.links:
                    href = link["href"]
                    link_hash = hashlib.md5(href.encode()).hexdigest()
                    if (
                        link_hash not in visited
                        and href.startswith(origin)
                        and self._matches_pattern(href, link_pattern)
                        and len(results) + len(queue) < max_pages
                    ):
                        queue.append((href, depth + 1))

        try:
            while queue and len(results) < max_pages:
                batch = []
                # Pull up to SCRAPE_CONCURRENCY items from queue
                for _ in range(min(settings.SCRAPE_CONCURRENCY, len(queue))):
                    if queue:
                        batch.append(queue.popleft())

                tasks = [_process(url, depth) for url, depth in batch]
                await asyncio.gather(*tasks, return_exceptions=True)

        except MaxPagesReachedError:
            logger.info("Max pages reached, stopping crawl", max_pages=max_pages)

        return results, failed

    @staticmethod
    def _matches_pattern(url: str, pattern: Optional[str]) -> bool:
        if not pattern:
            return True
        try:
            return bool(re.search(pattern, url))
        except re.error:
            return True
