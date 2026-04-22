# WebMind Extractor — Complete Project Blueprint

> Everything you need to build the AI-powered web data extractor.
> Follow this document top-to-bottom. Nothing is left out.

---

## Table of Contents

1. What You're Building
2. Architecture Overview
3. Tech Stack (exact versions & install commands)
4. Model Assignments & Pricing
5. Project Structure
6. Phase 1: Environment Setup
7. Phase 2: Browser Layer
8. Phase 3: HTML Preprocessing
9. Phase 4: Reasoning Chain (Navigate → Extract → Generate)
10. Phase 5: Image Extraction
11. Phase 6: Content Generation
12. Phase 7: Orchestrator (Full Pipeline)
13. Phase 8: Web UI
14. Phase 9: Error Handling & Retries
15. Phase 10: Cost Tracking
16. Phase 11: Output & Export
17. Phase 12: Testing Strategy
18. Phase 13: Edge Cases & Solutions
19. Phase 14: Deployment
20. Build Timeline (Week by Week)
21. Risk Register
22. Future Roadmap

---

## 1. What You're Building

A tool where a user provides a URL and a plain English query.
The tool scrapes the website, extracts structured data, and optionally
generates polished content from that data.

**Input:** URL + query (+ optional content format)
**Output:** Structured JSON data + generated content (articles, descriptions, social posts, etc.)

---

## 2. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        USER INPUT                               │
│                   URL + Query + Format                           │
└──────────────────────┬──────────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────────────┐
│                     WEB UI (FastAPI + HTML/JS)                   │
│  - URL input field                                               │
│  - Query text box                                                │
│  - Content format selector                                       │
│  - Results display panel                                         │
│  - Export buttons (JSON, CSV, Markdown)                           │
└──────────────────────┬──────────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────────────┐
│                   ORCHESTRATOR (Python)                           │
│  Coordinates the full pipeline, manages state & errors           │
└──────┬───────────────┬───────────────┬──────────────────────────┘
       │               │               │
       ▼               ▼               ▼
┌─────────────┐ ┌─────────────┐ ┌─────────────────┐
│ BROWSER     │ │ PREPROCESSOR│ │ LLM ROUTER      │
│ LAYER       │ │             │ │                  │
│             │ │ - Strip     │ │ Task 1 → 8B      │
│ Lightpanda  │ │   Tailwind  │ │ Task 2 → Small 4 │
│ (primary)   │ │ - Remove    │ │ Task 3 → Medium 3│
│             │ │   scripts   │ │                  │
│ Chromium    │ │ - Extract   │ │ - Retry logic    │
│ (fallback)  │ │   images    │ │ - Rate limiting  │
│             │ │ - Truncate  │ │ - Cost tracking  │
└─────────────┘ └─────────────┘ └─────────────────┘
```

**Data Flow:**

```
1. User submits URL + query
2. Browser fetches the page HTML
3. Preprocessor strips noise, extracts images separately
4. Step A (Ministral 8B): Analyze — what data is here vs missing?
5. Step B (Ministral 8B): Plan — where to navigate for missing data?
6. Browser navigates to each target page
7. Preprocessor cleans each page
8. Step C (Mistral Small 4): Extract — pull structured data per page
9. Merge extracted data + code-extracted images
10. (Optional) Step D (Mistral Medium 3): Generate content from data
11. Return results to user via UI
```

---

## 3. Tech Stack

### Language & Framework

| Component | Technology | Version | Why |
|-----------|-----------|---------|-----|
| Backend | Python | 3.11+ | Async support, ecosystem |
| Web Framework | FastAPI | 0.115+ | Async, WebSocket support, fast |
| Template Engine | Jinja2 | 3.1+ | For the simple web UI |
| Browser Automation | Playwright | 1.49+ | CDP compatible, Python async API |
| Headless Browser (primary) | Lightpanda | nightly | 11x faster, 9x less RAM |
| Headless Browser (fallback) | Chromium | via Playwright | 100% compatibility |
| LLM SDK | mistralai | 1.5+ | Official Mistral Python SDK |

### Install Commands

```bash
# 1. Create project directory
mkdir webmind-extractor && cd webmind-extractor

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

# 3. Install Python dependencies
pip install fastapi==0.115.6
pip install uvicorn[standard]==0.34.0
pip install mistralai==1.5.0
pip install playwright==1.49.1
pip install jinja2==3.1.5
pip install python-multipart==0.0.18
pip install aiofiles==24.1.0

# 4. Install Playwright browsers
playwright install chromium

# 5. Install Lightpanda (Linux/Mac)
# Linux x86_64:
curl -L -o lightpanda https://github.com/lightpanda-io/browser/releases/download/nightly/lightpanda-x86_64-linux
chmod a+x ./lightpanda

# Mac ARM:
curl -L -o lightpanda https://github.com/lightpanda-io/browser/releases/download/nightly/lightpanda-aarch64-macos
chmod a+x ./lightpanda

