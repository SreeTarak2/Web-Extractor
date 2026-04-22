"""Step A — Page analysis using Ministral 8B."""

import json
import logging

from app.llm.client import get_client
from app.llm.prompts import ANALYZER_SYSTEM
from app.llm.retry import call_with_retry
from app.llm.semaphore import llm_semaphore
from app.tracking.cost_tracker import CostTracker
from app.config import MODEL_NAVIGATOR

logger = logging.getLogger(__name__)


async def analyze_page(
    html: str,
    requested_fields: list[str],
    cost_tracker: CostTracker,
) -> dict:
    """
    Analyze a page to determine which requested fields are present vs missing.

    Returns:
        {
            "page_type": "listing|detail|...",
            "fields_found": [...],
            "fields_missing": [...],
            "has_detail_links": bool,
            "notes": "..."
        }
    """
    client = get_client()
    fields_str = ", ".join(requested_fields)

    user_message = f"Requested fields: {fields_str}\n\nHTML:\n{html}"

    async def _call():
        return await client.chat.completions.create(
            model=MODEL_NAVIGATOR,
            messages=[
                {"role": "system", "content": ANALYZER_SYSTEM},
                {"role": "user", "content": user_message},
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
            max_tokens=500,
        )

    async with llm_semaphore:
        response = await call_with_retry(_call)
    cost_tracker.log(MODEL_NAVIGATOR, response)

    content = response.choices[0].message.content or ""
    try:
        if not content.strip():
            # Model returned empty — assume all fields may be on the page
            # so extractor runs directly without unnecessary navigation
            logger.warning("Analyzer returned empty content; assuming detail page.")
            result = {
                "page_type": "detail",
                "fields_found": requested_fields,
                "fields_missing": [],
                "has_detail_links": False,
                "notes": "Empty response from model; defaulting to direct extraction",
            }
        else:
            result = json.loads(content)
            if isinstance(result, str):
                result = json.loads(result)
    except json.JSONDecodeError as e:
        logger.error(f"Analyzer returned invalid JSON: {e}")
        result = {
            "page_type": "detail",
            "fields_found": requested_fields,
            "fields_missing": [],
            "has_detail_links": False,
            "notes": "JSON parse error; defaulting to direct extraction",
        }

    logger.info(
        f"Analysis: page_type={result.get('page_type')}, "
        f"found={result.get('fields_found')}, "
        f"missing={result.get('fields_missing')}"
    )
    return result
