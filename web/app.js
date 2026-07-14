const state = {
  step: 1,
  connected: false,
  jobId: null,
  summary: null,
  elements: [],
  promptContext: "",
  panelPrompts: {},
  running: false,
  hasQaLlm: false,
  qaModel: null,
};

const STORAGE_KEY = "agentic-pi-migration-config";
const PUBLISH_TIPS = [
  "External LLM co-piloting prompts for IDMP panel AI…",
  "IDMP internal AI creating live trend panels…",
  "Creating Canvas pens and Formula bindings…",
  "Publishing live trend panels to IDMP…",
  "Wiring orthogonal pipelines and equipment…",
];

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
    state.hasQaLlm = Boolean(cfg.has_qa_llm);
    state.qaModel = cfg.qa_llm_model || null;
    const assist = $("external-assist");
    if (assist) {
      assist.checked = Boolean(cfg.has_qa_llm) && cfg.qa_assist_panels !== false;
      assist.disabled = !cfg.has_qa_llm;
    }
    const assistOpt = $("assist-option");
    if (assistOpt && !cfg.has_qa_llm) {
      assistOpt.title = "Set QA_LLM_API_KEY in .env to enable";
    }
  } catch {
    /* offline or server not ready */
  }
}

function setProgress(title, detail) {
  const titleEl = $("progress-title");
  const detailEl = $("progress-detail");
  if (titleEl) titleEl.textContent = title;
  if (detailEl) detailEl.textContent = detail || "";
}

function clearProgressLog() {
  const log = $("progress-log");
  if (log) log.innerHTML = "";
}

function appendProgressLog(message, stage) {
  const log = $("progress-log");
  if (!log || !message) return;
  const li = document.createElement("li");
  if (stage) li.className = `stage-${stage}`;
  const time = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  li.textContent = `${time}  ${message}`;
  log.appendChild(li);
  log.scrollTop = log.scrollHeight;
}

function startPublishTipRotation() {
  let i = 0;
  setProgress("Publishing dashboards", PUBLISH_TIPS[0]);
  appendProgressLog(PUBLISH_TIPS[0], "publish");
  return setInterval(() => {
    i = (i + 1) % PUBLISH_TIPS.length;
    setProgress("Publishing dashboards", PUBLISH_TIPS[i]);
    appendProgressLog(PUBLISH_TIPS[i], "publish");
  }, 2800);
}

function credentials() {
  return {
    idmp_url: $("idmp-url").value.trim(),
    user: $("idmp-user").value.trim(),
    password: $("idmp-password").value,
    api_key: $("idmp-api-key").value.trim(),
    keyword: $("keyword").value.trim() || "",
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
    if (s === n) el.setAttribute("aria-current", "step");
    else el.removeAttribute("aria-current");
  });
  const heading = $(`step-${n}`).querySelector("h2");
  if (heading) requestAnimationFrame(() => heading.focus());
  window.scrollTo({ top: 0, behavior: "smooth" });
}

async function api(path, options = {}) {
  const res = await fetch(path, options);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.detail || data.message || `Request failed (${res.status})`);
  }
  return data;
}

function setLoading(button, loading, label) {
  if (!button) return;
  if (loading) {
    button.dataset.label = button.textContent;
    button.disabled = true;
    button.classList.add("busy");
    button.setAttribute("aria-busy", "true");
    if (label) button.setAttribute("aria-label", label);
  } else {
    button.disabled = false;
    button.classList.remove("busy");
    button.removeAttribute("aria-busy");
    button.removeAttribute("aria-label");
  }
}

function showToast(message, type = "") {
  const toast = document.createElement("div");
  toast.className = `toast ${type}`;
  toast.textContent = message;
  $("toast-region").appendChild(toast);
  window.setTimeout(() => toast.remove(), 4500);
}

function setConnected(connected, label = "") {
  state.connected = connected;
  $("btn-step1-next").disabled = !connected;
  $("connect-hint").textContent = connected
    ? "Connection verified. You can continue."
    : "Test the connection to continue.";
  document.querySelector(".topbar-status").classList.toggle("connected", connected);
  $("connection-label").textContent = connected ? label || "Connected" : "Not connected";
}

