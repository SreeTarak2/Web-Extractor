"""Step D — Content generation using Mistral Medium 3."""

import json
import logging

from app.llm.client import get_client
from app.llm.prompts import GENERATOR_SYSTEM_TEMPLATES
from app.llm.retry import call_with_retry
from app.llm.semaphore import llm_semaphore
from app.tracking.cost_tracker import CostTracker
from app.config import MODEL_GENERATOR

logger = logging.getLogger(__name__)

_FORMAT_TEMPERATURES = {
    "product_description": 0.7,
    "comparison_article": 0.7,
    "social_media": 0.85,
    "seo_article": 0.55,
    "email_campaign": 0.65,
    "data_summary": 0.3,
}


async def generate_content(
    items: list[dict],
    content_format: str,
    cost_tracker: CostTracker,
    custom_prompt: str | None = None,
    tone: str = "professional",
    audience: str = "general",
) -> str:
    """
    Generate polished content from extracted data.

    Args:
        items: List of extracted item dicts
        content_format: One of the template keys or "custom"
        cost_tracker: For cost tracking
        custom_prompt: Used when content_format == "custom"
        tone: e.g. "professional", "casual", "enthusiastic"
        audience: Target audience description

    Returns:
        Generated content as a string
    """
    client = get_client()

    if content_format == "custom" and custom_prompt:
        system_prompt = custom_prompt
    else:
        system_prompt = GENERATOR_SYSTEM_TEMPLATES.get(
            content_format,
            GENERATOR_SYSTEM_TEMPLATES["data_summary"],
        )

    temperature = _FORMAT_TEMPERATURES.get(content_format, 0.7)

    data_str = json.dumps(items, indent=2)
    user_message = f"Tone: {tone}\nTarget audience: {audience}\n\nData:\n{data_str}"

    async def _call():
        return await client.chat.completions.create(
            model=MODEL_GENERATOR,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=temperature,
            max_tokens=4000,
        )

    async with llm_semaphore:
        response = await call_with_retry(_call)
    cost_tracker.log(MODEL_GENERATOR, response)

    content = response.choices[0].message.content
    logger.info(f"Generated {len(content)} chars of {content_format} content")
    return content
