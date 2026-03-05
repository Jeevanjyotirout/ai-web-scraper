"""
test_scraper.py
---------------
Unit and integration tests for the scraping engine.
Run with: pytest tests/ -v
"""

import asyncio
import pytest

from models.extracted_data import ExtractedData
from models.page_result import PageResult
from scraper.extractor import ContentExtractor
from scraper.paginator import PaginationHandler
from utils.text_utils import clean_text, truncate_text, extract_numbers, slugify
from utils.url_utils import normalize_url, url_fingerprint, is_valid_url, same_domain
from utils.visited_tracker import VisitedTracker


# ─────────────────────────────────────────────────────────────────────────────
# text_utils
# ─────────────────────────────────────────────────────────────────────────────

class TestCleanText:
    def test_collapses_whitespace(self):
        assert clean_text("hello   \n\t  world") == "hello world"

    def test_strips_leading_trailing(self):
        assert clean_text("  hi  ") == "hi"

    def test_empty_string(self):
        assert clean_text("") == ""

    def test_zero_width_removed(self):
        assert clean_text("hel\u200blo") == "hello"

    def test_unicode_nfc(self):
        # é as two code points → single NFC character
        assert clean_text("cafe\u0301") == "café"


class TestTruncateText:
    def test_no_truncation_needed(self):
        assert truncate_text("short", 100) == "short"

    def test_truncates_at_word_boundary(self):
        result = truncate_text("one two three four five", max_chars=15)
        assert len(result) <= 15
        assert result.endswith("…")

    def test_custom_suffix(self):
        result = truncate_text("hello world", max_chars=8, suffix="...")
        assert result.endswith("...")


class TestExtractNumbers:
    def test_integers(self):
        assert extract_numbers("Page 1 of 10") == [1.0, 10.0]

    def test_floats(self):
        assert extract_numbers("$1,299.99") == [1299.99]

    def test_negative(self):
        assert -5.0 in extract_numbers("Temperature: -5.0°C")


class TestSlugify:
    def test_basic(self):
        assert slugify("Hello World") == "hello-world"

    def test_special_chars(self):
        assert slugify("Hello, World! 2024") == "hello-world-2024"

    def test_accents_stripped(self):
        assert slugify("café résumé") == "cafe-resume"


# ─────────────────────────────────────────────────────────────────────────────
# url_utils
# ─────────────────────────────────────────────────────────────────────────────

class TestNormalizeUrl:
    def test_lowercase_scheme(self):
        assert normalize_url("HTTP://Example.com/path") == "http://example.com/path"

    def test_removes_default_port_80(self):
        assert normalize_url("http://example.com:80/") == "http://example.com"

    def test_removes_default_port_443(self):
        assert normalize_url("https://example.com:443/") == "https://example.com"

    def test_strips_tracking_params(self):
        url = "https://example.com/page?utm_source=google&id=1"
        normalised = normalize_url(url)
        assert "utm_source" not in normalised
        assert "id=1" in normalised

    def test_strips_fragment(self):
        assert "#section" not in normalize_url("https://example.com/page#section")

    def test_adds_scheme_if_missing(self):
        result = normalize_url("example.com/path")
        assert result.startswith("https://")


class TestIsValidUrl:
    def test_valid_http(self):
        assert is_valid_url("http://example.com")

    def test_valid_https(self):
        assert is_valid_url("https://example.com/path?q=1")

    def test_invalid_no_scheme(self):
        assert not is_valid_url("example.com")

    def test_invalid_ftp(self):
        assert not is_valid_url("ftp://example.com")


class TestSameDomain:
    def test_same_domain(self):
        assert same_domain("https://news.example.com/a", "https://blog.example.com/b")

    def test_different_domain(self):
        assert not same_domain("https://example.com", "https://other.com")


# ─────────────────────────────────────────────────────────────────────────────
# VisitedTracker
# ─────────────────────────────────────────────────────────────────────────────

class TestVisitedTracker:
    def test_initially_empty(self):
        tracker = VisitedTracker()
        assert not tracker.has("https://example.com")

    def test_add_and_has(self):
        tracker = VisitedTracker()
        tracker.add("https://example.com")
        assert tracker.has("https://example.com")

    def test_count(self):
        tracker = VisitedTracker()
        tracker.add("https://a.com")
        tracker.add("https://b.com")
        assert tracker.count() == 2

    def test_canonical_equivalence(self):
        tracker = VisitedTracker()
        tracker.add("https://example.com/?utm_source=x")
        # Normalised form (without tracking param) should also match
        assert tracker.has("https://example.com/")

    def test_clear(self):
        tracker = VisitedTracker()
        tracker.add("https://example.com")
        tracker.clear()
        assert tracker.count() == 0


# ─────────────────────────────────────────────────────────────────────────────
# ContentExtractor
# ─────────────────────────────────────────────────────────────────────────────