function invalidateConnection() {
  if (!state.connected) return;
  setConnected(false);
  $("validate-result").classList.add("hidden");
}

async function discoverIdmp() {
  const button = $("btn-discover");
  const root = $("discovery-results");
  setLoading(button, true, "Finding local IDMP instances");
  root.classList.remove("hidden");
  root.innerHTML = "<span class='status-line'>Scanning common local IDMP ports…</span>";
  try {
    const data = await api("/api/discover");
    if (!data.instances.length) {
      root.innerHTML = "<span class='status-line'>No local IDMP port responded. Start IDMP or enter its mapped port.</span>";
      return;
    }
    root.innerHTML = data.instances.map((item) => `
      <button type="button" class="discovery-item" data-url="${escapeHtml(item.url)}">
        <strong>${escapeHtml(item.url)}</strong>
        <small>${escapeHtml(item.detail || "IDMP responded")}</small>
      </button>`).join("");
    root.querySelectorAll(".discovery-item").forEach((item) => {
      item.addEventListener("click", () => {
        $("idmp-url").value = item.dataset.url;
        root.classList.add("hidden");
        invalidateConnection();
        $("idmp-user").focus();
      });
    });
  } catch (err) {
    root.innerHTML = `<span class="status-line error">${escapeHtml(err.message)}</span>`;
  } finally {
    setLoading(button, false);
  }
}

async function testConnection() {
  const box = $("validate-result");
  const button = $("btn-test");
  setLoading(button, true, "Testing IDMP connection");
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

    setConnected(true, new URL(data.idmp_url).host);
    state.elements = data.elements || [];
    const options = $("target-element-options");
    options.innerHTML = state.elements
      .map((e) => `<option value="${escapeHtml(e.id)}">${escapeHtml(e.name || "")}</option>`)
      .join("");
    if (!$("target-element-id").value && state.elements.length) {
      $("target-element-id").value = state.elements[0].id;
    }

    const items = data.elements
      .map((e) => `<li><code>${e.id}</code> ${escapeHtml(e.name || "")}</li>`)
      .join("");

    box.classList.add("ok");
    const profile = data.profile || {};
    const caps = Object.entries(profile.capabilities || {})
      .filter(([, enabled]) => enabled !== false)
      .map(([name, enabled]) => `<span class="capability">${enabled === null ? "Ready to test" : "Available"} · ${escapeHtml(name.replaceAll("_", " "))}</span>`)
      .join("");
    const warnings = (profile.warnings || []).map((w) => `<li>${escapeHtml(w)}</li>`).join("");
    box.innerHTML = `
      <strong>✓ Connected to ${escapeHtml(data.idmp_url)}</strong>
      <p>Found ${data.element_count} element(s) matching "${escapeHtml(data.keyword)}":</p>
      <ul>${items}</ul>
      ${caps ? `<div class="capability-row">${caps}</div>` : ""}
      ${warnings ? `<ul>${warnings}</ul>` : ""}
    `;
  } catch (err) {
    setConnected(false);
    box.classList.add("error");
    box.innerHTML = `<strong>Connection failed</strong><p>${escapeHtml(err.message)}</p><small>Tip: IDMP normally uses a host port ending in 42. Docker users can use host.docker.internal.</small>`;
  } finally {
    setLoading(button, false);
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
  if (!list) return;
  list.innerHTML = "<span class='status-line'>Loading examples...</span>";

  try {
    const examples = await api("/api/examples");
    list.innerHTML = "";
    for (const ex of examples) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "example-btn";
      btn.disabled = !ex.available;
      btn.innerHTML = `<strong>${escapeHtml(ex.label)}</strong><span>${escapeHtml(ex.blurb || "")}</span>`;
      btn.addEventListener("click", () => ingestExample(ex.id, ex.requires_element !== false));
      list.appendChild(btn);
    }
  } catch (err) {
    list.innerHTML = `<span class="status-line">Could not load examples: ${escapeHtml(err.message)}</span>`;
  }
}

