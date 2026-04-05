"""Load environment variables and define constants."""

import os
from dotenv import load_dotenv

load_dotenv()

# API — OpenRouter (OpenAI-compatible)
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
if not OPENROUTER_API_KEY:
    raise ValueError("OPENROUTER_API_KEY not set in .env file")

OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")

# Models (OpenRouter slugs)
MODEL_NAVIGATOR = os.getenv(
    "MODEL_NAVIGATOR", "mistralai/mistral-small-3.1-24b-instruct"
)
MODEL_EXTRACTOR = os.getenv(
    "MODEL_EXTRACTOR", "mistralai/mistral-small-3.1-24b-instruct"
)
MODEL_GENERATOR = os.getenv("MODEL_GENERATOR", "mistralai/mistral-medium-3")

# Model pricing (per 1M tokens)
MODEL_PRICING = {
    "mistralai/mistral-small-3.1-24b-instruct": {"input": 0.35, "output": 0.56},
    "mistralai/mistral-medium-3": {"input": 0.40, "output": 2.00},
}

# Browser
CHROMIUM_EXECUTABLE = os.getenv("CHROMIUM_EXECUTABLE", "/usr/bin/google-chrome-stable")
LIGHTPANDA_HOST = os.getenv("LIGHTPANDA_HOST", "127.0.0.1")
LIGHTPANDA_PORT = int(os.getenv("LIGHTPANDA_PORT", "9222"))
LIGHTPANDA_WS_URL = f"ws://{LIGHTPANDA_HOST}:{LIGHTPANDA_PORT}"

# Scraping limits
MAX_PAGES_PER_SCRAPE = int(os.getenv("MAX_PAGES_PER_SCRAPE", "50"))
MAX_DEPTH = int(os.getenv("MAX_DEPTH", "2"))
DEFAULT_TIMEOUT_MS = int(os.getenv("DEFAULT_TIMEOUT_MS", "15000"))
MAX_HTML_CHARS = 50_000  # For navigation/analysis calls
MAX_HTML_CHARS_EXTRACT = 80_000  # For extraction calls (higher budget)
MAX_RETRIES = 3

# Output directories
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "output")
os.makedirs(os.path.join(OUTPUT_DIR, "results"), exist_ok=True)
os.makedirs(os.path.join(OUTPUT_DIR, "content"), exist_ok=True)
os.makedirs(os.path.join(OUTPUT_DIR, "cache"), exist_ok=True)
