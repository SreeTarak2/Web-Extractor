"""Export results as JSON."""
import json
import os
from datetime import datetime, UTC
from app.config import OUTPUT_DIR


def export(result: dict, filename: str | None = None) -> str:
    """Save result dict as a JSON file. Returns the file path."""
    if not filename:
        ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        filename = f"result_{ts}.json"

    path = os.path.join(OUTPUT_DIR, "results", filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    return path
