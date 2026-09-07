// frontend/dashboard/app.js
let currentWidgetId = null;

function getAuthHeader() {
  const token = localStorage.getItem("tenant_token") || "";
  return {
    "Authorization": `Bearer ${token}`,
    "Content-Type": "application/json",
    "Accept": "application/json"
  };
}

// Boot handler: Load token from localStorage
window.addEventListener("DOMContentLoaded", () => {
  const saved = localStorage.getItem("tenant_token");
  if (saved) {
    document.getElementById("tenantToken").value = saved;
    loadWidgets();
    loadSubmissions();
  }
});

// ----------------- UI CONTROLS & NAVIGATION ----------------- //

function showCreateWidgetModal() {
  document.getElementById("createWidgetCard").style.display = "block";
}

function hideCreateWidgetModal() {
  document.getElementById("createWidgetCard").style.display = "none";
  document.getElementById("newWidgetTitle").value = "";
  document.getElementById("newWidgetOrigins").value = "";
}

function notify(msg, isError = false) {
  const box = document.getElementById("statusAlert");
  box.innerHTML = `<div class="alert ${isError ? 'alert-error' : 'alert-success'}" style="padding: 10px; margin-bottom: 12px; border-radius: 6px; background: ${isError ? '#fee2e2' : '#dcfce7'}; color: ${isError ? '#991b1b' : '#166534'};">${msg}</div>`;
  setTimeout(() => { box.innerHTML = ""; }, 4000);
}

function saveToken() {
  const token = document.getElementById("tenantToken").value.trim();
  localStorage.setItem("tenant_token", token);

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
      tbody.innerHTML = `<tr><td colspan="3">No widgets found for this workspace. Click "+ New Widget" above.</td></tr>`;
      return;
    }

    widgets.forEach(w => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><strong>${w.title}</strong></td>
        <td><code>${w.widget_id}</code></td>
        <td>
          <button class="btn btn-primary" onclick="openFieldConfig('${w.widget_id}', '${w.title.replace(/'/g, "\\'")}')">Fields</button>
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
  const allowed_origins = rawOrigins ? rawOrigins.split(",").map(s => s.trim()).filter(Boolean) : [];

  if (!title) {
    notify("Title is required", true);
    return;
  }

  try {
    const res = await fetch("/widgets", {
      method: "POST",
      headers: getAuthHeader(),
      body: JSON.stringify({ 
        title, 
        widget_type_id: widget_type_id || undefined, 
        allowed_origins 
      })
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }

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
    if (res.status !== 204 && res.status !== 200) throw new Error(`HTTP ${res.status}`);
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
    const wfRes = await fetch(`/widgets/${widgetId}/fields`, { headers: getAuthHeader() });
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
    container.innerHTML = `<p style="font-size:0.85rem;color:#64748b;margin-bottom:12px;">No fields currently configured for this widget.</p>`;
  }

  activeFields.forEach((f, idx) => {
    const fieldName = f.field_name || f.field_definition?.field_name || f.name || f.field_id;
    const div = document.createElement("div");
    div.className = "field-row";
    div.style.cssText = "display: flex; gap: 12px; align-items: center; margin-bottom: 8px;";
    div.innerHTML = `
      <span style="min-width: 140px; font-weight: 500;">${fieldName}</span>
      <code style="font-size: 0.75rem; color: #64748b;">${f.field_id.slice(0, 8)}...</code>
      <label style="font-size: 0.8rem;">Order:
        <input type="number" class="field-order" data-fid="${f.field_id}" value="${Number.isInteger(f.display_order) ? f.display_order : idx}" style="width: 50px; padding: 2px;">
      </label>
      <label style="font-size: 0.8rem;">
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
    const parsedOrder = parseInt(orderInp.value, 10);

    payloadFields.push({
      field_id: orderInp.getAttribute("data-fid"),
      display_order: Number.isNaN(parsedOrder) ? 0 : parsedOrder,
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
  const card = document.getElementById("fieldConfigCard");
  if (card) card.style.display = "none";
  currentWidgetId = null;
}

// ----------------- SUBMISSIONS DASHBOARD ----------------- //

async function loadSubmissions() {
  const tbody = document.getElementById("submissionsTableBody");
  try {
    const res = await fetch("/submissions", { headers: getAuthHeader() });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    const subs = data.submissions || [];

    tbody.innerHTML = "";
    if (subs.length === 0) {
      tbody.innerHTML = `<tr><td colspan="4">No submissions recorded yet.</td></tr>`;
      return;
    }

    subs.forEach(s => {
      const tr = document.createElement("tr");
      const summary = s.field_values ? JSON.stringify(s.field_values).slice(0, 45) + "..." : "No fields";
      const geo = s.geo ? `${s.geo.city || ''} ${s.geo.country || ''}`.trim() : "Direct / Local";
      tr.innerHTML = `
        <td><code>${s.submission_id.slice(0, 8)}...</code></td>
        <td>${summary}</td>
        <td><span class="badge" style="background:#e0f2fe; color:#0369a1; padding:2px 6px; border-radius:4px; font-size:11px;">${geo || "Direct"}</span></td>
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
    const res = await fetch(`/submissions/${subId}`, { headers: getAuthHeader() });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    const panel = document.getElementById("submissionDetailCard");
    const body = document.getElementById("submissionDetailBody");

    body.innerHTML = `
      <p><strong>Submission ID:</strong> <code>${data.submission_id}</code></p>
      <p><strong>Widget ID:</strong> <code>${data.widget_id}</code></p>
      <p><strong>Created At:</strong> ${data.created_at || 'N/A'}</p>
      <h4 style="margin-top:0.75rem;">Submitted Fields:</h4>
      <pre style="background:#f1f5f9; padding:0.75rem; border-radius:4px; margin:0.5rem 0; font-size:12px;">${JSON.stringify(data.fields || data.field_values, null, 2)}</pre>
      <h4 style="margin-top:0.75rem;">Enrichment / Geo:</h4>
      <pre style="background:#f1f5f9; padding:0.75rem; border-radius:4px; margin:0.5rem 0; font-size:12px;">${JSON.stringify(data.geo || {}, null, 2)}</pre>
    `;
    panel.style.display = "block";
  } catch (err) {
    notify(`Error opening submission: ${err.message}`, true);
  }
}

function closeSubmissionDetail() {
  const panel = document.getElementById("submissionDetailCard");
  if (panel) panel.style.display = "none";
}