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
    "blank.jpg",
    "1x1",
    "placeholder",
    ".svg",
    "svg+xml",
    "base64",
    "tracking",
    "analytics",
    "beacon",
    "wp.com/i/blank",
    "pixel.wp.com",
    "icon",
    "favicon",
    # NOTE: logo.png / logo.jpg are NOT skipped here — they go to the logos list
    # via _is_logo() so they can serve as fallback images
)

# Minimum meaningful dimension (filter tiny icons)
_MIN_SIZE_HINT = 50  # px — filters images with explicit small size in URL

# Logo patterns - common paths/names for organization logos
_LOGO_PATTERNS = (
    "/logo",
    "-logo",
    "_logo",
    "logo-",
    "logo.",
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
    """Parse srcset and return the URL with the largest width descriptor.
    If no width descriptors are present, return the first URL found."""
    best_url = None
    best_w = 0
    first_url = None
    for part in srcset.split(","):
        part = part.strip()
        if not part:
            continue
        tokens = part.split()
        if not tokens:
            continue
        candidate_url = tokens[0]
        if first_url is None:
            first_url = candidate_url
        width = 0
        if len(tokens) > 1:
            w_str = tokens[1].lower().rstrip("w").rstrip("x")
            try:
                width = int(w_str)
            except ValueError:
                pass
        if width > best_w:
            best_w = width
            best_url = candidate_url
    # If nothing had a width descriptor, return the first URL
    return best_url or first_url


def _extract_jsonld_logos(html: str) -> list[str]:
    """Pull logo URLs specifically from JSON-LD structured data."""
    urls = []
    for block in re.finditer(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html,
        re.DOTALL | re.IGNORECASE,
    ):
        try:
            data = json.loads(block.group(1))
            items = data if isinstance(data, list) else [data]
            for item in items:
                val = item.get("logo")
                if isinstance(val, str):
                    urls.append(val)
                elif isinstance(val, dict):
                    u = val.get("url") or val.get("contentUrl")
                    if u:
                        urls.append(u)
        except Exception:
            continue
    return urls


def _extract_context_logos(html: str, base_url: str = "") -> list[tuple[str, str]]:
    """
    Find logos by their HTML context (header/nav/brand areas) rather than URL.
    Returns list of (url, alt) tuples.

    Catches logos whose URLs have no logo-related text, e.g. /assets/mark.png
    """
    results: list[tuple[str, str]] = []

    # CSS class/id patterns that indicate a logo image
    _LOGO_CLASS_PATTERNS = re.compile(
        r'(?:class|id)=["\'][^"\']*\b(?:logo|brand|navbar-brand|site-logo|header-logo'
        r'|site-header|brand-logo|company-logo|org-logo)[^"\']*["\']',
        re.IGNORECASE,
    )

    # Find <a> or <div> wrappers that have logo class/id, then extract img inside them
    # Match a opening tag with logo class up to 600 chars ahead for the img
    for container_m in re.finditer(
        r'<(?:a|div|span|header|figure)\b[^>]*(?:class|id)=["\'][^"\']*\b(?:logo|brand|navbar-brand|site-logo|header-logo|site-header|brand-logo)[^"\']*["\'][^>]*>((?:.|\n){0,600}?)</(?:a|div|span|header|figure)>',
        html,
        re.IGNORECASE,
    ):
        inner = container_m.group(1)
        for img_m in re.finditer(r"<img\b([^>]*)>", inner, re.IGNORECASE):
            attrs = img_m.group(1)
            src = ""
            alt = ""
            for attr in ("data-src", "data-lazy-src", "data-original"):
                ds = re.search(rf'{attr}=["\']([^"\']+)["\']', attrs, re.IGNORECASE)
                if ds:
                    src = ds.group(1)
                    break
            if not src:
                src_m = re.search(r'\bsrc=["\']([^"\']+)["\']', attrs, re.IGNORECASE)
                if src_m:
                    src = src_m.group(1)
            alt_m = re.search(r'\balt=["\']([^"\']*)["\']', attrs, re.IGNORECASE)
            if alt_m:
                alt = alt_m.group(1).strip()
            if src:
                src = _normalize(src, base_url)
                if src and not _is_skip(src):
                    results.append((src, alt))

        # Also check srcset inside picture/source inside the container
        for srcset_m in re.finditer(
            r'srcset=["\']([^"\']+)["\']', inner, re.IGNORECASE
        ):
            best = _pick_best_srcset(srcset_m.group(1))
            if best:
                best = _normalize(best, base_url)
                if best and not _is_skip(best):
                    results.append((best, ""))

    # Also: <img> tags that directly have logo class/id themselves
    for img_m in re.finditer(r"<img\b([^>]*)>", html, re.IGNORECASE):
        attrs = img_m.group(1)
        if not _LOGO_CLASS_PATTERNS.search(attrs):
            continue
        src = ""
        alt = ""
        for attr in ("data-src", "data-lazy-src"):
            ds = re.search(rf'{attr}=["\']([^"\']+)["\']', attrs, re.IGNORECASE)
            if ds:
                src = ds.group(1)
                break
        if not src:
            src_m = re.search(r'\bsrc=["\']([^"\']+)["\']', attrs, re.IGNORECASE)
            if src_m:
                src = src_m.group(1)
        alt_m = re.search(r'\balt=["\']([^"\']*)["\']', attrs, re.IGNORECASE)
        if alt_m:
            alt = alt_m.group(1).strip()
        if src:
            src = _normalize(src, base_url)
            if src and not _is_skip(src):
                results.append((src, alt))

    return results


def _extract_site_icon(html: str, base_url: str = "") -> str:
    """
    Last-resort: extract apple-touch-icon or favicon as site icon.
    Returns URL or empty string.
    """
    # Prefer apple-touch-icon (higher resolution than favicon)
    for m in re.finditer(
        r'<link[^>]+rel=["\']apple-touch-icon["\'][^>]+href=["\']([^"\']+)["\']',
        html,
        re.IGNORECASE,
    ):
        url = _normalize(m.group(1), base_url)
        if url:
            return url
    for m in re.finditer(
        r'<link[^>]+href=["\']([^"\']+)["\'][^>]+rel=["\']apple-touch-icon["\']',
        html,
        re.IGNORECASE,
    ):
        url = _normalize(m.group(1), base_url)
        if url:
            return url
    return ""


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
                for key in (
                    "image",
                    "thumbnail",
                ):  # "logo" handled by _extract_jsonld_logos
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


def _extract_images_core(
    raw_html: str, base_url: str = ""
) -> tuple[list[str], list[str], dict[str, str]]:
    """
    Core extraction logic.
    Returns:
        content_urls: Banner/hero/content images (ordered best-first)
        logo_urls:    Organization logos (fallback candidates)
        alt_texts:    Map of url → alt text for any image we found alt for
    """
    tier1: list[str] = []  # JSON-LD
    tier2: list[str] = []  # OG meta
    tier3: list[str] = []  # srcset
    tier4: list[str] = []  # src / data-src
    tier5: list[str] = []  # background-image / data-bg
    logo_urls: list[str] = []

    alt_texts: dict[str, str] = {}

    # Logo source A: JSON-LD "logo" key (highest confidence)
    for url in _extract_jsonld_logos(raw_html):
        url = _normalize(url, base_url)
        if url and not _is_skip(url):
            logo_urls.append(url)

    # Logo source B: context-based detection (header/nav/brand wrappers)
    for url, alt in _extract_context_logos(raw_html, base_url):
        logo_urls.append(url)
        if alt:
            alt_texts[url] = alt

    # Tier 1: JSON-LD (content images — image/thumbnail keys)
    tier1.extend(_extract_jsonld_images(raw_html))

    # Tier 2: Open Graph image
    for m in re.finditer(
        r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
        raw_html,
        re.IGNORECASE,
    ):
        tier2.append(m.group(1))
    for m in re.finditer(
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
        raw_html,
        re.IGNORECASE,
    ):
        tier2.append(m.group(1))

    # OG image alt
    og_alt_m = re.search(
        r'<meta[^>]+property=["\']og:image:alt["\'][^>]+content=["\']([^"\']+)["\']',
        raw_html,
        re.IGNORECASE,
    )
    if og_alt_m and tier2:
        og_url = _normalize(tier2[0], base_url)
        if og_url:
            alt_texts[og_url] = og_alt_m.group(1)

    # Also try reverse attribute order for og:image:alt
    og_alt_m2 = re.search(
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image:alt["\']',
        raw_html,
        re.IGNORECASE,
    )
    if og_alt_m2 and tier2 and tier2[0] not in alt_texts:
        og_url = _normalize(tier2[0], base_url)
        if og_url:
            alt_texts[og_url] = og_alt_m2.group(1)

    # og:title as alt fallback for OG image
    og_title_m = re.search(
        r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']',
        raw_html,
        re.IGNORECASE,
    )
    if og_title_m is None:
        og_title_m = re.search(
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:title["\']',
            raw_html,
            re.IGNORECASE,
        )
    og_title = og_title_m.group(1).strip() if og_title_m else ""

    # Tier 3 & 4: <img> tags
    for m in re.finditer(r"<img\b([^>]*)>", raw_html, re.IGNORECASE):
        attrs = m.group(1)

        src = ""
        alt = ""

        # data-src / lazy-loading variants first
        for attr in ("data-src", "data-lazy-src", "data-original", "data-img"):
            ds_m = re.search(rf'{attr}=["\']([^"\']+)["\']', attrs, re.IGNORECASE)
            if ds_m:
                src = ds_m.group(1)
                break

        if not src:
            src_m = re.search(r'\bsrc=["\']([^"\']+)["\']', attrs, re.IGNORECASE)
            if src_m:
                src = src_m.group(1)

        alt_m = re.search(r'\balt=["\']([^"\']*)["\']', attrs, re.IGNORECASE)
        if alt_m:
            alt = alt_m.group(1).strip()

        if src:
            src = _normalize(src, base_url)
            if not _is_skip(src):
                if _is_logo(src):
                    logo_urls.append(src)
                    if alt:
                        alt_texts[src] = alt
                else:
                    tier4.append(src)
                    if alt:
                        alt_texts[src] = alt

        # srcset
        srcset_m = re.search(r'srcset=["\']([^"\']+)["\']', attrs, re.IGNORECASE)
        if srcset_m:
            best = _pick_best_srcset(srcset_m.group(1))
            if best:
                best = _normalize(best, base_url)
                if not _is_skip(best):
                    if _is_logo(best):
                        logo_urls.append(best)
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
                if not _is_skip(best):
                    if _is_logo(best):
                        logo_urls.append(best)
                    else:
                        tier3.append(best)

    # Tier 5a: data-bg / data-background attributes on any element (e.g. Fusion Builder)
    for m in re.finditer(
        r'\bdata-b(?:g|ackground(?:-image)?)\s*=\s*["\']([^"\']+)["\']',
        raw_html,
        re.IGNORECASE,
    ):
        url = _normalize(m.group(1), base_url)
        if url and not _is_skip(url):
            tier5.append(url)

    # Tier 5b: inline background-image (handles &quot; HTML-encoded quotes)
    for m in re.finditer(
        r'background(?:-image)?\s*:[^;]*?url\s*\(\s*(?:&quot;|["\'])?([^"\'&)\s]+)(?:&quot;|["\'])?\s*\)',
        raw_html,
        re.IGNORECASE,
    ):
        url = _normalize(m.group(1), base_url)
        if url and not _is_skip(url):
            tier5.append(url)

    # Deduplicate content images (preserve tier order)
    seen: set[str] = set()
    content_urls: list[str] = []
    for url in tier1 + tier2 + tier3 + tier4 + tier5:
        url = url.strip()
        if not url or url in seen:
            continue
        url_n = _normalize(url, base_url)
        if not url_n or _is_skip(url_n) or url_n in seen:
            continue
        seen.add(url_n)
        content_urls.append(url_n)

    # Deduplicate logo images
    seen_logos: set[str] = set()
    unique_logos: list[str] = []
    for url in logo_urls:
        if url and url not in seen_logos:
            seen_logos.add(url)
            unique_logos.append(url)

    # If OG title is available and the OG image has no alt, use the title
    if og_title and tier2:
        og_url = _normalize(tier2[0], base_url)
        if og_url and og_url not in alt_texts:
            alt_texts[og_url] = og_title

    logger.debug(
        f"Extracted {len(content_urls)} content images, {len(unique_logos)} logos"
    )
    return content_urls, unique_logos, alt_texts


def extract_images(raw_html: str, base_url: str = "") -> list[str]:
    """
    Extract all image URLs from raw HTML.
    Returns deduplicated list sorted by source quality (best first).
    Content images come first, logos at end as fallback.
    """
    content_urls, logo_urls, _ = _extract_images_core(raw_html, base_url)
    seen: set[str] = set(content_urls)
    result = list(content_urls)
    for url in logo_urls:
        if url not in seen:
            seen.add(url)
            result.append(url)
    return result


def extract_images_with_metadata(raw_html: str, base_url: str = "") -> dict:
    """
    Extract images with structured metadata for the normalizer.

    Returns:
        {
          "banner": str,          # best banner/hero image URL (empty string if none)
          "logo":   str,          # best logo URL as fallback (empty string if none)
          "alt":    str,          # alt text for banner (or logo if no banner)
          "all":    list[str],    # all URLs (content first, then logos)
        }
    """
    content_urls, logo_urls, alt_texts = _extract_images_core(raw_html, base_url)

    banner = content_urls[0] if content_urls else ""
    logo = logo_urls[0] if logo_urls else ""

    # Last resort: apple-touch-icon as logo if nothing else found
    if not logo:
        icon = _extract_site_icon(raw_html, base_url)
        if icon:
            logo = icon

    # Pick alt text: prefer banner alt, fall back to logo alt
    alt = ""
    if banner:
        alt = alt_texts.get(banner, "")
    if not alt and logo:
        alt = alt_texts.get(logo, "")

    all_urls = list(content_urls)
    seen = set(content_urls)
    for url in logo_urls:
        if url not in seen:
            seen.add(url)
            all_urls.append(url)

    return {
        "banner": banner,
        "logo": logo,
        "alt": alt,
        "all": all_urls,
    }
