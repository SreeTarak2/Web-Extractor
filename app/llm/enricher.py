"""
Step E — Post-normalization field enrichment via Lightpanda.

For each normalized contest item, detects fields that are still null
(or fee amount that is 0 when isFree=false), then:
  1. Visits the item's official link directly
  2. Falls back to a DuckDuckGo search and visits the top results

Each candidate page is sent to the LLM with a targeted prompt asking
only for the missing fields.
"""

import asyncio
import copy
import json
import logging
import re
from urllib.parse import quote_plus

from app.browser.manager import BrowserManager
from app.browser.page_actions import fetch_page
from app.llm.client import get_client
from app.llm.retry import call_with_retry
from app.llm.semaphore import llm_semaphore
from app.preprocessing.html_cleaner import clean_html
from app.tracking.cost_tracker import CostTracker
from app.config import MODEL_EXTRACTOR, MAX_HTML_CHARS_EXTRACT

logger = logging.getLogger(__name__)

# Fields we can enrich, mapped to plain-English search hints
ENRICHABLE_FIELDS: dict[str, str] = {
    "timeline.startDateUTC":    "entry open date application start",
    "timeline.eventEndUTC":     "ceremony winner results announcement date",
    "audience.age.min":         "minimum age requirement",
    "audience.age.max":         "maximum age limit eligibility",
    "constraints.teamSize.min": "minimum team size",
    "constraints.teamSize.max": "maximum team size members",
    "entry.fee.amount":         "entry fee cost per submission price",
}

_ENRICHER_SYSTEM = """You are a precise contest data extractor.

Given HTML from a webpage and a JSON object of fields to find for a specific
named contest, extract ONLY those fields and return a flat JSON object.

Rules:
- Keys must match exactly the keys given in the fields object
- Date values: ISO 8601 "YYYY-MM-DDTHH:mm:ss" or null
- Numeric values: integer or float, null if not found
- Only extract data clearly tied to the named contest — ignore other events
- Return null for any field you cannot find with confidence
- No fabrication. Return ONLY the JSON object, no markdown, no prose."""


async def _noop(msg: str) -> None:
    pass


def _get_nested(d: dict, path: str):
    for part in path.split("."):
        if isinstance(d, dict):
            d = d.get(part)
        else:
            return None
    return d


def _set_nested(d: dict, path: str, value) -> None:
    parts = path.split(".")
    for part in parts[:-1]:
        d = d.setdefault(part, {})
    d[parts[-1]] = value


def detect_null_fields(item: dict) -> dict[str, str]:
    """
    Return {field_path: search_hint} for every enrichable field that is
    null (or, for entry.fee.amount, is 0 while isFree=false).
    """
    result: dict[str, str] = {}
    for path, hint in ENRICHABLE_FIELDS.items():
        val = _get_nested(item, path)
        if path == "entry.fee.amount":
            is_free = _get_nested(item, "entry.isFree")
            if is_free is False and val == 0:
                result[path] = hint
        elif val is None:
            result[path] = hint
    return result


def _parse_candidate_urls(html: str, skip: set[str]) -> list[str]:
    """Extract the first few organic-result URLs from a search results page."""
    raw_urls: list[str] = re.findall(r'href=["\']?(https://[^"\'>\s&]+)', html)
    blocked_fragments = {
        "google.", "bing.", "duckduckgo.", "yahoo.",
        "youtube.", "facebook.", "twitter.", "instagram.",
        "webcache", "translate.", "policies.", "accounts.",
        "schema.org", "w3.org",
    }
    seen: set[str] = set()
    candidates: list[str] = []
    for url in raw_urls:
        base = url.split("?")[0].rstrip("/")
        if base in seen or base in skip:
            continue
        if any(b in url for b in blocked_fragments):
            continue
        seen.add(base)
        candidates.append(url)
        if len(candidates) >= 5:
            break
    return candidates


