# Rate Limiting, Caching & Batch Output Design

Date: 2026-04-05

## Problem Statement

1. **Rate limiting**: OpenRouter API returns 429 errors due to too many concurrent LLM requests
2. **No caching**: Re-scraping same URLs wastes API credits and time
3. **No progress visibility**: User wants batch output every 5 URLs and completion notification

---

## Solution

### 1. Rate Limiting Fix: Semaphore

Add `asyncio.Semaphore(2)` to limit concurrent LLM calls.

**Implementation**:
- Create `app/llm/semaphore.py` with module-level semaphore
- Wrap all LLM calls with `async with llm_semaphore:`

**Files modified**:
- `app/llm/semaphore.py` (new)
- All LLM modules (`analyzer.py`, `navigator.py`, `extractor.py`, `generator.py`, `normalizer.py`, `peeker.py`)

---

### 2. URL Caching: Persistent JSON Files

Cache scraped URLs to avoid re-scraping.

**Cache key**: URL + query fields (hash of both)
**Storage**: `output/cache/<hash>.json`
**Data stored**: URL, query fields, extracted result, timestamp

**Flow**:
1. Before scraping, check `cache.get(url, fields)`
2. If cached, return cached result
3. If not cached, scrape → save to cache → return result

**Files**:
- `app/cache/url_cache.py` (new) - get/set methods
- `app/pipeline/orchestrator.py` - integrate cache check

---

### 3. Batch Output: Every 5 URLs

Send progress callback after every 5 URLs AND when URL completes.

**Callbacks**:
- `progress_callback(f"Completed: {url}")` - after each URL
- `progress_callback(f"Batch 1 complete: 5 URLs scraped")` - every 5 URLs

**File output**:
- Write batch to `output/results/batch_<n>.json`
- Final results still in `output/results/<query>.json`

**Files modified**:
- `app/pipeline/orchestrator.py` - add batch logic

---

## File Structure After Changes

```
app/
├── cache/
│   └── url_cache.py      (NEW)
├── llm/
│   ├── semaphore.py      (NEW)
│   ├── analyzer.py
│   ├── navigator.py
│   ├── extractor.py
│   ├── generator.py
│   ├── normalizer.py
│   └── peeker.py
└── pipeline/
    └── orchestrator.py  (modified)
output/
├── cache/                (NEW - JSON cache files)
├── results/
│   └── batch_*.json     (NEW - batch outputs)
```

---

## Implementation Order

1. Create `app/llm/semaphore.py`
2. Modify LLM modules to use semaphore
3. Create `app/cache/url_cache.py`
4. Modify orchestrator to check cache before scraping
5. Add batch output logic to orchestrator
6. Test with sample URLs