# Or use Docker:
docker pull lightpanda/browser:nightly
```

### Environment Variables

Create a `.env` file in the project root:

```env
MISTRAL_API_KEY=your-api-key-here
LIGHTPANDA_HOST=127.0.0.1
LIGHTPANDA_PORT=9222
LIGHTPANDA_DISABLE_TELEMETRY=true
MAX_PAGES_PER_SCRAPE=50
MAX_DEPTH=2
DEFAULT_TIMEOUT_MS=15000
LOG_LEVEL=INFO
```

---

## 4. Model Assignments & Pricing

### Three Models, Three Jobs

| Task | Model | Model ID in Code | Input $/1M | Output $/1M | Temperature |
|------|-------|-----------------|-----------|-------------|-------------|
| A+B: Analyze & Navigate | Ministral 8B | `ministral-8b-latest` | $0.10 | $0.10 | 0.1 |
| C: Data Extraction | Mistral Small 4 | `mistral-small-latest` | $0.15 | $0.60 | 0.0 |
| D: Content Generation | Mistral Medium 3 | `mistral-medium-latest` | $0.40 | $2.00 | 0.5–0.9 |

### Cost Estimates

| Scenario | Nav Calls | Extract Calls | Gen Calls | Total Cost |
|----------|----------|--------------|-----------|-----------|
| 10 products, no content gen | ~2 | 10 | 0 | ~$0.02 |
| 50 products, no content gen | ~5 | 50 | 0 | ~$0.09 |
| 50 products + descriptions | ~5 | 50 | 50 | ~$0.28 |
| 50 products + 1 comparison article | ~5 | 50 | 1 | ~$0.10 |

### API Key Setup

1. Go to https://console.mistral.ai
2. Sign up (free tier available, no credit card needed to start)
3. Go to API Keys → Create new key
4. Copy the key into your `.env` file

---

## 5. Project Structure

```
webmind-extractor/
│
├── .env                          # Environment variables
├── requirements.txt              # Python dependencies
├── run.py                        # Entry point — starts the server
│
├── app/
│   ├── __init__.py
│   ├── main.py                   # FastAPI app, routes, WebSocket
│   ├── config.py                 # Load .env, constants, model IDs
│   │
│   ├── browser/
│   │   ├── __init__.py
│   │   ├── manager.py            # Browser lifecycle (start/stop/connect)
│   │   ├── lightpanda.py         # Lightpanda-specific connection
│   │   ├── fallback.py           # Chromium fallback logic
│   │   └── page_actions.py       # Scroll, click tabs, expand accordions
│   │
│   ├── preprocessing/
│   │   ├── __init__.py
│   │   ├── html_cleaner.py       # Strip Tailwind, scripts, styles, data attrs
│   │   ├── image_extractor.py    # Extract all image URLs from raw HTML
│   │   └── url_resolver.py       # Make relative URLs absolute, decode CDN URLs
│   │
│   ├── llm/
│   │   ├── __init__.py
│   │   ├── client.py             # Mistral client initialization
│   │   ├── analyzer.py           # Step A: Page analysis (Ministral 8B)
│   │   ├── navigator.py          # Step B: Navigation planning (Ministral 8B)
│   │   ├── extractor.py          # Step C: Data extraction (Mistral Small 4)
│   │   ├── generator.py          # Step D: Content generation (Mistral Medium 3)
│   │   ├── prompts.py            # All system prompts in one place
│   │   ├── schemas.py            # JSON schemas for structured output
│   │   └── retry.py              # Retry logic, rate limit handling
│   │
│   ├── pipeline/
│   │   ├── __init__.py
│   │   ├── orchestrator.py       # Main pipeline: connects all steps
│   │   ├── query_parser.py       # Convert user query → field list
│   │   └── result_merger.py      # Merge extracted data + images
│   │
│   ├── output/
│   │   ├── __init__.py
│   │   ├── json_export.py        # Export results as JSON
│   │   ├── csv_export.py         # Export results as CSV
│   │   └── markdown_export.py    # Export generated content as Markdown
│   │
│   ├── tracking/
│   │   ├── __init__.py
│   │   └── cost_tracker.py       # Track tokens & cost per model
│   │
│   └── templates/
│       ├── index.html            # Main web UI page
│       └── results.html          # Results display (or use same page with JS)
│
├── static/
│   ├── style.css                 # Minimal styling
│   └── app.js                    # Frontend JavaScript
│
├── tests/
│   ├── test_html_cleaner.py
│   ├── test_image_extractor.py
│   ├── test_analyzer.py
│   ├── test_extractor.py
│   ├── test_pipeline.py
│   └── fixtures/                 # Sample HTML files for testing
│       ├── tailwind_product_page.html
│       ├── nextjs_listing.html
│       ├── simple_listing.html
│       └── spa_react_page.html
│
├── output/                       # Generated output files
│   ├── results/
│   └── content/
│
└── lightpanda                    # Lightpanda binary (not committed to git)
```

---

## 6. Phase 1: Environment Setup

### Step 1.1 — Create the project

```bash
mkdir webmind-extractor && cd webmind-extractor
python -m venv venv
source venv/bin/activate
```

### Step 1.2 — Create requirements.txt

```
fastapi==0.115.6
uvicorn[standard]==0.34.0
mistralai==1.5.0
playwright==1.49.1
jinja2==3.1.5
python-multipart==0.0.18
aiofiles==24.1.0
python-dotenv==1.0.1
```

```bash
pip install -r requirements.txt
playwright install chromium
```

### Step 1.3 — Create config.py

```python
# app/config.py
import os
from dotenv import load_dotenv

