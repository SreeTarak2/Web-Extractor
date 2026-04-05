"""Step B — Navigation planning using Ministral 8B."""

import json
import logging

from app.llm.client import get_client
from app.llm.prompts import NAVIGATOR_SYSTEM
from app.llm.retry import call_with_retry
from app.llm.semaphore import llm_semaphore
from app.tracking.cost_tracker import CostTracker
from app.config import MODEL_NAVIGATOR

logger = logging.getLogger(__name__)


async def plan_navigation(
    html: str,
    analysis: dict,
    base_url: str,
    cost_tracker: CostTracker,
) -> dict:
    """
    Plan navigation strategy to find missing data.

    Returns:
        {
            "strategy": "click_each_item|click_load_more|paginate|no_navigation_needed",
            "targets": [{"url": "...", "label": "..."}],
            "pagination": {"has_next_page": bool, "next_page_url": str|null},
            "reasoning": "..."
        }
    """
    client = get_client()

    user_message = (
        f"Base URL: {base_url}\n"
        f"Analysis result: {json.dumps(analysis)}\n\n"
        f"HTML:\n{html}"
    )

    async def _call():
        return await client.chat.completions.create(
            model=MODEL_NAVIGATOR,
            messages=[
                {"role": "system", "content": NAVIGATOR_SYSTEM},
                {"role": "user", "content": user_message},
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
            max_tokens=2000,
        )

    async with llm_semaphore:
        response = await call_with_retry(_call)
    cost_tracker.log(MODEL_NAVIGATOR, response)

    try:
        result = json.loads(response.choices[0].message.content)
    except json.JSONDecodeError as e:
        logger.error(f"Navigator returned invalid JSON: {e}")
        result = {
            "strategy": "no_navigation_needed",
            "targets": [],
            "pagination": {"has_next_page": False, "next_page_url": None},
            "reasoning": "JSON parse error — defaulting to no navigation",
        }

    logger.info(
        f"Navigation plan: strategy={result.get('strategy')}, "
        f"targets={len(result.get('targets', []))}"
    )
    return result
