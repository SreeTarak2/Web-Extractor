# Interactive Batch Chat UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace 2-tab UI with a prompt box + chat-style results area where user controls batch-by-batch scraping with Continue/Stop buttons.

**Architecture:** Single prompt box at bottom, chat message area above with batch cards, Continue/Stop controls per batch. Backend processes one batch at a time, returns control to frontend.

**Tech Stack:** FastAPI (backend), Vanilla JS + HTML (frontend), WebSocket (real-time)

---

## File Structure After Changes

```
app/
├── main.py              (MODIFY) - Add batch API endpoints
static/
├── app.js              (MODIFY) - Chat UI, batch controls, prompt box
├── style.css           (MODIFY) - Chat styling
└── components/
    └── ai-prompt-box.tsx (NEW) - Prompt input component
app/templates/
└── index.html          (MODIFY) - Layout with chat area + prompt box
```

---

## Task 1: Create Prompt Box Component

**Files:**
- Create: `static/components/ai-prompt-box.tsx`
- Modify: `static/style.css` (add styles)
- Test: N/A (static component)

- [ ] **Step 1: Create the prompt box component**

```typescript
// static/components/ai-prompt-box.tsx
// Copy the PromptInputBox component from the prompt
// But we'll keep it as vanilla JS for simplicity instead of React
```

Since this is a vanilla JS project, create a simpler HTML-based version:

- [ ] **Step 2: Create HTML prompt box structure**

```html
<!-- In index.html - replace current input area -->
<div id="prompt-box" class="prompt-box">
  <div class="prompt-options">
    <select id="schema-select">
      <option value="contest">Contest</option>
      <option value="conference">Conference</option>
    </select>
    <input type="number" id="batch-size" value="5" min="1" max="50" placeholder="Batch size">
    <label class="file-upload">
      <input type="file" id="json-upload" accept=".json">
      📎 Upload JSON
    </label>
  </div>
  <div class="prompt-input-row">
    <input type="text" id="prompt-input" placeholder="Enter URL or paste JSON content...">
    <button id="send-btn">Send</button>
  </div>
</div>
```

- [ ] **Step 3: Add CSS for prompt box**

```css
.prompt-box {
  background: #1F2023;
  border: 1px solid #444;
  border-radius: 16px;
  padding: 12px;
  margin: 16px;
}

.prompt-options {
  display: flex;
  gap: 12px;
  margin-bottom: 12px;
}

.prompt-input-row {
  display: flex;
  gap: 8px;
}

#prompt-input {
  flex: 1;
  background: transparent;
  border: none;
  color: #fff;
  padding: 12px;
  font-size: 14px;
}

#send-btn {
  background: white;
  color: black;
  border: none;
  padding: 8px 16px;
  border-radius: 20px;
  cursor: pointer;
}
```

- [ ] **Step 4: Commit**

```bash
git add static/components/ai-prompt-box.tsx static/style.css app/templates/index.html
git commit -m "feat: add prompt box component with schema and batch options"
```

---

## Task 2: Create Chat Message System

**Files:**
- Modify: `static/app.js`
- Modify: `static/style.css`

- [ ] **Step 1: Add chat message HTML structure**

```html
<!-- In index.html - above prompt box -->
<div id="chat-area" class="chat-area">
  <!-- Messages will be inserted here -->
  <div class="chat-empty">Enter a URL to start scraping...</div>
</div>
```

- [ ] **Step 2: Add CSS for chat area**

```css
.chat-area {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.chat-message {
  background: #1F2023;
  border: 1px solid #333;
  border-radius: 12px;
  padding: 16px;
}

.chat-message.system {
  border-color: #9b87f5;
}

.chat-message.user {
  border-color: #444;
}

.message-header {
  font-size: 12px;
  color: #9CA3AF;
  margin-bottom: 12px;
}

.cards-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 12px;
  margin: 12px 0;
}

.result-card {
  background: #2E3033;
  border-radius: 8px;
  padding: 12px;
  cursor: pointer;
}

.result-card img {
  width: 100%;
  height: 120px;
  object-fit: cover;
  border-radius: 4px;
}

.batch-controls {
  display: flex;
  gap: 8px;
  margin-top: 12px;
}

.continue-btn {
  background: #22c55e;
  color: white;
  border: none;
  padding: 8px 16px;
  border-radius: 6px;
  cursor: pointer;
}

.stop-btn {
  background: #ef4444;
  color: white;
  border: none;
  padding: 8px 16px;
  border-radius: 6px;
  cursor: pointer;
}
```

- [ ] **Step 3: Add JS functions for chat messages**

```javascript
// In static/app.js

function addUserMessage(text) {
  const chat = document.getElementById("chat-area");
  const empty = chat.querySelector(".chat-empty");
  if (empty) empty.remove();
  
  const msg = document.createElement("div");
  msg.className = "chat-message user";
  msg.innerHTML = `
    <div class="message-header">You</div>
    <div class="message-content">${text}</div>
  `;
  chat.appendChild(msg);
  chat.scrollTop = chat.scrollHeight;
}

function addSystemMessage(title, items, batchNum, isComplete = false) {
  const chat = document.getElementById("chat-area");
  
  const msg = document.createElement("div");
  msg.className = "chat-message system";
  msg.dataset.batch = batchNum;
  
  const cardsHtml = items.map(item => `
    <div class="result-card" onclick="showItemDetail('${item.title || 'Item'}')">
      <img src="${item.image?.primary?.url || ''}" alt="">
      <div class="card-title">${item.title || 'Untitled'}</div>
      <div class="card-meta">${item.timeline?.submissionDeadlineUTC || ''}</div>
    </div>
  `).join('');
  
  const controlsHtml = !isComplete ? `
    <div class="batch-controls">
      <button class="continue-btn" onclick="continueBatch(${batchNum})">Continue</button>
      <button class="stop-btn" onclick="stopBatch(${batchNum})">Stop</button>
    </div>
  ` : '<div class="batch-complete">✅ Complete</div>';
  
  msg.innerHTML = `
    <div class="message-header">🤖 Batch ${batchNum} - ${title}</div>
    <div class="cards-grid">${cardsHtml}</div>
    ${controlsHtml}
  `;
  
  chat.appendChild(msg);
  chat.scrollTop = chat.scrollHeight;
}

function showItemDetail(title) {
  // Show detail modal
}
```

- [ ] **Step 4: Commit**

```bash
git add static/app.js static/style.css app/templates/index.html
git commit -m "feat: add chat message system with cards and batch controls"
```

---

## Task 3: Add Backend Batch API Endpoints

**Files:**
- Modify: `app/main.py`

- [ ] **Step 1: Add batch state management**

```python
# In app/main.py - add global state
batch_state = {
    "current_url": None,
    "batch_size": 5,
    "scraped_count": 0,
    "remaining_urls": [],
    "results": [],
    "is_active": False,
}
```

- [ ] **Step 2: Add batch scrape endpoint**

```python
class BatchScrapeRequest(BaseModel):
    url: str
    content_format: str  # "contest" or "conference"
    batch_size: int = 5

@app.post("/api/batch/start")
async def batch_start(req: BatchScrapeRequest):
    """Start batch scraping - process first batch and return control to user"""
    global batch_state
    
    # Reset state
    batch_state = {
        "current_url": req.url,
        "batch_size": req.batch_size,
        "scraped_count": 0,
        "remaining_urls": [req.url],  # Will be populated by orchestrator
        "results": [],
        "is_active": True,
        "content_format": req.content_format,
    }
    
    # This will be handled by orchestrate returning after one batch
    # For now, we'll modify the orchestrator
    
    return {"status": "started", "message": "Batch 1 started"}

@app.post("/api/batch/continue")
async def batch_continue():
    """Continue with next batch"""
    global batch_state
    if not batch_state.get("is_active"):
        return {"status": "inactive", "message": "No active batch"}
    
    # Return signal to continue - frontend will call scrape again
    return {"status": "continue", "batch_size": batch_state["batch_size"]}

@app.post("/api/batch/stop")
async def batch_stop():
    """Stop the batch process"""
    global batch_state
    batch_state["is_active"] = False
    return {"status": "stopped", "results": batch_state["results"]}

@app.get("/api/batch/status")
async def batch_status():
    """Get current batch status"""
    return batch_state
```

- [ ] **Step 3: Commit**

```bash
git add app/main.py
git commit -m "feat: add batch API endpoints for interactive scraping"
```

---

## Task 4: Integrate Frontend with Backend

**Files:**
- Modify: `static/app.js`

- [ ] **Step 1: Connect prompt input to batch API**

