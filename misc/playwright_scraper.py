import asyncio
from typing import Optional
from playwright.async_api import async_playwright, Page, Browser, BrowserContext
from app.core.config import settings
from loguru import logger


class PlaywrightScraper:
    """Async Playwright-based scraper that handles JS-rendered pages."""

    def __init__(self):
        self._browser: Optional[Browser] = None
        self._playwright = None

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, *args):
        await self.stop()

    async def start(self):
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=settings.BROWSER_HEADLESS,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
        )
        logger.debug("Playwright browser launched")

    async def stop(self):
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        logger.debug("Playwright browser closed")

    async def scrape_page(self, url: str) -> dict:
        """Scrape a single page and return its content."""
        context: BrowserContext = await self._browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
        )
        page: Page = await context.new_page()

        try:
            await page.goto(url, wait_until="networkidle", timeout=settings.SCRAPE_TIMEOUT * 1000)
            
            # Scroll to load lazy content
            await self._auto_scroll(page)

            html = await page.content()
            title = await page.title()
            
            # Extract meta description
            meta_desc = await page.evaluate(
                "() => document.querySelector('meta[name=\"description\"]')?.content || ''"
            )

            return {
                "url": url,
                "title": title,
                "meta_description": meta_desc,
                "html": html,
                "success": True,
            }

        except Exception as e:
            logger.warning(f"Failed to scrape {url}: {e}")
            return {"url": url, "title": "", "html": "", "success": False, "error": str(e)}
        finally:
            await page.close()
            await context.close()

    async def scrape_multiple(self, urls: list[str]) -> list[dict]:
        """Scrape multiple pages concurrently (limited concurrency)."""
        sem = asyncio.Semaphore(3)

        async def _scrape(url: str) -> dict:
            async with sem:
                return await self.scrape_page(url)

        results = await asyncio.gather(*[_scrape(u) for u in urls], return_exceptions=True)
        return [r if isinstance(r, dict) else {"url": "", "html": "", "success": False, "error": str(r)} for r in results]

    async def _auto_scroll(self, page: Page):
        """Scroll to bottom to trigger lazy loading."""
        await page.evaluate("""
            async () => {
                await new Promise(resolve => {
                    let totalHeight = 0;
                    const distance = 300;
                    const timer = setInterval(() => {
                        window.scrollBy(0, distance);
                        totalHeight += distance;
                        if (totalHeight >= document.body.scrollHeight - window.innerHeight) {
                            clearInterval(timer);
                            resolve();
                        }
                    }, 100);
                    setTimeout(() => { clearInterval(timer); resolve(); }, 8000);
                });
            }
        """)
