"""Export results as CSV — one row per item."""
import csv
import os
from datetime import datetime, UTC
from app.config import OUTPUT_DIR


def export(result: dict, filename: str | None = None) -> str:
    """Flatten items to CSV rows. Arrays joined with '|'. Returns file path."""
    items = result.get("items", [])
    if not items:
        return ""

    if not filename:
        ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        filename = f"result_{ts}.csv"

    path = os.path.join(OUTPUT_DIR, "results", filename)

    # Collect all keys across all items
    all_keys: list[str] = []
    seen: set[str] = set()
    for item in items:
        for k in item.keys():
            if k not in seen:
                all_keys.append(k)
                seen.add(k)

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=all_keys, extrasaction="ignore")
        writer.writeheader()
        for item in items:
            row = {}
            for k, v in item.items():
                if isinstance(v, list):
                    row[k] = "|".join(str(x) for x in v)
                else:
                    row[k] = v
            writer.writerow(row)

    return path
