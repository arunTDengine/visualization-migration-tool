# Agentic Visualization Migration Upgrade

**Product:** Agentic Visualization Migration Upgrade  
**Vendor:** TDengine  
**Audience:** Internal engineering, solutions, and customer-success teams  
**Status:** Ready for internal delivery  

**Runs standalone** — Use the browser **Migration Studio**, the **CLI**, or **Docker**. Optional agent docs (`AGENTS.md`) exist only if you choose to automate with an LLM coding agent.

Recreate PI Vision–style operator displays on **TDengine IDMP** when historian tags already map to IDMP elements. Publish editable **grid dashboards** and **Canvas P&IDs** over the IDMP REST API. No container shell access. No manual redraw of the customer display.

---

## What you get

| Surface | How to run | Who it’s for |
|---------|------------|--------------|
| **Migration Studio** | `./run-ui.sh` → `http://127.0.0.1:8765` | Demos, workshops, interactive migrations |
| **CLI** | `./run.sh …` | Scripts, CI, repeatable customer jobs |
| **Docker** | `docker compose up --build` | Shared / locked-down environments |

| Capability | Description |
|------------|-------------|
| Zip or individual file ingest | `tags.csv` / `tags.json`, optional `display.json`, optional screenshot |
| Built-in walkthroughs | One grid + one Canvas example, retargeted to a live IDMP element |
| Rename before publish | Edit job name, dashboard names, and panel titles in Review |
| Always-new dashboards | Creates a new dashboard by default; if the name exists, appends `· xxxx` |
| AF-style tag resolve | Paths like `TAG.PV` bind to child-element leaf attributes (e.g. `val`) |
| Grid + Canvas publish | KPI / gauge / trend panels and editable Meta2d P&IDs |
| Optional external LLM | Prompt co-pilot + post-publish QA scoring |
| Auth | IDMP password login or API key (Bearer), REST only |

**Prerequisite:** Source tags and data already match (or resolve under) IDMP elements. This product migrates *displays*, not historian topology.

---

## Requirements

| Component | Notes |
|-----------|--------|
| Python 3.10+ | Local Studio / CLI (venv created by `./run-ui.sh` / `./run.sh`) |
| Running IDMP | Web/API port typically ending in **42** (not TSDB **41**) |
| Network | Tool host → IDMP REST |
| Browser | Any modern browser for Studio |
| Optional | OpenAI-compatible or Anthropic API key for co-pilot / QA |
| Optional | Docker Desktop for Compose deployment |

---

## Quick start (standalone)

### 1. Get the repo and configure

```bash
git clone https://github.com/arunTDengine/agentic-pi-migration-tool.git
cd agentic-pi-migration-tool
cp .env.example .env
```

Edit `.env`:

```env
IDMP_URL=http://localhost:6842
IDMP_USER=you@company.com
IDMP_PASSWORD=••••••••
# IDMP_API_KEY=          # alternative to password

# Optional external LLM (Studio co-pilot + QA)
QA_LLM_API_KEY=
QA_LLM_PROVIDER=openai
QA_LLM_MODEL=gpt-4.1
QA_LLM_ASSIST_PANELS=1
QA_LLM_POWER=1
```

### 2. Launch Migration Studio

```bash
./run-ui.sh                 # macOS / Linux  →  http://127.0.0.1:8765
# .\run-ui.ps1              # Windows PowerShell
```

Or with Docker:

```bash
docker compose up --build
# Studio → http://localhost:8765
```

Open the URL in a browser. You do not need Cursor, VS Code, or any other IDE.

### 3. Run a migration in the Studio

1. **Connect** — enter IDMP URL and credentials; search for a site / element  
2. **Source** — upload a zip, drop individual files, or load a built-in walkthrough  
3. **Review** — rename displays/panels if needed; leave **Always create a new dashboard** on  
4. **Refine** — optional design direction and panel prompts  
5. **Publish** — create dashboards; open the returned IDMP URLs  

---

## Migration Studio

Five-step workflow for demos and customer workshops.