SAMPLE_HTML = """
<!DOCTYPE html>
<html>
<head>
  <title>Test Page</title>
  <meta name="description" content="A test page for scraping.">
  <meta property="og:title" content="OG Test Title">
</head>
<body>
  <h1>Main Heading</h1>
  <h2>Sub Heading One</h2>
  <h2>Sub Heading Two</h2>
  <p>This is a long enough paragraph to pass the 20-char filter easily.</p>
  <p>Another substantial paragraph with enough content to be included.</p>
  <p>Short</p>
  <a href="/relative">Relative Link</a>
  <a href="https://external.com">External</a>
  <table>
    <tr><th>Name</th><th>Value</th></tr>
    <tr><td>Alpha</td><td>1</td></tr>
  </table>
  <img src="/images/pic.jpg" alt="A picture">
  <script>console.log('noise');</script>
  <style>body { color: red; }</style>
</body>
</html>
"""


class TestContentExtractor:
    def setup_method(self):
        self.extractor = ContentExtractor()
        self.data = self.extractor.extract_content(SAMPLE_HTML, base_url="https://example.com")

    def test_title_extracted(self):
        assert self.data.title == "Test Page"

    def test_meta_description(self):
        assert self.data.meta["description"] == "A test page for scraping."

    def test_headings_h1(self):
        assert "Main Heading" in self.data.headings.get("h1", [])

    def test_headings_h2(self):
        assert len(self.data.headings.get("h2", [])) == 2

    def test_paragraphs_filtered(self):
        # "Short" should be filtered (< 20 chars)
        for p in self.data.paragraphs:
            assert len(p) >= 20

    def test_links_resolved(self):
        hrefs = [link["href"] for link in self.data.links]
        assert "https://example.com/relative" in hrefs
        assert "https://external.com" in hrefs

    def test_table_parsed(self):
        assert len(self.data.tables) == 1
        assert self.data.tables[0][0] == ["Name", "Value"]
        assert self.data.tables[0][1] == ["Alpha", "1"]

    def test_images_resolved(self):
        srcs = [img["src"] for img in self.data.images]
        assert "https://example.com/images/pic.jpg" in srcs

    def test_open_graph(self):
        assert self.data.open_graph.get("og:title") == "OG Test Title"

    def test_script_and_style_stripped(self):
        assert "console.log" not in self.data.raw_text
        assert "color: red" not in self.data.raw_text

    def test_to_dict_serialisable(self):
        import json
        d = self.data.to_dict()
        serialised = json.dumps(d)
        assert "Test Page" in serialised


# ─────────────────────────────────────────────────────────────────────────────
# PaginationHandler
# ─────────────────────────────────────────────────────────────────────────────

PAGINATED_HTML_WITH_NEXT = """
<html><body>
  <a href="/articles?page=2">Next</a>
</body></html>
"""

PAGINATED_HTML_REL_NEXT = """
<html>
<head>
  <link rel="next" href="/articles?page=3">
</head>
<body>Content</body>
</html>
"""

PAGINATED_HTML_NO_NEXT = """
<html><body><p>Last page, no next link.</p></body></html>
"""


class TestPaginationHandler:
    def setup_method(self):
        self.handler = PaginationHandler(max_pages=10)

    def test_yields_start_url(self):
        pages = list(self.handler.iter_pages("https://example.com/articles", PAGINATED_HTML_NO_NEXT))
        assert pages[0] == "https://example.com/articles"

    def test_finds_next_link(self):
        pages = list(self.handler.iter_pages("https://example.com/articles", PAGINATED_HTML_WITH_NEXT))
        assert len(pages) == 2
        assert pages[1] == "https://example.com/articles?page=2"

    def test_finds_rel_next(self):
        url = self.handler._find_next_page_url("https://example.com/articles?page=2", PAGINATED_HTML_REL_NEXT)
        assert url == "https://example.com/articles?page=3"

    def test_no_next_returns_none(self):
        url = self.handler._find_next_page_url("https://example.com/page", PAGINATED_HTML_NO_NEXT)
        assert url is None

    def test_build_page_url(self):
        url = self.handler.build_page_url("https://example.com/items", 5)
        assert "page=5" in url

    def test_max_pages_respected(self):
        handler = PaginationHandler(max_pages=3)
        html_with_next = '<html><body><a href="?page={n}">Next</a></body></html>'
        # Even if there's always a next link, should stop at max_pages
        pages = list(handler.iter_pages("https://example.com/?page=1", html_with_next))
        assert len(pages) <= 3


# ─────────────────────────────────────────────────────────────────────────────
# PageResult model
# ─────────────────────────────────────────────────────────────────────────────

class TestPageResult:
    def test_was_redirected_false(self):
        r = PageResult(url="https://a.com", final_url="https://a.com", status_code=200, html="")
        assert not r.was_redirected

    def test_was_redirected_true(self):
        r = PageResult(url="https://a.com", final_url="https://b.com", status_code=200, html="")
        assert r.was_redirected

    def test_html_size_bytes(self):
        r = PageResult(url="https://a.com", final_url="https://a.com", status_code=200, html="hello")
        assert r.html_size_bytes == 5
