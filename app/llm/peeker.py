"""Quick page peek — detect what data is extractable from a page."""

import json
import logging

from app.llm.client import get_client
from app.llm.retry import call_with_retry
from app.llm.semaphore import llm_semaphore
from app.config import MODEL_NAVIGATOR

logger = logging.getLogger(__name__)

_SYSTEM = """You are a web data analyst. Given cleaned HTML, identify what structured data is available.

Return JSON with this exact shape:
{
  "page_type": "listing|detail|article|search|other",
  "summary": "One sentence describing the page content",
  "available_fields": ["field1", "field2", ...],
  "suggested_query": "comma-separated field names the user could extract"
}

Rules for available_fields:
- Use short snake_case names (e.g. "product_name", "price", "rating", "image_url", "description")
- Only include fields that clearly exist on this page
- Maximum 12 fields
- Always include "source_url" at the end
"""


async def peek_page(html: str) -> dict:
    """
    Quickly analyse a page and return what fields are extractable.
    Uses the cheap navigator model — no cost tracker needed for previews.
    """
    client = get_client()

    async def _call():
        return await client.chat.completions.create(
            model=MODEL_NAVIGATOR,
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": f"HTML:\n{html[:30_000]}"},
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
            max_tokens=400,
        )

    try:
        async with llm_semaphore:
            response = await call_with_retry(_call)
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        logger.warning(f"Page peek failed: {e}")
        return {
            "page_type": "unknown",
            "summary": "Could not analyse page.",
            "available_fields": [],
            "suggested_query": "",
        }
