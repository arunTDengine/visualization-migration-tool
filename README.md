# Agentic PI Migration Upgrade

**Agentic Migration** for PI Vision → TDengine IDMP: an AI-assisted, API-driven tool that recreates historian displays when tags and data already match.

No container shell access. No manual dashboard clicking. Point it at a running IDMP instance, provide a display spec (PI tags + panel types + layout), and the agent builds live dashboards via REST.

## Migration Studio (easiest setup)

Start the wizard in your browser — no CLI commands required:

```bash
git clone https://github.com/arunTDengine/agentic-pi-migration-tool.git
cd agentic-pi-migration-tool
cp .env.example .env    # optional: pre-fill IDMP_URL and IDMP_USER

./run-ui.sh                     # macOS / Linux
# .\run-ui.ps1                  # Windows PowerShell
# Open http://127.0.0.1:8765
```

The responsive browser UI walks through five guided steps:

1. **Connect** — auto-discover a local IDMP or enter its URL; use password or API-key auth
2. **Source** — upload a `.zip` of your customer folder, or pick a built-in example
3. **Review** — confirm displays, panels, and tag mappings
4. **Refine** — optionally guide panel and Canvas generation
5. **Publish** — confirm the plan, migrate, and open live dashboard links

`run-ui.sh` creates a local `.venv` and installs dependencies automatically on first run.

### One-command Docker deployment

Docker Desktop works the same way on Windows, macOS, and Linux:

```bash
docker compose up --build
# Open http://localhost:8765
```

The Compose file persists uploads, includes a healthcheck, and maps
`host.docker.internal` on Linux. If IDMP runs on the host, enter its normal
browser URL such as `http://localhost:7142`; the container translates localhost
internally. If IDMP is another Compose service, set:

```env
IDMP_URL=http://your-idmp-service:6042
IDMP_PUBLIC_URL=http://localhost:7142
```

`IDMP_PUBLIC_URL` keeps generated dashboard links browser-accessible while the
tool uses the private service URL for API calls.

### Local IDMP compatibility

Migration Studio accepts URLs with or without `http://` and with or without an
`/api/v1` suffix. It probes current and legacy API roots, supports common token
response formats, password or API-key auth, request timeouts, and automatic
discovery across common local IDMP ports.

This means locally deployed **TDengine IDMP** versions exposing element, panel,
and dashboard REST APIs. It does not mean bare TDengine TSDB: port `xx41`
provides the TSDB REST/SQL service, while this tool needs the IDMP web/API port,
normally `xx42`.

```bash
./run.sh discover
./run.sh validate --keyword SCE
```

## Agent harness

AI agents (Cursor, CI, MCP) should read **[AGENTS.md](AGENTS.md)** first.

| Harness file | Purpose |
|--------------|---------|
| [AGENTS.md](AGENTS.md) | Primary agent instructions |
| [harness/AGENT_CONTEXT.md](harness/AGENT_CONTEXT.md) | Extended reference |
| [harness/FOLDER_SPEC.md](harness/FOLDER_SPEC.md) | Customer folder + tags.csv spec |
| [harness/run-agent-workflow.sh](harness/run-agent-workflow.sh) | End-to-end wrapper script |
| [.cursor/skills/agentic-pi-migration/SKILL.md](.cursor/skills/agentic-pi-migration/SKILL.md) | Cursor skill |

```bash
chmod +x harness/run-agent-workflow.sh
./harness/run-agent-workflow.sh full /path/to/customer-folder
```

## What it does

```
PI Vision display inventory          IDMP asset model (elements + attributes)
         │                                        │
         └──────────► scenario JSON ◄─────────────┘
                           │
                           ▼
              Agentic PI Migration Upgrade
                • login via REST
                • AI panel generation per symbol
                • editable Canvas P&ID generation
                • 15-minute live window + 30s resolution
                • themed 24-column grid layout
                • PUT dashboard (update or create)
                           │
                           ▼
                 Live IDMP dashboards
```

