"""tests/test_encoder.py"""
import numpy as np
import pytest
from src.embeddings.encoder import Encoder, EncodedChunks
from src.tokenizer.chunker import Chunker

TEXT = (
    "Deep learning models transform medical diagnosis accuracy. "
    "Neural networks detect patterns humans cannot see in imaging data."
)


@pytest.fixture(scope="module")
def enc():
    return Encoder()


@pytest.fixture(scope="module")
def chunks():
    return Chunker(size=64, overlap=8).chunk(TEXT)


def test_encode_returns_encoded_chunks(enc, chunks):
    result = enc.encode(chunks)
    assert isinstance(result, EncodedChunks)
    assert result.n == len(chunks)

def test_shape_is_correct(enc, chunks):
    result = enc.encode(chunks)
    assert result.vectors.shape == (result.n, 384)

def test_dtype_float32(enc, chunks):
    result = enc.encode(chunks)
    assert result.vectors.dtype == np.float32

def test_vectors_are_unit_norm(enc, chunks):
    result = enc.encode(chunks)
    norms = np.linalg.norm(result.vectors, axis=1)
    assert np.allclose(norms, 1.0, atol=1e-4)

def test_encode_query_shape(enc):
    q = enc.encode_query("What is machine learning?")
    assert q.shape == (1, 384)
    assert q.dtype == np.float32

def test_encode_text_single(enc):
    v = enc.encode_text("hello world")
    assert v.shape == (384,)

def test_encode_text_list(enc):
    v = enc.encode_text(["hello", "world", "AI"])
    assert v.shape == (3, 384)

def test_semantically_similar_closer(enc):
    v1 = enc.encode_text("machine learning artificial intelligence")
    v2 = enc.encode_text("deep learning neural networks AI")
    v3 = enc.encode_text("pasta cooking recipe tomato sauce")
    d_sim  = float(np.linalg.norm(v1 - v2))
    d_dis  = float(np.linalg.norm(v1 - v3))
    assert d_sim < d_dis

def test_empty_chunks(enc):
    result = enc.encode([])
    assert result.n == 0
    assert result.vectors.shape == (0, 384)
