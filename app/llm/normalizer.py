"""
Normalize raw scraped data into your DB schema.

Modes:
  "contest"    → Prompts.txt schema (v2.0)
  "conference" → ConferencesPrompt.txt schema (v2.0)
"""

import os
import asyncio
import json
import logging

from app.llm.client import get_client
from app.llm.prompts import NORMALIZER_CONTEST_SYSTEM, NORMALIZER_CONFERENCE_SYSTEM
from app.llm.retry import call_with_retry
from app.llm.semaphore import llm_semaphore
from app.tracking.cost_tracker import CostTracker
from app.config import MODEL_GENERATOR

logger = logging.getLogger(__name__)

_SYSTEM_MAP = {
    "contest": NORMALIZER_CONTEST_SYSTEM,
    "conference": NORMALIZER_CONFERENCE_SYSTEM,
}

NORMALIZE_BATCH_SIZE = int(os.getenv("NORMALIZE_BATCH_SIZE", "3"))


async def normalize(
    items: list[dict],
    mode: str,  # "contest" | "conference"
    source_url: str,
    cost_tracker: CostTracker,
    html_by_url: dict | None = None,
) -> list[dict]:
    """
    Run each scraped item through the normalization prompt.
    Returns a list of normalized DB-ready dicts (one per item).

    Args:
        items: List of extracted items
        mode: "contest" or "conference"
        source_url: Base URL for the scrape
        cost_tracker: Cost tracker instance
        html_by_url: Optional dict mapping URL -> raw HTML for re-extraction
    """
    system_prompt = _SYSTEM_MAP.get(mode)
    if not system_prompt:
        raise ValueError(
            f"Unknown normalize mode: {mode!r}. Use 'contest' or 'conference'."
        )

    client = get_client()
    results = []

    async def normalize_single(item: dict, idx: int) -> dict:
        item_url = item.get("source_url", source_url)
        html_content = ""

        if html_by_url and item_url in html_by_url:
            html_content = html_by_url[item_url]

        user_message_parts = [
            f"Source URL: {item_url}",
            "",
            f"Raw scraped data:\n{json.dumps(item, indent=2, ensure_ascii=False)}",
        ]

        if html_content:
            user_message_parts.extend(
                [
                    "",
                    "==============================================",
                    "WEBPAGE HTML CONTENT (use for extracting missing data):",
                    "==============================================",
                    html_content[:80000],
                ]
            )

        user_message = "\n".join(user_message_parts)

        async def _call(msg=user_message):
            return await client.chat.completions.create(
                model=MODEL_GENERATOR,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": msg
                        + "\n\nIMPORTANT: Return ONLY valid JSON, no other text.",
                    },
                ],
                temperature=0.0,
                max_tokens=2500,
            )

        response = None
        try:
            async with llm_semaphore:
                response = await call_with_retry(_call)
            cost_tracker.log(MODEL_GENERATOR, response)
            content = response.choices[0].message.content
            normalized = json.loads(content)
            logger.info(f"Normalized item {idx + 1}/{len(items)} ({mode})")
            return normalized
        except json.JSONDecodeError as e:
            logger.error(f"Normalizer returned invalid JSON for item {idx + 1}: {e}")
            if response:
                logger.error(
                    f"Response content was: {response.choices[0].message.content}"
                )
            return {"_normalize_error": str(e), "_raw": item}
        except Exception as e:
            logger.error(f"Normalizer failed for item {idx + 1}: {e}")
            return {"_normalize_error": str(e), "_raw": item}

    for i in range(0, len(items), NORMALIZE_BATCH_SIZE):
        batch = items[i : i + NORMALIZE_BATCH_SIZE]
        batch_results = await asyncio.gather(
            *[normalize_single(item, i + j) for j, item in enumerate(batch)]
        )
        results.extend(batch_results)

        if i + NORMALIZE_BATCH_SIZE < len(items):
            await asyncio.sleep(0.5)

    return results
