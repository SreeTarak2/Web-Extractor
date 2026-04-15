"""
V2 Scraper runtime configuration.
All values are tunable via environment variables.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ─── LLM API ──────────────────────────────────────────────────────────────────
OPENROUTER_API_KEY  = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")

# V2 uses stronger models for better extraction quality
# qwen/qwen3-30b-a3b offers excellent quality at low cost on OpenRouter
MODEL_NORMALIZE = os.getenv("V2_MODEL_NORMALIZE", "qwen/qwen3-30b-a3b")
MODEL_FALLBACK  = os.getenv("V2_MODEL_FALLBACK",  "qwen/qwen3-14b")

# ─── HTTP FETCHING ────────────────────────────────────────────────────────────
FETCH_TIMEOUT_S       = int(os.getenv("V2_FETCH_TIMEOUT",      "30"))
PLAYWRIGHT_TIMEOUT_MS = int(os.getenv("V2_PLAYWRIGHT_TIMEOUT", "30000"))
USE_PLAYWRIGHT        = os.getenv("V2_USE_PLAYWRIGHT", "true").lower() == "true"

# ─── CONTENT LIMITS ───────────────────────────────────────────────────────────
MAX_MARKDOWN_CHARS = int(os.getenv("V2_MAX_MARKDOWN_CHARS", "80000"))
MAX_FOLLOW_LINKS   = int(os.getenv("V2_MAX_FOLLOW_LINKS",   "3"))

# ─── LLM TUNING ───────────────────────────────────────────────────────────────
LLM_TEMPERATURE = 0.0
LLM_MAX_TOKENS  = 3000
LLM_MAX_RETRIES = 3
LLM_RETRY_DELAY = 2  # seconds; multiplied by attempt number
