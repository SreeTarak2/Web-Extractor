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

// ── Batch Processing Variables ────────────────────────────────────────────
let uploadBatchSize = 5;
let uploadBatchIndex = 0;
let uploadAllItems = [];
let uploadSchema = "contest";
let uploadEnrich = false;
let uploadAllNormalized = [];
let uploadProcessing = false;

async function startUpload() {
  if (!uploadedItems) {
    console.error("No items uploaded");
    alert("Please select a JSON file first");
    return;
  }
  
  const schema = document.getElementById("upload-schema")?.value;
  const enrich = document.getElementById("enrich-urls")?.checked;
  const file = document.getElementById("json-file")?.files?.[0];
  const batchSize = parseInt(document.getElementById("batch-size")?.value || "5");

  if (!file) {
    console.error("No file selected");
    alert("No file selected");
    return;
  }

  if (!schema) {
    console.error("No schema selected");
    alert("Please select a schema");
    return;
  }

  // Reset UI for upload tab
  const progressLog = document.getElementById("upload-progress-log");
  const progressBar = document.getElementById("upload-progress-bar");
  const resultsSection = document.getElementById("upload-results-section");
  
  if (!progressLog || !progressBar || !resultsSection) {
    console.error("UI elements not found", { progressLog, progressBar, resultsSection });
    return;
  }
  
  progressLog.innerHTML = "";
  progressBar.style.width = "0%";
  resultsSection.classList.add("hidden");
  
  document.getElementById("upload-progress-section").classList.remove("hidden");
  document.getElementById("upload-btn").disabled = true;
  
  // Initialize batch processing state
  uploadBatchSize = batchSize;
  uploadBatchIndex = 0;
  uploadAllItems = uploadedItems;
  uploadSchema = schema;
  uploadEnrich = enrich;
  uploadAllNormalized = [];
  uploadProcessing = true;
  
  // Log messages directly to upload progress log
  function logUpload(msg) {
    console.log("[Upload]", msg);
    const entry = document.createElement("div");
    entry.textContent = msg;
    entry.style.marginBottom = "0.5rem";
    entry.style.fontSize = "0.75rem";
    entry.style.color = "var(--on-surface-variant)";
    progressLog.appendChild(entry);
    progressLog.scrollTop = progressLog.scrollHeight;
  }
  
  const totalBatches = Math.ceil(uploadAllItems.length / uploadBatchSize);
  logUpload(`📦 Processing ${uploadAllItems.length} items in ${totalBatches} batch${totalBatches !== 1 ? "es" : ""} of ${uploadBatchSize} items`);
  logUpload(`Schema: ${schema} | Enrichment: ${enrich ? "ON" : "OFF"}`);
  logUpload("");
  
  // Start batch processing
  await processNextUploadBatch(logUpload);
}

async function processNextUploadBatch(logUpload) {
  if (!uploadProcessing) return;
  
  const totalItems = uploadAllItems.length;
  const totalBatches = Math.ceil(totalItems / uploadBatchSize);
  const startIdx = uploadBatchIndex * uploadBatchSize;
  const endIdx = Math.min(startIdx + uploadBatchSize, totalItems);
  const batch = uploadAllItems.slice(startIdx, endIdx);
  const batchNum = uploadBatchIndex + 1;
  
  if (startIdx >= totalItems) {
    // All batches processed
    finalizeBatchProcessing(logUpload);
    return;
  }
  
  logUpload(`\n⚙️ Batch ${batchNum}/${totalBatches} — Processing ${batch.length} items...`);
  
  try {
    const res = await fetch("/api/normalize-batch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ items: batch, schema: uploadSchema }),
    });
    
    if (!res.ok) {
      const text = await res.text();
      logUpload(`❌ Batch ${batchNum} failed: ${text}`);
      uploadProcessing = false;
      document.getElementById("upload-btn").disabled = false;
      return;
    }
    
    const data = await res.json();
    
    if (data.error) {
      logUpload(`❌ Batch ${batchNum} error: ${data.error}`);
      uploadProcessing = false;
      document.getElementById("upload-btn").disabled = false;
      return;
    }
    
    // Collect normalized items
    uploadAllNormalized.push(...(data.items || []));
    
    logUpload(`✅ Batch ${batchNum} complete — ${data.items?.length} items normalized`);
    logUpload(`   Cost: $${(data.cost?.total_usd || 0).toFixed(6)} | Duration: ${data.duration_seconds}s`);
    
    // Update progress bar
    const progress = Math.round((endIdx / totalItems) * 100);
    document.getElementById("upload-progress-bar").style.width = progress + "%";
    
    uploadBatchIndex++;
    
    // If more batches remain, ask user for confirmation
    if (uploadBatchIndex < totalBatches) {
      logUpload("");
      logUpload(`📋 Review completed. Continue with batch ${uploadBatchIndex + 1}?`);
      showBatchConfirmationDialog(logUpload, totalBatches);
    } else {
      finalizeBatchProcessing(logUpload);
    }
    
  } catch (e) {
    console.error("Batch processing failed:", e);
    logUpload(`❌ Request failed: ${e.message}`);
    uploadProcessing = false;
    document.getElementById("upload-btn").disabled = false;
  }
}

function showBatchConfirmationDialog(logUpload, totalBatches) {
  const progressLog = document.getElementById("upload-progress-log");
  
  // Create button container
  const btnContainer = document.createElement("div");
  btnContainer.style.display = "flex";
  btnContainer.style.gap = "0.75rem";
  btnContainer.style.marginTop = "0.75rem";
  btnContainer.style.marginBottom = "0.75rem";
  
  // Continue button
  const continueBtn = document.createElement("button");
  continueBtn.textContent = `✓ Continue (${uploadBatchIndex + 1}/${totalBatches})`;
  continueBtn.style.padding = "0.5rem 1rem";
  continueBtn.style.background = "var(--primary)";
  continueBtn.style.color = "var(--surface)";
  continueBtn.style.border = "none";
  continueBtn.style.borderRadius = "4px";
  continueBtn.style.cursor = "pointer";
  continueBtn.style.fontSize = "0.75rem";
  continueBtn.style.fontWeight = "700";
  continueBtn.onclick = async () => {
    btnContainer.remove();
    logUpload("Continuing to next batch...");
    await processNextUploadBatch(logUpload);
  };
  
  // Finish button
  const finishBtn = document.createElement("button");
  finishBtn.textContent = "⊗ Stop & Finalize";
  finishBtn.style.padding = "0.5rem 1rem";
  finishBtn.style.background = "var(--surface-container-high)";
  finishBtn.style.color = "var(--on-surface)";
  finishBtn.style.border = "1px solid var(--outline-variant)";
  finishBtn.style.borderRadius = "4px";
  finishBtn.style.cursor = "pointer";
  finishBtn.style.fontSize = "0.75rem";
  finishBtn.style.fontWeight = "700";
  finishBtn.onclick = () => {
    btnContainer.remove();
    logUpload("Processing stopped by user.");
    finalizeBatchProcessing(logUpload);
  };
  
  btnContainer.appendChild(continueBtn);
  btnContainer.appendChild(finishBtn);
  progressLog.appendChild(btnContainer);
  progressLog.scrollTop = progressLog.scrollHeight;
}

function finalizeBatchProcessing(logUpload) {
  uploadProcessing = false;
  
  const progressBar = document.getElementById("upload-progress-bar");
  const resultsSection = document.getElementById("upload-results-section");
  
  progressBar.style.width = "100%";
  
  const processedCount = uploadAllNormalized.length;
  const totalCount = uploadAllItems.length;
  
  logUpload("");
  logUpload(`━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`);
  logUpload(`✨ Processing complete!`);
  logUpload(`   Total items processed: ${processedCount}/${totalCount}`);
  logUpload(`   Batches completed: ${uploadBatchIndex}/${Math.ceil(totalCount / uploadBatchSize)}`);
  logUpload(`━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`);
  
  // Display results
  document.getElementById("upload-results-json").textContent = JSON.stringify(uploadAllNormalized, null, 2);
  resultsSection.classList.remove("hidden");
  
  document.getElementById("upload-btn").disabled = false;
}

function copyUploadResults() {
  const resultsText = document.getElementById("upload-results-json").textContent;
  if (!resultsText) {
    alert("No results to copy");
    return;
  }
  
  navigator.clipboard.writeText(resultsText).then(() => {
    const btn = event.target.closest(".results-btn");
    if (btn) {
      const originalText = btn.innerHTML;
      btn.innerHTML = '<i data-lucide="check"></i> Copied!';
      btn.style.background = "var(--primary)";
      btn.style.color = "var(--surface)";
      
      setTimeout(() => {
        btn.innerHTML = originalText;
        btn.style.background = "var(--surface-container)";
        btn.style.color = "var(--on-surface)";
        lucide.createIcons();
      }, 2000);
    }
  }).catch(err => {
    console.error("Failed to copy:", err);
    alert("Failed to copy to clipboard");
  });
}

function downloadUploadResults(format) {
  const resultsText = document.getElementById("upload-results-json").textContent;
  if (!resultsText) {
    alert("No results to download");
    return;
  }
  
  try {
    const items = JSON.parse(resultsText);
    
    if (format === "json") {
      downloadFile(
        JSON.stringify(items, null, 2),
        "webmind-normalized.json",
        "application/json"
      );
    } else if (format === "csv") {
      if (!Array.isArray(items) || items.length === 0) {
        alert("No items to export as CSV");
        return;
      }
      
      // Get all unique keys
      const keys = [...new Set(items.flatMap(Object.keys))];
      
      // Create CSV header
      const rows = [keys.map(k => `"${k}"`).join(",")];
      
      // Create CSV rows
      for (const item of items) {
        const values = keys.map(k => {
          const v = item[k];
          const str = Array.isArray(v) 
            ? v.join("|") 
            : (typeof v === "object" ? JSON.stringify(v) : String(v ?? ""));
          return `"${str.replace(/"/g, '""')}"`;
        });
        rows.push(values.join(","));
      }
      
      downloadFile(rows.join("\n"), "webmind-normalized.csv", "text/csv");
    }
  } catch (e) {
    console.error("Download failed:", e);
    alert("Failed to download results");
  }
}

function downloadFile(content, filename, mimeType) {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function copyScrapeResults() {
  const resultsText = document.getElementById("results-json").textContent;
  if (!resultsText) {
    alert("No results to copy");
    return;
  }
  
  navigator.clipboard.writeText(resultsText).then(() => {
    const btn = event.target.closest(".results-btn");
    if (btn) {
      const originalText = btn.innerHTML;
      btn.innerHTML = '<i data-lucide="check"></i> Copied!';
      btn.style.background = "var(--primary)";
      btn.style.color = "var(--surface)";
      
      setTimeout(() => {
        btn.innerHTML = originalText;
        btn.style.background = "var(--surface-container)";
        btn.style.color = "var(--on-surface)";
        lucide.createIcons();
      }, 2000);
    }
  }).catch(err => {
    console.error("Failed to copy:", err);
    alert("Failed to copy to clipboard");
  });
}

function downloadScrapeResults(format) {
  const resultsText = document.getElementById("results-json").textContent;
  if (!resultsText) {
    alert("No results to download");
    return;
  }
  
  try {
    const items = JSON.parse(resultsText);
    
    if (format === "json") {
      downloadFile(
        JSON.stringify(items, null, 2),
        "webmind-results.json",
        "application/json"
      );
    } else if (format === "csv") {
      if (!Array.isArray(items) || items.length === 0) {
        alert("No items to export as CSV");
        return;
      }
      
      // Get all unique keys
      const keys = [...new Set(items.flatMap(Object.keys))];
      
      // Create CSV header
      const rows = [keys.map(k => `"${k}"`).join(",")];
      
      // Create CSV rows
      for (const item of items) {
        const values = keys.map(k => {
          const v = item[k];
          const str = Array.isArray(v) 
            ? v.join("|") 
            : (typeof v === "object" ? JSON.stringify(v) : String(v ?? ""));
          return `"${str.replace(/"/g, '""')}"`;
        });
        rows.push(values.join(","));
      }
      
      downloadFile(rows.join("\n"), "webmind-results.csv", "text/csv");
    }
  } catch (e) {
    console.error("Download failed:", e);
    alert("Failed to download results");
  }
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
  const entry = document.createElement("div");
  entry.textContent = msg;
  entry.style.marginBottom = "0.5rem";
  entry.style.fontSize = "0.75rem";
  entry.style.color = "var(--on-surface-variant)";
  log.appendChild(entry);
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
let currentQuery = "";
let allResults = [];
let showSearch = false;
let showThink = false;
let showCanvas = false;
let promptFiles = [];
let jsonData = null;
let jsonBatchIndex = 0;
let scrapeWs = null;
let scrapeAbortController = null;

// Initialize chat UI
document.addEventListener("DOMContentLoaded", () => {
  // Schema dropdown toggle
  const schemaToggle = document.getElementById("schema-toggle");
  const schemaDropdown = document.getElementById("schema-dropdown");
  const schemaLabel = document.getElementById("schema-label");
  
  if (schemaToggle && schemaDropdown) {
    schemaToggle.addEventListener("click", (e) => {
      e.stopPropagation();
      schemaDropdown.classList.toggle("hidden");
    });
    
    schemaDropdown.querySelectorAll(".dropdown-item").forEach(item => {
      item.addEventListener("click", () => {
        currentSchema = item.dataset.value;
        if (schemaLabel) schemaLabel.textContent = currentSchema.charAt(0).toUpperCase() + currentSchema.slice(1);
        schemaDropdown.classList.add("hidden");
      });
    });
  }

  // Close dropdown when clicking outside
  document.addEventListener("click", () => {
    if (schemaDropdown && !schemaDropdown.classList.contains("hidden")) {
      schemaDropdown.classList.add("hidden");
    }
  });

  // Search toggle
  const searchToggle = document.getElementById("search-toggle");
  if (searchToggle) {
    searchToggle.addEventListener("click", () => {
      showSearch = !showSearch;
      searchToggle.classList.toggle("active", showSearch);
      if (showSearch) showThink = false;
      const thinkToggle = document.getElementById("think-toggle");
      if (thinkToggle) thinkToggle.classList.remove("active");
    });
  }

  // Think toggle
  const thinkToggle = document.getElementById("think-toggle");
  if (thinkToggle) {
    thinkToggle.addEventListener("click", () => {
      showThink = !showThink;
      thinkToggle.classList.toggle("active", showThink);
      if (showThink) showSearch = false;
      const searchToggleEl = document.getElementById("search-toggle");
      if (searchToggleEl) searchToggleEl.classList.remove("active");
    });
  }

  // Upload button
  const uploadBtn = document.getElementById("upload-btn");
  const jsonUpload = document.getElementById("json-upload");
  if (uploadBtn && jsonUpload) {
    uploadBtn.addEventListener("click", () => jsonUpload.click());
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

  // Enter key in input (shift+enter for newline, enter to send)
  const promptInput = document.getElementById("prompt-input");
  if (promptInput) {
    promptInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleSend();
      }
    });
    
    // Auto-resize textarea
    promptInput.addEventListener("input", function() {
      this.style.height = 'auto';
      this.style.height = Math.min(this.scrollHeight, 200) + 'px';
    });
  }

  // JSON upload
  if (jsonUpload) {
    jsonUpload.addEventListener("change", handleJsonUpload);
  }
});

async function handleSend() {
  const input = document.getElementById("prompt-input");
  const url = input.value.trim();
  const fileNames = promptFiles.map(f => f.file.name).join(", ");
  
  if (!url && promptFiles.length === 0) return;

  let messagePrefix = "";
  if (showSearch) messagePrefix = "[Search: ";
  else if (showThink) messagePrefix = "[Think: ";
  else if (showCanvas) messagePrefix = "[Canvas: ";
  
  let formattedInput = messagePrefix ? `${messagePrefix}${url}]` : url;
  if(fileNames) formattedInput += `\n(Attachments: ${fileNames})`;

  addUserMessage(formattedInput);
  input.value = "";
  input.style.height = 'auto';
  
  promptFiles = [];
  document.getElementById("file-previews").innerHTML = "";

  const sendBtn = document.getElementById("send-btn");
  sendBtn.className = "send-btn";
  document.getElementById("send-icon").setAttribute("data-lucide", "mic");
  lucide.createIcons();

  if(!url) return;

  currentUrl = url;
  currentQuery = "extract all";
  currentBatchNum = 1;
  isBatchActive = true;
  allResults = [];

  await startScrapeViaWebSocket(url, currentQuery, currentBatchNum);
}

async function handleJsonUpload(e) {
  const file = e.target.files[0];
  if (!file) return;

  const reader = new FileReader();
  reader.onload = async (event) => {
    try {
      let data = JSON.parse(event.target.result);
      if (!Array.isArray(data)) data = data.items ? data.items : [data];

      jsonData = data;
      jsonBatchIndex = 0;
      currentBatchNum = 0;
      currentUrl = "";
      allResults = [];
      isBatchActive = true;

      const totalBatches = Math.ceil(data.length / currentBatchSize);
      addUserMessage(`📄 ${file.name} — ${data.length} items · ${totalBatches} batch${totalBatches !== 1 ? "es" : ""} of ${currentBatchSize}`);

      // Kick off first batch immediately
      await processNextJsonBatch();
    } catch (err) {
      addUserMessage(`Error: Invalid JSON file — ${err.message}`);
    }
  };
  reader.readAsText(file);
}

async function processNextJsonBatch() {
  if (!jsonData || !isBatchActive) return;

  const startIdx = jsonBatchIndex * currentBatchSize;
  if (startIdx >= jsonData.length) {
    addBatchCompleteMessage();
    return;
  }

  const batch = jsonData.slice(startIdx, startIdx + currentBatchSize);
  const batchNum = currentBatchNum + 1;
  const totalBatches = Math.ceil(jsonData.length / currentBatchSize);
  const isLast = startIdx + currentBatchSize >= jsonData.length;

  currentBatchNum = batchNum;
  jsonBatchIndex++;

  // Show loading card in chat
  const loadingId = `batch-loading-${batchNum}`;
  addLoadingMessage(loadingId, `Normalizing batch ${batchNum}/${totalBatches} (${batch.length} items)…`);

  try {
    const res = await fetch("/api/normalize-batch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ items: batch, schema: currentSchema }),
    });

    removeLoadingMessage(loadingId);

    if (!res.ok) {
      const txt = await res.text();
      addSystemMessage(`Batch ${batchNum} failed: ${txt}`, [], batchNum, true);
      return;
    }

    const result = await res.json();
    if (result.error) {
      addSystemMessage(`Batch ${batchNum} error: ${result.error}`, [], batchNum, true);
      return;
    }

    const items = result.items ?? [];
    allResults.push(...items);

    const reviewItems = result.needsReview ?? [];
    const reviewHtml = reviewItems.length
      ? `<div class="review-warnings">
           <div class="review-title">⚠️ ${reviewItems.length} item${reviewItems.length !== 1 ? "s" : ""} need category review</div>
           ${reviewItems.map(r => `
             <div class="review-row">
               <span class="review-item-title">${r.title || "Untitled"}</span>
               <span class="review-assigned">assigned: <b>${r.assignedCategory}</b></span>
               ${r.suggestedCategory ? `<span class="review-suggested">→ suggested: <b>${r.suggestedCategory}</b></span>` : ""}
               <span class="review-confidence confidence-${r.confidence}">${r.confidence}</span>
             </div>
           `).join("")}
         </div>`
      : "";

    addSystemMessage(
      `Batch ${batchNum}/${totalBatches} — ${items.length} normalized · $${(result.cost?.total_usd ?? 0).toFixed(4)}`,
      items,
      batchNum,
      isLast,
      reviewHtml
    );
  } catch (err) {
    removeLoadingMessage(loadingId);
    addSystemMessage(`Batch ${batchNum} failed: ${err.message}`, [], batchNum, true);
  }
}

function addLoadingMessage(id, text) {
  const chat = document.getElementById("chat-area");
  const el = document.createElement("div");
  el.className = "chat-message system";
  el.id = id;
  el.innerHTML = `
    <div class="message-header">🤖 ${text}</div>
    <div class="loading-spinner"></div>
  `;
  chat.appendChild(el);
  chat.scrollTop = chat.scrollHeight;
}

function removeLoadingMessage(id) {
  const el = document.getElementById(id);
  if (el) el.remove();
}

function addBatchCompleteMessage() {
  const chat = document.getElementById("chat-area");
  const el = document.createElement("div");
  el.className = "chat-message system";
  el.innerHTML = `
    <div class="message-header">✅ All done — ${allResults.length} items normalized</div>
    <div class="batch-controls">
      <button class="export-all-btn" onclick="exportAllResults()">Export All JSON</button>
    </div>
  `;
  chat.appendChild(el);
  chat.scrollTop = chat.scrollHeight;
  isBatchActive = false;
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

function getCardFields(item) {
  // Contest schema
  if (item.title || item.timeline) {
    return {
      img: item.image?.primary?.url || "",
      title: item.title || "Untitled",
      meta: item.timeline?.submissionDeadlineUTC || item.category || "",
    };
  }
  // Conference schema
  if (item.basicInfo) {
    return {
      img: item.image?.url || "",
      title: item.basicInfo?.title || "Untitled",
      meta: item.schedule?.startDate || item.location?.city || "",
    };
  }
  // Fallback: raw data
  const keys = Object.keys(item);
  return {
    img: "",
    title: item.title || item.name || item[keys[0]] || "Item",
    meta: item.url || item.source_url || "",
  };
}

function addSystemMessage(title, items, batchNum, isComplete = false, extraHtml = "") {
  const chat = document.getElementById("chat-area");
  if (!chat) return;

  // Store items in a closure-accessible map so showItemDetail can find them
  if (!window._batchItems) window._batchItems = {};
  window._batchItems[batchNum] = items;

  const msg = document.createElement("div");
  msg.className = "chat-message system";
  msg.dataset.batch = batchNum;

  const cardsHtml = items.map((item, idx) => {
    const f = getCardFields(item);
    return `
      <div class="result-card" onclick="showItemDetail(${batchNum}, ${idx})">
        ${f.img ? `<img src="${f.img}" alt="" onerror="this.style.display='none'" />` : ""}
        <div class="card-title">${f.title}</div>
        <div class="card-meta">${f.meta}</div>
      </div>
    `;
  }).join("");

  let controlsHtml;
  if (isComplete) {
    controlsHtml = `<div class="batch-complete">✅ Complete — ${allResults.length} total items</div>`;
  } else if (jsonData) {
    // Only show Continue/Stop for JSON uploads
    controlsHtml = `
      <div class="batch-controls">
        <button class="continue-btn" onclick="continueBatch(${batchNum})">Continue</button>
        <button class="stop-btn" onclick="stopBatch(${batchNum})">Stop</button>
      </div>
    `;
  } else {
    // URL scraping — show Stop only (scrape runs in one go)
    controlsHtml = `
      <div class="batch-controls">
        <button class="stop-btn" onclick="stopBatch(${batchNum})">Stop</button>
      </div>
    `;
  }

  msg.innerHTML = `
    <div class="message-header">🤖 ${title}</div>
    ${items.length > 0 ? `<div class="cards-grid">${cardsHtml}</div>` : ''}
    ${extraHtml}
    ${controlsHtml}
  `;

  chat.appendChild(msg);
  chat.scrollTop = chat.scrollHeight;
}

async function startScrapeViaWebSocket(url, query, batchNum) {
  if (scrapeWs) {
    scrapeWs.close();
    scrapeWs = null;
  }

  const protocol = location.protocol === "https:" ? "wss" : "ws";
  scrapeWs = new WebSocket(`${protocol}://${location.host}/ws/scrape`);

  const chat = document.getElementById("chat-area");
  const empty = chat.querySelector(".chat-empty");
  if (empty) empty.remove();

  // Show loading indicator
  const loadingMsg = document.createElement("div");
  loadingMsg.className = "chat-message system";
  loadingMsg.id = "loading-indicator";
  loadingMsg.innerHTML = `
    <div class="message-header">🤖 Scraping batch ${batchNum}...</div>
    <div class="loading-spinner"></div>
  `;
  chat.appendChild(loadingMsg);
  chat.scrollTop = chat.scrollHeight;

  scrapeWs.onopen = () => {
    scrapeWs.send(JSON.stringify({
      type: "scrape",
      url: url,
      query: query,
      content_format: currentSchema,
    }));
  };

  scrapeWs.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    if (msg.type === "progress") {
      // Update loading indicator with progress
      if (loadingMsg) {
        loadingMsg.innerHTML = `<div class="message-header">🤖 ${msg.message}</div>`;
        chat.scrollTop = chat.scrollHeight;
      }
    } else if (msg.type === "result") {
      // Remove loading indicator
      if (loadingMsg && loadingMsg.parentNode) {
        loadingMsg.remove();
      }

      const items = msg.data.items || [];
      const stopped = msg.data.metadata?.stopped === true;
      const itemCount = items.length;

      if (itemCount > 0) {
        allResults.push(...items);
        addSystemMessage(
          `Scraped ${itemCount} item${itemCount !== 1 ? "s" : ""}`,
          items,
          batchNum,
          stopped
        );
      } else if (stopped) {
        addSystemMessage(`Stopped — ${allResults.length} items saved`, allResults, batchNum, true);
      } else {
        addSystemMessage("No items found", [], batchNum, true);
      }

      isBatchActive = !stopped;
      scrapeWs = null;
    } else if (msg.type === "stopping") {
      if (loadingMsg && loadingMsg.parentNode) {
        loadingMsg.innerHTML = `<div class="message-header">🤖 ${msg.message}</div>`;
        chat.scrollTop = chat.scrollHeight;
      }
    } else if (msg.type === "error") {
      if (loadingMsg && loadingMsg.parentNode) {
        loadingMsg.remove();
      }
      addSystemMessage(`Error: ${msg.message}`, [], batchNum, true);
      isBatchActive = false;
      scrapeWs = null;
    }
  };

  scrapeWs.onerror = () => {
    console.error("WebSocket error");
    if (loadingMsg && loadingMsg.parentNode) {
      loadingMsg.remove();
    }
    addSystemMessage("WebSocket connection error.", [], batchNum, true);
    isBatchActive = false;
    scrapeWs = null;
  };

  scrapeWs.onclose = () => {
    console.log("WebSocket closed");
    scrapeWs = null;
  };
}