load_dotenv()

# API
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")
if not MISTRAL_API_KEY:
    raise ValueError("MISTRAL_API_KEY not set in .env file")

# Models
MODEL_NAVIGATOR = "ministral-8b-latest"       # Task A+B
MODEL_EXTRACTOR = "mistral-small-latest"       # Task C
MODEL_GENERATOR = "mistral-medium-latest"      # Task D

# Model pricing (per 1M tokens) — for cost tracking
MODEL_PRICING = {
    MODEL_NAVIGATOR: {"input": 0.10, "output": 0.10},
    MODEL_EXTRACTOR: {"input": 0.15, "output": 0.60},
    MODEL_GENERATOR: {"input": 0.40, "output": 2.00},
}

# Browser
LIGHTPANDA_HOST = os.getenv("LIGHTPANDA_HOST", "127.0.0.1")
LIGHTPANDA_PORT = int(os.getenv("LIGHTPANDA_PORT", "9222"))
LIGHTPANDA_WS_URL = f"ws://{LIGHTPANDA_HOST}:{LIGHTPANDA_PORT}"

# Limits
MAX_PAGES_PER_SCRAPE = int(os.getenv("MAX_PAGES_PER_SCRAPE", "50"))
MAX_DEPTH = int(os.getenv("MAX_DEPTH", "2"))
DEFAULT_TIMEOUT_MS = int(os.getenv("DEFAULT_TIMEOUT_MS", "15000"))
MAX_HTML_CHARS = 50000            # For navigation/analysis
MAX_HTML_CHARS_EXTRACT = 80000    # For extraction (higher budget)
MAX_RETRIES = 3

# Output
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "output")
os.makedirs(os.path.join(OUTPUT_DIR, "results"), exist_ok=True)
os.makedirs(os.path.join(OUTPUT_DIR, "content"), exist_ok=True)
```

### Step 1.4 — Verify Mistral API access

```python
# test_api.py — run once to verify
from mistralai import Mistral
from app.config import MISTRAL_API_KEY

client = Mistral(api_key=MISTRAL_API_KEY)
response = client.chat.complete(
    model="ministral-8b-latest",
    messages=[{"role": "user", "content": "Say hello in JSON: {\"greeting\": \"...\"}"}],
    response_format={"type": "json_object"},
    max_tokens=50
)
print(response.choices[0].message.content)
print(f"Tokens used: {response.usage.prompt_tokens} in, {response.usage.completion_tokens} out")
print("API connection successful!")
```

---

## 7. Phase 2: Browser Layer

### Step 2.1 — Browser Manager

```python
# app/browser/manager.py
import asyncio
from playwright.async_api import async_playwright, Browser, Page
from app.config import LIGHTPANDA_WS_URL, DEFAULT_TIMEOUT_MS
import logging

logger = logging.getLogger(__name__)


class BrowserManager:
    """
    Manages browser lifecycle.
    Tries Lightpanda first, falls back to Chromium.
    """
    
    def __init__(self):
        self._playwright = None
        self._browser: Browser = None
        self._using_lightpanda = False
    
    async def start(self):
        """Initialize Playwright and connect to a browser."""
        self._playwright = await async_playwright().start()
        
        # Try Lightpanda first
        try:
            self._browser = await self._playwright.chromium.connect_over_cdp(
                LIGHTPANDA_WS_URL,
                timeout=5000
            )
            self._using_lightpanda = True
            logger.info("Connected to Lightpanda")
        except Exception as e:
            logger.warning(f"Lightpanda not available ({e}). Using Chromium.")
            self._browser = await self._playwright.chromium.launch(
                headless=True,
                args=[
                    "--disable-gpu",
                    "--disable-dev-shm-usage",
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                ]
            )
            self._using_lightpanda = False
            logger.info("Launched Chromium")
    
    async def new_page(self) -> Page:
        """Create a new browser page/tab."""
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
        """Clean up browser and Playwright."""
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
    
    @property
    def browser_name(self) -> str:
        return "Lightpanda" if self._using_lightpanda else "Chromium"
```

### Step 2.2 — Page Actions

```python
# app/browser/page_actions.py
import asyncio
from playwright.async_api import Page
import logging

logger = logging.getLogger(__name__)


async def fetch_page(page: Page, url: str, scroll: bool = True) -> str:
    """
    Navigate to a URL, wait for content, scroll for lazy loading.
    Returns the full page HTML.
    """
    try:
        await page.goto(url, wait_until="networkidle", timeout=15000)
    except Exception:
        # Fallback: some pages never fully reach "networkidle"
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=10000)
            await asyncio.sleep(2)  # Give JS time to run
        except Exception as e:
            logger.error(f"Failed to load {url}: {e}")
            raise
    
    if scroll:
        await auto_scroll(page)
    
    return await page.content()


