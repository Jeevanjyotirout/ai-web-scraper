from bs4 import BeautifulSoup
from typing import Optional
from app.utils.text_utils import clean_text, chunk_text
from app.core.config import settings
from loguru import logger


# Tags that typically contain noise
NOISE_TAGS = {"script", "style", "noscript", "svg", "path", "meta", "link", "head"}


class BS4Parser:
    """Parse raw HTML into clean, chunked text segments."""

    def parse(self, html: str, url: str = "") -> dict:
        """Full parse: extract structured content from HTML."""
        soup = BeautifulSoup(html, "lxml")

        # Remove noise elements
        for tag in soup(NOISE_TAGS):
            tag.decompose()

        title = self._get_title(soup)
        headings = self._get_headings(soup)
        paragraphs = self._get_paragraphs(soup)
        tables = self._get_tables(soup)
        links = self._get_links(soup, url)
        lists = self._get_lists(soup)
        full_text = self._get_full_text(soup)

        # Chunk the full text for embedding
        chunks = chunk_text(full_text, settings.CHUNK_SIZE, settings.CHUNK_OVERLAP)

        logger.debug(f"Parsed {url}: {len(chunks)} chunks, {len(tables)} tables")

        return {
            "url": url,
            "title": title,
            "headings": headings,
            "paragraphs": paragraphs,
            "tables": tables,
            "links": links,
            "lists": lists,
            "full_text": full_text,
            "chunks": chunks,
        }

    def _get_title(self, soup: BeautifulSoup) -> str:
        tag = soup.find("title")
        return clean_text(tag.get_text()) if tag else ""

    def _get_headings(self, soup: BeautifulSoup) -> list[dict]:
        headings = []
        for level in range(1, 7):
            for tag in soup.find_all(f"h{level}"):
                text = clean_text(tag.get_text())
                if text:
                    headings.append({"level": level, "text": text})
        return headings

    def _get_paragraphs(self, soup: BeautifulSoup) -> list[str]:
        paras = []
        for p in soup.find_all("p"):
            text = clean_text(p.get_text())
            if len(text) > 30:
                paras.append(text)
        return paras

    def _get_tables(self, soup: BeautifulSoup) -> list[dict]:
        tables = []
        for table in soup.find_all("table"):
            rows = []
            headers = []

            # Extract headers
            for th in table.find_all("th"):
                headers.append(clean_text(th.get_text()))

            # Extract rows
            for tr in table.find_all("tr"):
                cells = [clean_text(td.get_text()) for td in tr.find_all("td")]
                if cells:
                    rows.append(cells)

            if rows:
                tables.append({"headers": headers, "rows": rows})

        return tables

    def _get_links(self, soup: BeautifulSoup, base_url: str) -> list[dict]:
        links = []
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            text = clean_text(a.get_text())
            if text and href and not href.startswith(("#", "javascript:")):
                links.append({"text": text, "href": href})
        return links[:100]  # cap at 100

    def _get_lists(self, soup: BeautifulSoup) -> list[list[str]]:
        result = []
        for ul in soup.find_all(["ul", "ol"]):
            items = [clean_text(li.get_text()) for li in ul.find_all("li")]
            items = [i for i in items if len(i) > 3]
            if items:
                result.append(items)
        return result

    def _get_full_text(self, soup: BeautifulSoup) -> str:
        text = soup.get_text(separator=" ", strip=True)
        return clean_text(text)