| Step | Purpose |
|------|---------|
| **Connect** | Discover or enter IDMP URL; password or API-key auth; element search |
| **Source** | Zip package, individual files, or hardcoded walkthroughs |
| **Review** | Rename job / dashboards / panels; accuracy warnings; create-new + LLM toggles |
| **Refine** | Global design direction and optional per-panel prompts |
| **Publish** | Live progress, results, streaming QA feedback |

**Reusable uploads:** Clear files and re-upload from Source without restarting the app.

### Source options

| Option | Use when |
|--------|----------|
| **Zip upload** | Full customer folder (tags + display + screenshot) |
| **Individual files** | You only have `tags.csv` (and optionally `display.json` / screenshot). Set display name, element ID, and dashboard type in the form |
| **Hardcoded walkthroughs** | Demo the product path without a customer package. Pick **target element ID** from Connect; optionally override **display name** |

| Walkthrough | Type | What it shows |
|-------------|------|----------------|
| Example · Grid dashboard | Grid | KPI / gauge / trend publish path |
| Example · Canvas P&ID | Canvas | Animated process Canvas + embedded trend |

Walkthrough placeholder tags (e.g. `quality_index`) are **remapped at publish** to live child attributes under the target element. Production jobs should still ship real `tags.csv` series.

### Naming and dashboard create policy

- In **Review**, edit the job name, each dashboard / display name, and each panel title before continuing.  
- **Always create a new dashboard** is on by default — existing dashboard IDs in a scenario are not overwritten.  
- If a dashboard with the same name already exists on that element, publish appends a random suffix, e.g. `Plant Ops · a3f9`.

### Tag binding (AF-style element trees)

Tags are resolved against the element tree when publishing:

| Tag form | Resolution |
|----------|------------|
| `UNIT101.PV` | Walk children `UNIT101` → `PV` → leaf attribute (usually `val`) |
| Exact attribute on host / leaf | Bound when the path exists |
| Unknown walkthrough placeholders | Sample distinct live leaves under the target so demos still publish |

Historian series bindings win over model-invented attribute names.

---

## Input contract

Accuracy comes from structured assets — not from a long chat prompt alone.

| File | Required | Role |
|------|----------|------|
| `tags.csv` / `tags.json` | **Yes** | Panel keys, titles, types, `element_id`, `pi_tags` |
| `display.json` | Recommended for P&ID | Canvas plan, placements, time window, theme |
| `screenshot.*` | Recommended | Human visual reference (not computer vision) |

### `tags.csv` columns

| Column | Required | Description |
|--------|----------|-------------|
| `panel_key` | Yes | Stable key referenced by layout / Canvas placements |
| `title` | Yes | Operator-facing panel title |
| `type` | Yes | `trend`, `kpi`, `gauge`, `bar`, `pie`, … or `pnid`/`process` for Canvas |
| `element_id` | Yes* | IDMP element (`*` or set once in `display.json` / Studio form) |
| `pi_tags` | Strongly recommended | Pipe-separated paths, e.g. `UNIT101.PV\|UNIT101.MV` |
| `prompt` | Optional | Panel-specific guidance |

```csv
panel_key,title,type,element_id,pi_tags,prompt
product_flows,Flow Control Valve Readings,trend,1234567890,UNIT101.PV|UNIT101.MV,multi-series product flows
feed_flow,Feed Flow,trend,1234567890,FEED01.PV|FEED01.SV,scheduled vs actual
```

Folder layout and Canvas fields: **[harness/FOLDER_SPEC.md](harness/FOLDER_SPEC.md)**.

### Accuracy policy

- Tag series bindings win over model-invented attributes  
- Intake surfaces warnings (missing tags, empty Canvas plan, absolute time windows, no screenshot)  
- Optional external LLM polishes prompts / chart chrome; it does **not** invent tags  
- Optional QA agent scores topology, live data, completeness, and demo-readiness after publish  

---

## CLI (no browser required)

Configure `.env`, then:

```bash
./run.sh discover
./run.sh validate --keyword YOUR_SITE

./run.sh ingest-folder /path/to/display -o scenarios/generated.json
./run.sh migrate scenarios/generated.json --report reports/latest.json
# Default: create a new dashboard (add --update-existing only to overwrite by ID)

./run.sh qa reports/latest.json --folder /path/to/display -o reports/latest-qa.json

# End-to-end harness
./harness/run-agent-workflow.sh full /path/to/display
```