async def auto_scroll(page: Page, pause: float = 0.3):
    """
    Scroll the page incrementally to trigger lazy-loaded images and content.
    Stops when no new content loads.
    """
    try:
        previous_height = 0
        for _ in range(20):  # Max 20 scroll iterations
            current_height = await page.evaluate("document.body.scrollHeight")
            if current_height == previous_height:
                break
            previous_height = current_height
            await page.evaluate("window.scrollBy(0, 600)")
            await asyncio.sleep(pause)
        
        # Scroll back to top
        await page.evaluate("window.scrollTo(0, 0)")
    except Exception as e:
        logger.warning(f"Scroll failed (non-critical): {e}")


async def expand_hidden_content(page: Page):
    """
    Click tabs, accordions, and "show more" buttons to reveal hidden content.
    Runs after page load, before extracting HTML.
    """
    selectors_to_try = [
        # Tabs
        "[data-tab='description']",
        "[data-tab='specs']",
        "[data-tab='specifications']",
        "#tab-description",
        "#tab-specs",
        "button[role='tab']",
        ".product-tabs button",
        ".tab-button",
        
        # Accordions
        ".accordion-toggle",
        ".accordion-header",
        "[data-toggle='collapse']",
        "details > summary",
        
        # "Show more" / "Read more"
        "button:has-text('Show More')",
        "button:has-text('Read More')",
        "button:has-text('See More')",
        "button:has-text('View All')",
        "a:has-text('Show More')",
        "a:has-text('Read More')",
        "[class*='show-more']",
        "[class*='read-more']",
        "[class*='expand']",
    ]
    
    for selector in selectors_to_try:
        try:
            elements = await page.query_selector_all(selector)
            for el in elements[:5]:  # Max 5 clicks per selector type
                try:
                    await el.click(timeout=2000)
                    await asyncio.sleep(0.3)
                except Exception:
                    continue
        except Exception:
            continue


async def click_load_more(page: Page, max_clicks: int = 5) -> int:
    """
    Click "Load More" buttons to expand listings.
    Returns the number of successful clicks.
    """
    load_more_selectors = [
        "button:has-text('Load More')",
        "button:has-text('Show More Products')",
        "button:has-text('View More')",
        "a:has-text('Load More')",
        "[class*='load-more']",
        "[class*='loadmore']",
        "[data-action='load-more']",
    ]
    
    clicks = 0
    for _ in range(max_clicks):
        clicked = False
        for selector in load_more_selectors:
            try:
                button = await page.query_selector(selector)
                if button and await button.is_visible():
                    await button.click()
                    await asyncio.sleep(1.5)  # Wait for content to load
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
```

---

## 8. Phase 3: HTML Preprocessing

### Step 3.1 — Tailwind Stripper + HTML Cleaner

This is the most cost-impactful piece. Every token you strip here
saves money on every LLM call.

File: `app/preprocessing/html_cleaner.py`

**What it does:**
1. Removes `<script>`, `<style>`, `<noscript>`, `<svg>`, comments
2. Removes `data-*` attributes (data-testid, data-nimg, etc.)
3. Removes inline `style=""` attributes
4. Removes `aria-*` attributes and `role` attributes
5. Strips Tailwind utility classes but keeps semantic classes
6. Removes empty wrapper `<div>` and `<span>` tags
7. Removes framework noise (Next.js, Nuxt, React attributes)
8. Extracts `<body>` content only
9. Collapses whitespace
10. Truncates to token budget

**Key patterns to strip:**
- Layout: flex, grid, block, hidden, items-*, justify-*
- Spacing: p-*, m-*, gap-*, space-*
- Sizing: w-*, h-*, max-w-*, min-h-*
- Typography: text-sm, text-lg, font-bold, text-gray-*
- Colors: bg-*, text-*-[number], border-*-[number]
- Borders: rounded-*, border-*, ring-*
- Effects: shadow-*, opacity-*, transition-*, duration-*
- States: hover:*, focus:*, dark:*, sm:*, md:*, lg:*
- Position: relative, absolute, fixed, z-*, inset-*
- Overflow: overflow-*, truncate, line-clamp-*

**Classes to KEEP:**
- Any class containing: product, price, description, rating, review, 
  cart, availability, stock, category, breadcrumb, pagination, nav-main,
  header-main, footer-main, search, filter

**Expected result:** 85% token reduction on Tailwind-heavy pages.

See the full implementation in the Tailwind_And_Image_Handling.md guide.

### Step 3.2 — Image Extractor

File: `app/preprocessing/image_extractor.py`

**What it does (runs on RAW HTML before cleaning):**
1. Extracts `<img>` src, srcset, data-src, data-lazy-src
2. Parses `srcset` → picks the largest width
3. Extracts `<picture>` → `<source>` elements
4. Extracts CSS `background-image: url(...)` from inline styles
5. Extracts Open Graph `<meta property="og:image">`
6. Extracts JSON-LD structured data images
7. Decodes Next.js `/_next/image?url=...` → original URL
8. Decodes Shopify CDN `_300x300.jpg` → full size
9. Decodes WordPress `-300x200.jpg` → full size
10. Filters out: base64 placeholders, tracking pixels, spacer GIFs, SVG blur
11. Deduplicates by URL
12. Scores images by source quality (JSON-LD > OG > srcset > src > background)
13. Returns sorted list with best image first

**Why code, not LLM:** Image URL extraction is deterministic pattern matching.
Using an LLM for this would cost tokens and sometimes hallucinate URLs.
Code is free, fast, and 100% reliable.

### Step 3.3 — URL Resolver

File: `app/preprocessing/url_resolver.py`

**What it does:**
- Converts relative URLs (`/products/123`) to absolute (`https://example.com/products/123`)
- Handles protocol-relative URLs (`//cdn.example.com/img.jpg`)
- Handles path-relative URLs (`../images/photo.jpg`)
- Normalizes URL encoding

