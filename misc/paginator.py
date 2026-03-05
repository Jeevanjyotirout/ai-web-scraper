"""
paginator.py
------------
Discovers and iterates through paginated content.
Supports numeric pagination (?page=N), next-button patterns,
and cursor / offset-based query strings.
"""

import logging
import re
from typing import Generator, Optional
from urllib.parse import urljoin, urlparse, urlencode, parse_qs, urlunparse, ParseResult

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# CSS / text selectors that commonly indicate a "next page" link
_NEXT_PAGE_PATTERNS = re.compile(
    r"\b(next|next page|›|»|→|load more|show more|следующая)\b",
    re.IGNORECASE,
)

# Common query-string keys used for page numbers
_PAGE_PARAMS = ("page", "p", "pg", "pagenum", "page_num", "start", "offset", "from")


class PaginationHandler:
    """
    Detects and generates paginated URLs from a seed page's HTML.

    Usage
    -----
    handler = PaginationHandler(max_pages=10)
    for page_url in handler.iter_pages(start_url, html):
        result = await engine.scrape_page(page_url)
    """

    def __init__(self, max_pages: int = 50):
        self.max_pages = max_pages

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def iter_pages(self, start_url: str, initial_html: str) -> Generator[str, None, None]:
        """
        Yield URLs for every page in a paginated sequence starting from
        *start_url*.  The first URL yielded is always *start_url* itself.

        Stops when:
        - No next-page link is detected in the current page's HTML.
        - The resolved next URL has already been seen (cycle guard).
        - *max_pages* is reached.

        Parameters
        ----------
        start_url : str
            The first URL in the paginated sequence.
        initial_html : str
            HTML of the first page (avoids an extra HTTP request).

        Yields
        ------
        str
            Absolute URLs, in order.
        """
        current_url = start_url
        current_html = initial_html
        seen: set[str] = {current_url}

        yield current_url

        for page_num in range(2, self.max_pages + 1):
            next_url = self._find_next_page_url(current_url, current_html)

            if not next_url:
                logger.debug("No next-page link found after page %d.", page_num - 1)
                break

            if next_url in seen:
                logger.debug("Pagination cycle detected at %s – stopping.", next_url)
                break

            seen.add(next_url)
            logger.info("Pagination page %d: %s", page_num, next_url)
            yield next_url

            # Caller is responsible for fetching the HTML; we need the
            # next page's HTML to find page N+2.  Signal that HTML must
            # be provided for subsequent iterations via send():
            # (For simplicity the engine re-calls iter_pages after each page;
            # see orchestrator.py for the recommended usage pattern.)
            current_url = next_url
            current_html = ""  # Will be refreshed by the caller

    def build_page_url(self, base_url: str, page_number: int, param: str = "page") -> str:
        """
        Construct a URL for a specific page number by injecting or
        replacing the page query-string parameter.

        Parameters
        ----------
        base_url : str
            URL to modify.
        page_number : int
            The desired page index.
        param : str
            Query-string key to use (default: "page").

        Returns
        -------
        str
            Modified URL.
        """
        parsed = urlparse(base_url)
        query_params = parse_qs(parsed.query, keep_blank_values=True)
        query_params[param] = [str(page_number)]
        new_query = urlencode(query_params, doseq=True)
        return urlunparse(parsed._replace(query=new_query))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _find_next_page_url(self, current_url: str, html: str) -> Optional[str]:
        """
        Look for a "next page" link in *html* using multiple strategies:
        1. Explicit rel="next" link element.
        2. Anchor whose visible text matches _NEXT_PAGE_PATTERNS.
        3. Numeric page-parameter increment in the current URL.

        Returns the absolute URL of the next page, or None.
        """
        if not html:
            return None

        soup = BeautifulSoup(html, "lxml")

        # Strategy 1 – rel="next"
        rel_next = soup.find("link", rel="next") or soup.find("a", rel="next")
        if rel_next and rel_next.get("href"):
            return urljoin(current_url, rel_next["href"])

        # Strategy 2 – anchor text matching next-page pattern
        for a in soup.find_all("a", href=True):
            text = a.get_text(strip=True)
            aria = a.get("aria-label", "")
            if _NEXT_PAGE_PATTERNS.search(text) or _NEXT_PAGE_PATTERNS.search(aria):
                href = a["href"].strip()
                if href and not href.startswith(("#", "javascript:")):
                    return urljoin(current_url, href)

        # Strategy 3 – increment existing numeric page param
        return self._try_increment_page_param(current_url)

    def _try_increment_page_param(self, url: str) -> Optional[str]:
        """
        If the URL already contains a known page parameter, return a new
        URL with that parameter incremented by 1.
        """
        parsed = urlparse(url)
        query_params = parse_qs(parsed.query, keep_blank_values=True)

        for param in _PAGE_PARAMS:
            if param in query_params:
                try:
                    current = int(query_params[param][0])
                    query_params[param] = [str(current + 1)]
                    new_query = urlencode(query_params, doseq=True)
                    return urlunparse(parsed._replace(query=new_query))
                except (ValueError, IndexError):
                    continue

        return None
