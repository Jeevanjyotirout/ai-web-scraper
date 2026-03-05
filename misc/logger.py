"""src/utils/logger.py — project-wide structured logger (Loguru)."""
from __future__ import annotations
import sys
from loguru import logger as _log
from config.settings import cfg

_log.remove()
_FMT = (
    "<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{line}</cyan> — <level>{message}</level>"
)
_log.add(sys.stdout, format=_FMT, level=cfg.log_level, colorize=True)
_log.add("logs/rag.log", format=_FMT, level="DEBUG",
         rotation="10 MB", retention="7 days", compression="zip", enqueue=True)


def get_logger(name: str):
    return _log.bind(name=name)