## PI Vision → IDMP mapping

| PI Vision symbol | IDMP panel |
|------------------|------------|
| Trend | `line` |
| Gauge | `gauge` |
| Value / KPI | `stat` |
| Bar | `bar` |
| Pie | `pie` |
| XY Plot | `scatter` |
| State / timeline | `state-history` |
| P&ID / process graphic | IDMP `CANVAS` (editable Meta2d P&ID) |

**Prerequisite:** PI tags must map to IDMP element attributes (e.g. `SUMMIT_CREEK_ENERGY...P101.vibration_mm_s` → `SCE-AST-EFA-P101.vibration_mm_s`).

## Customer folder layout

Each PI Vision display is one subfolder with `screenshot.png`, `tags.csv`, and optional `display.json`. Multiple PI tags in one CSV cell are separated with `|` (pipe).

Full folder spec: [harness/FOLDER_SPEC.md](harness/FOLDER_SPEC.md). Sample folder: [scenarios/examples/ops-overview/](scenarios/examples/ops-overview/).

## Customer upgrade example

This walkthrough shows how an operations team migrates PI Vision displays to TDengine IDMP without rebuilding dashboards by hand.

### Situation

Summit Creek Energy runs PI Vision for three production displays:

- **Eagle Ford Production Control Board** — fleet KPIs and production trends
- **P-101 Mechanical Performance Monitor** — pump vibration, pressure, runtime
- **SEP-101 Vessel Operations Display** — separator level, pressure, throughput

They deploy TDengine IDMP on a parallel stack (`oilupstream-idmp` at `http://localhost:7142`). Historian tags already map to IDMP element attributes (for example, `SCE-AST-EFA-P101.vibration_mm_s`).

### Step 1 — Prepare the migration folder

For each PI Vision screen, create a subfolder with a screenshot and tag list:

```
summit-creek-migration/
  ops-overview/
    screenshot.png          # PI Vision screen capture
    tags.csv                # panels + PI tags (required)
    display.json            # optional: name, element_id, theme
  p101-pump/
    screenshot.png
    tags.csv
    display.json
  sep101-vessel/
    screenshot.png
    tags.csv
    display.json
```

Example `ops-overview/tags.csv`:

```csv
panel_key,title,type,element_id,pi_tags,prompt
fleet_kpi,Fleet Production Summary,kpi,2023515258075392,total_oil_production_bpd|total_gas_production_mcfd,stat card oil bpd and gas mcfd
reliability,Station Reliability Index,gauge,2023515258075392,asset_health_pct,gauge asset health 0-100
allocation,Production Allocation by Station,pie,2023515258075392,total_oil_production_bpd,pie chart production by station
trend,15-Minute Production Profile,trend,2023515258075392,total_oil_production_bpd|total_gas_production_mcfd,line chart oil and gas last 15 minutes
kpi_snapshot,Fleet KPI Snapshot,bar-gauge,2023515258075392,total_oil_production_bpd|active_alarm_count|asset_health_pct,bar-gauge fleet KPIs
```

Optional `ops-overview/display.json`:

```json
{
  "name": "Eagle Ford Production Control Board",
  "element_id": 2023515258075392,
  "theme": "control-room"
}
```

See `scenarios/examples/ops-overview/` for a working sample folder.

### Step 2 — Install and configure the tool

```bash
git clone https://github.com/arunTDengine/agentic-pi-migration-tool.git
cd agentic-pi-migration-tool
cp .env.example .env
# Edit .env: IDMP_URL plus IDMP_USER/IDMP_PASSWORD or IDMP_API_KEY
```

### Step 3 — Validate IDMP connectivity

Confirm the IDMP instance is reachable and assets exist:

```bash
./run.sh validate --keyword SCE
```

This lists matching elements (station, pumps, separators) and confirms credentials work.

### Step 4 — Convert folder to scenario JSON

No login required for this step:

```bash
./run.sh ingest-folder ./summit-creek-migration -o scenarios/summit-creek-generated.json
```

