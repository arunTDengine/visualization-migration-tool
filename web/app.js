const state = {
  step: 1,
  connected: false,
  jobId: null,
  summary: null,
  promptContext: "",
  panelPrompts: {},
};

const STORAGE_KEY = "agentic-pi-migration-config";

function $(id) {
  return document.getElementById(id);
}

function saveConfig() {
  localStorage.setItem(
    STORAGE_KEY,
    JSON.stringify({
      idmp_url: $("idmp-url").value,
      user: $("idmp-user").value,
      keyword: $("keyword").value,
    }),
  );
}

function loadConfig() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return;
    const cfg = JSON.parse(raw);
    if (cfg.idmp_url) $("idmp-url").value = cfg.idmp_url;
    if (cfg.user) $("idmp-user").value = cfg.user;
    if (cfg.keyword) $("keyword").value = cfg.keyword;
  } catch {
    /* ignore */
  }
}

async function loadDefaults() {
  try {
    const res = await fetch("/api/config");
    const cfg = await res.json();
    if (!$("idmp-url").value) $("idmp-url").value = cfg.idmp_url || "";
    if (!$("idmp-user").value) $("idmp-user").value = cfg.user || "";
  } catch {
    /* offline or server not ready */
  }
}

function credentials() {
  return {
    idmp_url: $("idmp-url").value.trim(),
    user: $("idmp-user").value.trim(),
    password: $("idmp-password").value,
    keyword: $("keyword").value.trim() || "SCE",
  };
}

function setStep(n) {
  state.step = n;
  document.querySelectorAll(".step-panel").forEach((el) => el.classList.remove("active"));
  $(`step-${n}`).classList.add("active");

  document.querySelectorAll(".stepper .step").forEach((el) => {
    const s = Number(el.dataset.step);
    el.classList.toggle("active", s === n);
    el.classList.toggle("done", s < n);
  });
}

async function api(path, options = {}) {
  const res = await fetch(path, options);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.detail || data.message || `Request failed (${res.status})`);
  }
  return data;
}

async function testConnection() {
  const box = $("validate-result");
  box.classList.remove("hidden", "ok", "error");
  box.textContent = "Testing connection...";

  try {
    saveConfig();
    const body = credentials();
    const data = await api("/api/validate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });

    state.connected = true;
    $("btn-step1-next").disabled = false;

    const items = data.elements
      .map((e) => `<li><code>${e.id}</code> ${escapeHtml(e.name || "")}</li>`)
      .join("");

    box.classList.add("ok");
    box.innerHTML = `
      <strong>Connected to ${escapeHtml(data.idmp_url)}</strong>
      <p>Found ${data.element_count} element(s) matching "${escapeHtml(data.keyword)}":</p>
      <ul>${items}</ul>
    `;
  } catch (err) {
    state.connected = false;
    $("btn-step1-next").disabled = true;
    box.classList.add("error");
    box.innerHTML = `<strong>Connection failed</strong><p>${escapeHtml(err.message)}</p>`;
  }
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

async function loadExamples() {
  const list = $("example-list");
  list.innerHTML = "<span class='status-line'>Loading examples...</span>";

  try {
    const examples = await api("/api/examples");
    list.innerHTML = "";
    for (const ex of examples) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "example-btn";
      btn.disabled = !ex.available;
      btn.innerHTML = `<strong>${escapeHtml(ex.id)}</strong><span>${escapeHtml(ex.label)}</span>`;
      btn.addEventListener("click", () => ingestExample(ex.id));
      list.appendChild(btn);
    }
  } catch (err) {
    list.innerHTML = `<span class="status-line">Could not load examples: ${escapeHtml(err.message)}</span>`;
  }
}

async function ingestExample(exampleId) {
  await runIngest(async () => {
    return api("/api/ingest/example", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ example_id: exampleId }),
    });
  }, `Loaded example: ${exampleId}`);
}

async function ingestZip(file) {
  if (!file.name.toLowerCase().endsWith(".zip")) {
    alert("Please upload a .zip file");
    return;
  }

  await runIngest(async () => {
    const form = new FormData();
    form.append("file", file);
    return api("/api/ingest/upload", { method: "POST", body: form });
  }, `Uploaded ${file.name}`);
}

async function runIngest(fn, label) {
  const status = $("ingest-status");
  status.classList.remove("hidden");
  status.textContent = `${label} — processing...`;

  try {
    const data = await fn();
    state.jobId = data.job_id;
    state.summary = data.summary;
    status.textContent = `Ready: ${data.summary.display_count} display(s), ${totalPanels(data.summary)} panel(s)`;
    renderReview(data.summary);
    setStep(3);
  } catch (err) {
    status.textContent = `Error: ${err.message}`;
  }
}

function totalPanels(summary) {
  return (summary.displays || []).reduce((n, d) => n + (d.panel_count || 0), 0);
}

function renderContextStep(summary) {
  const root = $("panel-prompts");
  root.innerHTML = "";

  const hasPanels = (summary.displays || []).some((d) => (d.panels || []).length);
  if (!hasPanels) {
    root.innerHTML = "<p class='lead'>No panels to customize — global context above still applies.</p>";
    return;
  }

  for (const d of summary.displays || []) {
    const panels = d.panels || [];
    if (!panels.length) continue;

    const section = document.createElement("div");
    section.className = "display-card";
    section.innerHTML = `<h3>${escapeHtml(d.name)}</h3>`;
    root.appendChild(section);

    for (const p of panels) {
      const field = document.createElement("label");
      field.className = "context-field panel-prompt-field";
      field.innerHTML = `
        <span class="panel-prompt-label">${escapeHtml(p.title)} <code>${escapeHtml(p.type)}</code></span>
        <textarea data-panel-key="${escapeHtml(p.key)}" rows="2" placeholder="Panel-specific AI prompt">${escapeHtml(state.panelPrompts[p.key] ?? p.prompt ?? "")}</textarea>
      `;
      section.appendChild(field);
    }
  }
}

function collectPanelPrompts() {
  const prompts = {};
  document.querySelectorAll("#panel-prompts textarea[data-panel-key]").forEach((el) => {
    const key = el.dataset.panelKey;
    const value = el.value.trim();
    if (key && value) prompts[key] = value;
  });
  state.panelPrompts = prompts;
  return prompts;
}

function renderReview(summary) {
  const root = $("review-summary");
  root.innerHTML = "";

  const header = document.createElement("p");
  header.className = "lead";
  header.textContent = `${summary.display_count} display(s) ready to migrate.`;
  root.appendChild(header);

  for (const d of summary.displays || []) {
    const card = document.createElement("div");
    card.className = "display-card";
    card.innerHTML = `
      <h3>${escapeHtml(d.name)}</h3>
      <div class="display-meta">
        Element ${d.element_id}
        ${d.dashboard_id ? ` · Dashboard ${d.dashboard_id}` : " · New dashboard"}
        · Theme: ${escapeHtml(d.theme || "control-room")}
        · ${d.panel_count} panel(s)
        ${d.has_screenshot ? " · Screenshot attached" : ""}
      </div>
      <div class="panel-tags">
        ${(d.panels || [])
          .map(
            (p) =>
              `<span class="tag" title="${escapeHtml((p.pi_tags || []).join(", "))}">${escapeHtml(p.title)} (${escapeHtml(p.type)})</span>`,
          )
          .join("")}
      </div>
    `;
    root.appendChild(card);
  }
}

async function loadTypeMap() {
  try {
    const rows = await api("/api/map-types");
    const tbody = $("type-map-table").querySelector("tbody");
    tbody.innerHTML = rows
      .map((r) => `<tr><td>${escapeHtml(r.pi_vision)}</td><td><code>${escapeHtml(r.idmp)}</code></td></tr>`)
      .join("");
  } catch {
    /* optional */
  }
}

async function runMigration() {
  if (!state.jobId) {
    alert("No migration job loaded. Go back and select a source.");
    return;
  }

  const progress = $("migrate-progress");
  const resultsEl = $("migrate-results");
  progress.classList.remove("hidden");
  resultsEl.innerHTML = "";
  $("btn-start-over").disabled = true;

  try {
    saveConfig();
    const creds = credentials();
    const data = await api("/api/migrate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        job_id: state.jobId,
        idmp_url: creds.idmp_url,
        user: creds.user,
        password: creds.password,
        create_new: $("create-new").checked,
        workers: 3,
        prompt_context: state.promptContext.trim(),
        panel_prompts: state.panelPrompts,
      }),
    });

    progress.classList.add("hidden");
    renderMigrationResults(data, creds.idmp_url);
  } catch (err) {
    progress.classList.add("hidden");
    resultsEl.innerHTML = `<div class="result-card fail"><h3>Migration failed</h3><p>${escapeHtml(err.message)}</p></div>`;
  } finally {
    $("btn-start-over").disabled = false;
  }
}

function renderMigrationResults(data, idmpUrl) {
  const root = $("migrate-results");
  root.innerHTML = "";

  if (data.errors && data.errors.length) {
    for (const err of data.errors) {
      const card = document.createElement("div");
      card.className = "result-card fail";
      card.innerHTML = `<h3>Error</h3><p>${escapeHtml(err)}</p>`;
      root.appendChild(card);
    }
  }

  for (const r of data.results || []) {
    const card = document.createElement("div");
    card.className = "result-card ok";
    card.innerHTML = `
      <h3>${escapeHtml(r.action || "Migrated")}: dashboard ${r.dashboard_id}</h3>
      <p>${r.panel_count || 0} panel(s)</p>
      <p><a href="${escapeHtml(r.url)}" target="_blank" rel="noopener">${escapeHtml(r.url)}</a></p>
    `;
    root.appendChild(card);
  }

  if (data.migrated > 0) {
    $("btn-open-idmp").classList.remove("hidden");
    $("btn-open-idmp").onclick = () => window.open(idmpUrl.replace(/\/$/, ""), "_blank");
  }

  const summary = document.createElement("p");
  summary.className = "lead";
  summary.textContent = `Completed: ${data.migrated} succeeded, ${data.failed} failed.`;
  root.prepend(summary);
}

function setupDropzone() {
  const zone = $("dropzone");
  const input = $("file-input");

  zone.addEventListener("click", () => input.click());
  input.addEventListener("change", () => {
    if (input.files[0]) ingestZip(input.files[0]);
  });

  zone.addEventListener("dragover", (e) => {
    e.preventDefault();
    zone.classList.add("dragover");
  });
  zone.addEventListener("dragleave", () => zone.classList.remove("dragover"));
  zone.addEventListener("drop", (e) => {
    e.preventDefault();
    zone.classList.remove("dragover");
    const file = e.dataTransfer.files[0];
    if (file) ingestZip(file);
  });
}

function bindEvents() {
  $("btn-test").addEventListener("click", testConnection);
  $("btn-step1-next").addEventListener("click", () => {
    if (!state.connected) return;
    setStep(2);
  });
  $("btn-step2-back").addEventListener("click", () => setStep(1));
  $("btn-step3-back").addEventListener("click", () => setStep(2));
  $("btn-step3-next").addEventListener("click", () => {
    if (state.summary) renderContextStep(state.summary);
    $("prompt-context").value = state.promptContext;
    setStep(4);
  });
  $("btn-step4-back").addEventListener("click", () => setStep(3));
  $("btn-step4-next").addEventListener("click", () => {
    state.promptContext = $("prompt-context").value;
    collectPanelPrompts();
    setStep(5);
    runMigration();
  });
  $("btn-start-over").addEventListener("click", () => {
    state.jobId = null;
    state.summary = null;
    state.promptContext = "";
    state.panelPrompts = {};
    $("ingest-status").classList.add("hidden");
    $("migrate-results").innerHTML = "";
    $("migrate-progress").classList.add("hidden");
    $("btn-open-idmp").classList.add("hidden");
    setStep(1);
  });

  $("connect-form").addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      testConnection();
    }
  });
}

document.addEventListener("DOMContentLoaded", async () => {
  loadConfig();
  await loadDefaults();
  bindEvents();
  setupDropzone();
  loadExamples();
  loadTypeMap();
});