async def _llm_extract_fields(
    html: str,
    fields: dict[str, str],
    title: str,
    cost_tracker: CostTracker,
) -> dict:
    """
    Ask the LLM to extract specific fields from HTML.
    Returns a flat {field_path: value} dict (values may be None).
    """
    client = get_client()
    fields_spec = json.dumps(
        {path: f"Find: {hint}" for path, hint in fields.items()},
        indent=2,
    )
    clean = clean_html(html, max_chars=MAX_HTML_CHARS_EXTRACT)
    user_msg = (
        f"Contest: {title}\n\n"
        f"Fields to extract (return JSON with these exact keys):\n{fields_spec}\n\n"
        f"HTML:\n{clean}\n\n"
        f"IMPORTANT: Return ONLY a valid JSON object."
    )

    async def _call():
        return await client.chat.completions.create(
            model=MODEL_EXTRACTOR,
            messages=[
                {"role": "system", "content": _ENRICHER_SYSTEM},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.0,
            max_tokens=400,
        )

    try:
        async with llm_semaphore:
            response = await call_with_retry(_call)
        cost_tracker.log(MODEL_EXTRACTOR, response)
        raw = response.choices[0].message.content.strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        return json.loads(raw)
    except Exception as e:
        logger.warning(f"Enricher LLM extraction failed: {e}")
        return {}


async def enrich(
    item: dict,
    browser_manager: BrowserManager,
    cost_tracker: CostTracker,
    progress_callback=None,
) -> dict:
    """
    Fill null fields in a normalized item using Lightpanda.

    Pass 1 — official link: navigate directly to item['link'] and extract.
    Pass 2 — search fallback: query DuckDuckGo, visit top results.

    Returns an updated deep copy of item.
    """
    null_fields = detect_null_fields(item)
    if not null_fields:
        return item

    cb = progress_callback or _noop
    title = item.get("title", "")
    link = item.get("link", "")
    source_url = item.get("source", {}).get("url", "")

    await cb(f"Enriching {len(null_fields)} null field(s) for: {title}")

    item = copy.deepcopy(item)
    remaining = dict(null_fields)
    filled: list[str] = []

    # ── Pass 1: Visit official link directly ──────────────────────────────
    if link and link != source_url and remaining:
        page = await browser_manager.new_page()
        try:
            html = await fetch_page(page, link, scroll=False)
            found = await _llm_extract_fields(html, remaining, title, cost_tracker)
            for path, val in found.items():
                if val is not None and path in remaining:
                    _set_nested(item, path, val)
                    filled.append(path)
                    del remaining[path]
            if filled:
                await cb(f"Official site filled: {filled}")
        except Exception as e:
            logger.warning(f"Enricher pass 1 failed ({link}): {e}")
        finally:
            await page.close()

    # ── Pass 2: DuckDuckGo search → visit top organic results ─────────────
    if remaining:
        terms = " ".join(list(remaining.values())[:3])
        query = f"{title} {terms}"
        ddg_url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"

        page = await browser_manager.new_page()
        search_html = ""
        try:
            search_html = await fetch_page(page, ddg_url, scroll=False)
        except Exception as e:
            logger.warning(f"Enricher DDG search failed: {e}")
        finally:
            await page.close()

        if search_html:
            skip = {source_url, link}
            candidates = _parse_candidate_urls(search_html, skip=skip)
            for candidate_url in candidates[:3]:
                if not remaining:
                    break
                page = await browser_manager.new_page()
                try:
                    html = await fetch_page(page, candidate_url, scroll=False)
                    found = await _llm_extract_fields(html, remaining, title, cost_tracker)
                    batch: list[str] = []
                    for path, val in found.items():
                        if val is not None and path in remaining:
                            _set_nested(item, path, val)
                            filled.append(path)
                            batch.append(path)
                            del remaining[path]
                    if batch:
                        await cb(f"Search result filled: {batch}")
                except Exception as e:
                    logger.warning(f"Enricher candidate failed ({candidate_url}): {e}")
                finally:
                    await page.close()
                await asyncio.sleep(0.3)

    if filled:
        await cb(f"Enrichment complete — filled {len(filled)} field(s): {filled}")
    else:
        await cb(f"Enrichment done — no new data found for: {title}")

    return item