---

## 9. Phase 4: Reasoning Chain

This is the brain of the application. Three LLM steps that mirror
how a human would think about navigating a website.

### Step A: Page Analysis (Ministral 8B)

File: `app/llm/analyzer.py`

**Input:** Cleaned HTML + list of requested fields
**Output:** JSON with fields_found, fields_missing, page_type, has_detail_links

**System prompt key instructions:**
- Identify page type (listing, detail, search, category, other)
- For each requested field, check if it exists in the HTML
- For missing fields, reason about where they likely exist
- Recognize patterns: truncated text with "...", thumbnail images,
  cards with links, "View Details" buttons
- Return structured JSON (enforced via response_format)

**When to skip:** If user's query only asks for fields that are
typically on listing pages (name, price, thumbnail), you can skip
analysis and go straight to extraction.

### Step B: Navigation Planning (Ministral 8B)

File: `app/llm/navigator.py`

**Input:** Cleaned HTML + analysis result from Step A
**Output:** JSON with strategy, targets (URLs + selectors), pagination info

**Only runs IF** Step A found missing fields.

**Strategies the model can return:**
- `click_each_item` — visit each product/item detail page
- `click_load_more` — expand the current page (no navigation)
- `paginate` — go to next page of results
- `no_navigation_needed` — all data is on current page

**System prompt key instructions:**
- Look for `<a>` tags wrapping product titles, images, or cards
- Look for buttons: "View Details", "Read More", "See More"
- Look for href patterns: /product/, /item/, /p/, /detail/, /dp/
- Prefer the most specific link (product name link, not generic "Shop Now")
- Ignore: nav menus, footers, ads, login links, social links
- Extract ALL item links, not just the first one
- Check for pagination (next page button/link)

### Step C: Data Extraction (Mistral Small 4)

File: `app/llm/extractor.py`

**Input:** Cleaned HTML from a detail page + JSON schema
**Output:** Structured JSON matching the schema exactly

**Key features:**
- Uses `response_format` with `json_schema` for guaranteed structure
- Temperature 0.0 for deterministic output
- Schema is dynamically built from user's requested fields
- `reasoning_effort` can be adjusted based on page complexity:
  - Simple page (<500 tags): "none" (fastest)
  - Moderate page (500-2000 tags): "medium"
  - Complex page (>2000 tags, nested tables, iframes): "high"

**System prompt key instructions:**
- Extract text content, not HTML tags
- For prices: extract numeric value and currency separately
- For missing fields: return null, never invent data
- Clean whitespace and formatting artifacts
- Never hallucinate — if not in the HTML, return null

### Step D: Content Generation (Mistral Medium 3)

File: `app/llm/generator.py`

**Input:** Extracted structured data + prompt format template
**Output:** Polished content (text, markdown, HTML, or JSON)

**Runs only when** user requests content generation.

**Built-in prompt formats:**
- product_description
- comparison_article
- social_media (multi-platform)
- seo_article
- email_campaign
- data_summary
- custom (user provides their own system prompt)

**Temperature varies by format:**
- Product descriptions: 0.7
- Blog articles: 0.7-0.8
- Social media: 0.8-0.9
- SEO articles: 0.5-0.6
- Data summaries: 0.3-0.4

---

## 10. Phase 5: Putting Images into the Pipeline

**Critical rule:** Extract images with CODE, not with the LLM.

```
Raw HTML
   │
   ├──→ image_extractor.py → List of image URLs (free, reliable)
   │
   └──→ html_cleaner.py → Clean HTML (stripped of image noise)
                │
                └──→ LLM extracts TEXT fields only
                        │
                        └──→ result_merger.py combines text + images
```

The LLM never sees srcset attributes, data-nimg, CDN parameters.
It only deals with product names, prices, descriptions — text.

Images are merged into the final result:

```python
{
    "name": "iPhone 15",              # From LLM
    "price": 799,                     # From LLM
    "description": "...",             # From LLM
    "image_urls": ["https://..."],    # From code
    "primary_image": "https://...",   # From code (highest quality)
}
```

---

## 11. Phase 6: The Orchestrator

File: `app/pipeline/orchestrator.py`

This is the main function that connects everything.

