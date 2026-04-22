"""FastAPI application — routes and WebSocket."""

import json
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, Form
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi import Request
from pydantic import BaseModel

from app.pipeline.orchestrator import orchestrate
from app.browser.manager import BrowserManager
from app.browser.page_actions import fetch_page
from app.preprocessing.html_cleaner import clean_html
from app.llm.peeker import peek_page
from app.llm.normalizer import normalize
from app.tracking.cost_tracker import CostTracker

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

browser_manager = BrowserManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await browser_manager.start()
    logger.info(f"Browser started: {browser_manager.browser_name}")
    yield
    await browser_manager.stop()
    logger.info("Browser stopped")


app = FastAPI(title="WebMind Extractor", lifespan=lifespan)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="app/templates")


class ScrapeRequest(BaseModel):
    url: str
    query: str
    content_format: str | None = None


class PreviewRequest(BaseModel):
    url: str


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    import time
    return templates.TemplateResponse("index.html", {"request": request, "now": int(time.time())})


@app.post("/api/preview")
async def preview(req: PreviewRequest):
    """Fetch a URL and return what data fields are extractable."""
    try:
        page = await browser_manager.new_page()
    except RuntimeError as e:
        logger.error(f"Browser not available: {e}")
        return {
            "error": "Browser connection lost. Please refresh the page.",
            "available_fields": [],
            "summary": "",
            "suggested_query": "",
        }

    try:
        raw_html = await fetch_page(page, req.url)
    except Exception as e:
        logger.error(f"Preview fetch failed: {e}")
        return {
            "error": str(e),
            "available_fields": [],
            "summary": "",
            "suggested_query": "",
        }
    finally:
        await page.close()

    clean = clean_html(raw_html, max_chars=30_000)
    result = await peek_page(clean)
    return result


class NormalizeBatchRequest(BaseModel):
    items: list[dict]
    schema: str  # "contest" | "conference"


@app.post("/api/normalize-batch")
async def normalize_batch(req: NormalizeBatchRequest):
    """Normalize a batch of items (plain JSON — no file upload)."""
    import time

    start = time.time()
    if not req.items:
        return {"error": "No items provided", "items": [], "cost": {}}

    cost_tracker = CostTracker()

    # Inject per-item source_url so the normalizer uses each item's own URL,
    # not the session scraping URL. Checks common field names.
    URL_FIELDS = ("url", "link", "source_url", "href", "contest_url")
    items_with_url = []
    for item in req.items:
        item_copy = dict(item)
        if not item_copy.get("source_url"):
            for field in URL_FIELDS:
                if item_copy.get(field):
                    item_copy["source_url"] = item_copy[field]
                    break
        items_with_url.append(item_copy)

    try:
        normalized = await normalize(
            items=items_with_url,
            mode=req.schema,
            source_url="",  # normalizer now reads source_url per-item
            cost_tracker=cost_tracker,
        )
    except ValueError as e:
        return {"error": str(e), "items": [], "cost": {}}

    cost_summary = cost_tracker.get_cost()

    # Separate review signals (_fields) from clean DB items
    needs_review = []
    for item in normalized:
        confidence = item.get("_categoryConfidence", "high")
        suggested = item.get("_suggestedCategory")
        if confidence != "high" or suggested:
            needs_review.append(
                {
                    "title": item.get("title"),
                    "assignedCategory": item.get("category"),
                    "suggestedCategory": suggested,
                    "confidence": confidence,
                }
            )

    return {
        "items": normalized,
        "needsReview": needs_review,
        "cost": cost_summary,
        "duration_seconds": round(time.time() - start, 1),
    }