| Document | Purpose |
|----------|---------|
| [harness/FOLDER_SPEC.md](harness/FOLDER_SPEC.md) | Customer package schema |
| [harness/QA_AGENT.md](harness/QA_AGENT.md) | External LLM quality-check |
| [harness/run-agent-workflow.sh](harness/run-agent-workflow.sh) | validate → ingest → migrate → qa |
| [AGENTS.md](AGENTS.md) | **Optional** — only if using Cursor or another coding agent |

---

## Architecture

```text
Customer package                    TDengine IDMP
┌─────────────────────┐            ┌──────────────────────────┐
│ tags.csv            │            │ Elements / attributes    │
│ display.json        │── ingest ─▶│ REST login / Bearer      │
│ screenshot (ref)    │            │ Panels + dashboards      │
└─────────────────────┘            │ Canvas (Meta2d)          │
          │                        └──────────────────────────┘
          ▼                                    ▲
  scenario.json ── migrate (REST) ─────────────┘
          │
          ├─ Tag resolve (AF paths → leaf attrs)
          ├─ Unique dashboard name (·xxxx if needed)
          ├─ IDMP panel AI (optional path)
          ├─ External LLM co-pilot (optional)
          └─ QA agent (optional post-check)
```

Sign-in is IDMP REST login (`POST /api/v1/users/login`) or API-key Bearer. The tool does not use the IDMP browser session cookie.

IDMP host ports ending in **42** are the web/API surface. Ports ending in **41** are TSDB REST/SQL and are not used for dashboard publish.

---

## Configuration reference

| Variable | Default | Description |
|----------|---------|-------------|
| `IDMP_URL` | `http://localhost:6042` | IDMP base URL |
| `IDMP_USER` / `IDMP_PASSWORD` | — | Password auth |
| `IDMP_API_KEY` | — | Alternative Bearer auth |
| `IDMP_AUTO_DISCOVER` | `1` | Probe common local ports |
| `IDMP_PUBLIC_URL` | — | Browser-facing URL when API is on a private host |
| `UI_HOST` / `UI_PORT` | `127.0.0.1` / `8765` | Studio bind |
| `MAX_UPLOAD_MB` | `100` | Upload size limit |
| `QA_LLM_API_KEY` | — | External LLM for co-pilot + QA |
| `QA_LLM_PROVIDER` | `openai` | `openai` or `anthropic` |
| `QA_LLM_MODEL` | `gpt-4.1` | Model id |
| `QA_LLM_ASSIST_PANELS` | `1` | Enable panel co-pilot |
| `QA_LLM_POWER` | `1` | Richer briefs and series polish |
| `QA_LLM_TIMEOUT` | `180` | Seconds |
| `QA_PASS_SCORE` | `75` | QA pass threshold |

Complete template: **[.env.example](.env.example)**.

---

## Docker notes

- Compose maps Studio to host port `8765` and persists uploads.  
- If IDMP runs on the host, keep `IDMP_URL=http://localhost:…42`; the container resolves localhost via `host.docker.internal`.  
- If IDMP is another Compose service, set `IDMP_URL` to the service URL and `IDMP_PUBLIC_URL` to the browser URL for generated links.

---

## Verify installation

```bash
./run.sh discover
./run.sh validate --keyword YOUR_SITE
./run-ui.sh   # then:
curl -s http://127.0.0.1:8765/api/health
```

Expected health response includes `"status":"ok"`.

---

## Support and ownership

| Item | Detail |
|------|--------|
| Repository | https://github.com/arunTDengine/agentic-pi-migration-tool |
| Primary path (no IDE) | `./run-ui.sh` → Migration Studio in a browser |
| Automation | `./run.sh` and `./harness/run-agent-workflow.sh` |
| Internal delivery | Configure `.env`, launch Studio, Connect → walkthrough or customer package → Review names → Publish |

Optional: for agent-assisted delivery inside Cursor, load **[AGENTS.md](AGENTS.md)** first. Day-to-day use does not depend on it.
