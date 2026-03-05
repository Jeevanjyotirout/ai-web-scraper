"""src/utils/text_cleaner.py — normalise raw scraped text."""
from __future__ import annotations
import html, re, unicodedata
from typing import Optional


def clean(text: str) -> str:
    """Full cleaning pipeline for raw web-scraped text."""
    if not text or not text.strip():
        return ""
    text = html.unescape(text)
    text = unicodedata.normalize("NFC", text)
    # Remove control characters (keep \n \t)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    # Normalise punctuation variants
    for src, dst in [("\u2018","'"),("\u2019","'"),("\u201c",'"'),
                     ("\u201d",'"'),("\u2013","-"),("\u2014","-"),("\u00a0"," ")]:
        text = text.replace(src, dst)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return "\n".join(l.strip() for l in text.splitlines()).strip()


def truncate(text: str, max_chars: int = 1800) -> str:
    """Truncate to max_chars at a word boundary."""
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars]
    sp = cut.rfind(" ")
    return cut[:sp] if sp > 0 else cut


def first_line_title(text: str) -> Optional[str]:
    """Heuristically extract a title from the first non-empty line."""
    for line in text.splitlines():
        line = line.strip()
        if 10 <= len(line) <= 200:
            return line
    return None