The tool reads each subfolder, attaches screenshot paths as `reference_screenshot`, and builds a migration spec. An AI agent can open those screenshots to refine titles and layout before the next step.

### Step 5 — Run the migration

```bash
./run.sh migrate scenarios/summit-creek-generated.json --report reports/summit-creek.json
```

The migrator logs in via REST, creates AI panels for each symbol, applies a 24-column grid layout, sets a 15-minute live window (`now-15m` to `now`), and publishes dashboards on the target elements.

Or run the full pipeline in one command:

```bash
./harness/run-agent-workflow.sh full ./summit-creek-migration
```

### Step 6 — Verify in IDMP

Open each dashboard in the IDMP UI and confirm:

- Panels show live data (start the data simulator if charts are empty)
- Titles and chart types match the PI Vision reference screenshots
- Time range is the last 15 minutes with 15-second refresh

### What the customer does not need to do

- Shell into the IDMP container
- Click through the dashboard builder panel by panel
- Export PI Vision displays in a proprietary format (screenshots + tag CSV is enough)

P&ID and process-graphics displays can be listed in `tags.csv` as type
`process`, `pid`, or `pnid`. They automatically publish as editable IDMP Canvas
dashboards with animated flows, equipment symbols, live Formula values, and
embedded trend/KPI panels. Add an equipment/flow plan—or raw Meta2d `pens`—to
`display.json` for screenshot-level fidelity. The Canvas path uses REST only and
does not modify source data.

## Quick start (Summit Creek oil)

```bash
cd agentic-pi-migration
export IDMP_URL=http://localhost:7142
export IDMP_USER=arun@tdengine.com
export IDMP_PASSWORD='your-password'

# Test connection
./run.sh validate --keyword SCE

# See type mapping
./run.sh map-types

# Migrate all 3 oil dashboards from scenario spec
./run.sh migrate scenarios/summit-creek-oil.json --report reports/latest.json
```

## Scenario file format

Each display in `scenarios/*.json` describes one PI Vision screen:

```json
{
  "name": "Eagle Ford Production Control Board",
  "element_id": 2023515258075392,
  "dashboard_id": 2025648565328640,
  "theme": "control-room",
  "panels": [
    {
      "key": "trend",
      "title": "15-Minute Production Profile",
      "type": "trend",
      "element_id": 2023515258075392,
      "prompt": "line chart oil bpd and gas mcfd",
      "pi_tags": ["total_oil_production_bpd", "total_gas_production_mcfd"]
    }
  ],
  "layout": [
    {"panel": "header", "col": 0, "row": 0, "w": 24, "h": 2},
    {"panel": "trend", "col": 0, "row": 6, "w": 16, "h": 8}
  ]
}
```

## Agentic workflow (MCP)

1. **Discover** — list IDMP elements + attributes (MCP or `/elements/search`)
2. **Map** — PI tag list → element ID + attribute names
3. **Spec** — write scenario JSON (panel types, titles, layout)
4. **Migrate** — run `agentic-pi-migration migrate scenario.json`
5. **Validate** — open dashboards, confirm live 15-minute data flow

## Limitations

- **Chart displays** (trends, KPIs, gauges, bars): fully automated via REST + AI
- **P&ID process graphics**: generated as editable IDMP Canvas dashboards; exact
  screenshot matching still benefits from a supplied equipment/flow plan or raw Meta2d pens
- **PI Vision drag-and-drop export**: not native — you provide tag/layout spec or a CSV export converted to JSON
- **Compatibility boundary**: requires TDengine IDMP REST element/panel/dashboard
  APIs; a standalone TDengine TSDB endpoint is not sufficient

## Branding

| Term | Meaning |
|------|---------|
| **Agentic Migration** | AI + API automates display recreation; human defines tag map + layout |
| **Agentic PI Migration Upgrade** | This tool — PI Vision → IDMP upgrade path without rip-and-replace |
