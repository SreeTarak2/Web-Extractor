"""
V2 HTML Preprocessor — Firecrawl-inspired pipeline.

Pipeline:
  HTML
  ├─ BeautifulSoup noise removal
  ├─ Signal extraction  (dates · money · meta · JSON-LD · OG · images · CTAs)
  └─ Markdown conversion  (clean, token-efficient input for the LLM)

Returns a PreprocessResult with both the markdown and the ExtractedSignals.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlparse, urljoin

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Regex pattern banks
# ---------------------------------------------------------------------------

_DATE_PATTERNS: list[str] = [
    # "January 15, 2026"  or  "Jan 15, 2026"
    r'\b(?:January|February|March|April|May|June|July|August|September|October|'
    r'November|December|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\.?\s+'
    r'\d{1,2}(?:st|nd|rd|th)?,?\s*\d{4}\b',
    # "15 January 2026"
    r'\b\d{1,2}(?:st|nd|rd|th)?\s+(?:January|February|March|April|May|June|July|'
    r'August|September|October|November|December|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|'
    r'Sep|Oct|Nov|Dec)\.?\s*\d{4}\b',
    # ISO: "2026-03-15"
    r'\b20\d{2}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01])\b',
    # "15/03/2026" or "03/15/2026"
    r'\b(?:0?[1-9]|[12]\d|3[01])[/\-](?:0?[1-9]|1[0-2])[/\-]20\d{2}\b',
    # "March 2026"
    r'\b(?:January|February|March|April|May|June|July|August|September|October|'
    r'November|December)\s+20\d{2}\b',
]

_MONEY_PATTERNS: list[str] = [
    r'\$\s*[\d,]+(?:\.\d{2})?(?:\s*(?:USD|CAD|AUD|NZD))?\b',
    r'\b(?:USD|EUR|GBP|INR|CAD|AUD)\s*[\d,]+(?:\.\d{2})?\b',
    r'\b[\d,]+\s*(?:dollars?|euros?|pounds?|rupees?|lakhs?)\b',
    r'Rs\.?\s*[\d,]+',
    r'₹\s*[\d,]+',
]

_DEADLINE_CONTEXT_PATTERNS: list[str] = [
    r'(?:submission|entry|application|entries|registration)\s+'
    r'(?:deadline|due\s+date|closes?|last\s+date|end\s+date)',
    r'deadline\s*[:\-]',
    r'submit\s+(?:by|before|on|before)',
    r'(?:last|final|closing)\s+date',
    r'entries?\s+(?:due|close|accepted\s+until)',
    r'open\s+(?:until|through|till)',
    r'closes?\s+on',
]

_PRIZE_CONTEXT_PATTERNS: list[str] = [
    r'(?:first|2nd|second|3rd|third|grand|top|1st)\s*(?:place\s+)?prize',
    r'cash\s+(?:prize|award)',
    r'award[s]?\s+(?:of|worth|valued)',
    r'winner[s]?\s+(?:will|shall)\s+(?:receive|get|win|be\s+awarded)',
    r'prize\s+(?:pool|money|fund|amount)',
    r'grant[s]?\s+(?:of|up\s+to|worth)',
    r'stipend',
    r'scholarship\s+(?:of|worth)',
    r'(?:cash|monetary)\s+reward',
]

_FREE_PATTERNS: list[str] = [
    r'\bfree\s+(?:to\s+enter|entry|submission|participation|registration)\b',
    r'\bno\s+(?:entry|registration|submission)?\s*fee\b',
    r'\bcost[:\s]+free\b',
    r'\bopen\s+and\s+free\b',
    r'\bfree\s+of\s+charge\b',
]

_FEE_PATTERNS: list[str] = [
    r'(?:entry|registration|submission)\s+fee[:\s]+',
    r'fee[:\s]+\$',
    r'pay(?:ment)?\s+(?:of\s+)?\$',
    r'processing\s+fee',
]


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ExtractedSignals:
    """Structured signals extracted from raw HTML before sending to the LLM."""
    # Page identity
    title: str = ""
    meta_description: str = ""
    # Open Graph / Twitter Card
    og_title: str = ""
    og_description: str = ""
    og_image: str = ""
    og_url: str = ""
    # Structured data
    json_ld: list[dict] = field(default_factory=list)
    # Dates
    all_dates: list[str] = field(default_factory=list)
    deadline_snippets: list[str] = field(default_factory=list)
    # Money
    all_money: list[str] = field(default_factory=list)
    prize_snippets: list[str] = field(default_factory=list)
    # Entry fee
    is_free_signals: list[str] = field(default_factory=list)
    fee_snippets: list[str] = field(default_factory=list)
    # Images
    images: list[dict] = field(default_factory=list)
    # CTA / registration links
    cta_links: list[dict] = field(default_factory=list)


@dataclass
class PreprocessResult:
    """Complete preprocessed page data, ready for LLM consumption."""
    url: str
    markdown: str          # Clean markdown representation (main LLM input)
    signals: ExtractedSignals   # Pre-extracted structured data
    raw_text: str = ""    # Plain-text fallback


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def preprocess(html: str, url: str, max_chars: int = 80_000) -> PreprocessResult:
    """
    Full preprocessing pipeline: HTML → markdown + signals.

    Args:
        html:      Raw HTML string.
        url:       Source URL (for resolving relative links).
        max_chars: Hard cap on markdown length sent to LLM.

    Returns:
        PreprocessResult containing clean markdown and structured signals.
    """
    soup = BeautifulSoup(html, "html.parser")
    signals  = _extract_signals(soup, url)
    markdown = _to_markdown(soup, url, max_chars)
    raw_text = soup.get_text(separator=" ", strip=True)[:20_000]

    return PreprocessResult(url=url, markdown=markdown, signals=signals, raw_text=raw_text)


def signals_to_context_block(signals: ExtractedSignals) -> str:
    """
    Format ExtractedSignals into a human-readable context block for the LLM prompt.
    This gives the LLM pre-digested, high-confidence facts to minimise hallucination.
    """
    parts = ["=== PRE-EXTRACTED SIGNALS ==="]

    if signals.title:
        parts.append(f"Page title        : {signals.title}")
    if signals.og_title and signals.og_title != signals.title:
        parts.append(f"OG title          : {signals.og_title}")
    if signals.meta_description:
        parts.append(f"Meta description  : {signals.meta_description}")
    if signals.og_description and signals.og_description != signals.meta_description:
        parts.append(f"OG description    : {signals.og_description}")
    if signals.og_image:
        parts.append(f"OG image          : {signals.og_image}")
    if signals.og_url:
        parts.append(f"OG url            : {signals.og_url}")

    if signals.all_dates:
        parts.append(f"\nAll dates found   : {', '.join(signals.all_dates[:12])}")
    if signals.deadline_snippets:
        parts.append("\nDeadline-related snippets:")
        for snip in signals.deadline_snippets[:5]:
            parts.append(f"  › {snip}")

    if signals.all_money:
        parts.append(f"\nMoney amounts     : {', '.join(signals.all_money[:10])}")
    if signals.prize_snippets:
        parts.append("\nPrize-related snippets:")
        for snip in signals.prize_snippets[:4]:
            parts.append(f"  › {snip}")

    if signals.is_free_signals:
        parts.append(f"\nFree-entry signals: {', '.join(signals.is_free_signals[:3])}")
    if signals.fee_snippets:
        parts.append("\nFee snippets:")
        for snip in signals.fee_snippets[:3]:
            parts.append(f"  › {snip}")

    if signals.images:
        parts.append("\nImages found:")
        for img in signals.images[:5]:
            alt = img.get("alt", "")
            suffix = f" (alt: {alt})" if alt else ""
            parts.append(f"  › {img['url']}{suffix}")

    if signals.cta_links:
        parts.append("\nCTA / Registration links:")
        for lnk in signals.cta_links[:5]:
            parts.append(f"  › [{lnk['text']}]({lnk['url']})")

    if signals.json_ld:
        parts.append("\nJSON-LD structured data:")
        try:
            parts.append(json.dumps(signals.json_ld, indent=2)[:3000])
        except Exception:
            pass

    parts.append("=== END SIGNALS ===")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Signal extraction
# ---------------------------------------------------------------------------

def _extract_signals(soup: BeautifulSoup, base_url: str) -> ExtractedSignals:
    s = ExtractedSignals()

    # Page title
    t = soup.find("title")
    s.title = t.get_text(strip=True) if t else ""

    # Meta description
    md = soup.find("meta", attrs={"name": "description"})
    s.meta_description = md.get("content", "") if md else ""

    # Open Graph / Twitter Card
    _og_map = [
        ("og:title",       "og_title"),
        ("og:description", "og_description"),
        ("og:image",       "og_image"),
        ("og:url",         "og_url"),
        ("twitter:title",       "og_title"),
        ("twitter:description", "og_description"),
        ("twitter:image",       "og_image"),
    ]
    for prop, attr in _og_map:
        tag = soup.find("meta", property=prop) or soup.find("meta", attrs={"name": prop})
        if tag:
            val = tag.get("content", "").strip()
            if val and not getattr(s, attr):
                setattr(s, attr, val)

    # JSON-LD structured data
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
            if isinstance(data, list):
                s.json_ld.extend(data)
            elif isinstance(data, dict):
                s.json_ld.append(data)
        except Exception:
            pass

    # Full page text for pattern matching
    page_text = soup.get_text(separator=" ", strip=True)

    # Dates
    for pat in _DATE_PATTERNS:
        s.all_dates.extend(re.findall(pat, page_text, re.IGNORECASE))
    s.all_dates = list(dict.fromkeys(s.all_dates))  # deduplicate, preserve order

    # Deadline context snippets
    s.deadline_snippets = _context_snippets(page_text, _DEADLINE_CONTEXT_PATTERNS, window=200)

    # Money
    for pat in _MONEY_PATTERNS:
        s.all_money.extend(re.findall(pat, page_text, re.IGNORECASE))
    s.all_money = list(dict.fromkeys(s.all_money))

    # Prize context snippets
    s.prize_snippets = _context_snippets(page_text, _PRIZE_CONTEXT_PATTERNS, window=200)

    # Free-entry signals
    for pat in _FREE_PATTERNS:
        s.is_free_signals.extend(re.findall(pat, page_text, re.IGNORECASE))

    # Fee snippets
    s.fee_snippets = _context_snippets(page_text, _FEE_PATTERNS, window=150)

    # Images
    s.images = _extract_images(soup, base_url)

    # CTA links
    s.cta_links = _extract_cta_links(soup, base_url)

    return s


def _context_snippets(text: str, patterns: list[str], window: int = 200) -> list[str]:
    """Return short text snippets centred around each regex match."""
    combined = "|".join(f"(?:{p})" for p in patterns)
    snippets: list[str] = []
    for m in re.finditer(combined, text, re.IGNORECASE):
        start = max(0, m.start() - window)
        end   = min(len(text), m.end() + window)
        snippet = re.sub(r'\s{2,}', ' ', text[start:end].strip())
        if snippet and snippet not in snippets:
            snippets.append(snippet)
    return snippets[:8]


def _extract_images(soup: BeautifulSoup, base_url: str) -> list[dict]:
    images: list[dict] = []
    seen: set[str] = set()

    for img in soup.find_all("img"):
        src = (
            img.get("src") or img.get("data-src") or
            img.get("data-lazy-src") or img.get("data-original", "")
        )
        if not src:
            continue

        # Normalise protocol-relative URLs
        if src.startswith("//"):
            src = "https:" + src
        elif src.startswith("/"):
            src = urljoin(base_url, src)

        if not src.startswith("http") or src in seen:
            continue
        seen.add(src)

        # Skip tracking pixels and tiny icons
        try:
            if int(img.get("width", 100)) < 50 or int(img.get("height", 100)) < 50:
                continue
        except (ValueError, TypeError):
            pass

        images.append({
            "url":    src,
            "alt":    img.get("alt", ""),
            "width":  img.get("width", ""),
            "height": img.get("height", ""),
        })

    return images[:10]


def _extract_cta_links(soup: BeautifulSoup, base_url: str) -> list[dict]:
    """Extract registration / submission / CTA links from the page."""
    cta_keywords = {
        "submit", "register", "apply", "enter", "sign up",
        "join", "participate", "upload", "send your", "click here",
    }
    form_hosts = [
        "google.com/forms", "forms.gle", "typeform.com", "jotform.com",
        "cognito", "airtable.com", "tinyurl.com", "bit.ly",
    ]

    results: list[dict] = []
    for a in soup.find_all("a", href=True):
        text = a.get_text(strip=True)
        href = a["href"]
        text_l = text.lower()
        href_l = href.lower()

        is_cta  = any(kw in text_l for kw in cta_keywords)
        is_form = any(h in href_l for h in form_hosts)

        if is_cta or is_form:
            full_url = urljoin(base_url, href)
            results.append({"url": full_url, "text": text[:100]})

    # Deduplicate by URL
    seen: set[str] = set()
    unique = []
    for lnk in results:
        if lnk["url"] not in seen:
            seen.add(lnk["url"])
            unique.append(lnk)

    return unique[:5]


# ---------------------------------------------------------------------------
# HTML → Markdown conversion
# ---------------------------------------------------------------------------

_NOISE_TAGS = [
    "script", "style", "noscript", "head", "meta", "link",
    "nav", "header", "footer", "aside", "iframe", "svg",
    "canvas", "dialog", "template",
]

_NOISE_CLASS_RE = re.compile(
    r"(\bnav\b|navbar|navigation|breadcrumb|cookie|banner|"
    r"popup|modal|overlay|advertisement|social[-_]share|"
    r"share[-_]button|related[-_]post|widget|sidebar|header|footer)",
    re.IGNORECASE,
)


def _to_markdown(soup: BeautifulSoup, base_url: str, max_chars: int) -> str:
    """
    Convert BeautifulSoup DOM to clean Markdown optimised for LLM token efficiency.
    Removes all noise (nav, scripts, ads) and preserves meaningful content.
    """
    # Work on a fresh parse to avoid mutating the caller's tree
    working = BeautifulSoup(str(soup), "html.parser")

    # Remove noisy tags entirely
    for tag in working.find_all(_NOISE_TAGS):
        tag.decompose()

    # Remove elements with noisy classes / IDs
    for tag in working.find_all(True):
        cls_str = " ".join(tag.get("class", []))
        id_str  = tag.get("id", "")
        if _NOISE_CLASS_RE.search(cls_str) or _NOISE_CLASS_RE.search(id_str):
            tag.decompose()

    # Prefer the main content region
    main = (
        working.find("main")
        or working.find(id=re.compile(r"main|content|article|post", re.I))
        or working.find(class_=re.compile(r"main[-_]?content|page[-_]?content|entry[-_]?content", re.I))
        or working.find("article")
    )
    root = main or working.find("body") or working

    # Convert to Markdown
    try:
        import markdownify as md_lib
        markdown = md_lib.markdownify(
            str(root),
            heading_style="ATX",
            bullets="-",
            newline_style="backslash",
        )
    except ImportError:
        # Fallback: plain-text extraction with heading pseudo-formatting
        markdown = _plain_text_fallback(root)

    # Tidy up whitespace
    markdown = re.sub(r'\n{3,}', '\n\n', markdown)
    markdown = re.sub(r'[ \t]{2,}', ' ', markdown)
    markdown = markdown.strip()

    return markdown[:max_chars]


def _plain_text_fallback(element) -> str:
    """Simple text extraction when markdownify is unavailable."""
    lines: list[str] = []
    for el in element.descendants:
        if not hasattr(el, 'name'):
            continue
        if el.name in ("h1", "h2", "h3", "h4"):
            lines.append(f"\n## {el.get_text(strip=True)}\n")
        elif el.name in ("p", "li", "td", "th", "dt", "dd"):
            t = el.get_text(strip=True)
            if t:
                lines.append(t)
    return "\n".join(lines)
