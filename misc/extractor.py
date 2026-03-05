"""
extractor.py
------------
HTML content extraction using BeautifulSoup4.
Parses raw HTML into structured data: headings, paragraphs, links,
tables, metadata, and open-graph tags.
"""

import logging
import re
from typing import Any
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Tag

from models.extracted_data import ExtractedData
from utils.text_utils import clean_text

logger = logging.getLogger(__name__)

# Tags whose content should be completely removed before extraction
_NOISE_TAGS = {
    "script", "style", "noscript", "iframe", "svg",
    "header", "footer", "nav", "aside", "form",
    "button", "input", "select", "textarea",
    "advertisement", "ads",
}

# CSS class / id patterns that commonly indicate ad / nav boilerplate
_NOISE_PATTERNS = re.compile(
    r"(sidebar|breadcrumb|cookie|banner|popup|modal|overlay|"
    r"newsletter|subscribe|share|social|widget|advert|promo)",
    re.IGNORECASE,
)


class ContentExtractor:
    """
    Stateless extractor that converts raw HTML strings into structured
    ExtractedData objects.  All methods are pure functions of their inputs.
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract_content(self, html: str, base_url: str = "") -> ExtractedData:
        """
        Parse *html* and return a fully populated ExtractedData object.

        Parameters
        ----------
        html : str
            Raw HTML string returned by the browser.
        base_url : str
            Origin URL used to resolve relative hrefs into absolute URLs.

        Returns
        -------
        ExtractedData
            Structured representation of the page content.
        """
        soup = BeautifulSoup(html, "lxml")
        self._strip_noise(soup)

        return ExtractedData(
            title=self._extract_title(soup),
            meta=self._extract_meta(soup),
            headings=self._extract_headings(soup),
            paragraphs=self._extract_paragraphs(soup),
            links=self._extract_links(soup, base_url),
            tables=self._extract_tables(soup),
            images=self._extract_images(soup, base_url),
            raw_text=self._extract_raw_text(soup),
            open_graph=self._extract_open_graph(soup),
        )

    # ------------------------------------------------------------------
    # Noise removal
    # ------------------------------------------------------------------

    def _strip_noise(self, soup: BeautifulSoup) -> None:
        """
        Remove script / style / navigation elements and elements whose
        class or id match known boilerplate patterns in-place.
        """
        # Remove tags by type
        for tag in soup.find_all(_NOISE_TAGS):
            tag.decompose()

        # Remove elements whose class/id looks like boilerplate
        for tag in soup.find_all(True):
            classes = " ".join(tag.get("class", []))
            tag_id = tag.get("id", "")
            if _NOISE_PATTERNS.search(classes) or _NOISE_PATTERNS.search(tag_id):
                tag.decompose()

    # ------------------------------------------------------------------
    # Field extractors
    # ------------------------------------------------------------------

    def _extract_title(self, soup: BeautifulSoup) -> str:
        """Return the page <title> text, falling back to the first <h1>."""
        title_tag = soup.find("title")
        if title_tag and title_tag.get_text(strip=True):
            return clean_text(title_tag.get_text())

        h1 = soup.find("h1")
        if h1:
            return clean_text(h1.get_text())

        return ""

    def _extract_meta(self, soup: BeautifulSoup) -> dict[str, str]:
        """
        Collect common <meta> tags: description, keywords, author,
        robots, canonical, and viewport.
        """
        meta: dict[str, str] = {}
        keys_of_interest = {"description", "keywords", "author", "robots", "viewport"}

        for tag in soup.find_all("meta"):
            name = (tag.get("name") or tag.get("property") or "").lower().strip()
            content = tag.get("content", "").strip()
            if name in keys_of_interest and content:
                meta[name] = content

        # Canonical link
        canonical = soup.find("link", rel="canonical")
        if canonical and canonical.get("href"):
            meta["canonical"] = canonical["href"]

        return meta

    def _extract_headings(self, soup: BeautifulSoup) -> dict[str, list[str]]:
        """
        Return a mapping of heading level → list of heading texts.
        e.g. {"h1": ["Page Title"], "h2": ["Section A", "Section B"]}
        """
        headings: dict[str, list[str]] = {}
        for level in ("h1", "h2", "h3", "h4", "h5", "h6"):
            texts = [
                clean_text(tag.get_text())
                for tag in soup.find_all(level)
                if tag.get_text(strip=True)
            ]
            if texts:
                headings[level] = texts
        return headings

    def _extract_paragraphs(self, soup: BeautifulSoup) -> list[str]:
        """
        Return non-empty <p> paragraphs with cleaned whitespace.
        Filters out paragraphs shorter than 20 characters (likely captions).
        """
        paragraphs = []
        for p in soup.find_all("p"):
            text = clean_text(p.get_text())
            if len(text) >= 20:
                paragraphs.append(text)
        return paragraphs

    def _extract_links(self, soup: BeautifulSoup, base_url: str) -> list[dict[str, str]]:
        """
        Return all anchor tags as {"href": <absolute_url>, "text": <anchor_text>}.
        Skips mailto, tel, javascript, and fragment-only links.
        """
        links = []
        seen: set[str] = set()

        for a in soup.find_all("a", href=True):
            href: str = a["href"].strip()

            # Skip non-http schemes and fragments
            if href.startswith(("#", "mailto:", "tel:", "javascript:")):
                continue

            # Resolve relative URLs
            if base_url:
                href = urljoin(base_url, href)

            # Deduplicate
            if href in seen:
                continue
            seen.add(href)

            text = clean_text(a.get_text())
            links.append({"href": href, "text": text})

        return links

    def _extract_tables(self, soup: BeautifulSoup) -> list[list[list[str]]]:
        """
        Parse all <table> elements into a list of 2-D string arrays.
        Each table → list of rows → list of cell texts.
        """
        tables = []
        for table in soup.find_all("table"):
            rows = []
            for tr in table.find_all("tr"):
                cells = [
                    clean_text(cell.get_text())
                    for cell in tr.find_all(["td", "th"])
                ]
                if any(cells):
                    rows.append(cells)
            if rows:
                tables.append(rows)
        return tables

    def _extract_images(self, soup: BeautifulSoup, base_url: str) -> list[dict[str, str]]:
        """
        Return all <img> elements as {"src": <absolute_url>, "alt": <alt_text>}.
        """
        images = []
        for img in soup.find_all("img", src=True):
            src = img["src"].strip()
            if base_url:
                src = urljoin(base_url, src)
            alt = clean_text(img.get("alt", ""))
            images.append({"src": src, "alt": alt})
        return images

    def _extract_raw_text(self, soup: BeautifulSoup) -> str:
        """
        Return the full visible text of the page with normalised whitespace.
        Useful as a fallback for full-text search or NLP pipelines.
        """
        return clean_text(soup.get_text(separator=" "))

    def _extract_open_graph(self, soup: BeautifulSoup) -> dict[str, str]:
        """
        Extract Open Graph (og:*) and Twitter Card (twitter:*) meta properties.
        """
        og: dict[str, str] = {}
        for tag in soup.find_all("meta"):
            prop = (tag.get("property") or tag.get("name") or "").lower().strip()
            content = tag.get("content", "").strip()
            if (prop.startswith("og:") or prop.startswith("twitter:")) and content:
                og[prop] = content
        return og
