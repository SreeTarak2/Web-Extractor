"""URL caching - avoids re-scraping same URLs with same query fields."""

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

CACHE_DIR = Path(__file__).parent.parent.parent / "output" / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _make_key(url: str, fields: list[str]) -> str:
    """Create cache key from URL and fields."""
    combined = f"{url}:{','.join(sorted(fields))}"
    return hashlib.sha256(combined.encode()).hexdigest()[:16]


def get(url: str, fields: list[str]) -> dict | None:
    """Get cached result for URL + fields. Returns None if not cached."""
    key = _make_key(url, fields)
    cache_file = CACHE_DIR / f"{key}.json"
    if cache_file.exists():
        try:
            with open(cache_file) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return None
    return None


def set(url: str, fields: list[str], result: dict) -> None:
    """Save result to cache for URL + fields."""
    key = _make_key(url, fields)
    cache_file = CACHE_DIR / f"{key}.json"
    data = {
        "url": url,
        "fields": fields,
        "result": result,
        "cached_at": datetime.now().isoformat(),
    }
    with open(cache_file, "w") as f:
        json.dump(data, f, indent=2)
