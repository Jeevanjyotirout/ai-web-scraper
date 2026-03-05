"""tests/test_store.py"""
import numpy as np
import pytest
from config.settings import VectorStoreConfig
from src.embeddings.encoder import Encoder, EncodedChunks
from src.tokenizer.chunker import Chunker
from src.vector_store.store import Hit, VectorStore

TEXT = (
    "AI improves cancer detection accuracy significantly. "
    "Machine learning algorithms help radiologists read CT scans. "
    "Neural networks classify tumours with high precision. "
    "Natural language processing simplifies clinical note documentation."
)


@pytest.fixture(scope="module")
def encoder():
    return Encoder()


@pytest.fixture(scope="module")
def encoded(encoder):
    chunks = Chunker(size=64, overlap=8).chunk(TEXT)
    return encoder.encode(chunks)


@pytest.fixture
def store(tmp_path):
    return VectorStore(index_dir=tmp_path, index_name="test", dim=384)


def test_add_and_size(store, encoded):
    assert store.is_empty
    store.add(encoded)
    assert store.size == encoded.n
    assert not store.is_empty

def test_search_returns_hits(store, encoder, encoded):
    if store.is_empty:
        store.add(encoded)
    hits = store.search(encoder.encode_query("cancer detection AI"))
    assert len(hits) > 0
    assert all(isinstance(h, Hit) for h in hits)

def test_hits_ranked(store, encoder, encoded):
    if store.is_empty:
        store.add(encoded)
    hits = store.search(encoder.encode_query("machine learning diagnosis"))
    scores = [h.score for h in hits]
    assert scores == sorted(scores)

def test_ranks_sequential(store, encoder, encoded):
    if store.is_empty:
        store.add(encoded)
    hits = store.search(encoder.encode_query("deep learning"))
    assert [h.rank for h in hits] == list(range(1, len(hits) + 1))

def test_similarity_in_range(store, encoder, encoded):
    if store.is_empty:
        store.add(encoded)
    hits = store.search(encoder.encode_query("healthcare AI"))
    for h in hits:
        assert 0.0 <= h.similarity <= 1.0

def test_search_empty_store(tmp_path, encoder):
    s    = VectorStore(index_dir=tmp_path / "empty", index_name="e")
    hits = s.search(encoder.encode_query("test"))
    assert hits == []

def test_save_and_load(tmp_path, encoded):
    s = VectorStore(index_dir=tmp_path, index_name="sl", dim=384)
    s.add(encoded)
    s.save()
    s2 = VectorStore(index_dir=tmp_path, index_name="sl", dim=384)
    assert s2.load()
    assert s2.size == s.size

def test_load_missing_returns_false(tmp_path):
    s = VectorStore(index_dir=tmp_path / "no", index_name="none")
    assert s.load() is False

def test_reset(tmp_path, encoded):
    s = VectorStore(index_dir=tmp_path / "r", index_name="r", dim=384)
    s.add(encoded)
    s.reset()
    assert s.is_empty

def test_add_empty_encoded(store):
    empty = EncodedChunks(np.zeros((0, 384), dtype=np.float32), [])
    store.add(empty)   # must not raise