@app.post("/api/normalize-upload")
async def normalize_upload(
    file: UploadFile = File(...),
    schema: str = Form(...),  # "contest" | "conference"
    enrich: str = Form("false"),  # "true" | "false"
):
    """
    Accept a JSON file (array of objects) and normalize each item to the
    contest or conference DB schema. Optionally re-scrape URLs to fill gaps.
    """
    import time

    start = time.time()

    # 1. Parse the uploaded JSON
    raw_bytes = await file.read()
    try:
        payload = json.loads(raw_bytes)
    except json.JSONDecodeError as e:
        return {"error": f"Invalid JSON: {e}", "items": [], "cost": {}}

    # Accept both a bare array and {items: [...]}
    if isinstance(payload, dict):
        items = payload.get("items", [payload])
    elif isinstance(payload, list):
        items = payload
    else:
        return {
            "error": "JSON must be an array or an object with an 'items' key",
            "items": [],
            "cost": {},
        }

    if not items:
        return {"error": "No items found in JSON", "items": [], "cost": {}}

    cost_tracker = CostTracker()
    should_enrich = enrich.lower() == "true"

    # 2. Optional: re-scrape each item's URL to fill missing fields
    if should_enrich:
        url_field = next(
            (
                k
                for k in ("url", "link", "source_url", "href")
                if any(k in item for item in items)
            ),
            None,
        )
        if url_field:
            enriched = []
            for item in items:
                item_url = item.get(url_field, "")
                if not item_url:
                    enriched.append(item)
                    continue
                try:
                    page = await browser_manager.new_page()
                    try:
                        from app.browser.page_actions import fetch_page as _fetch
                        from app.preprocessing.html_cleaner import clean_html as _clean
                        from app.preprocessing.image_extractor import extract_images_with_metadata
                        from app.llm.extractor import extract_data

                        raw_html = await _fetch(page, item_url)
                    finally:
                        await page.close()

                    existing_fields = [k for k in item if item[k] is not None]
                    all_fields = list(set(existing_fields + list(item.keys())))
                    clean = _clean(raw_html, max_chars=80_000)
                    scraped = await extract_data(
                        clean, all_fields, item_url, cost_tracker
                    )
                    
                    # Also extract images from the raw HTML
                    images = extract_images_with_metadata(raw_html, item_url)
                    if images.get("banner"):
                        scraped["_banner_url"] = images["banner"]
                    if images.get("logo"):
                        scraped["_logo_url"] = images["logo"]
                    if images.get("alt"):
                        scraped["_image_alt"] = images["alt"]
                    if images.get("all"):
                        scraped["_image_urls"] = images["all"]
                    
                    # Merge: scraped fills gaps, existing values win
                    merged = {
                        **scraped,
                        **{k: v for k, v in item.items() if v is not None},
                    }
                    enriched.append(merged)
                except Exception as e:
                    logger.warning(f"Enrich failed for {item_url}: {e}")
                    enriched.append(item)
            items = enriched

    # 3. Normalize to schema
    source_url = (
        items[0].get("url") or items[0].get("link") or items[0].get("source_url") or ""
    )
    try:
        normalized = await normalize(
            items=items,
            mode=schema,
            source_url=source_url,
            cost_tracker=cost_tracker,
        )
    except ValueError as e:
        return {"error": str(e), "items": [], "cost": {}}

    cost_summary = cost_tracker.get_cost()
    return {
        "metadata": {
            "items_in": len(items),
            "items_out": len(normalized),
            "schema": schema,
            "enriched": should_enrich,
            "duration_seconds": round(time.time() - start, 1),
            "cost_usd": cost_summary["total_usd"],
        },
        "items": normalized,
        "generated_content": "",
        "cost": cost_summary,
    }


@app.post("/api/scrape")
async def scrape(req: ScrapeRequest):
    result = await orchestrate(
        browser_manager=browser_manager,
        url=req.url,
        query=req.query,
        content_format=req.content_format,
    )
    return result


@app.websocket("/ws/scrape")
async def ws_scrape(websocket: WebSocket):
    await websocket.accept()
    stop_event = asyncio.Event()
    scrape_task = None
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                logger.warning(f"Received non-JSON message: {raw}")
                continue
            msg_type = data.get("type", "scrape")

            if msg_type == "stop":
                stop_event.set()
                await websocket.send_json(
                    {"type": "stopping", "message": "Stopping scrape..."}
                )
                continue

            if msg_type == "scrape":
                url = data.get("url", "")
                query = data.get("query", "")
                content_format = data.get("content_format")

                stop_event.clear()

                async def progress_callback(message: str):
                    await websocket.send_json({"type": "progress", "message": message})

                scrape_task = asyncio.create_task(
                    orchestrate(
                        browser_manager=browser_manager,
                        url=url,
                        query=query,
                        content_format=content_format,
                        progress_callback=progress_callback,
                        stop_event=stop_event,
                    )
                )
                result = await scrape_task
                await websocket.send_json({"type": "result", "data": result})
                scrape_task = None

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
        if scrape_task and not scrape_task.done():
            stop_event.set()
            scrape_task.cancel()
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        import traceback

        logger.error(traceback.format_exc())
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass
