# Rate Limiting, Caching & Batch Output Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add concurrency control to prevent OpenRouter rate limiting, implement persistent URL caching to avoid re-scraping, and add batch progress output every 5 URLs.

**Architecture:** 
- Semaphore for LLM call limiting
- JSON file cache keyed by URL+query hash
- Batch counter in orchestrator with callback + file output

**Tech Stack:** asyncio.Semaphore, JSON files, existing progress_callback

---

## File Structure

```
app/
├── cache/
│   └── url_cache.py      (NEW) - URL + fields caching with file persistence
├── llm/
│   ├── semaphore.py       (NEW) - Concurrency control semaphore
│   ├── analyzer.py       (MODIFY) - Add semaphore wrapper
│   ├── navigator.py      (MODIFY) - Add semaphore wrapper
│   ├── extractor.py     (MODIFY) - Add semaphore wrapper
│   ├── generator.py     (MODIFY) - Add semaphore wrapper
│   ├── normalizer.py    (MODIFY) - Add semaphore wrapper
│   └── peeker.py        (MODIFY) - Add semaphore wrapper
└── pipeline/
    └── orchestrator.py  (MODIFY) - Cache check + batch output
```

```
output/
├── cache/                (NEW) - JSON cache files
└── results/
    └── batch_*.json     (NEW) - Batch output files
```

---

## Task 1: Create LLM Semaphore

**Files:**
- Create: `app/llm/semaphore.py`

- [ ] **Step 1: Create semaphore module**

```python
"""LLM concurrency control - prevents rate limiting from too many parallel calls."""
import asyncio

llm_semaphore = asyncio.Semaphore(2)
```

- [ ] **Step 2: Commit**

```bash
git add app/llm/semaphore.py
git commit -m "feat: add LLM semaphore for rate limit prevention"
```

---

## Task 2: Wrap LLM Calls with Semaphore

**Files:**
- Modify: `app/llm/analyzer.py:1-60`
- Modify: `app/llm/navigator.py:1-60`
- Modify: `app/llm/extractor.py:1-80`
- Modify: `app/llm/generator.py:1-85`
- Modify: `app/llm/normalizer.py:1-70`
- Modify: `app/llm/peeker.py:1-60`

- [ ] **Step 1: Modify analyzer.py**

```python
# Add import at top
from app.llm.semaphore import llm_semaphore

# Wrap the call_with_retry call (around line 51)
async def analyze_page(html: str, requested_fields: list[str], cost_tracker) -> dict:
    # ... existing code ...
    async with llm_semaphore:
        response = await call_with_retry(_call)
    # ... rest of code ...
```

- [ ] **Step 2: Modify navigator.py**

```python
# Add import at top
from app.llm.semaphore import llm_semaphore

# Wrap the call_with_retry call (around line 51)
async with llm_semaphore:
    response = await call_with_retry(_call)
```

- [ ] **Step 3: Modify extractor.py**

```python
# Add import at top
from app.llm.semaphore import llm_semaphore

# Wrap the call_with_retry call (around line 61)
async with llm_semaphore:
    response = await call_with_retry(_call)
```

- [ ] **Step 4: Modify generator.py**

```python
# Add import at top
from app.llm.semaphore import llm_semaphore

# Wrap the call_with_retry call (around line 75)
async with llm_semaphore:
    response = await call_with_retry(_call)
```

- [ ] **Step 5: Modify normalizer.py**

```python
# Add import at top
from app.llm.semaphore import llm_semaphore

# Wrap the call_with_retry call (around line 61)
async with llm_semaphore:
    response = await call_with_retry(_call)
```

- [ ] **Step 6: Modify peeker.py**

```python
# Add import at top
from app.llm.semaphore import llm_semaphore

# Wrap the call_with_retry call (around line 49)
async with llm_semaphore:
    response = await call_with_retry(_call)
```

- [ ] **Step 7: Commit**

```bash
git add app/llm/analyzer.py app/llm/navigator.py app/llm/extractor.py app/llm/generator.py app/llm/normalizer.py app/llm/peeker.py
git commit -m "feat: wrap all LLM calls with semaphore for rate limiting"
```

---

## Task 3: Create URL Cache Module

**Files:**
- Create: `app/cache/url_cache.py`

- [ ] **Step 1: Create cache module**

```python
"""URL caching - avoids re-scraping same URLs with same query fields."""
import hashlib
import json
import os
from pathlib import Path
from typing import Any

CACHE_DIR = Path(__file__).parent.parent.parent / "output" / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

def _make_key(url: str, fields: list[str]) -> str:
    """Create cache key from URL and fields."""
    combined = f"{url}:{','.join(sorted(fields))}"
    return hashlib.sha256(combined.encode()).hexdigest()[:16]

def get(url: str, fields: list[str]) -> dict | None:
    """Get cached result for URL + fields. Returns None if not cached."""
    key = _make_key(url, fields)
    cache_file = CACHE_DIR / f"{key}.json"
    if cache_file.exists():
        try:
            with open(cache_file) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return None
    return None

def set(url: str, fields: list[str], result: dict) -> None:
    """Save result to cache for URL + fields."""
    key = _make_key(url, fields)
    cache_file = CACHE_DIR / f"{key}.json"
    data = {
        "url": url,
        "fields": fields,
        "result": result,
        "cached_at": __import__("datetime").datetime.now().isoformat(),
    }
    with open(cache_file, "w") as f:
        json.dump(data, f, indent=2)
```

