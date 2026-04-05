"""LLM concurrency control - prevents rate limiting from too many parallel calls."""

import asyncio

llm_semaphore = asyncio.Semaphore(2)
