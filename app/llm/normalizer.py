"""
Normalize raw scraped data into your DB schema.

Modes:
  "contest"    → Prompts.txt schema (v2.0)
  "conference" → ConferencesPrompt.txt schema (v2.0)
"""

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


async def normalize(
    items: list[dict],
    mode: str,  # "contest" | "conference"
    source_url: str,
    cost_tracker: CostTracker,
) -> list[dict]:
    """
    Run each scraped item through the normalization prompt.
    Returns a list of normalized DB-ready dicts (one per item).
    """
    system_prompt = _SYSTEM_MAP.get(mode)
    if not system_prompt:
        raise ValueError(
            f"Unknown normalize mode: {mode!r}. Use 'contest' or 'conference'."
        )

    client = get_client()
    results = []

    for i, item in enumerate(items):
        user_message = (
            f"Source URL: {source_url}\n\n"
            f"Raw scraped data:\n{json.dumps(item, indent=2, ensure_ascii=False)}"
        )

        async def _call(msg=user_message):
            return await client.chat.completions.create(
                model=MODEL_GENERATOR,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": msg},
                ],
                response_format={"type": "json_object"},
                temperature=0.0,
                max_tokens=2000,
            )

        try:
            async with llm_semaphore:
                response = await call_with_retry(_call)
            cost_tracker.log(MODEL_GENERATOR, response)
            normalized = json.loads(response.choices[0].message.content)
            results.append(normalized)
            logger.info(f"Normalized item {i + 1}/{len(items)} ({mode})")
        except json.JSONDecodeError as e:
            logger.error(f"Normalizer returned invalid JSON for item {i + 1}: {e}")
            results.append({"_normalize_error": str(e), "_raw": item})
        except Exception as e:
            logger.error(f"Normalizer failed for item {i + 1}: {e}")
            results.append({"_normalize_error": str(e), "_raw": item})

    return results
