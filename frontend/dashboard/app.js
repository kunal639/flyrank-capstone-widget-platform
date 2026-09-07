// frontend/dashboard/app.js
let currentWidgetId = null;
let fieldDefinitionsCache = [];

function getAuthHeader() {
  const token = localStorage.getItem("tenant_token") || "";
  return {
    "Authorization": `Bearer ${token}`,
    "Content-Type": "application/json",
    "Accept": "application/json"
  };
}

function resetOpenPanels() {
  // Hide field config panel and clear active widget reference
  closeFieldConfig();
  
  // Hide submission detail panel
  closeSubmissionDetail();

  // Hide create widget card if open
  hideCreateWidgetModal();
}

function notify(msg, isError = false) {
  const box = document.getElementById("statusAlert");
  box.innerHTML = `<div class="alert ${isError ? 'alert-error' : 'alert-success'}">${msg}</div>`;
  setTimeout(() => { box.innerHTML = ""; }, 4000);
}

function saveToken() {
  const token = document.getElementById("tenantToken").value.trim();
  localStorage.setItem("tenant_token", token);

  // Explicitly close open detail panels on auth change
  closeFieldConfig();
  closeSubmissionDetail();

  notify("Tenant token updated");
  loadWidgets();
  loadSubmissions();
}

function switchTab(tab) {
  document.querySelectorAll(".nav-item").forEach(el => el.classList.remove("active"));
  document.querySelectorAll(".section").forEach(el => el.classList.remove("active"));

  if (tab === "widgets") {
    document.querySelector(".nav-item:nth-child(1)").classList.add("active");
    document.getElementById("widgetsSection").classList.add("active");
    loadWidgets();
  } else {
    document.querySelector(".nav-item:nth-child(2)").classList.add("active");
    document.getElementById("submissionsSection").classList.add("active");
    loadSubmissions();
  }
}

// ----------------- WIDGET CRUD ----------------- //

async function loadWidgets() {
  try {
    const res = await fetch("/widgets", { headers: getAuthHeader() });
    if (!res.ok) {
    if (res.status === 401 || res.status === 403) {
        closeFieldConfig();
    }
    throw new Error(`HTTP ${res.status}`);
    }
    

    const data = await res.json();
    const tbody = document.getElementById("widgetsTableBody");
    tbody.innerHTML = "";

    const widgets = data.widgets || [];
    if (widgets.length === 0) {
      tbody.innerHTML = `<tr><td colspan="3">No widgets found for this tenant.</td></tr>`;
      return;
    }

    widgets.forEach(w => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><strong>${w.title}</strong></td>
        <td><code>${w.widget_id}</code></td>
        <td>
          <button class="btn btn-primary" onclick="openFieldConfig('${w.widget_id}', '${w.title}')">Fields</button>
          <button class="btn btn-danger" onclick="deleteWidget('${w.widget_id}')">Delete</button>
        </td>
      `;
      tbody.appendChild(tr);
    });
  } catch (err) {
    document.getElementById("widgetsTableBody").innerHTML =
      `<tr><td colspan="3" style="color:red">Failed to load widgets: ${err.message}</td></tr>`;
  }
}

async function createWidget() {
  const title = document.getElementById("newWidgetTitle").value.trim();
  const widget_type_id = document.getElementById("newWidgetTypeId").value.trim();
  const rawOrigins = document.getElementById("newWidgetOrigins").value.trim();
  const allowed_origins = rawOrigins ? rawOrigins.split(",").map(s => s.trim()) : [];

  if (!title || !widget_type_id) {
    notify("Title and Widget Type ID are required", true);
    return;
  }

  try {
    const res = await fetch("/widgets", {
      method: "POST",
      headers: getAuthHeader(),
      body: JSON.stringify({ title, widget_type_id, allowed_origins })
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    notify("Widget created successfully");
    hideCreateWidgetModal();
    loadWidgets();
  } catch (err) {
    notify(`Failed to create widget: ${err.message}`, true);
  }
}

async function deleteWidget(widgetId) {
  if (!confirm("Are you sure you want to delete this widget?")) return;
  try {
    const res = await fetch(`/widgets/${widgetId}`, {
      method: "DELETE",
      headers: getAuthHeader()
    });
    if (res.status !== 204) throw new Error(`HTTP ${res.status}`);
    notify("Widget deleted");
    loadWidgets();
  } catch (err) {
    notify(`Failed to delete widget: ${err.message}`, true);
  }
}

// ----------------- FIELD CONFIGURATION ----------------- //

async function openFieldConfig(widgetId, widgetTitle) {
  currentWidgetId = widgetId;
  const card = document.getElementById("fieldConfigCard");
  document.getElementById("fieldConfigTitle").innerText = `Configure Fields — ${widgetTitle}`;
  card.style.display = "block";

  try {
    // 1. Fetch all system field definitions (or common fields)
    let defsRes = await fetch("/field-definitions", { credentials: "omit" }).catch(() => null);
    if (!defsRes || !defsRes.ok) {
      // Fallback standard fields if GET /field-definitions is not directly exposed
      fieldDefinitionsCache = [
        { field_id: "00000000-0000-0000-0000-000000000001", field_name: "email", field_type: "email" },
        { field_id: "00000000-0000-0000-0000-000000000002", field_name: "message", field_type: "text" }
      ];
    }

    // 2. Fetch current widget fields
    const wfRes = await fetch(`/widgets/${widgetId}/fields`, { credentials: "omit", headers: getAuthHeader() });
    let activeFields = [];
    if (wfRes.ok) {
      const data = await wfRes.json();
      activeFields = data.fields || [];
    }

    renderFieldConfigList(activeFields);
  } catch (err) {
    notify(`Error loading field configuration: ${err.message}`, true);
  }
}

function renderFieldConfigList(activeFields) {
  const container = document.getElementById("fieldConfigList");
  container.innerHTML = "";

  if (activeFields.length === 0) {
    container.innerHTML = `<p style="font-size:0.85rem;color:#64748b;">No fields configured yet. Add fields below.</p>`;
  }

  activeFields.forEach((f, idx) => {
    const div = document.createElement("div");
    div.className = "field-row";
    div.innerHTML = `
      <span style="width: 250px;"><code>${f.field_id}</code></span>
      <label>Order:
        <input type="number" class="field-order" data-fid="${f.field_id}" value="${f.display_order ?? idx}" style="width: 50px; padding: 2px;">
      </label>
      <label>
        <input type="checkbox" class="field-req" data-fid="${f.field_id}" ${f.required ? 'checked' : ''}> Required
      </label>
    `;
    container.appendChild(div);
  });
}

async function saveFieldConfiguration() {
  if (!currentWidgetId) return;

  const rows = document.querySelectorAll(".field-row");
  const payloadFields = [];

  rows.forEach(r => {
    const orderInp = r.querySelector(".field-order");
    const reqInp = r.querySelector(".field-req");
    payloadFields.push({
      field_id: orderInp.getAttribute("data-fid"),
      display_order: parseInt(orderInp.value, 10),
      required: reqInp.checked
    });
  });

  try {
    const res = await fetch(`/widgets/${currentWidgetId}/fields`, {
      method: "PUT",
      headers: getAuthHeader(),
      body: JSON.stringify({ fields: payloadFields })
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || `HTTP ${res.status}`);
    }
    notify("Widget fields successfully updated");
  } catch (err) {
    notify(`Validation failed: ${err.message}`, true);
  }
}

function closeFieldConfig() {
  document.getElementById("fieldConfigCard").style.display = "none";
  currentWidgetId = null;
}

// ----------------- SUBMISSIONS DASHBOARD ----------------- //

async function loadSubmissions() {
  const tbody = document.getElementById("submissionsTableBody");
  try {
    const res = await fetch("/submissions", { credentials: "omit", headers: getAuthHeader() });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    const subs = data.submissions || [];

    tbody.innerHTML = "";
    if (subs.length === 0) {
      tbody.innerHTML = `<tr><td colspan="4">No submissions found.</td></tr>`;
      return;
    }

    subs.forEach(s => {
      const tr = document.createElement("tr");
      const summary = s.field_values ? JSON.stringify(s.field_values).slice(0, 40) + "..." : "No fields";
      const geo = s.geo ? `${s.geo.city || ''} ${s.geo.country || ''}`.trim() : "Direct / Local";
      tr.innerHTML = `
        <td><code>${s.submission_id.slice(0, 8)}...</code></td>
        <td>${summary}</td>
        <td><span class="badge">${geo || "Unknown"}</span></td>
        <td>
          <button class="btn btn-secondary" onclick="viewSubmission('${s.submission_id}')">View</button>
        </td>
      `;
      tbody.appendChild(tr);
    });
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="4" style="color:red">Failed to load submissions: ${err.message}</td></tr>`;
  }
}

async function viewSubmission(subId) {
  try {
    const res = await fetch(`/submissions/${subId}`, { credentials: "omit", headers: getAuthHeader() });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    const panel = document.getElementById("submissionDetailCard");
    const body = document.getElementById("submissionDetailBody");

    body.innerHTML = `
      <p><strong>Submission ID:</strong> <code>${data.submission_id}</code></p>
      <p><strong>Widget ID:</strong> <code>${data.widget_id}</code></p>
      <p><strong>Created At:</strong> ${data.created_at || 'N/A'}</p>
      <h4 style="margin-top:0.75rem;">Submitted Fields:</h4>
      <pre style="background:#f1f5f9; padding:0.75rem; border-radius:4px; margin:0.5rem 0;">${JSON.stringify(data.fields || data.field_values, null, 2)}</pre>
      <h4 style="margin-top:0.75rem;">Enrichment / Geo:</h4>
      <pre style="background:#f1f5f9; padding:0.75rem; border-radius:4px; margin:0.5rem 0;">${JSON.stringify(data.geo || {}, null, 2)}</pre>
    `;
    panel.style.display = "block";
  } catch (err) {
    notify(`Error opening submission: ${err.message}`, true);
  }
}

function closeSubmissionDetail() {
  document.getElementById("submissionDetailCard").style.display = "none";
}

// Initialize on page load
window.addEventListener("DOMContentLoaded", () => {
  const saved = localStorage.getItem("tenant_token");
  if (saved) {
    document.getElementById("tenantToken").value = saved;
    loadWidgets();
  }
});