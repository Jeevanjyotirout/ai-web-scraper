import numpy as np
from sentence_transformers import SentenceTransformer
from typing import Optional
from app.core.config import settings
from loguru import logger

_model: Optional[SentenceTransformer] = None


def get_embedding_model() -> SentenceTransformer:
    global _model
    if _model is None:
        logger.info(f"Loading embedding model: {settings.EMBEDDING_MODEL}")
        _model = SentenceTransformer(settings.EMBEDDING_MODEL)
        logger.info("Embedding model loaded")
    return _model


def embed_texts(texts: list[str]) -> np.ndarray:
    """Embed a list of text strings into float32 vectors."""
    model = get_embedding_model()
    embeddings = model.encode(texts, show_progress_bar=False, convert_to_numpy=True)
    return embeddings.astype("float32")


def embed_query(query: str) -> np.ndarray:
    """Embed a single query string."""
    return embed_texts([query])[0]
