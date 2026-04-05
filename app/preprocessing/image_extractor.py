"""Extract image URLs from raw HTML using code — never the LLM."""

import json
import re
import logging
from urllib.parse import urlparse, unquote, parse_qs, urljoin

logger = logging.getLogger(__name__)

# Patterns to skip (placeholders, tracking pixels, base64)
_SKIP_PATTERNS = (
    "data:image",
    "pixel.gif",
    "spacer.gif",
    "blank.gif",
    "1x1",
    "placeholder",
    ".svg",
    "svg+xml",
    "base64",
    "tracking",
    "analytics",
    "beacon",
    "icon",
    "favicon",
    "logo.png",  # Will handle logos separately
    "logo.jpg",
)

# Minimum meaningful dimension (filter tiny icons)
_MIN_SIZE_HINT = 50  # px — filters images with explicit small size in URL

# Logo patterns - common paths/names for organization logos
_LOGO_PATTERNS = (
    "/logo",
    "-logo",
    "_logo",
    "logo-",
    "/brand",
    "/branding",
    "/identity",
    "/site-logo",
    "/header-logo",
    "brand-logo",
)


def _is_logo(url: str) -> bool:
    """Check if URL looks like a logo based on path patterns."""
    url_lower = url.lower()
    return any(pat in url_lower for pat in _LOGO_PATTERNS)


def _is_skip(url: str) -> bool:
    url_lower = url.lower()
    return any(pat in url_lower for pat in _SKIP_PATTERNS)


def _normalize(url: str, base_url: str = "") -> str:
    """Decode CDN wrappers and return the cleanest URL."""
    if not url:
        return ""

    # Skip data URLs
    if url.startswith("data:"):
        return ""

    # Skip empty strings
    url = url.strip()
    if not url:
        return ""

    # Decode next.js images
    decoded = _decode_nextjs_image(url)
    if decoded:
        url = decoded

    # Decode other CDNs
    url = _decode_cdn_url(url)

    # Make relative URLs absolute
    if base_url:
        if url.startswith("/"):
            url = urljoin(base_url, url)
        elif not url.startswith("http"):
            url = urljoin(base_url, url)

    return url


def _decode_nextjs_image(url: str) -> str | None:
    """/_next/image?url=<encoded>&w=...  →  original URL."""
    if "/_next/image" in url:
        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        if "url" in qs:
            return unquote(qs["url"][0])
    return None


def _decode_shopify_cdn(url: str) -> str:
    """Remove Shopify size modifiers: _300x300.jpg → .jpg"""
    return re.sub(r"_\d+x\d+(\.\w+)", r"\1", url)


def _decode_wordpress_cdn(url: str) -> str:
    """Remove WordPress size suffix: -300x200.jpg → .jpg"""
    return re.sub(r"-\d+x\d+(\.\w+)", r"\1", url)


def _decode_cloudinary(url: str) -> str:
    """Remove Cloudinary transformations: /w_500,c_limit/ → /"""
    return re.sub(r"/[a-z]_\d+,[a-z_]+/", "/", url)


def _decode_imgix(url: str) -> str:
    """Remove imgix parameters: ?w=500&h=400&fit=crop → ?"""
    return url.split("?")[0] if "?" in url else url


def _decode_cdn_url(url: str) -> str:
    """Decode various CDN URL patterns to get original image."""
    # WordPress
    if "wp-content" in url or "wordpress" in url:
        url = _decode_wordpress_cdn(url)
    # Shopify
    if "shopify" in url or "cdn.shopify" in url:
        url = _decode_shopify_cdn(url)
    # Cloudinary
    if "cloudinary" in url:
        url = _decode_cloudinary(url)
    # imgix
    if "imgix" in url:
        url = _decode_imgix(url)
    # Generic CDN cleanup
    if any(cdn in url for cdn in ("cloudfront", "imgix", "fastly", "cdn")):
        url = url.split("?")[0]
    # Remove common size params
    url = re.sub(r"[?&](w|h)=\d+", "", url)
    url = re.sub(r"[?&]fit=\w+", "", url)
    url = re.sub(r"[?&]crop=\w+", "", url)
    url = re.sub(r"[?&]auto=\w+", "", url)
    return url.split("?")[0] if "?" in url else url


def _pick_best_srcset(srcset: str) -> str | None:
    """Parse srcset and return the URL with the largest width descriptor."""
    best_url = None
    best_w = 0
    for part in srcset.split(","):
        part = part.strip()
        if not part:
            continue
        tokens = part.split()
        if not tokens:
            continue
        candidate_url = tokens[0]
        width = 0
        if len(tokens) > 1:
            w_str = tokens[1].lower().rstrip("w")
            try:
                width = int(w_str)
            except ValueError:
                pass
        if width > best_w:
            best_w = width
            best_url = candidate_url
    return best_url


def _extract_jsonld_images(html: str) -> list[str]:
    """Pull image URLs from JSON-LD structured data blocks."""
    urls = []
    for block in re.finditer(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html,
        re.DOTALL | re.IGNORECASE,
    ):
        try:
            data = json.loads(block.group(1))
            # Support both single object and @graph arrays
            items = data if isinstance(data, list) else [data]
            for item in items:
                for key in ("image", "thumbnail", "logo"):
                    val = item.get(key)
                    if isinstance(val, str):
                        urls.append(val)
                    elif isinstance(val, dict):
                        u = val.get("url") or val.get("contentUrl")
                        if u:
                            urls.append(u)
                    elif isinstance(val, list):
                        for v in val:
                            if isinstance(v, str):
                                urls.append(v)
        except Exception:
            continue
    return urls


