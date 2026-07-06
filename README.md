# Agentic PI Migration Upgrade

**Agentic Migration** for PI Vision → TDengine IDMP: an AI-assisted, API-driven tool that recreates historian displays when tags and data already match.

No container shell access. No manual dashboard clicking. Point it at a running IDMP instance, provide a display spec (PI tags + panel types + layout), and the agent builds live dashboards via REST.

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
| P&ID / process graphic | `advanced` *(manual polish)* |

**Prerequisite:** PI tags must map to IDMP element attributes (e.g. `SUMMIT_CREEK_ENERGY...P101.vibration_mm_s` → `SCE-AST-EFA-P101.vibration_mm_s`).

## Customer folder submission (screenshots + tags)

Customers can drop **PI Vision screenshots** and **tag files** in a folder — no JSON editing required.

```
customer-migration/
  ops-overview/
    screenshot.png       ← PI Vision screen capture
    tags.csv             ← required: panels + PI tags
    display.json         ← optional: name, element_id, theme
  p101-pump/
    screenshot.png
    tags.csv
    display.json
```

**tags.csv columns:**

```csv
panel_key,title,type,element_id,pi_tags,prompt
trend,15-Min Production,trend,2023515258075392,oil_bpd|gas_mcfd,line chart oil and gas
```

Multiple PI tags in one cell: separate with `|` (pipe).

```bash
# Step 1: folder → scenario JSON
./run.sh ingest-folder /path/to/customer-migration -o scenarios/generated.json

# Step 2: scenario → live IDMP dashboards
./run.sh migrate scenarios/generated.json
```

Screenshots are saved as `reference_screenshot` in the scenario. An AI agent (Cursor) can open them to refine layout/titles before migrate. Example folder: `scenarios/examples/ops-overview/`.

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

- **Chart displays** (trends, KPIs, gauges, bars): fully agentic ✅
- **P&ID process graphics**: spec maps to `advanced`; needs human finish ⚠️
- **PI Vision drag-and-drop export**: not native — you provide tag/layout spec or a CSV export converted to JSON

## Branding

| Term | Meaning |
|------|---------|
| **Agentic Migration** | AI + API automates display recreation; human defines tag map + layout |
| **Agentic PI Migration Upgrade** | This tool — PI Vision → IDMP upgrade path without rip-and-replace |
