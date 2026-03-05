"""
Basic tests for AI Scraper backend.
Run: pytest backend/tests/ -v
"""
import pytest
from app.utils.text_utils import clean_text, chunk_text, extract_json_from_llm, sanitize_filename
from app.services.scraper.bs4_parser import BS4Parser


# ── text_utils ────────────────────────────────────────────────────────────────

def test_clean_text_removes_extra_whitespace():
    assert clean_text("hello   world\n\n  foo") == "hello world foo"


def test_clean_text_removes_control_chars():
    assert clean_text("hello\x00world") == "helloworld"


def test_chunk_text_basic():
    text = " ".join([f"word{i}" for i in range(200)])
    chunks = chunk_text(text, chunk_size=50, overlap=10)
    assert len(chunks) > 1
    for c in chunks:
        assert len(c.split()) <= 50


def test_chunk_text_empty():
    assert chunk_text("") == []


def test_extract_json_array():
    raw = 'Here is the result:\n```json\n[{"name": "Alice", "age": 30}]\n```'
    extracted = extract_json_from_llm(raw)
    import json
    data = json.loads(extracted)
    assert data[0]["name"] == "Alice"


def test_sanitize_filename():
    name = sanitize_filename("Hello World! @#$%")
    assert " " not in name
    assert "@" not in name


# ── BS4Parser ─────────────────────────────────────────────────────────────────

SAMPLE_HTML = """
<html>
<head><title>Test Page</title></head>
<body>
  <h1>Welcome to Test</h1>
  <p>This is a paragraph with enough content to be included in parsing results.</p>
  <table>
    <tr><th>Name</th><th>Price</th></tr>
    <tr><td>Widget A</td><td>$9.99</td></tr>
    <tr><td>Widget B</td><td>$19.99</td></tr>
  </table>
  <ul>
    <li>Item One</li>
    <li>Item Two</li>
  </ul>
</body>
</html>
"""


def test_bs4_parse_title():
    parser = BS4Parser()
    result = parser.parse(SAMPLE_HTML, "http://test.com")
    assert result["title"] == "Test Page"


def test_bs4_parse_headings():
    parser = BS4Parser()
    result = parser.parse(SAMPLE_HTML, "http://test.com")
    assert any(h["text"] == "Welcome to Test" for h in result["headings"])


def test_bs4_parse_tables():
    parser = BS4Parser()
    result = parser.parse(SAMPLE_HTML, "http://test.com")
    assert len(result["tables"]) == 1
    assert result["tables"][0]["headers"] == ["Name", "Price"]
    assert result["tables"][0]["rows"][0] == ["Widget A", "$9.99"]


def test_bs4_parse_lists():
    parser = BS4Parser()
    result = parser.parse(SAMPLE_HTML, "http://test.com")
    assert len(result["lists"]) >= 1


def test_bs4_parse_chunks_generated():
    parser = BS4Parser()
    result = parser.parse(SAMPLE_HTML, "http://test.com")
    assert len(result["chunks"]) >= 1
