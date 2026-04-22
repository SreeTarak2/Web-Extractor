"""Retry logic for LLM calls — handles rate limits and transient errors."""
import asyncio
import logging
from typing import Callable, Any

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
BASE_DELAY = 1.0  # seconds


async def call_with_retry(fn: Callable, *args, **kwargs) -> Any:
    """
    Call an async function with exponential backoff retry.
    Handles rate limits (429) and server errors (500/503).
    """
    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            return await fn(*args, **kwargs)
        except Exception as e:
            last_error = e
            error_str = str(e).lower()

            # Don't retry auth errors
            if "401" in error_str or "unauthorized" in error_str:
                logger.error("API key invalid — stopping retries")
                raise

            # Rate limit
            if "429" in error_str or "rate limit" in error_str:
                wait = BASE_DELAY * (2 ** attempt)
                logger.warning(f"Rate limited. Waiting {wait}s before retry {attempt + 1}/{MAX_RETRIES}")
                await asyncio.sleep(wait)
                continue

            # Server errors
            if any(code in error_str for code in ("500", "503", "502")):
                wait = BASE_DELAY * (2 ** attempt)
                logger.warning(f"Server error. Waiting {wait}s before retry {attempt + 1}/{MAX_RETRIES}")
                await asyncio.sleep(wait)
                continue

            # JSON parse errors — propagate, let caller fix prompt
            if "json" in error_str or "parse" in error_str:
                logger.warning(f"JSON parse error on attempt {attempt + 1}: {e}")
                if attempt == MAX_RETRIES - 1:
                    break
                await asyncio.sleep(BASE_DELAY)
                continue

            # Unknown error
            logger.error(f"Unexpected error on attempt {attempt + 1}: {e}")
            if attempt == MAX_RETRIES - 1:
                break
            await asyncio.sleep(BASE_DELAY * (attempt + 1))

    raise last_error
