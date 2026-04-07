let currentResult = null;
let ws = null;
let progressStep = 0;
let uploadedItems = null;

// ── Tab switching ────────────────────────────────────────────────────────────
function switchTab(tab) {
  document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
  document.querySelectorAll(".tab-btn")[tab === "scrape" ? 0 : 1].classList.add("active");
  document.getElementById("tab-scrape").classList.toggle("hidden", tab !== "scrape");
  document.getElementById("tab-upload").classList.toggle("hidden", tab !== "upload");
}

// ── File upload ──────────────────────────────────────────────────────────────
function onFileSelected(input) {
  const file = input.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = e => {
    try {
      let data = JSON.parse(e.target.result);
      // Normalise to array
      if (!Array.isArray(data)) data = data.items ? data.items : [data];
      uploadedItems = data;
      showUploadPreview(file.name, data);
      document.getElementById("upload-btn").disabled = false;
    } catch {
      alert("Invalid JSON file.");
      uploadedItems = null;
    }
  };
  reader.readAsText(file);
}

function showUploadPreview(filename, items) {
  // Collect all unique keys across items
  const allKeys = [...new Set(items.flatMap(Object.keys))];
  const filled = k => items.filter(i => i[k] != null && i[k] !== "").length;

  document.getElementById("upload-summary").innerHTML =
    `<span class="page-type-badge">JSON</span> <strong>${filename}</strong> — ${items.length} item${items.length !== 1 ? "s" : ""}, ${allKeys.length} fields detected`;

  const wrap = document.getElementById("upload-fields");
  wrap.innerHTML = "";
  for (const k of allKeys) {
    const chip = document.createElement("span");
    const pct = Math.round((filled(k) / items.length) * 100);
    chip.className = "field-chip selected";
    chip.title = `${filled(k)}/${items.length} items have this field`;
    chip.textContent = `${k} (${pct}%)`;
    wrap.appendChild(chip);
  }

  document.getElementById("upload-preview").classList.remove("hidden");
  document.getElementById("drop-zone-label").textContent = filename;
}

// Drag and drop
document.addEventListener("DOMContentLoaded", () => {
  const dz = document.getElementById("drop-zone");
  if (!dz) return;
  dz.addEventListener("dragover", e => { e.preventDefault(); dz.classList.add("drag-over"); });
  dz.addEventListener("dragleave", () => dz.classList.remove("drag-over"));
  dz.addEventListener("drop", e => {
    e.preventDefault();
    dz.classList.remove("drag-over");
    const file = e.dataTransfer.files[0];
    if (file) {
      const input = document.getElementById("json-file");
      const dt = new DataTransfer();
      dt.items.add(file);
      input.files = dt.files;
      onFileSelected(input);
    }
  });
});

async function startUpload() {
  if (!uploadedItems) return;
  const schema = document.getElementById("upload-schema").value;
  const enrich = document.getElementById("enrich-urls").checked;
  const file = document.getElementById("json-file").files[0];

  resetResultsUI();
  show("progress-section");
  document.getElementById("upload-btn").disabled = true;
  addLog(`Normalizing ${uploadedItems.length} items to ${schema} schema...`);
  if (enrich) addLog("URL enrichment enabled — will re-scrape each item URL");

  const formData = new FormData();
  formData.append("file", file);
  formData.append("schema", schema);
  formData.append("enrich", enrich ? "true" : "false");

  try {
    const res = await fetch("/api/normalize-upload", { method: "POST", body: formData });
    if (!res.ok) {
      const text = await res.text();
      addLog("Server error: " + text);
      document.getElementById("upload-btn").disabled = false;
      return;
    }
    const data = await res.json();
    if (data.error) {
      addLog("Error: " + data.error);
    } else {
      addLog(`Done — ${data.items?.length ?? 0} items normalized in ${data.metadata?.duration_seconds}s`);
      handleResult(data);
    }
  } catch (e) {
    addLog("Request failed: " + e.message);
  }
  document.getElementById("upload-btn").disabled = false;
}

async function previewUrl() {
  const url = document.getElementById("url").value.trim();
  if (!url) return;

  const btn = document.getElementById("preview-btn");
  btn.disabled = true;
  btn.textContent = "Detecting...";
  hide("preview-section");

  try {
    const res = await fetch("/api/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });
    const data = await res.json();

    if (data.error) {
      document.getElementById("preview-summary").textContent = "Error: " + data.error;
      show("preview-section");
      return;
    }

    // Summary line
    const pageType = data.page_type ?? "page";
    const summary = data.summary ?? "";
    document.getElementById("preview-summary").innerHTML =
      `<span class="page-type-badge">${pageType}</span> ${summary}`;

    // Field chips
    const chips = document.getElementById("field-chips");
    chips.innerHTML = "";
    const fields = (data.available_fields ?? []).filter(f => f !== "source_url");
    for (const field of fields) {
      const chip = document.createElement("span");
      chip.className = "field-chip";
      chip.textContent = field;
      chip.onclick = () => toggleField(chip, field);
      chips.appendChild(chip);
    }

    // Auto-fill query with suggestion if query is empty
    const queryEl = document.getElementById("query");
    if (!queryEl.value.trim() && data.suggested_query) {
      queryEl.value = data.suggested_query;
      // Mark those chips as selected
      for (const chip of chips.children) {
        if (data.suggested_query.includes(chip.textContent)) {
          chip.classList.add("selected");
        }
      }
    }

    show("preview-section");
  } catch (e) {
    console.error(e);
  } finally {
    btn.disabled = false;
    btn.textContent = "Detect";
  }
}

function toggleField(chip, field) {
  const queryEl = document.getElementById("query");
  const current = queryEl.value.trim();
  const fields = current ? current.split(",").map(f => f.trim()).filter(Boolean) : [];
  const idx = fields.indexOf(field);

  if (idx === -1) {
    fields.push(field);
    chip.classList.add("selected");
  } else {
    fields.splice(idx, 1);
    chip.classList.remove("selected");
  }
  queryEl.value = fields.join(", ");
}

function show(id) {
  document.getElementById(id).classList.remove("hidden");
}

function hide(id) {
  document.getElementById(id).classList.add("hidden");
}

function addLog(msg) {
  const log = document.getElementById("progress-log");
  const li = document.createElement("li");
  li.textContent = msg;
  log.appendChild(li);
  log.scrollTop = log.scrollHeight;

  progressStep = Math.min(progressStep + 8, 90);
  document.getElementById("progress-bar").style.width = progressStep + "%";
}

function resetResultsUI() {
  currentResult = null;
  progressStep = 0;
  document.getElementById("progress-log").innerHTML = "";
  document.getElementById("progress-bar").style.width = "0%";
  document.getElementById("results-json").textContent = "";
  document.getElementById("results-header-extra").innerHTML = "";
  hide("results-section");
  hide("content-section");
  hide("cost-section");
}

function startScrape() {
  const url = document.getElementById("url").value.trim();
  const query = document.getElementById("query").value.trim();
  const contentFormat = document.getElementById("content-format").value;

  if (!url || !query) {
    alert("Please enter a URL and a query.");
    return;
  }

  resetResultsUI();
  show("progress-section");

  const btn = document.getElementById("scrape-btn");
  btn.disabled = true;
  btn.textContent = "Scraping...";

  if (ws) ws.close();

  const protocol = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${protocol}://${location.host}/ws/scrape`);

  ws.onopen = () => {
    ws.send(JSON.stringify({ url, query, content_format: contentFormat || null }));
    addLog(`Connecting to ${url}...`);
  };

  ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    if (msg.type === "progress") {
      addLog(msg.message);
    } else if (msg.type === "result") {
      handleResult(msg.data);
    } else if (msg.type === "error") {
      addLog("Error: " + msg.message);
      finishScrape();
    }
  };

  ws.onerror = () => {
    addLog("WebSocket connection error.");
    finishScrape();
  };

  ws.onclose = () => {
    finishScrape();
  };
}