```
orchestrate(url, query, content_format=None)
    │
    ├── 1. Parse query → list of requested fields
    │
    ├── 2. Fetch listing page (browser)
    │
    ├── 3. Preprocess: extract images + clean HTML
    │
    ├── 4. Step A: Analyze page (Ministral 8B)
    │       └── Returns: fields_found, fields_missing
    │
    ├── 5. Decision point:
    │       ├── All fields found → Extract from this page directly
    │       └── Fields missing → Continue to Step B
    │
    ├── 6. Step B: Plan navigation (Ministral 8B)
    │       └── Returns: strategy + list of target URLs
    │
    ├── 7. For each target URL:
    │       ├── a. Fetch page (browser)
    │       ├── b. Expand hidden content (click tabs/accordions)
    │       ├── c. Preprocess: extract images + clean HTML
    │       ├── d. Step C: Extract data (Mistral Small 4)
    │       └── e. Merge text data + image data
    │
    ├── 8. Handle pagination (if detected):
    │       └── Fetch next page → repeat from Step 3
    │
    ├── 9. Compile all results
    │
    ├── 10. (Optional) Step D: Generate content (Mistral Medium 3)
    │
    └── 11. Return final results + cost summary
```

**State management during pipeline:**

```python
class PipelineState:
    """Tracks state across the entire scraping session."""
    
    def __init__(self, url: str, query: str):
        self.start_url = url
        self.query = query
        self.requested_fields: list[str] = []
        self.pages_visited: list[str] = []
        self.pages_failed: list[dict] = []
        self.extracted_items: list[dict] = []
        self.generated_content: str = ""
        self.cost_tracker = CostTracker()
        self.start_time: float = 0
        self.end_time: float = 0
    
    @property
    def duration_seconds(self) -> float:
        return self.end_time - self.start_time
    
    def summary(self) -> dict:
        return {
            "url": self.start_url,
            "query": self.query,
            "pages_visited": len(self.pages_visited),
            "pages_failed": len(self.pages_failed),
            "items_extracted": len(self.extracted_items),
            "has_content": bool(self.generated_content),
            "duration_seconds": round(self.duration_seconds, 1),
            "cost": self.cost_tracker.get_cost()
        }
```

---

## 12. Phase 7: Web UI

Simple, functional, no framework needed.

### Backend Routes (FastAPI)

```python
# app/main.py

GET  /                    → Serve the main page (index.html)
POST /api/scrape          → Start a scraping job, return results
WS   /ws/scrape           → WebSocket for real-time progress updates
GET  /api/export/{job_id} → Download results as JSON/CSV/Markdown
```

### Frontend (index.html)

**Layout:**
```
┌──────────────────────────────────────────────┐
│  WebMind Extractor                            │
├──────────────────────────────────────────────┤
│                                              │
│  URL: [________________________] [Scrape]    │
│                                              │
│  Query: [________________________________]   │
│  "Get me all product names, prices, and      │
│   descriptions"                              │
│                                              │
│  ┌─ Content Generation (optional) ────────┐  │
│  │ Format: [Product Description ▼]        │  │
│  │ Tone:   [Professional ▼]              │  │
│  │ Audience: [________________]           │  │
│  └────────────────────────────────────────┘  │
│                                              │
│  ┌─ Progress ─────────────────────────────┐  │
│  │ [■■■■■■■░░░] 7/10 pages               │  │
│  │ Step A: Analyzing... ✓                 │  │
│  │ Step B: Found 10 links ✓              │  │
│  │ Step C: Extracting page 7/10...       │  │
│  └────────────────────────────────────────┘  │
│                                              │
│  ┌─ Results ──────────────────────────────┐  │
│  │ { "name": "iPhone 15", ... }           │  │
│  │ { "name": "Pixel 8", ... }             │  │
│  │                                        │  │
│  │ [Export JSON] [Export CSV] [Copy]       │  │
│  └────────────────────────────────────────┘  │
│                                              │
│  ┌─ Cost ─────────────────────────────────┐  │
│  │ Navigation: $0.002  │  Extraction: $0.07│  │
│  │ Generation: $0.19   │  Total: $0.262    │  │
│  └────────────────────────────────────────┘  │
│                                              │
└──────────────────────────────────────────────┘
```

Use WebSocket for real-time progress updates during scraping.
This prevents the UI from appearing frozen during long scrapes.

---

## 13. Phase 8: Error Handling & Retries

### Retry Logic

```
Every LLM call goes through call_with_retry():
    Attempt 1 → call model
        Success → return result
        JSON parse error → append "Return ONLY valid JSON" to prompt, retry
        Rate limit (429) → wait 1s, retry
        Server error (500/503) → wait 2s, retry
    Attempt 2 → call model (with modified prompt if needed)
        Success → return result
        Same errors → wait 4s, retry
    Attempt 3 → call model
        Success → return result
        Failure → return error object, don't crash pipeline
```

### Browser Retry Logic

```
Every page fetch goes through fetch_with_retry():
    Attempt 1 → navigate to URL with "networkidle"
        Timeout → retry with "domcontentloaded" + 2s wait
        Navigation error → retry once
        Anti-bot block detected (403/captcha) → log, skip page
    Attempt 2 → navigate with relaxed settings
        Still failing → add to pages_failed list, continue pipeline
```

