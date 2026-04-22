"""Convert relative URLs to absolute URLs."""
from urllib.parse import urljoin, urlparse


def resolve(url: str, base_url: str) -> str:
    """Make a URL absolute given a base URL."""
    if not url:
        return url
    # Protocol-relative
    if url.startswith("//"):
        parsed = urlparse(base_url)
        return f"{parsed.scheme}:{url}"
    # Already absolute
    if url.startswith("http://") or url.startswith("https://"):
        return url
    return urljoin(base_url, url)


def resolve_all(urls: list[str], base_url: str) -> list[str]:
    return [resolve(u, base_url) for u in urls]