function handleResult(data) {
  currentResult = data;

  document.getElementById("progress-bar").style.width = "100%";
  addLog(`Done — ${data.items?.length ?? 0} items extracted`);

  // Results
  const items = data.items ?? [];
  // Schema mode: from scrape dropdown OR from upload schema selector OR from metadata
  const scrapeFormat = document.getElementById("content-format").value;
  const uploadSchema = document.getElementById("upload-schema")?.value;
  const metaSchema = data.metadata?.schema;
  const format = metaSchema || scrapeFormat || uploadSchema || "";
  const isSchema = format === "contest" || format === "conference";
  const label = isSchema
    ? `(${items.length} normalized)`
    : items.length ? `(${items.length} items)` : "";
  document.getElementById("item-count").textContent = label;

  if (isSchema && items.length) {
    // Show schema badge + pretty JSON
    const badge = `<span class="schema-badge">${format.toUpperCase()} SCHEMA v2.0</span>`;
    document.getElementById("results-header-extra").innerHTML = badge;
  } else {
    document.getElementById("results-header-extra").innerHTML = "";
  }

  document.getElementById("results-json").textContent =
    JSON.stringify(items, null, 2);
  show("results-section");

  // Generated content (non-schema modes)
  if (data.generated_content) {
    document.getElementById("generated-content").textContent = data.generated_content;
    show("content-section");
  }

  // Cost
  const cost = data.cost ?? {};
  renderCost(cost);
  show("cost-section");

  finishScrape();
}

function renderCost(cost) {
  const breakdown = cost.breakdown ?? {};
  const total = cost.total_usd ?? 0;
  const div = document.getElementById("cost-breakdown");
  div.innerHTML = "";

  for (const [model, info] of Object.entries(breakdown)) {
    const row = document.createElement("div");
    row.className = "cost-row";
    row.innerHTML = `
      <span>${model}</span>
      <span>${info.calls} calls &nbsp;|&nbsp; ${info.input_tokens} in / ${info.output_tokens} out &nbsp;|&nbsp; $${info.cost_usd.toFixed(6)}</span>
    `;
    div.appendChild(row);
  }

  const totalRow = document.createElement("div");
  totalRow.className = "cost-row cost-total";
  totalRow.innerHTML = `<span>Total</span><span>$${total.toFixed(6)}</span>`;
  div.appendChild(totalRow);
}

function finishScrape() {
  const btn = document.getElementById("scrape-btn");
  btn.disabled = false;
  btn.textContent = "Scrape";
}

function exportAs(format) {
  if (!currentResult) return;
  const items = currentResult.items ?? [];

  if (format === "json") {
    downloadFile(
      JSON.stringify(currentResult, null, 2),
      "webmind-result.json",
      "application/json"
    );
  } else if (format === "csv") {
    if (!items.length) return;
    const keys = [...new Set(items.flatMap(Object.keys))];
    const rows = [keys.join(",")];
    for (const item of items) {
      rows.push(
        keys.map(k => {
          const v = item[k];
          const str = Array.isArray(v) ? v.join("|") : String(v ?? "");
          return `"${str.replace(/"/g, '""')}"`;
        }).join(",")
      );
    }
    downloadFile(rows.join("\n"), "webmind-result.csv", "text/csv");
  }
}

function downloadFile(content, filename, mime) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([content], { type: mime }));
  a.download = filename;
  a.click();
}

function copyToClipboard() {
  const text = document.getElementById("results-json").textContent;
  navigator.clipboard.writeText(text).then(() => {
    const btn = event.target;
    btn.textContent = "Copied!";
    setTimeout(() => (btn.textContent = "Copy"), 1500);
  });
}

// ── Chat UI Functions ────────────────────────────────────────────────────────────

let currentSchema = "contest";
let currentBatchSize = 5;
let currentBatchNum = 1;
let isBatchActive = false;
let currentUrl = "";
let allResults = [];

// Initialize chat UI
document.addEventListener("DOMContentLoaded", () => {
  // Schema selector
  const schemaSelect = document.getElementById("schema-select");
  if (schemaSelect) {
    schemaSelect.addEventListener("change", (e) => {
      currentSchema = e.target.value;
    });
  }

  // Batch size
  const batchSizeInput = document.getElementById("batch-size");
  if (batchSizeInput) {
    batchSizeInput.addEventListener("change", (e) => {
      currentBatchSize = parseInt(e.target.value) || 5;
    });
  }

  // Send button
  const sendBtn = document.getElementById("send-btn");
  if (sendBtn) {
    sendBtn.addEventListener("click", handleSend);
  }

  // Enter key in input
  const promptInput = document.getElementById("prompt-input");
  if (promptInput) {
    promptInput.addEventListener("keypress", (e) => {
      if (e.key === "Enter") handleSend();
    });
  }

  // JSON upload
  const jsonUpload = document.getElementById("json-upload");
  if (jsonUpload) {
    jsonUpload.addEventListener("change", handleJsonUpload);
  }
});