async function ingestExample(exampleId, requiresElement = true) {
  const targetElementId = Number($("target-element-id").value);
  if (requiresElement && (!Number.isInteger(targetElementId) || targetElementId <= 0)) {
    showToast("Choose a target element ID from Step 1.", "error");
    $("target-element-id").focus();
    return;
  }
  const displayName = ($("example-display-name")?.value || "").trim();
  await runIngest(async () => {
    return api("/api/ingest/example", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        example_id: exampleId,
        target_element_id: targetElementId,
        display_name: displayName,
      }),
    });
  }, `Loaded ${exampleId}`);
}

async function ingestZip(file) {
  if (!file.name.toLowerCase().endsWith(".zip")) {
    showToast("Please upload a .zip file.", "error");
    return;
  }

  await runIngest(async () => {
    const form = new FormData();
    form.append("file", file);
    return api("/api/ingest/upload", { method: "POST", body: form });
  }, `Uploaded ${file.name}`);
  // Allow selecting the same zip again later
  const input = $("file-input");
  if (input) input.value = "";
}

async function ingestFiles() {
  const tagsInput = $("file-tags");
  if (!tagsInput?.files?.[0]) {
    showToast("tags.csv (or tags.json) is required.", "error");
    tagsInput?.focus();
    return;
  }
  await runIngest(async () => {
    const form = new FormData();
    form.append("tags", tagsInput.files[0]);
    const display = $("file-display")?.files?.[0];
    const shot = $("file-screenshot")?.files?.[0];
    if (display) form.append("display", display);
    if (shot) form.append("screenshot", shot);
    const name = $("file-name")?.value?.trim();
    const elementId = $("file-element-id")?.value;
    const dtype = $("file-dashboard-type")?.value;
    if (name) form.append("name", name);
    if (elementId) form.append("element_id", elementId);
    if (dtype) form.append("dashboard_type", dtype);
    return api("/api/ingest/files", { method: "POST", body: form });
  }, "Assembled files");
  // Keep form reusable — clear file picks so another selection always fires change
  clearSourceFileInputs({ keepMeta: true });
}

function clearSourceFileInputs({ keepMeta = false } = {}) {
  ["file-input", "file-tags", "file-display", "file-screenshot"].forEach((id) => {
    const el = $(id);
    if (el) el.value = "";
  });
  if (!keepMeta) {
    if ($("file-name")) $("file-name").value = "";
    if ($("file-element-id")) $("file-element-id").value = "";
    if ($("file-dashboard-type")) $("file-dashboard-type").value = "";
  }
}

function showIntakeWarnings(warnings) {
  const box = $("intake-warnings");
  if (!box) return;
  if (!warnings || !warnings.length) {
    box.classList.add("hidden");
    box.innerHTML = "";
    return;
  }
  box.classList.remove("hidden", "ok");
  box.classList.add("error");
  box.innerHTML = `<strong>Accuracy checks</strong><ul>${warnings
    .map((w) => `<li>${escapeHtml(w)}</li>`)
    .join("")}</ul><small>Fix tags / display.json for higher fidelity, or continue if intentional.</small>`;
}

function resetSourceState() {
  state.jobId = null;
  state.summary = null;
  state.panelPrompts = {};
  clearSourceFileInputs();
  if ($("example-display-name")) $("example-display-name").value = "";
  showIntakeWarnings([]);
  const status = $("ingest-status");
  if (status) {
    status.classList.add("hidden");
    status.textContent = "";
  }
  if ($("job-badge")) $("job-badge").classList.add("hidden");
  if ($("review-summary")) $("review-summary").innerHTML = "";
}

async function runIngest(fn, label) {
  const status = $("ingest-status");
  status.classList.remove("hidden", "error", "ok");
  status.textContent = `${label} — processing...`;
  const btnFiles = $("btn-ingest-files");
  if (btnFiles) btnFiles.disabled = true;

  try {
    const data = await fn();
    state.jobId = data.job_id;
    state.summary = data.summary;
    status.classList.add("ok");
    status.textContent = `Ready: ${data.summary.display_count} display(s), ${totalPanels(data.summary)} panel(s) — you can re-upload anytime from Source`;
    showIntakeWarnings(data.intake_warnings || data.summary?.intake_warnings || []);
    renderReview(data.summary);
    $("job-badge").classList.remove("hidden");
    $("job-badge").textContent = `${data.summary.display_count} display(s) · ${totalPanels(data.summary)} panel(s) ready`;
    setStep(3);
  } catch (err) {
    status.classList.add("error");
    status.textContent = `Error: ${err.message}`;
  } finally {
    if (btnFiles) btnFiles.disabled = false;
  }
}