- [ ] **Step 2: Commit**

```bash
git add app/cache/url_cache.py
git commit -m "feat: add URL cache module for persistent caching"
```

---

## Task 4: Integrate Cache in Orchestrator

**Files:**
- Modify: `app/pipeline/orchestrator.py:1-70`

- [ ] **Step 1: Add import at top of orchestrator.py**

```python
from app.cache.url_cache import get as cache_get, set as cache_set
```

- [ ] **Step 2: Modify orchestrate function to check cache before scraping**

After line 52 (parse query) and before line 57 (fetch start page), add:

```python
    # ── 0. Check cache for URL + fields ────────────────────────────────────────
    cache_key_fields = requested_fields
    cached_result = cache_get(url, cache_key_fields)
    if cached_result:
        logger.info(f"Cache hit for {url}")
        await cb(f"Cached: {url}")
        result_data = cached_result.get("result", {})
        return {
            "metadata": {
                "url": url,
                "query": query,
                "from_cache": True,
                "scraped_at": cached_result.get("cached_at", ""),
            },
            "items": result_data.get("items", []),
            "generated_content": result_data.get("generated_content"),
            "cost": result_data.get("cost", {}),
            "pages_visited": result_data.get("pages_visited", []),
            "pages_failed": result_data.get("pages_failed", []),
        }
```

- [ ] **Step 3: Save to cache at end of orchestrate**

Before the return statement at end of function (around line 220), add:

```python
    # ── Save to cache ─────────────────────────────────────────────────────────
    cache_set(url, cache_key_fields, {
        "items": extracted_items,
        "generated_content": generated_content,
        "cost": cost_tracker.get_summary(),
        "pages_visited": pages_visited,
        "pages_failed": pages_failed,
    })
```

- [ ] **Step 4: Commit**

```bash
git add app/pipeline/orchestrator.py
git commit -m "feat: integrate URL cache in orchestrator"
```

---

## Task 5: Add Batch Output Logic

**Files:**
- Modify: `app/pipeline/orchestrator.py:100-150`

- [ ] **Step 1: Add batch counter variables**

After line 47 (pages_visited declaration), add:

```python
    batch_count = 0
    batch_items = []
```

- [ ] **Step 2: After each URL completes, send callback**

In the detail page loop (around line 147), after `extracted_items.append(item)`, add:

```python
                extracted_items.append(item)
                await cb(f"Completed: {target_url}")
                
                # Batch output every 5 URLs
                batch_items.append(item)
                if len(batch_items) >= 5:
                    batch_count += 1
                    batch_file = os.path.join(OUTPUT_DIR, "results", f"batch_{batch_count}.json")
                    with open(batch_file, "w") as f:
                        json.dump({
                            "batch": batch_count,
                            "items": batch_items,
                            "urls": pages_visited[-5:],
                        }, f, indent=2)
                    await cb(f"Batch {batch_count} complete: {len(batch_items)} URLs")
                    batch_items = []
```

- [ ] **Step 3: Handle remaining batch items at end**

Before the cache save (Task 4, Step 3), add:

```python
    # Flush remaining batch
    if batch_items:
        batch_count += 1
        batch_file = os.path.join(OUTPUT_DIR, "results", f"batch_{batch_count}.json")
        with open(batch_file, "w") as f:
            json.dump({
                "batch": batch_count,
                "items": batch_items,
                "urls": [],
            }, f, indent=2)
        await cb(f"Final batch complete: {len(batch_items)} URLs")
```

- [ ] **Step 4: Add json import if not present**

Check top of orchestrator.py - if `import json` not present, add it.

- [ ] **Step 5: Commit**

```bash
git add app/pipeline/orchestrator.py
git commit -m "feat: add batch output every 5 URLs with callbacks and files"
```

---

## Task 6: Create cache directory on startup

**Files:**
- Modify: `app/config.py:40-50`

- [ ] **Step 1: Add cache directory creation in config.py**

After line 45-46 (output dirs), add:

```python
os.makedirs(os.path.join(OUTPUT_DIR, "cache"), exist_ok=True)
```

- [ ] **Step 2: Commit**

```bash
git add app/config.py
git commit -m "feat: create cache directory on startup"
```

---

## Verification

- [ ] Run the app with a few URLs and verify:
  1. No 429 rate limit errors appear
  2. Re-scraping same URL returns cached result (check log for "Cache hit")
  3. Every 5 URLs shows batch callback
  4. batch_X.json files appear in output/results/
  5. Completed: {url} callback fires for each URL