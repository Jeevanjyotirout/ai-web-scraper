import re
from typing import Generator


def clean_text(text: str) -> str:
    """Remove extra whitespace, control characters, and normalize text."""
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def chunk_text(text: str, chunk_size: int = 512, overlap: int = 50) -> list[str]:
    """Split text into overlapping chunks by word boundary."""
    words = text.split()
    chunks = []
    start = 0
    while start < len(words):
        end = start + chunk_size
        chunk = ' '.join(words[start:end])
        if chunk.strip():
            chunks.append(chunk)
        start += chunk_size - overlap
    return chunks


def truncate_text(text: str, max_chars: int = 4000) -> str:
    """Truncate text to max_chars, preserving word boundary."""
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rsplit(' ', 1)[0] + "..."


def extract_json_from_llm(text: str) -> str:
    """Extract JSON block from LLM response."""
    # Try markdown code block first
    match = re.search(r'```(?:json)?\s*([\s\S]*?)```', text)
    if match:
        return match.group(1).strip()
    # Try to find raw JSON array or object
    match = re.search(r'(\[[\s\S]*\]|\{[\s\S]*\})', text)
    if match:
        return match.group(1).strip()
    return text.strip()


def sanitize_filename(name: str) -> str:
    """Make a string safe for use as a filename."""
    name = re.sub(r'[^\w\s-]', '', name)
    name = re.sub(r'[-\s]+', '_', name)
    return name[:64].strip('_')
