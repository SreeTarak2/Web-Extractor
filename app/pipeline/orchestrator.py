"""Main pipeline orchestrator — connects browser, preprocessor, and LLM steps."""

import asyncio
import json
import logging
import os
import time
from typing import Callable, Awaitable

from app.browser.manager import BrowserManager
from app.browser.page_actions import fetch_page, expand_hidden_content, click_load_more
from app.cache.url_cache import get as cache_get, set as cache_set
from app.preprocessing.html_cleaner import clean_html
from app.preprocessing.image_extractor import extract_images_with_metadata
from app.preprocessing.url_resolver import resolve_all
from app.pipeline.query_parser import parse_query
from app.pipeline.result_merger import merge
from app.llm.analyzer import analyze_page
from app.llm.navigator import plan_navigation
from app.llm.extractor import extract_data
from app.llm.generator import generate_content
from app.llm.normalizer import normalize
from app.tracking.cost_tracker import CostTracker
from app.config import (
    MAX_PAGES_PER_SCRAPE,
    MAX_HTML_CHARS,
    MAX_HTML_CHARS_EXTRACT,
    OUTPUT_DIR,
)

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[str], Awaitable[None]] | None


async def _noop(msg: str):
    pass


async def orchestrate(
    browser_manager: BrowserManager,
    url: str,
    query: str,
    content_format: str | None = None,
    progress_callback: ProgressCallback = None,
    stop_event: asyncio.Event | None = None,
) -> dict:
    """
    Full pipeline: URL + query → structured data (+ optional content).

    Returns a dict with metadata, items, generated_content, and cost.
    """
    cb = progress_callback or _noop
    cost_tracker = CostTracker()
    start_time = time.time()
    stopped = False

    async def check_stop() -> bool:
        if stop_event and stop_event.is_set():
            return True
        return False

    pages_visited: list[str] = []
    pages_failed: list[dict] = []
    extracted_items: list[dict] = []
    html_by_url: dict[str, str] = {}  # Store HTML for normalization

    # Batch output tracking
    batch_count = 0
    batch_items = []

    # ── 1. Parse query ────────────────────────────────────────────────────────
    if await check_stop():
        await cb("Stopped by user")
        return _stopped_response(
            url,
            query,
            extracted_items,
            cost_tracker,
            start_time,
            pages_visited,
            pages_failed,
        )

    requested_fields = parse_query(query, schema=content_format)
    logger.info(f"Requested fields: {requested_fields}")
    await cb(f"Parsed query → fields: {', '.join(requested_fields)}")

    # ── 0. Check cache for URL + fields ────────────────────────────────────────
    if await check_stop():
        await cb("Stopped by user")
        return _stopped_response(
            url,
            query,
            extracted_items,
            cost_tracker,
            start_time,
            pages_visited,
            pages_failed,
        )

    cache_key_fields = requested_fields
    cached_result = cache_get(url, cache_key_fields)
    if cached_result:
        logger.info(f"Cache hit for {url}")
        await cb(f"Cached: {url}")
        result_data = cached_result.get("result", {})
        return {
            "metadata": {
                "url": url,
                "query": query,
                "from_cache": True,
                "scraped_at": cached_result.get("cached_at", ""),
            },
            "items": result_data.get("items", []),
            "generated_content": result_data.get("generated_content"),
            "cost": result_data.get("cost", {}),
            "pages_visited": result_data.get("pages_visited", []),
            "pages_failed": result_data.get("pages_failed", []),
        }

    # ── 2. Fetch listing/start page ───────────────────────────────────────────
    if await check_stop():
        await cb("Stopped by user")
        return _stopped_response(
            url,
            query,
            extracted_items,
            cost_tracker,
            start_time,
            pages_visited,
            pages_failed,
        )

    await cb(f"Fetching {url} ...")
    page = await browser_manager.new_page()
    try:
        raw_html = await fetch_page(page, url)
        pages_visited.append(url)
    except Exception as e:
        logger.error(f"Failed to fetch start URL: {e}")
        return _error_response(url, query, str(e), cost_tracker, start_time)
    finally:
        await page.close()

    # ── 3. Preprocess start page ──────────────────────────────────────────────
    image_meta_start = extract_images_with_metadata(raw_html, base_url=url)
    # Resolve all URLs in the metadata to absolute
    image_meta_start["banner"] = resolve_all([image_meta_start["banner"]], url)[0] if image_meta_start["banner"] else ""
    image_meta_start["logo"] = resolve_all([image_meta_start["logo"]], url)[0] if image_meta_start["logo"] else ""
    image_meta_start["all"] = resolve_all(image_meta_start["all"], url)
    clean = clean_html(raw_html, max_chars=MAX_HTML_CHARS)

    # Store HTML for normalization
    html_by_url[url] = raw_html

    # ── 4. Step A: Analyze ────────────────────────────────────────────────────
    await cb("Analyzing page structure (Step A)...")
    analysis = await analyze_page(clean, requested_fields, cost_tracker)

    # ── 5. Decision point ─────────────────────────────────────────────────────
    fields_missing = analysis.get("fields_missing", [])
    strategy_needed = bool(fields_missing) and analysis.get("has_detail_links", False)

    if not strategy_needed:
        # All data is on this page — extract directly
        await cb("All data found on listing page. Extracting...")
        clean_extract = clean_html(raw_html, max_chars=MAX_HTML_CHARS_EXTRACT)
        item = await extract_data(clean_extract, requested_fields, url, cost_tracker)
        item = merge(item, image_meta_start)
        extracted_items.append(item)
        await cb(f"Completed: {url}")

        # Batch output for single page
        batch_items.append(item)
        if len(batch_items) >= 5:
            batch_count += 1
            batch_file = os.path.join(
                OUTPUT_DIR, "results", f"batch_{batch_count}.json"
            )
            os.makedirs(os.path.dirname(batch_file), exist_ok=True)
            with open(batch_file, "w") as f:
                json.dump(
                    {
                        "batch": batch_count,
                        "items": batch_items,
                        "urls": pages_visited[-5:],
                    },
                    f,
                    indent=2,
                )
            await cb(f"Batch {batch_count} complete: {len(batch_items)} URLs")
            batch_items = []
    else:
        # ── 6. Step B: Plan navigation ────────────────────────────────────────
        await cb("Planning navigation (Step B)...")
        nav_plan = await plan_navigation(clean, analysis, url, cost_tracker)

        strategy = nav_plan.get("strategy", "no_navigation_needed")
        targets = nav_plan.get("targets", [])
        pagination = nav_plan.get("pagination", {})

        if strategy == "click_load_more":
            # Expand current page and extract from it
            await cb("Clicking 'Load More' to expand listing...")
            page2 = await browser_manager.new_page()
            try:
                await fetch_page(page2, url, scroll=False)
                await click_load_more(page2)
                raw_html = await page2.content()
            finally:
                await page2.close()
            image_meta_start = extract_images_with_metadata(raw_html, base_url=url)
            image_meta_start["banner"] = resolve_all([image_meta_start["banner"]], url)[0] if image_meta_start["banner"] else ""
            image_meta_start["logo"] = resolve_all([image_meta_start["logo"]], url)[0] if image_meta_start["logo"] else ""
            image_meta_start["all"] = resolve_all(image_meta_start["all"], url)
            clean_extract = clean_html(raw_html, max_chars=MAX_HTML_CHARS_EXTRACT)
            item = await extract_data(
                clean_extract, requested_fields, url, cost_tracker
            )
            item = merge(item, image_meta_start)
            extracted_items.append(item)
            await cb(f"Completed: {url}")

        elif strategy == "click_each_item" and targets:
            # ── 7. Scrape each detail page ────────────────────────────────────
            limit = min(len(targets), MAX_PAGES_PER_SCRAPE)
            await cb(f"Scraping {limit} detail pages (Step C)...")

            for i, target in enumerate(targets[:limit]):
                if await check_stop():
                    await cb("Stopped by user — saving extracted items so far")
                    stopped = True
                    break

                target_url = target.get("url", "")
                if not target_url:
                    continue

                await cb(f"Extracting page {i + 1}/{limit}: {target_url}")

                detail_page = await browser_manager.new_page()
                try:
                    raw_detail = await fetch_page(detail_page, target_url)
                    await expand_hidden_content(detail_page)
                    raw_detail = await detail_page.content()
                    pages_visited.append(target_url)

                    # Store raw HTML for normalization phase
                    html_by_url[target_url] = raw_detail
                except Exception as e:
                    logger.warning(f"Failed to fetch {target_url}: {e}")
                    pages_failed.append({"url": target_url, "error": str(e)})
                    continue
                finally:
                    await detail_page.close()

                img_meta = extract_images_with_metadata(raw_detail, base_url=target_url)
                img_meta["banner"] = resolve_all([img_meta["banner"]], target_url)[0] if img_meta["banner"] else ""
                img_meta["logo"] = resolve_all([img_meta["logo"]], target_url)[0] if img_meta["logo"] else ""
                img_meta["all"] = resolve_all(img_meta["all"], target_url)
                clean_detail = clean_html(raw_detail, max_chars=MAX_HTML_CHARS_EXTRACT)
                item = await extract_data(
                    clean_detail, requested_fields, target_url, cost_tracker
                )
                item = merge(item, img_meta)
                extracted_items.append(item)

                # Notify completion and batch output
                await cb(f"Completed: {target_url}")

                # Batch output every 5 URLs
                batch_items.append(item)
                if len(batch_items) >= 5:
                    batch_count += 1
                    batch_file = os.path.join(
                        OUTPUT_DIR, "results", f"batch_{batch_count}.json"
                    )
                    os.makedirs(os.path.dirname(batch_file), exist_ok=True)
                    with open(batch_file, "w") as f:
                        json.dump(
                            {
                                "batch": batch_count,
                                "items": batch_items,
                                "urls": pages_visited[-5:],
                            },
                            f,
                            indent=2,
                        )
                    await cb(f"Batch {batch_count} complete: {len(batch_items)} URLs")
                    batch_items = []

                # Small delay between requests to be polite
                await asyncio.sleep(0.5)

        # ── 8. Handle pagination ──────────────────────────────────────────────
        if pagination.get("has_next_page") and pagination.get("next_page_url"):
            next_url = pagination["next_page_url"]
            await cb(f"Following pagination to {next_url}...")
            # Recursive call (depth limited by MAX_PAGES_PER_SCRAPE)
            if len(pages_visited) < MAX_PAGES_PER_SCRAPE:
                next_result = await orchestrate(
                    browser_manager=browser_manager,
                    url=next_url,
                    query=query,
                    content_format=None,  # Don't generate content for sub-pages
                    progress_callback=progress_callback,
                    stop_event=stop_event,
                )
                extracted_items.extend(next_result.get("items", []))
                pages_visited.extend(next_result.get("_pages_visited", []))

    # ── 9. Compile results ────────────────────────────────────────────────────
    if stopped:
        await cb(f"Stopped. Extracted {len(extracted_items)} items so far")
        end_time = time.time()
        cost_summary = cost_tracker.get_cost()

        # Flush remaining batch
        if batch_items:
            batch_count += 1
            batch_file = os.path.join(
                OUTPUT_DIR, "results", f"batch_{batch_count}.json"
            )
            os.makedirs(os.path.dirname(batch_file), exist_ok=True)
            with open(batch_file, "w") as f:
                json.dump(
                    {
                        "batch": batch_count,
                        "items": batch_items,
                        "urls": pages_visited[-len(batch_items) :]
                        if pages_visited
                        else [],
                    },
                    f,
                    indent=2,
                )

        return {
            "metadata": {
                "url": url,
                "query": query,
                "stopped": True,
                "requested_fields": requested_fields,
                "pages_visited": len(pages_visited),
                "pages_failed": len(pages_failed),
                "duration_seconds": round(end_time - start_time, 1),
                "cost_usd": cost_summary["total_usd"],
            },
            "items": extracted_items,
            "generated_content": "",
            "cost": cost_summary,
            "_pages_visited": pages_visited,
        }

    generated_content = ""
    normalize_mode: str | None = None
    if content_format in ("contest", "conference"):
        normalize_mode = content_format

    # Check if we should normalize inline (for contest/conference format)
    normalize_inline = normalize_mode and extracted_items

    if normalize_inline:
        await cb(f"Normalizing to {normalize_mode} schema (Step D)...")
        normalized_items = []

        # Normalize each item immediately after extraction
        for idx, item in enumerate(extracted_items):
            item_url = item.get("source_url", url)
            html_content = html_by_url.get(item_url, "") if html_by_url else ""

            normalized = await normalize(
                items=[item],
                mode=normalize_mode,  # type: ignore
                source_url=item_url,
                cost_tracker=cost_tracker,
                html_by_url={item_url: html_content} if html_content else None,
            )
            if normalized:
                normalized_items.extend(normalized)

            await cb(f"Normalized {idx + 1}/{len(extracted_items)}: {item_url}")

        extracted_items = normalized_items
        await cb(
            f"Normalized {len(extracted_items)} item(s) to {normalize_mode} schema"
        )
    elif content_format and extracted_items:
        await cb(f"Generating {content_format} content (Step D)...")
        generated_content = await generate_content(
            items=extracted_items,
            content_format=content_format,
            cost_tracker=cost_tracker,
        )

    end_time = time.time()
    cost_summary = cost_tracker.get_cost()

    await cb(
        f"Done. Extracted {len(extracted_items)} items in {end_time - start_time:.1f}s"
    )

    # Flush remaining batch
    if batch_items:
        batch_count += 1
        batch_file = os.path.join(OUTPUT_DIR, "results", f"batch_{batch_count}.json")
        with open(batch_file, "w") as f:
            json.dump(
                {
                    "batch": batch_count,
                    "items": batch_items,
                    "urls": [],
                },
                f,
                indent=2,
            )
        await cb(f"Final batch complete: {len(batch_items)} URLs")

    # Save to cache
    cache_set(
        url,
        cache_key_fields,
        {
            "items": extracted_items,
            "generated_content": generated_content,
            "cost": cost_summary,
            "pages_visited": pages_visited,
            "pages_failed": pages_failed,
        },
    )

    return {
        "metadata": {
            "url": url,
            "query": query,
            "requested_fields": requested_fields,
            "pages_visited": len(pages_visited),
            "pages_failed": len(pages_failed),
            "duration_seconds": round(end_time - start_time, 1),
            "cost_usd": cost_summary["total_usd"],
        },
        "items": extracted_items,
        "generated_content": generated_content,
        "cost": cost_summary,
        # Internal fields for recursive calls
        "_pages_visited": pages_visited,
    }


def _error_response(
    url: str, query: str, error: str, cost_tracker: CostTracker, start_time: float
) -> dict:
    return {
        "metadata": {
            "url": url,
            "query": query,
            "error": error,
            "pages_visited": 0,
            "pages_failed": 1,
            "duration_seconds": round(time.time() - start_time, 1),
            "cost_usd": 0.0,
        },
        "items": [],
        "generated_content": "",
        "cost": cost_tracker.get_cost(),
        "_pages_visited": [],
    }


def _stopped_response(
    url: str,
    query: str,
    extracted_items: list[dict],
    cost_tracker: CostTracker,
    start_time: float,
    pages_visited: list[str],
    pages_failed: list[dict],
) -> dict:
    return {
        "metadata": {
            "url": url,
            "query": query,
            "stopped": True,
            "pages_visited": len(pages_visited),
            "pages_failed": len(pages_failed),
            "duration_seconds": round(time.time() - start_time, 1),
            "cost_usd": cost_tracker.get_cost()["total_usd"],
        },
        "items": extracted_items,
        "generated_content": "",
        "cost": cost_tracker.get_cost(),
        "_pages_visited": pages_visited,
    }