function totalPanels(summary) {
  return (summary.displays || []).reduce((n, d) => n + (d.panel_count || 0), 0);
}

function renderContextStep(summary) {
  const root = $("panel-prompts");
  root.innerHTML = "";

  const canvasTypes = new Set(["process", "p&id", "pid", "pnid"]);
  const hasPanels = (summary.displays || []).some((d) =>
    (d.panels || []).some((p) => !canvasTypes.has(String(p.type || "").toLowerCase())),
  );
  if (!hasPanels) {
    root.innerHTML = "<p class='lead'>The Canvas equipment and flow plan controls this P&amp;ID. There are no AI-generated chart prompts to customize.</p>";
    return;
  }

  for (const d of summary.displays || []) {
    const panels = (d.panels || []).filter(
      (p) => !canvasTypes.has(String(p.type || "").toLowerCase()),
    );
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
  header.textContent = `${summary.display_count} display(s) ready to migrate. Edit names below before continuing.`;
  root.appendChild(header);

  const jobName = document.createElement("label");
  jobName.className = "context-field rename-field";
  jobName.innerHTML = `
    <span>Job / scenario name</span>
    <input type="text" id="rename-scenario-name" value="${escapeHtml(summary.name || "")}" placeholder="Migration job name">
  `;
  root.appendChild(jobName);

  const warnings = summary.intake_warnings || [];
  if (warnings.length) {
    const warn = document.createElement("div");
    warn.className = "result-box error";
    warn.innerHTML = `<strong>Accuracy checks (${warnings.length})</strong><ul>${warnings
      .map((w) => `<li>${escapeHtml(w)}</li>`)
      .join("")}</ul>`;
    root.appendChild(warn);
  }

  for (const d of summary.displays || []) {
    const idx = d.index ?? 0;
    const card = document.createElement("div");
    card.className = "display-card";
    card.dataset.displayIndex = String(idx);
    const pens = d.canvas_pen_count || 0;
    card.innerHTML = `
      <label class="context-field rename-field">
        <span>Display / dashboard name</span>
        <input type="text" data-rename="display-name" data-display-index="${idx}" value="${escapeHtml(d.name || "")}" placeholder="Dashboard name in IDMP">
      </label>
      <div class="display-meta">
        <span class="meta-chip">Element ${d.element_id}</span>
        <span class="meta-chip">${d.dashboard_id ? `Dashboard ${d.dashboard_id}` : "New dashboard"}</span>
        <span class="meta-chip">${escapeHtml(d.dashboard_type || "grid")}</span>
        <span class="meta-chip">${d.panel_count} panel(s)</span>
        ${d.has_canvas_plan ? `<span class="meta-chip">${d.canvas_equipment_count || 0} equipment · ${d.canvas_flow_count || 0} flows${pens ? ` · ${pens} pens` : ""}</span>` : ""}
        ${d.has_screenshot ? '<span class="meta-chip">Screenshot attached</span>' : '<span class="meta-chip">No screenshot</span>'}
      </div>
      <div class="panel-rename-list">
        ${(d.panels || [])
          .map(
            (p) => `
          <label class="context-field rename-field panel-rename">
            <span>Panel <code>${escapeHtml(p.key || "")}</code> · ${escapeHtml(p.type || "")}${(p.pi_tags || []).length ? "" : " · no tags"}</span>
            <input type="text" data-rename="panel-title" data-display-index="${idx}" data-panel-key="${escapeHtml(p.key || "")}" value="${escapeHtml(p.title || "")}" placeholder="Panel title">
          </label>`,
          )
          .join("")}
      </div>
    `;
    root.appendChild(card);
  }
}

function collectRenamePayload() {
  const displaysByIndex = new Map();
  document.querySelectorAll("[data-rename='display-name']").forEach((el) => {
    const index = Number(el.dataset.displayIndex);
    if (!Number.isInteger(index)) return;
    if (!displaysByIndex.has(index)) displaysByIndex.set(index, { index, panels: [] });
    displaysByIndex.get(index).name = el.value.trim();
  });
  document.querySelectorAll("[data-rename='panel-title']").forEach((el) => {
    const index = Number(el.dataset.displayIndex);
    const key = el.dataset.panelKey;
    if (!Number.isInteger(index) || !key) return;
    if (!displaysByIndex.has(index)) displaysByIndex.set(index, { index, panels: [] });
    displaysByIndex.get(index).panels.push({ key, title: el.value.trim() });
  });
  const nameEl = $("rename-scenario-name");
  return {
    name: nameEl ? nameEl.value.trim() : undefined,
    displays: Array.from(displaysByIndex.values()),
  };
}

async function saveReviewNames() {
  if (!state.jobId) return state.summary;
  const payload = collectRenamePayload();
  const data = await api(`/api/jobs/${state.jobId}/rename`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  state.summary = data.summary;
  $("job-badge").textContent = `${data.summary.display_count} display(s) · ${totalPanels(data.summary)} panel(s) ready`;
  return data.summary;
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
    showToast("No migration job loaded. Select a source first.", "error");
    return;
  }

  const progress = $("migrate-progress");
  const resultsEl = $("migrate-results");
  const qaEl = $("qa-results");
  progress.classList.remove("hidden");
  progress.setAttribute("aria-busy", "true");
  state.running = true;
  resultsEl.innerHTML = "";
  if (qaEl) qaEl.innerHTML = "";
  clearProgressLog();
  $("btn-start-over").disabled = true;
  $("btn-step5-back").disabled = true;
  $("btn-run-migration").classList.add("hidden");
  $("publish-status").textContent = "Publishing";

  const tipTimer = startPublishTipRotation();

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
        api_key: creds.api_key,
        create_new: $("create-new").checked,
        workers: 3,
        prompt_context: state.promptContext.trim(),
        panel_prompts: state.panelPrompts,
        run_qa: true,
        external_assist: $("external-assist") ? $("external-assist").checked : null,
      }),
    });

    clearInterval(tipTimer);
    appendProgressLog(
      `Published ${data.migrated} dashboard(s)` + (data.failed ? `, ${data.failed} failed` : ""),
      "publish_done",
    );
    const assisted = (data.results || []).flatMap((r) => r.assist_log || []);
    if (assisted.length) {
      appendProgressLog(
        `External LLM co-pilot touched ${assisted.filter((a) => a.assisted).length}/${assisted.length} panel prompt(s)`,
        "assist",
      );
    }
    renderMigrationResults(data, creds.idmp_url);

    if (data.migrated > 0) {
      $("publish-status").textContent = "QA agent";
      setProgress(
        "LLM quality check",
        state.hasQaLlm
          ? `External judge${state.qaModel ? ` · ${state.qaModel}` : ""} reviewing the IDMP panel…`
          : "Structural checks (no QA_LLM_API_KEY — LLM judge skipped)",
      );
      appendProgressLog("Starting quality-check agent…", "start");
      const qa = await runQaStream(state.jobId);
      renderQaResults(qa);
      $("publish-status").textContent =
        qa?.verdict === "pass" ? "Complete" : qa?.verdict === "fail" ? "QA flagged" : "Needs review";
    } else {
      $("publish-status").textContent = data.failed ? "Needs attention" : "Complete";
    }
  } catch (err) {
    clearInterval(tipTimer);
    $("publish-status").textContent = "Failed";
    resultsEl.innerHTML = `<div class="result-card fail"><h3>Migration failed</h3><p>${escapeHtml(err.message)}</p></div>`;
    $("btn-run-migration").textContent = "Try again";
    $("btn-run-migration").classList.remove("hidden");
  } finally {
    clearInterval(tipTimer);
    progress.classList.add("hidden");
    progress.setAttribute("aria-busy", "false");
    state.running = false;
    $("btn-start-over").disabled = false;
    $("btn-step5-back").disabled = false;
  }
}

