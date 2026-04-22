"""Page interaction helpers — scroll, expand tabs/accordions, load more."""
import asyncio
import logging

from playwright.async_api import Page

logger = logging.getLogger(__name__)


async def fetch_page(page: Page, url: str, scroll: bool = True) -> str:
    """Navigate to URL, wait for content, scroll for lazy loading. Returns HTML."""
    try:
        await page.goto(url, wait_until="networkidle", timeout=15000)
    except Exception:
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=10000)
            await asyncio.sleep(2)
        except Exception as e:
            logger.error(f"Failed to load {url}: {e}")
            raise

    if scroll:
        await auto_scroll(page)

    return await page.content()


async def auto_scroll(page: Page, pause: float = 0.3):
    """Scroll incrementally to trigger lazy-loaded content."""
    try:
        previous_height = 0
        for _ in range(20):
            current_height = await page.evaluate("document.body.scrollHeight")
            if current_height == previous_height:
                break
            previous_height = current_height
            await page.evaluate("window.scrollBy(0, 600)")
            await asyncio.sleep(pause)
        await page.evaluate("window.scrollTo(0, 0)")
    except Exception as e:
        logger.warning(f"Scroll failed (non-critical): {e}")


async def expand_hidden_content(page: Page):
    """Click tabs, accordions, and 'show more' buttons to reveal hidden content."""
    selectors_to_try = [
        # Tabs
        "[data-tab='description']", "[data-tab='specs']", "[data-tab='specifications']",
        "#tab-description", "#tab-specs", "button[role='tab']",
        ".product-tabs button", ".tab-button",
        # Accordions
        ".accordion-toggle", ".accordion-header", "[data-toggle='collapse']",
        "details > summary",
        # Show more
        "button:has-text('Show More')", "button:has-text('Read More')",
        "button:has-text('See More')", "button:has-text('View All')",
        "a:has-text('Show More')", "a:has-text('Read More')",
        "[class*='show-more']", "[class*='read-more']", "[class*='expand']",
    ]

    for selector in selectors_to_try:
        try:
            elements = await page.query_selector_all(selector)
            for el in elements[:5]:
                try:
                    await el.click(timeout=2000)
                    await asyncio.sleep(0.3)
                except Exception:
                    continue
        except Exception:
            continue


async def click_load_more(page: Page, max_clicks: int = 5) -> int:
    """Click 'Load More' buttons to expand listings. Returns click count."""
    load_more_selectors = [
        "button:has-text('Load More')", "button:has-text('Show More Products')",
        "button:has-text('View More')", "a:has-text('Load More')",
        "[class*='load-more']", "[class*='loadmore']", "[data-action='load-more']",
    ]

    clicks = 0
    for _ in range(max_clicks):
        clicked = False
        for selector in load_more_selectors:
            try:
                button = await page.query_selector(selector)
                if button and await button.is_visible():
                    await button.click()
                    await asyncio.sleep(1.5)
                    clicks += 1
                    clicked = True
                    break
            except Exception:
                continue
        if not clicked:
            break

    if clicks > 0:
        logger.info(f"Clicked 'Load More' {clicks} times")

    return clicks