async function handleSend() {
  const input = document.getElementById("prompt-input");
  const url = input.value.trim();
  if (!url) return;

  // Add user message
  addUserMessage(url);
  input.value = "";

  // Start batch processing
  currentUrl = url;
  currentBatchNum = 1;
  isBatchActive = true;
  allResults = [];

  await processBatch(url, currentBatchNum);
}

async function handleJsonUpload(e) {
  const file = e.target.files[0];
  if (!file) return;

  const reader = new FileReader();
  reader.onload = async (event) => {
    try {
      let data = JSON.parse(event.target.result);
      if (!Array.isArray(data)) data = data.items ? data.items : [data];

      addUserMessage(`📄 Uploaded JSON: ${file.name} (${data.length} items)`);

      // Process in batches
      currentBatchNum = 1;
      isBatchActive = true;

      for (let i = 0; i < data.length; i += currentBatchSize) {
        const batch = data.slice(i, i + currentBatchSize);
        addSystemMessage(
          `Batch ${currentBatchNum} - ${batch.length} items`,
          batch,
          currentBatchNum,
          i + currentBatchSize >= data.length
        );
        currentBatchNum++;
      }

      isBatchActive = false;
    } catch (err) {
      addUserMessage(`Error: Invalid JSON file`);
    }
  };
  reader.readAsText(file);
}

function addUserMessage(text) {
  const chat = document.getElementById("chat-area");
  if (!chat) return;

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
  if (!chat) return;

  const msg = document.createElement("div");
  msg.className = "chat-message system";
  msg.dataset.batch = batchNum;

  // Store results
  allResults.push(...items);

  const cardsHtml = items.map((item, idx) => `
    <div class="result-card" onclick="showItemDetail(${batchNum}, ${idx})">
      <img src="${item.image?.primary?.url || ''}" alt="" onerror="this.style.display='none'" />
      <div class="card-title">${item.title || 'Untitled'}</div>
      <div class="card-meta">${item.timeline?.submissionDeadlineUTC || item.timeline?.submissionDeadlineUTC || ''}</div>
    </div>
  `).join('');

  const controlsHtml = !isComplete ? `
    <div class="batch-controls">
      <button class="continue-btn" onclick="continueBatch(${batchNum})">Continue</button>
      <button class="stop-btn" onclick="stopBatch(${batchNum})">Stop</button>
    </div>
  ` : `<div class="batch-complete">✅ Complete - ${allResults.length} total items</div>`;

  msg.innerHTML = `
    <div class="message-header">🤖 ${title}</div>
    <div class="cards-grid">${cardsHtml}</div>
    ${controlsHtml}
  `;

  chat.appendChild(msg);
  chat.scrollTop = chat.scrollHeight;
}

async function processBatch(url, batchNum) {
  try {
    const res = await fetch("/api/scrape", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        url: url,
        query: "extract all",
        content_format: currentSchema,
      })
    });

    const result = await res.json();

    if (result.items && result.items.length > 0) {
      // Show system message with cards
      addSystemMessage(
        `Scraped ${result.items.length} items`,
        result.items,
        batchNum,
        result.batch_info?.has_more === false
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
  if (!isBatchActive) return;
  currentBatchNum = batchNum + 1;
  await processBatch(currentUrl, currentBatchNum);
};

window.stopBatch = function(batchNum) {
  isBatchActive = false;
  addSystemMessage(`Stopped - ${allResults.length} items saved`, allResults, batchNum, true);
};

window.showItemDetail = function(batchNum, idx) {
  const item = allResults[(batchNum - 1) * currentBatchSize + idx];
  if (!item) return;

  // Show in a simple alert for now (can be modal later)
  const details = JSON.stringify(item, null, 2);
  alert(`Item Details:\n\n${details.slice(0, 1000)}${details.length > 1000 ? '...' : ''}`);
};