async function runQaStream(jobId) {
  const res = await fetch("/api/qa/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      job_id: jobId,
      structural_only: !state.hasQaLlm,
      include_screenshot: true,
    }),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || `QA failed (${res.status})`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let finalResult = null;

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";
    for (const line of lines) {
      if (!line.trim()) continue;
      let event;
      try {
        event = JSON.parse(line);
      } catch {
        continue;
      }
      if (event.type === "progress") {
        setProgress(
          event.stage === "llm_start" || event.stage === "llm_done"
            ? "LLM feedback"
            : "Quality check",
          event.message || "",
        );
        appendProgressLog(event.message || event.stage, event.stage);
        if (event.judgment) {
          appendProgressLog(
            `LLM draft · score ${event.judgment.overall_score ?? "—"} · ${(event.judgment.issues || [])[0] || "rubric scored"}`,
            "llm_done",
          );
          // Live preview while still loading
          renderQaResults({
            verdict: event.judgment.verdict || "needs_review",
            overall_score: event.judgment.overall_score,
            pass_score: 75,
            strengths: event.judgment.strengths,
            issues: event.judgment.issues,
            fixes: event.judgment.fixes,
            dimensions: event.judgment.dimensions,
            llm: { provider: event.provider, model: event.model, judgment: event.judgment },
            structural: event.structural,
            preview: true,
          });
        }
        if (event.structural && event.stage === "structural_done") {
          const failed = (event.structural.critical_failures || []).join(", ") || "none";
          appendProgressLog(`Critical structural failures: ${failed}`, "structural_done");
        }
      } else if (event.type === "final") {
        finalResult = event.result;
        appendProgressLog(
          `QA verdict: ${finalResult.verdict} (${finalResult.overall_score}/${finalResult.pass_score})`,
          "done",
        );
      } else if (event.type === "error") {
        appendProgressLog(event.message || "QA error", "error");
        throw new Error(event.message || "QA stream error");
      }
    }
  }
  return finalResult;
}

