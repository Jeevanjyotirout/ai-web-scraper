"""
visited_tracker.py
------------------
Thread-safe, memory-efficient tracker for visited URLs.
Uses URL fingerprints (SHA-256 truncated) to keep memory usage flat
regardless of URL string length.
"""

import logging
import threading
from pathlib import Path
from typing import Optional

from utils.url_utils import normalize_url, url_fingerprint

logger = logging.getLogger(__name__)


class VisitedTracker:
    """
    Tracks which URLs have already been scraped to prevent duplicate work.

    Uses a compact fingerprint set in memory and optionally persists the
    state to a text file so scraping jobs can be resumed after a crash.

    Parameters
    ----------
    persist_path : str | None
        If given, load existing fingerprints from this file on startup
        and append new ones as they are added.  Each line = one fingerprint.
    """

    def __init__(self, persist_path: Optional[str] = None):
        self._seen: set[str] = set()
        self._lock = threading.Lock()
        self._persist_path = Path(persist_path) if persist_path else None

        if self._persist_path and self._persist_path.exists():
            self._load_from_disk()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def has(self, url: str) -> bool:
        """
        Return True if *url* (or its canonical form) has been visited.

        Parameters
        ----------
        url : str

        Returns
        -------
        bool
        """
        fp = url_fingerprint(url)
        with self._lock:
            return fp in self._seen

    def add(self, url: str) -> None:
        """
        Mark *url* as visited.

        Parameters
        ----------
        url : str
        """
        fp = url_fingerprint(url)
        with self._lock:
            if fp not in self._seen:
                self._seen.add(fp)
                if self._persist_path:
                    self._append_to_disk(fp)
        logger.debug("Marked as visited: %s (fp=%s)", url, fp)

    def count(self) -> int:
        """Return the total number of tracked URLs."""
        with self._lock:
            return len(self._seen)

    def clear(self) -> None:
        """
        Clear all tracked URLs from memory (and truncate the persist file).
        """
        with self._lock:
            self._seen.clear()
            if self._persist_path and self._persist_path.exists():
                self._persist_path.write_text("")
        logger.info("VisitedTracker cleared.")

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    def _load_from_disk(self) -> None:
        """Load previously persisted fingerprints into memory."""
        try:
            text = self._persist_path.read_text(encoding="utf-8")
            fingerprints = {line.strip() for line in text.splitlines() if line.strip()}
            self._seen.update(fingerprints)
            logger.info("Loaded %d visited fingerprints from %s", len(fingerprints), self._persist_path)
        except OSError as exc:
            logger.warning("Could not load visited state from %s: %s", self._persist_path, exc)

    def _append_to_disk(self, fingerprint: str) -> None:
        """Append a single fingerprint to the persist file."""
        try:
            with open(self._persist_path, "a", encoding="utf-8") as f:
                f.write(fingerprint + "\n")
        except OSError as exc:
            logger.warning("Could not persist fingerprint: %s", exc)
