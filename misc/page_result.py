"""
page_result.py
--------------
Data container returned by the scraping engine after a successful fetch.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class PageResult:
    """
    Raw output from a single browser navigation.

    Attributes
    ----------
    url : str
        The original requested URL.
    final_url : str
        The URL after all redirects have been followed.
    status_code : int
        HTTP status code of the final response (0 if unavailable).
    html : str
        Complete rendered HTML of the page after JavaScript execution.
    fetched_at : datetime
        UTC timestamp of when the page was captured.
    """

    url: str
    final_url: str
    status_code: int
    html: str
    fetched_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def was_redirected(self) -> bool:
        """True if the final URL differs from the requested URL."""
        return self.url != self.final_url

    @property
    def html_size_bytes(self) -> int:
        """Size of the raw HTML in bytes."""
        return len(self.html.encode("utf-8"))

    def __repr__(self) -> str:
        return (
            f"PageResult(url={self.url!r}, status={self.status_code}, "
            f"size={self.html_size_bytes} bytes)"
        )