function renderQaResults(qa) {
  const root = $("qa-results");
  if (!root || !qa) return;
  const verdict = qa.verdict || "needs_review";
  const llm = qa.llm || {};
  const judgment = llm.judgment || {};
  const dims = qa.dimensions || judgment.dimensions || [];
  const strengths = qa.strengths || judgment.strengths || [];
  const issues = qa.issues || judgment.issues || [];
  const fixes = qa.fixes || judgment.fixes || [];
  const modelLine = llm.model
    ? `${llm.provider || "llm"} · ${llm.model}`
    : qa.preview
      ? "LLM feedback streaming…"
      : "structural only";

  root.innerHTML = `
    <div class="qa-card ${escapeHtml(verdict)}">
      <h3>
        ${qa.preview ? "Live LLM feedback" : "QA agent report"}
        <span class="qa-score">${escapeHtml(String(verdict).replace("_", " "))} · ${escapeHtml(String(qa.overall_score ?? "—"))}/${escapeHtml(String(qa.pass_score ?? 75))}</span>
      </h3>
      <div class="qa-meta">${escapeHtml(modelLine)}${qa.primary?.url ? ` · <a href="${escapeHtml(qa.primary.url)}" target="_blank" rel="noopener">open panel</a>` : ""}</div>
      ${
        dims.length
          ? `<div class="qa-dims">${dims
              .map(
                (d) =>
                  `<div class="qa-dim"><strong>${escapeHtml(String(d.score ?? "—"))}</strong>${escapeHtml(d.id || "")}${d.notes ? `<div>${escapeHtml(d.notes)}</div>` : ""}</div>`,
              )
              .join("")}</div>`
          : ""
      }
      ${
        strengths.length
          ? `<strong style="font-size:.82rem">Strengths</strong><ul class="qa-list">${strengths
              .slice(0, 5)
              .map((s) => `<li>${escapeHtml(s)}</li>`)
              .join("")}</ul>`
          : ""
      }
      ${
        issues.length
          ? `<strong style="font-size:.82rem">Issues</strong><ul class="qa-list">${issues
              .slice(0, 6)
              .map((s) => `<li>${escapeHtml(s)}</li>`)
              .join("")}</ul>`
          : ""
      }
      ${
        fixes.length
          ? `<strong style="font-size:.82rem">Suggested fixes</strong><ul class="qa-list">${fixes
              .slice(0, 5)
              .map((s) => `<li>${escapeHtml(s)}</li>`)
              .join("")}</ul>`
          : ""
      }
    </div>`;
}

