"""
config/settings.py
Central configuration loaded from environment / .env file.
Import the `cfg` singleton everywhere — never hardcode values.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    # ── Tokenizer / Chunker ───────────────────────────────────────────────────
    tokenizer_model: str  = os.getenv("TOKENIZER_MODEL",
                                      "sentence-transformers/all-MiniLM-L6-v2")
    chunk_size:      int  = int(os.getenv("CHUNK_SIZE",      "256"))
    chunk_overlap:   int  = int(os.getenv("CHUNK_OVERLAP",   "32"))

    # ── Embedding model ───────────────────────────────────────────────────────
    embedding_model: str  = os.getenv("EMBEDDING_MODEL",     "all-MiniLM-L6-v2")
    embed_batch:     int  = int(os.getenv("EMBED_BATCH",     "64"))
    embed_device:    str  = os.getenv("EMBED_DEVICE",        "cpu")
    embed_dim:       int  = 384                                    # fixed for MiniLM

    # ── FAISS ─────────────────────────────────────────────────────────────────
    index_dir:  Path = ROOT / "data" / "indices"
    index_name: str  = os.getenv("INDEX_NAME",               "rag_index")
    top_k:      int  = int(os.getenv("TOP_K",               "5"))

    # ── TinyLlama ─────────────────────────────────────────────────────────────
    model_path:   Path  = ROOT / "models" / os.getenv(
                            "MODEL_FILE",
                            "tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf")
    llm_ctx:      int   = int(os.getenv("LLM_CTX",          "2048"))
    llm_tokens:   int   = int(os.getenv("LLM_MAX_TOKENS",   "512"))
    llm_temp:     float = float(os.getenv("LLM_TEMPERATURE", "0.1"))
    llm_top_p:    float = float(os.getenv("LLM_TOP_P",      "0.9"))
    llm_threads:  int   = int(os.getenv("LLM_THREADS",      "4"))
    llm_gpu:      int   = int(os.getenv("LLM_GPU_LAYERS",   "0"))
    llm_verbose:  bool  = os.getenv("LLM_VERBOSE", "false").lower() == "true"

    # ── Misc ──────────────────────────────────────────────────────────────────
    log_level:  str  = os.getenv("LOG_LEVEL",               "INFO")
    cache_dir:  Path = ROOT / "data" / "processed"


cfg = Settings()

# Ensure required directories exist at import time
for _d in [cfg.index_dir, cfg.cache_dir, ROOT / "models", ROOT / "logs"]:
    _d.mkdir(parents=True, exist_ok=True)