async function processBatch(url, batchNum) {
  try {
    const res = await fetch("/api/scrape", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        url: url,
        query: currentQuery || "extract all",
        content_format: currentSchema,
      })
    });

    const result = await res.json();

    if (result.items && result.items.length > 0) {
      allResults.push(...result.items);
      addSystemMessage(
        `Scraped ${result.items.length} items`,
        result.items,
        batchNum,
        result.metadata?.stopped === true
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

function disableBatchButtons(batchNum) {
  const msg = document.querySelector(`[data-batch="${batchNum}"]`);
  if (!msg) return;
  msg.querySelectorAll(".continue-btn, .stop-btn").forEach(btn => {
    btn.disabled = true;
    btn.style.opacity = "0.4";
    btn.style.cursor = "not-allowed";
  });
}

window.continueBatch = async function(batchNum) {
  disableBatchButtons(batchNum);
  isBatchActive = true;
  if (jsonData) {
    await processNextJsonBatch();
  } else if (currentUrl) {
    await startScrapeViaWebSocket(currentUrl, currentQuery, batchNum + 1);
  }
};

window.stopBatch = function(batchNum) {
  disableBatchButtons(batchNum);
  isBatchActive = false;
  if (scrapeWs && scrapeWs.readyState === WebSocket.OPEN) {
    scrapeWs.send(JSON.stringify({ type: "stop" }));
  }
  addBatchCompleteMessage();
};

window.exportAllResults = function() {
  if (!allResults.length) return;
  const blob = new Blob([JSON.stringify(allResults, null, 2)], { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `normalized-${currentSchema}-${allResults.length}items.json`;
  a.click();
};

window.showItemDetail = function(batchNum, idx) {
  const items = (window._batchItems || {})[batchNum] || [];
  const item = items[idx];
  if (!item) return;

  // Build a simple modal instead of alert
  let modal = document.getElementById("item-detail-modal");
  if (!modal) {
    modal = document.createElement("div");
    modal.id = "item-detail-modal";
    modal.className = "modal-overlay";
    modal.innerHTML = `
      <div class="modal-content">
        <button class="modal-close" onclick="document.getElementById('item-detail-modal').remove()">✕</button>
        <pre id="item-detail-json" style="white-space:pre-wrap;font-size:0.8rem;color:#a5f3fc;margin-top:1rem;"></pre>
      </div>
    `;
    document.body.appendChild(modal);
    modal.addEventListener("click", e => { if (e.target === modal) modal.remove(); });
  }
  document.getElementById("item-detail-json").textContent = JSON.stringify(item, null, 2);
};