function renderPublishSummary() {
  const displays = state.summary?.display_count || 0;
  const panels = state.summary ? totalPanels(state.summary) : 0;
  const canvas = (state.summary?.displays || []).filter((d) => (d.dashboard_type || "grid") === "canvas").length;
  $("publish-summary").innerHTML = `
    <div class="summary-stat"><strong>${displays}</strong><span>displays</span></div>
    <div class="summary-stat"><strong>${panels}</strong><span>live panels</span></div>
    <div class="summary-stat"><strong>${canvas}</strong><span>Canvas P&amp;IDs</span></div>`;
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
      ${r.edit_url ? `<p><a href="${escapeHtml(r.edit_url)}" target="_blank" rel="noopener">Open Canvas editor</a></p>` : ""}
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
  if (!zone || !input) return;

  const openPicker = () => {
    // Always clear so choosing the same file again triggers change
    input.value = "";
    input.click();
  };

  zone.addEventListener("click", openPicker);
  zone.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      openPicker();
    }
  });
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
  $("btn-discover").addEventListener("click", discoverIdmp);
  ["idmp-url", "idmp-user", "idmp-password", "idmp-api-key", "keyword"].forEach((id) => {
    $(id).addEventListener("input", invalidateConnection);
  });
  document.querySelectorAll(".stepper .step").forEach((step) => {
    step.addEventListener("click", () => {
      if (state.running) return;
      const target = Number(step.dataset.step);
      // Allow jumping back to Source anytime to re-upload
      if (target <= state.step || (target === 2 && state.connected)) setStep(target);
    });
  });
  $("btn-step1-next").addEventListener("click", () => {
    if (!state.connected) return;
    setStep(2);
  });
  $("btn-step2-back").addEventListener("click", () => setStep(1));
  if ($("btn-clear-source")) {
    $("btn-clear-source").addEventListener("click", () => {
      resetSourceState();
      showToast("Source cleared — upload zip or files again.", "ok");
      setStep(2);
    });
  }
  $("btn-step3-back").addEventListener("click", () => setStep(2));
  $("btn-step3-next").addEventListener("click", async () => {
    try {
      const summary = await saveReviewNames();
      if (summary) renderContextStep(summary);
      $("prompt-context").value = state.promptContext;
      setStep(4);
    } catch (err) {
      showToast(err.message || "Could not save names", "error");
    }
  });
  $("btn-step4-back").addEventListener("click", () => setStep(3));
  $("btn-step4-next").addEventListener("click", () => {
    state.promptContext = $("prompt-context").value;
    collectPanelPrompts();
    renderPublishSummary();
    setStep(5);
  });
  $("btn-step5-back").addEventListener("click", () => {
    if (!state.running) setStep(4);
  });
  $("btn-run-migration").addEventListener("click", runMigration);
  if ($("btn-ingest-files")) {
    $("btn-ingest-files").addEventListener("click", ingestFiles);
  }
  // Re-pick individual files without stuck input cache
  ["file-tags", "file-display", "file-screenshot"].forEach((id) => {
    const el = $(id);
    if (!el) return;
    el.addEventListener("click", () => {
      el.value = "";
    });
  });
  $("btn-start-over").addEventListener("click", () => {
    if ((state.jobId || state.summary) && !window.confirm("Clear this migration plan and start over?")) return;
    state.promptContext = "";
    resetSourceState();
    $("migrate-results").innerHTML = "";
    if ($("qa-results")) $("qa-results").innerHTML = "";
    $("migrate-progress").classList.add("hidden");
    clearProgressLog();
    $("btn-open-idmp").classList.add("hidden");
    $("btn-run-migration").classList.remove("hidden");
    $("btn-run-migration").textContent = "Publish dashboards";
    $("publish-status").textContent = "Ready";
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