### What NOT to retry:
- 401 Unauthorized (bad API key) → stop immediately, tell user
- 404 Not Found (page doesn't exist) → skip, log
- Anti-bot detection → skip, log, suggest proxy

---

## 14. Phase 9: Cost Tracking

Track every LLM call. Show cost to user after each session.

```python
class CostTracker:
    PRICING = {
        "ministral-8b-latest":    {"input": 0.10, "output": 0.10},
        "mistral-small-latest":   {"input": 0.15, "output": 0.60},
        "mistral-medium-latest":  {"input": 0.40, "output": 2.00},
    }
    
    # Track per model:
    #   - Number of calls
    #   - Total input tokens
    #   - Total output tokens
    #   - Calculated cost in USD
    
    # After every LLM call:
    #   tracker.log(model_id, response)
    
    # At the end:
    #   tracker.print_summary()
    #   tracker.get_cost() → dict with breakdown
```

---

## 15. Phase 10: Output & Export

### JSON Export
```python
# Standard JSON output
{
    "metadata": {
        "url": "https://example.com/products",
        "query": "Get all products with descriptions",
        "scraped_at": "2026-04-04T10:30:00Z",
        "pages_visited": 12,
        "duration_seconds": 45.2,
        "cost_usd": 0.094
    },
    "items": [
        {
            "name": "iPhone 15",
            "price": 799,
            "currency": "USD",
            "description": "...",
            "image_urls": ["https://..."],
            "primary_image": "https://...",
            "rating": 4.7,
            "source_url": "https://example.com/products/iphone-15"
        }
    ],
    "generated_content": "..." // Only if content generation was requested
}
```

### CSV Export
Flatten the JSON into a table. One row per item.
Array fields (image_urls) joined with `|` separator.

### Markdown Export
For generated content — save as .md file with frontmatter.

---

## 16. Phase 11: Testing Strategy

### Unit Tests (run without API calls)

| Test File | What It Tests |
|-----------|---------------|
| test_html_cleaner.py | Tailwind stripping, script removal, whitespace collapse |
| test_image_extractor.py | srcset parsing, Next.js URL decoding, deduplication |
| test_url_resolver.py | Relative → absolute URL conversion |
| test_query_parser.py | "Get prices and images" → ["price", "image_urls"] |
| test_result_merger.py | Merging LLM data + code-extracted images |

### Integration Tests (require API key, run sparingly)

| Test File | What It Tests |
|-----------|---------------|
| test_analyzer.py | Feed sample HTML → verify analysis output structure |
| test_extractor.py | Feed sample HTML + schema → verify extraction accuracy |
| test_pipeline.py | Full pipeline on 3 known test sites |

### Test Fixtures

Create 4 sample HTML files in `tests/fixtures/`:
1. `simple_listing.html` — basic product cards with links
2. `tailwind_product_page.html` — heavy Tailwind, Next.js images
3. `nextjs_listing.html` — SSR React page with JSON-LD
4. `spa_react_page.html` — client-rendered SPA content

### Manual Testing Checklist

Test against 10 real websites of different types:

| # | Site Type | Example | Tests |
|---|-----------|---------|-------|
| 1 | Simple e-commerce | Hacker News | Basic extraction |
| 2 | Shopify store | Any Shopify site | CDN images, Tailwind |
| 3 | Amazon product page | amazon.com | Complex HTML, lazy images |
| 4 | WordPress blog | Any WP blog | Article extraction |
| 5 | React SPA | Any React site | JS-rendered content |
| 6 | Next.js e-commerce | Vercel commerce demo | /_next/image, SSR |
| 7 | News site | BBC/CNN | Article text + images |
| 8 | Restaurant menu | Any restaurant site | Prices + descriptions |
| 9 | Real estate listing | Zillow/similar | Multi-field extraction |
| 10 | Directory/listing | Yelp/similar | Cards + pagination |

---

## 17. Phase 12: Edge Cases & Solutions

| Edge Case | Detection | Solution |
|-----------|-----------|----------|
| All data on listing page | Step A: fields_missing = [] | Skip navigation, extract directly |
| "Load More" button | Step B: strategy = "click_load_more" | Click button via Playwright, re-extract |
| Pagination | Step B: pagination.has_next_page = true | Follow next page URL, repeat pipeline |
| Hidden tabs/accordions | Content behind tabs | expand_hidden_content() before extraction |
| Infinite scroll | No "next page" but content loads on scroll | auto_scroll() with detection loop |
| Anti-bot (403/captcha) | HTTP 403 or captcha HTML detected | Log warning, skip page, suggest proxy |
| Very large HTML (>200KB) | char count check | Truncate to MAX_HTML_CHARS, warn user |
| Empty extraction result | All fields return null | Log warning, try re-extraction with higher reasoning_effort |
| JS-only rendering (no SSR) | Empty body after load | Wait longer, ensure JS executed, try Chromium fallback |
| Login-required page | Redirect to login page | Detect login form, warn user, skip |
| Rate limited by target site | HTTP 429 from target | Add delay between page fetches (1-2s) |
| Rate limited by Mistral API | HTTP 429 from Mistral | Exponential backoff in retry logic |
| Nested navigation (3+ levels) | Detail page still has missing fields | Recursive scrape with MAX_DEPTH limit |
| Non-English content | Page in another language | Works fine — all 3 Mistral models are multilingual |
| Price in unusual format | "Rs. 1,23,456" or "€1.234,56" | LLM handles this — trained on diverse formats |

---

## 18. Phase 13: Deployment (When Ready)

### Local Development
```bash
# Terminal 1: Start Lightpanda
./lightpanda serve --host 127.0.0.1 --port 9222

# Terminal 2: Start the app
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Docker (Production)

```dockerfile
FROM python:3.11-slim

# Install system deps
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Lightpanda
RUN curl -L -o /usr/local/bin/lightpanda \
    https://github.com/lightpanda-io/browser/releases/download/nightly/lightpanda-x86_64-linux \
    && chmod +x /usr/local/bin/lightpanda

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install chromium && playwright install-deps chromium

COPY . .

# Start both Lightpanda and the app
CMD lightpanda serve --host 127.0.0.1 --port 9222 & \
    uvicorn app.main:app --host 0.0.0.0 --port 8000
```

---

## 19. Build Timeline

### Week 1: Foundation
- Day 1-2: Project setup, config, virtual env, verify API access
- Day 3-4: Browser manager (Chromium only, no Lightpanda yet)
- Day 5-6: HTML cleaner (Tailwind stripper + basic preprocessing)
- Day 7: Image extractor (srcset, data-src, Next.js, basic patterns)
- **Milestone:** Can fetch a page and get clean HTML + image list

### Week 2: LLM Pipeline
- Day 1-2: Step A — Analyzer (feed HTML, get fields_found/missing)
- Day 3-4: Step B — Navigator (get target URLs from analysis)
- Day 5-6: Step C — Extractor (extract structured data with schema)
- Day 7: Wire A → B → C together in orchestrator (no UI yet)
- **Milestone:** Can run full pipeline from Python script, get JSON results

### Week 3: Robustness
- Day 1-2: Error handling, retry logic, rate limiting
- Day 3: Cost tracker
- Day 4: Page actions (scroll, expand tabs, click "Load More")
- Day 5-6: Test on 10 real websites, fix edge cases
- Day 7: Add Lightpanda as primary browser, Chromium as fallback
- **Milestone:** Reliable pipeline that handles most real websites

### Week 4: UI & Content Generation
- Day 1-2: FastAPI routes + basic HTML/JS frontend
- Day 3: WebSocket for real-time progress
- Day 4-5: Step D — Content generator with prompt format templates
- Day 6: Export functionality (JSON, CSV, Markdown)
- Day 7: Polish UI, add cost display
- **Milestone:** Working web app, end to end

### Week 5: Polish & Testing
- Day 1-2: Write unit tests for preprocessor and image extractor
- Day 3: Write integration tests for LLM steps
- Day 4-5: Test on 10 more websites, fix remaining issues
- Day 6: Documentation (README, API docs)
- Day 7: Docker setup for deployment
- **Milestone:** Production-ready MVP

---

## 20. Risk Register

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Mistral API downtime | Pipeline stops | Low | Add timeout, show friendly error |
| Lightpanda breaks on specific site | No data from that site | Medium | Auto-fallback to Chromium |
| Target site blocks scraping | No data | Medium | User-agent rotation, delay between requests |
| HTML too large for context window | Incomplete extraction | Medium | Aggressive preprocessing, chunking |
| Mistral rate limit hit | Slow pipeline | Medium | Exponential backoff, concurrency limit |
| Extraction returns wrong data | Bad output quality | Medium | Schema enforcement, manual spot-check |
| Cost exceeds expectations | Budget overrun | Low | Cost tracker with hard limit option |
| Gemini/OpenAI releases cheaper model | Competitive pressure | N/A | Architecture is model-agnostic, swap anytime |

---

## 21. Future Roadmap (Post-MVP)

| Feature | Priority | Effort |
|---------|----------|--------|
| Save & re-run past queries | High | 1 week |
| Scheduled scraping (cron) | High | 1 week |
| Multi-page deep crawling (3+ levels) | Medium | 1 week |
| Proxy rotation support | Medium | 2-3 days |
| Login/session cookie support | Medium | 1 week |
| Fine-tune Ministral 8B on your common sites | Low | 2 weeks |
| Result caching (don't re-scrape same URL within X hours) | High | 2-3 days |
| CSV/Google Sheets direct export | Medium | 2-3 days |
| Browser extension for "scrape this page" | Low | 2 weeks |
| Multi-language content generation | Medium | 2-3 days |

---

## Quick Start Commands

Once everything is set up, this is your daily workflow:

```bash
# 1. Activate environment
cd webmind-extractor
source venv/bin/activate

# 2. Start Lightpanda (separate terminal)
./lightpanda serve --host 127.0.0.1 --port 9222 --obey-robots

# 3. Start the app
uvicorn app.main:app --reload --port 8000

# 4. Open browser
# http://localhost:8000

# 5. Run tests
pytest tests/ -v
```
