// Base URL of the FastAPI backend. Change this if you host the API elsewhere.
const API_BASE = "http://localhost:8000";

const downloadBtn = document.getElementById("download-btn");
const tableHead = document.getElementById("table-head");
const tableBody = document.getElementById("table-body");
const rowCountEl = document.getElementById("row-count");

const insightsStatus = document.getElementById("insights-status");
const insightsContent = document.getElementById("insights-content");
const downloadInsightsBtn = document.getElementById("download-insights-btn");
const resetInsightsBtn = document.getElementById("reset-insights-btn");

const topNInput = document.getElementById("top-n-input");
const groupBySelect = document.getElementById("group-by-select");
const filterValueLabel = document.getElementById("filter-value-label");
const filterValueSelect = document.getElementById("filter-value-select");
const generateBtn = document.getElementById("generate-btn");

// Populated from GET /insights/filters: { primary_game: [...], country: [...] }
let filterOptionsByGroup = {};

// ---------------------------------------------------------------------------
// 1. Download CSV
// ---------------------------------------------------------------------------
downloadBtn.addEventListener("click", () => {
  // Simply navigate to the download endpoint; the browser handles the save.
  window.location.href = `${API_BASE}/csv/download`;
});

// ---------------------------------------------------------------------------
// 2. Fetch CSV JSON and render as a table
// ---------------------------------------------------------------------------
async function loadTable() {
  try {
    const res = await fetch(`${API_BASE}/csv`);
    if (!res.ok) throw new Error(`Request failed: ${res.status}`);
    const data = await res.json();

    rowCountEl.textContent = `${data.count} rows loaded`;

    if (data.rows.length === 0) return;

    // Build header from the keys of the first row
    const columns = Object.keys(data.rows[0]);
    tableHead.innerHTML =
      "<tr>" + columns.map((c) => `<th>${c}</th>`).join("") + "</tr>";

    // Build body rows
    tableBody.innerHTML = data.rows
      .map(
        (row) =>
          "<tr>" +
          columns.map((c) => `<td>${row[c] ?? ""}</td>`).join("") +
          "</tr>"
      )
      .join("");
  } catch (err) {
    rowCountEl.textContent = "Failed to load data from server.";
    console.error(err);
  }
}

// ---------------------------------------------------------------------------
// 3. Fetch and display the latest generated insights.txt
// ---------------------------------------------------------------------------
async function loadInsights() {
  try {
    const res = await fetch(`${API_BASE}/insights`);

    if (res.status === 404) {
      insightsStatus.textContent =
        "No insights file uploaded yet. Run workflow/workflow.py to generate one.";
      insightsContent.hidden = true;
      downloadInsightsBtn.hidden = true;
      resetInsightsBtn.hidden = true;
      return;
    }

    if (!res.ok) throw new Error(`Request failed: ${res.status}`);

    const data = await res.json();
    insightsStatus.textContent = `Showing "${data.filename}"`;
    insightsContent.textContent = data.content;
    insightsContent.hidden = false;
    downloadInsightsBtn.hidden = false;
    resetInsightsBtn.hidden = false;
  } catch (err) {
    insightsStatus.textContent = "Failed to load insights from server.";
    insightsContent.hidden = true;
    downloadInsightsBtn.hidden = true;
    resetInsightsBtn.hidden = true;
    console.error(err);
  }
}

downloadInsightsBtn.addEventListener("click", () => {
  window.location.href = `${API_BASE}/insights/download`;
});

resetInsightsBtn.addEventListener("click", () => {
  resetInsightsBtn.disabled = true;

  fetch(`${API_BASE}/insights`, { method: "DELETE" })
    .then((res) => {
      if (!res.ok) throw new Error(`Request failed: ${res.status}`);
      insightsStatus.textContent = "Insights output cleared.";
      insightsContent.textContent = "";
      insightsContent.hidden = true;
      downloadInsightsBtn.hidden = true;
      resetInsightsBtn.hidden = true;
    })
    .catch((err) => {
      insightsStatus.textContent = `Failed to clear insights: ${err.message}`;
      console.error(err);
    })
    .finally(() => {
      resetInsightsBtn.disabled = false;
    });
});

// ---------------------------------------------------------------------------
// Filters: populate the "Filter to" dropdown from the CSV's own values
// ---------------------------------------------------------------------------
async function loadFilterOptions() {
  try {
    const res = await fetch(`${API_BASE}/insights/filters`);
    if (!res.ok) throw new Error(`Request failed: ${res.status}`);
    filterOptionsByGroup = await res.json(); // { primary_game: [...], country: [...] }
  } catch (err) {
    console.error("Failed to load filter options:", err);
  }
}

function updateFilterValueDropdown() {
  const groupBy = groupBySelect.value;

  if (groupBy === "none") {
    filterValueLabel.hidden = true;
    filterValueSelect.value = "";
    return;
  }

  const values = filterOptionsByGroup[groupBy] || [];
  filterValueSelect.innerHTML =
    `<option value="">All ${groupBy === "primary_game" ? "games" : "countries"}</option>` +
    values.map((v) => `<option value="${v}">${v}</option>`).join("");
  filterValueLabel.hidden = false;
}

groupBySelect.addEventListener("change", updateFilterValueDropdown);

// ---------------------------------------------------------------------------
// Generate insights on demand (used by both the manual Generate button and
// the quick-preset buttons below), using the chosen filters
// ---------------------------------------------------------------------------
async function generateInsights(topN, groupBy, filterValue) {
  insightsStatus.textContent = "Generating…";
  generateBtn.disabled = true;

  try {
    const res = await fetch(`${API_BASE}/insights/generate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ top_n: topN, group_by: groupBy, filter_value: filterValue }),
    });

    if (!res.ok) {
      const errBody = await res.json().catch(() => ({}));
      throw new Error(errBody.detail || `Request failed: ${res.status}`);
    }

    const data = await res.json();
    insightsStatus.textContent = `Showing "${data.filename}" (top ${topN}${
      groupBy !== "none" ? `, by ${groupBy}${filterValue ? `: ${filterValue}` : " (all)"}` : ""
    })`;
    insightsContent.textContent = data.content;
    insightsContent.hidden = false;
    downloadInsightsBtn.hidden = false;
    resetInsightsBtn.hidden = false;
  } catch (err) {
    insightsStatus.textContent = `Error: ${err.message}`;
    console.error(err);
  } finally {
    generateBtn.disabled = false;
  }
}

generateBtn.addEventListener("click", () => {
  const topN = parseInt(topNInput.value, 10) || 20;
  const groupBy = groupBySelect.value;
  const filterValue = groupBy === "none" ? null : (filterValueSelect.value || null);
  generateInsights(topN, groupBy, filterValue);
});

// ---------------------------------------------------------------------------
// Quick presets: mirror the CLI examples exactly, e.g.
//   python workflow.py --top-n 5 --group-by primary_game
// Clicking a preset syncs the visible filter controls (so the UI reflects
// what ran) and immediately triggers generation -- no extra click needed.
// ---------------------------------------------------------------------------
document.querySelectorAll(".preset-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    const topN = parseInt(btn.dataset.topN, 10);
    const groupBy = btn.dataset.groupBy;

    topNInput.value = topN;
    groupBySelect.value = groupBy;
    updateFilterValueDropdown(); // reveal/hide "Filter to" to match groupBy
    filterValueSelect.value = ""; // presets always mean "all games/countries"

    generateInsights(topN, groupBy, null);
  });
});

// Initial load
loadTable();
loadInsights();
loadFilterOptions();
