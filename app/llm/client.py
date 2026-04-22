"""OpenRouter async client singleton (OpenAI-compatible)."""
from openai import AsyncOpenAI
from app.config import OPENROUTER_API_KEY, OPENROUTER_BASE_URL

_client: AsyncOpenAI | None = None


def get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            api_key=OPENROUTER_API_KEY,
            base_url=OPENROUTER_BASE_URL,
        )
    return _client