```javascript
// In static/app.js

let currentSchema = "contest";
let currentBatchSize = 5;
let currentBatchNum = 1;
let isBatchActive = false;

// Handle schema selection
document.getElementById("schema-select")?.addEventListener("change", (e) => {
  currentSchema = e.target.value;
});

// Handle batch size
document.getElementById("batch-size")?.addEventListener("change", (e) => {
  currentBatchSize = parseInt(e.target.value) || 5;
});

// Handle send button
document.getElementById("send-btn")?.addEventListener("click", handleSend);
document.getElementById("prompt-input")?.addEventListener("keypress", (e) => {
  if (e.key === "Enter") handleSend();
});

async function handleSend() {
  const input = document.getElementById("prompt-input");
  const url = input.value.trim();
  if (!url) return;
  
  // Add user message
  addUserMessage(url);
  input.value = "";
  
  // Start batch processing
  currentBatchNum = 1;
  isBatchActive = true;
  
  await processBatch(url, currentBatchNum);
}
```

- [ ] **Step 2: Add batch processing function**

```javascript
async function processBatch(url, batchNum) {
  try {
    const res = await fetch("/api/scrape", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        url: url,
        query: "extract all",
        content_format: currentSchema,
        batch_size: currentBatchSize,
        batch_num: batchNum
      })
    });
    
    const result = await res.json();
    
    if (result.items && result.items.length > 0) {
      // Show system message with cards
      addSystemMessage(
        `Scraped ${result.items.length} items`,
        result.items,
        batchNum,
        false  // Not complete - show Continue button
      );
    } else {
      addSystemMessage("No more items found", [], batchNum, true);
      isBatchActive = false;
    }
  } catch (e) {
    console.error("Batch error:", e);
    addSystemMessage(`Error: ${e.message}`, [], batchNum, true);
    isBatchActive = false;
  }
}

// Global functions for buttons
window.continueBatch = async function(batchNum) {
  await processBatch(currentUrl, batchNum + 1);
};

window.stopBatch = function(batchNum) {
  isBatchActive = false;
  // Show completion message
  addSystemMessage("Stopped by user", [], batchNum, true);
};
```

- [ ] **Step 3: Commit**

```bash
git add static/app.js
git commit -m "feat: integrate frontend with batch API for interactive scraping"
```

---

## Task 5: Modify Orchestrator for Batch Control

**Files:**
- Modify: `app/pipeline/orchestrator.py`

- [ ] **Step 1: Add batch control to orchestrate function**

```python
async def orchestrate(
    browser_manager: BrowserManager,
    url: str,
    query: str,
    content_format: str | None = None,
    progress_callback: ProgressCallback = None,
    batch_size: int = 5,  # NEW: limit items per batch
    batch_num: int = 1,   # NEW: which batch this is
) -> dict:
```

- [ ] **Step 2: Apply batch limit when extracting items**

```python
# In the detail page scraping loop:
limit = min(len(targets), MAX_PAGES_PER_SCRAPE)

# Add batch_size limit
if batch_size > 0:
    limit = min(limit, batch_size)
```

- [ ] **Step 3: Return metadata about batch status**

```python
return {
    "metadata": {...},
    "items": extracted_items,
    "batch_info": {
        "batch_num": batch_num,
        "batch_size": batch_size,
        "has_more": len(targets) > limit,  # Are there more URLs?
    },
    ...
}
```

- [ ] **Step 4: Commit**

```bash
git add app/pipeline/orchestrator.py
git commit -m "feat: add batch control to orchestrator for interactive mode"
```

---

## Task 6: Final Integration & Testing

**Files:**
- Modify: `app/main.py`
- Modify: `static/app.js`

- [ ] **Step 1: Update scrape endpoint to handle batch params**

```python
@app.post("/api/scrape")
async def scrape(req: ScrapeRequest):
    # Check for batch parameters
    batch_size = getattr(req, 'batch_size', 0)  # 0 = no limit (all)
    batch_num = getattr(req, 'batch_num', 1)
    
    result = await orchestrate(
        browser_manager=browser_manager,
        url=req.url,
        query=req.query,
        content_format=req.content_format,
        batch_size=batch_size,
        batch_num=batch_num,
    )
    return result
```

- [ ] **Step 2: Test the complete flow**

Test:
1. Enter URL in prompt box
2. Select "Contest" schema
3. Set batch size to 5
4. Click Send
5. Should see 5 cards in chat area
6. Click "Continue" → next 5 cards
7. Click "Stop" → stops

- [ ] **Step 3: Commit**

```bash
git add app/main.py static/app.js
git commit -m "feat: complete batch chat UI integration"
```

---

## Verification

- [ ] Test: URL input with schema selection works
- [ ] Test: Batch size can be changed (default 5)
- [ ] Test: JSON upload still works
- [ ] Test: Results show as cards in chat area
- [ ] Test: Continue button fetches next batch
- [ ] Test: Stop button ends the session
- [ ] Test: Progress updates shown in real-time