"""
V2 Smart Web Fetcher.

Fetch strategy per URL:
  1. httpx   — fast, no JS (works for SSR/static sites)
  2. Playwright — full headless Chrome for JS-heavy sites (Squarespace, Wix, Webflow)

Also provides:
  • Short-URL resolution  (tinyurl, bit.ly, ow.ly, etc.)
  • Automatic scroll + lazy-load triggering
  • Link classification for intelligent follow-through
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Optional
from urllib.parse import urlparse, urljoin

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT": "1",
    "Connection": "keep-alive",
}

# Domains known to require full JS rendering
_JS_HEAVY_DOMAINS = {
    "squarespace.com", "wix.com", "webflow.io", "webflow.com",
    "framer.com", "notion.so", "unbounce.com", "strikingly.com",
    "cargo.site", "format.com",
}

# Short-URL domains that redirect to actual content
_SHORTLINK_DOMAINS = {
    "tinyurl.com", "bit.ly", "t.co", "goo.gl", "ow.ly",
    "short.io", "cutt.ly", "rb.gy", "is.gd", "tiny.cc",
    "lnkd.in", "buff.ly", "dlvr.it",
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def resolve_short_url(url: str, timeout: int = 15) -> str:
    """
    Follow HTTP redirects to discover the final destination URL.
    Critical for links like tinyurl.com/GAPC26 that hide the real registration page.
    Returns the original URL unchanged if resolution fails.
    """
    parsed = urlparse(url)
    domain = parsed.netloc.lower().lstrip("www.")

    if domain not in _SHORTLINK_DOMAINS:
        return url  # Not a shortlink — skip

    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            headers=_BROWSER_HEADERS,
            timeout=timeout,
        ) as client:
            resp = await client.head(url)
            final = str(resp.url)
            if final != url:
                logger.info(f"Short URL resolved: {url}  →  {final}")
            return final
    except Exception as exc:
        logger.warning(f"Short URL resolution failed for {url}: {exc}")
        return url


async def fetch_page(
    url: str,
    *,
    timeout: int = 30,
    use_playwright: bool = True,
    wait_for_idle: bool = True,
) -> tuple[str, str]:
    """
    Fetch a page and return (html_content, final_url).

    Resolution order:
      1. httpx (fast)
      2. Playwright if httpx returns a JS shell or fails
    """
    # Always use Playwright for known JS-heavy platforms
    force_playwright = use_playwright and _needs_playwright(url)

    if not force_playwright:
        html, final_url = await _httpx_fetch(url, timeout)
        if html and _is_real_content(html):
            return html, final_url
        logger.info(f"httpx returned shallow content for {url}, retrying with Playwright")

    if use_playwright:
        html, final_url = await _playwright_fetch(url, timeout, wait_for_idle)
        if html:
            return html, final_url

    return "", url


def extract_all_links(html: str, base_url: str) -> list[dict]:
    """
    Extract every <a href> link with its text, surrounding context, and type.
    Returns [{ "url", "text", "context", "type" }]
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    seen: set[str] = set()
    links: list[dict] = []

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue

        full_url = urljoin(base_url, href)
        if full_url in seen:
            continue
        seen.add(full_url)

        text = a.get_text(strip=True)[:120]
        parent = a.parent
        context = (parent.get_text(" ", strip=True) if parent else text)[:250]
        link_type = _classify_link(full_url, text)

        links.append({
            "url": full_url,
            "text": text,
            "context": context,
            "type": link_type,
        })

    return links


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _httpx_fetch(url: str, timeout: int) -> tuple[Optional[str], str]:
    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            headers=_BROWSER_HEADERS,
            timeout=timeout,
            verify=False,  # Some contest sites have self-signed certs
        ) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                return resp.text, str(resp.url)
            logger.warning(f"httpx status {resp.status_code} for {url}")
            return None, url
    except Exception as exc:
        logger.warning(f"httpx error for {url}: {exc}")
        return None, url


async def _playwright_fetch(
    url: str,
    timeout: int,
    wait_for_idle: bool,
) -> tuple[Optional[str], str]:
    try:
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
            ctx = await browser.new_context(
                extra_http_headers=_BROWSER_HEADERS,
                user_agent=_BROWSER_HEADERS["User-Agent"],
            )
            page = await ctx.new_page()
            try:
                wait_until = "networkidle" if wait_for_idle else "domcontentloaded"
                await page.goto(url, wait_until=wait_until, timeout=timeout * 1000)

                # Scroll to bottom to trigger lazy-loaded content
                await page.evaluate(
                    "window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' })"
                )
                await asyncio.sleep(1.5)

                # Expand any collapsed sections
                await _expand_collapsibles(page)

                html = await page.content()
                final_url = page.url
                return html, final_url
            finally:
                await browser.close()
    except Exception as exc:
        logger.warning(f"Playwright error for {url}: {exc}")
        return None, url


async def _expand_collapsibles(page) -> None:
    """Click common 'read more / show more / load more' buttons to reveal hidden content."""
    selectors = [
        "button:has-text('Read more')",
        "button:has-text('Show more')",
        "button:has-text('Load more')",
        "a:has-text('Read more')",
        "[aria-expanded='false'][data-toggle]",
    ]
    for sel in selectors:
        try:
            elements = await page.query_selector_all(sel)
            for el in elements[:3]:  # cap clicks to 3 per selector
                await el.click(timeout=2000)
                await asyncio.sleep(0.3)
        except Exception:
            pass  # Click failures are non-fatal


def _is_real_content(html: str) -> bool:
    """Return True if HTML appears to have real text content, not just a JS loading shell."""
    if not html or len(html) < 1000:
        return False
    # Detect common SPA empty shells
    shells = [
        r'<div id="root">\s*</div>',
        r'<div id="app">\s*</div>',
        r'<div id="__next">\s*</div>',
    ]
    for pattern in shells:
        if re.search(pattern, html) and len(html) < 10_000:
            return False
    return True


def _needs_playwright(url: str) -> bool:
    """Return True if the URL's domain is known to require JS rendering."""
    domain = urlparse(url).netloc.lower().lstrip("www.")
    return any(d in domain for d in _JS_HEAVY_DOMAINS)


def _classify_link(url: str, text: str) -> str:
    """Classify a link as: shortlink | registration_form | cta | social | page."""
    url_l = url.lower()
    text_l = (text or "").lower()
    parsed_domain = urlparse(url_l).netloc.lstrip("www.")

    if parsed_domain in _SHORTLINK_DOMAINS or "tinyurl" in url_l:
        return "shortlink"
    if any(s in url_l for s in ["google.com/forms", "typeform.com", "jotform.com",
                                  "cognito", "airtable.com", "forms.gle"]):
        return "registration_form"
    if any(s in url_l for s in ["instagram.com", "twitter.com", "x.com",
                                  "facebook.com", "linkedin.com", "youtube.com"]):
        return "social"
    if any(kw in text_l for kw in ["submit", "register", "apply", "enter now",
                                    "sign up", "join now", "participate", "upload"]):
        return "cta"
    return "page"
