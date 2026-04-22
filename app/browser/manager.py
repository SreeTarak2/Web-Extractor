"""Browser lifecycle management — Lightpanda primary, Chromium fallback."""

import asyncio
import logging
import os

from playwright.async_api import async_playwright, Browser, BrowserContext, Page

from app.config import LIGHTPANDA_WS_URL, DEFAULT_TIMEOUT_MS, CHROMIUM_EXECUTABLE

logger = logging.getLogger(__name__)


class BrowserManager:
    def __init__(self):
        self._playwright = None
        self._browser: Browser | None = None
        self._lp_context: BrowserContext | None = None  # persistent context for Lightpanda
        self._using_lightpanda = False

    async def start(self):
        self._playwright = await async_playwright().start()
        try:
            self._browser = await self._playwright.chromium.connect_over_cdp(
                LIGHTPANDA_WS_URL,
                timeout=5000,
            )
            self._using_lightpanda = True
            logger.info("Connected to Lightpanda")
            await self._bootstrap_lightpanda()
        except Exception as e:
            logger.warning(f"Lightpanda not available ({e}). Using Chromium.")
            launch_kwargs: dict = dict(
                headless=True,
                args=[
                    "--disable-gpu",
                    "--disable-dev-shm-usage",
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                ],
            )
            if CHROMIUM_EXECUTABLE and os.path.exists(CHROMIUM_EXECUTABLE):
                launch_kwargs["executable_path"] = CHROMIUM_EXECUTABLE
            self._browser = await self._playwright.chromium.launch(**launch_kwargs)
            self._using_lightpanda = False
            logger.info("Launched Chromium")

    async def _bootstrap_lightpanda(self):
        """
        Lightpanda starts with zero open targets, so browser.contexts is empty.
        It also doesn't support Target.createBrowserContext (Chrome-only CDP).
        Fix: open one blank page via raw CDP (Target.createTarget), which causes
        Playwright to register the default browser context. We cache that context
        and reuse it for all subsequent new_page() calls.
        """
        cdp = await self._browser.new_browser_cdp_session()
        try:
            await cdp.send("Target.createTarget", {"url": "about:blank"})
        finally:
            await cdp.dispose()

        # Wait for Playwright to process the targetCreated event (max 3 s)
        for _ in range(30):
            if self._browser.contexts:
                break
            await asyncio.sleep(0.1)
        else:
            raise RuntimeError("Lightpanda: timed out waiting for browser context to initialise")

        self._lp_context = self._browser.contexts[0]
        # Close the bootstrap blank page — context stays alive
        for page in self._lp_context.pages:
            await page.close()
        logger.info("Lightpanda context bootstrapped")

    async def new_page(self) -> Page:
        if self._browser is None:
            raise RuntimeError("Browser not started.")

        if self._using_lightpanda:
            # Reuse the persistent context — only Target.createTarget (no contextId),
            # which Lightpanda supports. context.new_page() does exactly that.
            context = self._lp_context
        else:
            context = await self._browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/131.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1280, "height": 800},
                java_script_enabled=True,
            )

        page = await context.new_page()
        page.set_default_timeout(DEFAULT_TIMEOUT_MS)
        return page

    async def stop(self):
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    @property
    def browser_name(self) -> str:
        return "Lightpanda" if self._using_lightpanda else "Chromium"