def extract_images(raw_html: str, base_url: str = "") -> list[str]:
    """
    Extract all image URLs from raw HTML.
    Returns deduplicated list sorted by source quality (best first).
    """
    tier1: list[str] = []  # JSON-LD
    tier2: list[str] = []  # OG meta
    tier3: list[str] = []  # srcset
    tier4: list[str] = []  # src / data-src
    tier5: list[str] = []  # background-image
    logos: list[str] = []  # Logo images

    # Track alt text for each URL
    alt_texts: dict[str, str] = {}

    # Tier 1: JSON-LD
    tier1.extend(_extract_jsonld_images(raw_html))

    # Tier 2: Open Graph
    for m in re.finditer(
        r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
        raw_html,
        re.IGNORECASE,
    ):
        tier2.append(m.group(1))
    # reversed attribute order
    for m in re.finditer(
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
        raw_html,
        re.IGNORECASE,
    ):
        tier2.append(m.group(1))

    # OG image alt (sometimes available)
    for m in re.finditer(
        r'<meta[^>]+property=["\']og:image:alt["\'][^>]+content=["\']([^"\']+)["\']',
        raw_html,
        re.IGNORECASE,
    ):
        og_url_m = re.search(
            r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
            raw_html[max(0, m.start() - 200) : m.start()],
            re.IGNORECASE,
        )
        if og_url_m:
            url = _normalize(og_url_m.group(1), base_url)
            alt_texts[url] = m.group(1)

    # Tier 3 & 4: <img> tags with alt extraction
    for m in re.finditer(r"<img\b([^>]*)>", raw_html, re.IGNORECASE):
        attrs = m.group(1)

        # Extract src and alt
        src = ""
        alt = ""

        # data-src / data-lazy-src (lazy loading)
        for attr in ("data-src", "data-lazy-src", "data-original", "data-img"):
            ds_m = re.search(rf'{attr}=["\']([^"\']+)["\']', attrs, re.IGNORECASE)
            if ds_m:
                src = ds_m.group(1)
                break

        # src (fallback)
        if not src:
            src_m = re.search(r'\bsrc=["\']([^"\']+)["\']', attrs, re.IGNORECASE)
            if src_m:
                src = src_m.group(1)

        # alt attribute
        alt_m = re.search(r'\balt=["\']([^"\']*)["\']', attrs, re.IGNORECASE)
        if alt_m:
            alt = alt_m.group(1).strip()

        if src:
            src = _normalize(src, base_url)

            # Check if it's a logo
            if _is_logo(src):
                logos.append(src)
            else:
                # Add to appropriate tier
                tier4.append(src)
                if alt:
                    alt_texts[src] = alt

        # srcset (separate tier)
        srcset_m = re.search(r'srcset=["\']([^"\']+)["\']', attrs, re.IGNORECASE)
        if srcset_m:
            best = _pick_best_srcset(srcset_m.group(1))
            if best:
                best = _normalize(best, base_url)
                if _is_logo(best):
                    logos.append(best)
                else:
                    tier3.append(best)

    # <picture> sources
    for m in re.finditer(r"<source\b([^>]*)>", raw_html, re.IGNORECASE):
        attrs = m.group(1)
        srcset_m = re.search(r'srcset=["\']([^"\']+)["\']', attrs, re.IGNORECASE)
        if srcset_m:
            best = _pick_best_srcset(srcset_m.group(1))
            if best:
                best = _normalize(best, base_url)
                if _is_logo(best):
                    logos.append(best)
                else:
                    tier3.append(best)

    # Tier 5: inline background-image
    for m in re.finditer(
        r'background-image\s*:\s*url\(["\']?([^"\')\s]+)["\']?\)',
        raw_html,
        re.IGNORECASE,
    ):
        tier5.append(m.group(1))

    # Merge in quality order: tier1-3-4-5, then logos as fallback
    seen: set[str] = set()
    result: list[str] = []

    # First: main content images
    for url in tier1 + tier2 + tier3 + tier4 + tier5:
        url = url.strip()
        if not url:
            continue
        url = _normalize(url, base_url)
        if _is_skip(url):
            continue
        if url in seen:
            continue
        seen.add(url)
        result.append(url)

    # Then: logos (as fallback)
    for url in logos:
        url = url.strip()
        if not url:
            continue
        url = _normalize(url, base_url)
        if _is_skip(url):
            continue
        if url in seen:
            continue
        seen.add(url)
        result.append(url)

    logger.debug(f"Extracted {len(result)} unique images (incl. {len(logos)} logos)")
    return result


def extract_images_with_metadata(raw_html: str, base_url: str = "") -> dict:
    """
    Extract images with full metadata (URLs, alt text, logos).
    Returns: {"images": [...], "logos": [...], "alt_texts": {...}}
    """
    images = extract_images(raw_html, base_url)

    # Now separate logos from main images
    logos = [url for url in images if _is_logo(url)]
    main_images = [url for url in images if not _is_logo(url)]

    return {
        "images": main_images,
        "logos": logos,
        "all": images,
    }
