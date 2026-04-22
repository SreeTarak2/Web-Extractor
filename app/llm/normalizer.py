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
from datetime import datetime, timezone

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

        # Pull pre-extracted image data injected by the orchestrator/merger
        banner_url = item.get("_banner_url", "")
        logo_url = item.get("_logo_url", "")
        image_alt = item.get("_image_alt", "")

        # Strip private fields before sending raw data to LLM (cleaner prompt)
        item_clean = {k: v for k, v in item.items() if not k.startswith("_")}

        # If no pre-extracted banner, try to pull one from legacy image_urls field
        if not banner_url:
            image_urls = item.get("image_urls", [])
            primary = item.get("primary_image", "")
            if primary:
                banner_url = primary
            elif image_urls:
                banner_url = image_urls[0]

        user_message_parts = [
            f"Source URL: {item_url}",
            "",
            "==============================================",
            "PRE-EXTRACTED IMAGE DATA (use these directly — do NOT hunt for images in HTML):",
            "==============================================",
            f"banner_url: {banner_url if banner_url else '(none)'}",
            f"logo_url:   {logo_url if logo_url else '(none)'}",
            f"image_alt:  {image_alt if image_alt else '(none)'}",
            "",
            f"Raw scraped data:\n{json.dumps(item_clean, indent=2, ensure_ascii=False)}",
        ]

        if html_content:
            user_message_parts.extend(
                [
                    "",
                    "==============================================",
                    "WEBPAGE HTML CONTENT (use for extracting missing text fields only):",
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

            # Log category confidence for observability
            confidence = normalized.get("_categoryConfidence", "high")
            suggested = normalized.get("_suggestedCategory")
            if confidence != "high" or suggested:
                logger.warning(
                    f"Item {idx + 1} category confidence={confidence!r}, "
                    f"suggested={suggested!r}, assigned={normalized.get('category')!r}"
                )

            # Stamp lastVerifiedAt with current UTC time (never leave as null)
            normalized["lastVerifiedAt"] = datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%S"
            )

            # Safety net: if LLM left image URL null, inject from pre-extracted data
            primary = normalized.get("image", {}).get("primary", {})
            if not primary.get("url") and banner_url:
                normalized.setdefault("image", {}).setdefault("primary", {})["url"] = banner_url
                normalized["image"]["primary"].setdefault("source", "external")
                normalized["image"]["primary"].setdefault("status", "active")

            # Safety net: derive alt text from title if still empty
            if not normalized.get("image", {}).get("alt") and normalized.get("title"):
                normalized.setdefault("image", {})["alt"] = normalized["title"]

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
