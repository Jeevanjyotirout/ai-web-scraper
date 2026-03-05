"""tests/test_chunker.py"""
import pytest
from src.tokenizer.chunker import Chunk, Chunker

TEXT = (
    "Artificial intelligence is transforming healthcare diagnostics. "
    "Machine learning models now detect cancer with 95% accuracy. "
    "Deep learning has revolutionised medical imaging and clinical workflows. "
    "Researchers at Stanford have pioneered AI-assisted diagnostic tools."
)


@pytest.fixture(scope="module")
def ck():
    return Chunker(size=64, overlap=8)


def test_returns_chunks(ck):
    chunks = ck.chunk(TEXT)
    assert len(chunks) >= 1
    assert all(isinstance(c, Chunk) for c in chunks)

def test_chunk_text_nonempty(ck):
    for c in ck.chunk(TEXT):
        assert c.text.strip() != ""

def test_ids_sequential(ck):
    chunks = ck.chunk(TEXT * 10)
    assert [c.chunk_id for c in chunks] == list(range(len(chunks)))

def test_token_count_within_size(ck):
    for c in ck.chunk(TEXT * 5):
        assert c.token_count <= ck.size

def test_empty_input_returns_empty(ck):
    assert ck.chunk("") == []
    assert ck.chunk("   \n\t") == []

def test_meta_propagated(ck):
    chunks = ck.chunk(TEXT, meta={"src": "unit-test"})
    for c in chunks:
        assert c.meta["src"] == "unit-test"

def test_overlap_start_tokens(ck):
    chunks = ck.chunk(TEXT * 8)
    if len(chunks) > 1:
        # Each chunk starts before the previous one ended
        assert chunks[1].start_tok < chunks[0].end_tok

def test_token_count_method(ck):
    n = ck.token_count("hello world")
    assert n > 0
