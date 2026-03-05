"""
url_utils.py
------------
URL normalisation and validation helpers.
"""

import hashlib
import re
from urllib.parse import (
    ParseResult,
    urljoin,
    urlparse,
    urlunparse,
    urlencode,
    parse_qs,
    quote,
)


# Query-string parameters that carry no semantic content and should be
# stripped before URL comparison / deduplication.
_TRACKING_PARAMS = frozenset(
    {
        "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
        "fbclid", "gclid", "msclkid", "ref", "referrer", "source",
        "_ga", "_gl", "mc_cid", "mc_eid",
    }
)


def normalize_url(url: str) -> str:
    """
    Produce a canonical form of *url* suitable for deduplication.

    Transformations applied:
    - Lowercase scheme and host.
    - Remove default ports (80 for http, 443 for https).
    - Sort query parameters alphabetically.
    - Remove known tracking query parameters.
    - Remove trailing slash from the path (except for root "/").
    - Strip URL fragment (#section).

    Parameters
    ----------
    url : str
        Raw URL string.

    Returns
    -------
    str
        Normalised URL.
    """
    url = url.strip()
    if not url:
        return url

    # Ensure scheme is present
    if not re.match(r"^https?://", url, re.IGNORECASE):
        url = "https://" + url

    parsed = urlparse(url)

    # Lowercase scheme + netloc
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()

    # Strip default ports
    if netloc.endswith(":80") and scheme == "http":
        netloc = netloc[:-3]
    elif netloc.endswith(":443") and scheme == "https":
        netloc = netloc[:-4]

    # Strip tracking params and sort remaining
    query_params = parse_qs(parsed.query, keep_blank_values=False)
    filtered = {k: v for k, v in query_params.items() if k not in _TRACKING_PARAMS}
    sorted_query = urlencode(sorted(filtered.items()), doseq=True)

    # Remove trailing slash (unless root path)
    path = parsed.path
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")

    normalised = urlunparse((scheme, netloc, path, parsed.params, sorted_query, ""))
    return normalised


def url_fingerprint(url: str) -> str:
    """
    Return a short SHA-256 hex digest of the normalised URL.
    Useful as a compact deduplification key.

    Parameters
    ----------
    url : str

    Returns
    -------
    str
        16-character hex string.
    """
    norm = normalize_url(url)
    return hashlib.sha256(norm.encode()).hexdigest()[:16]


def is_valid_url(url: str) -> bool:
    """
    Return True if *url* has a valid http(s) scheme and a non-empty host.

    Parameters
    ----------
    url : str

    Returns
    -------
    bool
    """
    try:
        parsed = urlparse(url)
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except Exception:
        return False


def same_domain(url_a: str, url_b: str) -> bool:
    """
    Return True if *url_a* and *url_b* share the same registered domain
    (excluding subdomains).

    Parameters
    ----------
    url_a, url_b : str

    Returns
    -------
    bool
    """
    def _root_domain(url: str) -> str:
        host = urlparse(url).netloc.lower().split(":")[0]
        parts = host.split(".")
        return ".".join(parts[-2:]) if len(parts) >= 2 else host

    return _root_domain(url_a) == _root_domain(url_b)
