"""Step C — Structured data extraction using Mistral Small 4."""

import json
import logging

from app.llm.client import get_client
from app.llm.prompts import EXTRACTOR_SYSTEM
from app.llm.schemas import build_extraction_schema
from app.llm.retry import call_with_retry
from app.llm.semaphore import llm_semaphore
from app.tracking.cost_tracker import CostTracker
from app.config import MODEL_EXTRACTOR

logger = logging.getLogger(__name__)


def _estimate_tag_count(html: str) -> int:
    return html.count("<")


def _pick_reasoning_effort(html: str) -> str:
    tags = _estimate_tag_count(html)
    if tags < 500:
        return "none"
    if tags < 2000:
        return "medium"
    return "high"


async def extract_data(
    html: str,
    requested_fields: list[str],
    source_url: str,
    cost_tracker: CostTracker,
) -> dict:
    """
    Extract structured data from a single page.

    Returns a dict with the requested fields (nulls for missing).
    """
    client = get_client()
    schema = build_extraction_schema(requested_fields)
    fields_str = ", ".join(requested_fields)

    user_message = (
        f"Source URL: {source_url}\nExtract these fields: {fields_str}\n\nHTML:\n{html}"
    )

    async def _call():
        return await client.chat.completions.create(
            model=MODEL_EXTRACTOR,
            messages=[
                {"role": "system", "content": EXTRACTOR_SYSTEM},
                {"role": "user", "content": user_message},
            ],
            response_format=schema,
            temperature=0.0,
            max_tokens=1000,
        )

    async with llm_semaphore:
        response = await call_with_retry(_call)
    cost_tracker.log(MODEL_EXTRACTOR, response)

    try:
        result = json.loads(response.choices[0].message.content)
        result["source_url"] = source_url
    except json.JSONDecodeError as e:
        logger.error(f"Extractor returned invalid JSON for {source_url}: {e}")
        result = {field: None for field in requested_fields}
        result["source_url"] = source_url
        result["_extraction_error"] = str(e)

    logger.info(
        f"Extracted {sum(1 for v in result.values() if v is not None)} fields from {source_url}"
    )
    return result
