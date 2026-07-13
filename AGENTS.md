# Agent Harness — Agentic PI Migration Upgrade

This file is the primary context harness for AI agents working in this repository.

## Product name

**Agentic PI Migration Upgrade** (standalone CLI tool)

Recreates PI Vision displays on TDengine IDMP via REST + AI when historian tags already match IDMP attributes.

## When to use this repo

- User mentions PI Vision migration, agentic migration, historian upgrade, parallel deployment
- User submits a folder with screenshots + tags.csv
- User wants IDMP dashboards built without touching the container or UI
- User references Summit Creek oil demo or scenario JSON files

## Agent workflow (always follow in order)

```
1. validate   → confirm IDMP URL + credentials + elements exist
2. ingest     → (if customer folder) ingest-folder → scenario JSON
3. refine     → open reference_screenshot paths; align titles/layout with PI Vision
4. migrate    → run migrate on scenario JSON
5. verify     → confirm dashboards URL, 15-min window, no tables unless asked
```

## Commands (run from repo root)

```bash
export IDMP_URL=http://localhost:6042  # or the mapped IDMP xx42 host port
export IDMP_USER=...
export IDMP_PASSWORD=...

./run.sh validate --keyword <site_keyword>
./run.sh map-types
./run.sh ingest-folder <customer-folder> -o scenarios/generated.json
./run.sh migrate scenarios/<scenario>.json --report reports/latest.json
```

`ingest-folder` does not require IDMP credentials.

## Portable deployment

- macOS/Linux UI: `./run-ui.sh`
- Windows UI: `.\run-ui.ps1` or double-click `run-ui.cmd`
- Docker Desktop / Compose: `docker compose up --build`
- Browser UI: `http://localhost:8765`
- Local discovery: `./run.sh discover` or **Find local** in the UI

The tool requires TDengine **IDMP** REST APIs, not a bare TDengine TSDB endpoint.
IDMP normally uses a port ending in `42`; TSDB REST normally ends in `41`.
Inside Docker, localhost targets are translated to `host.docker.internal`.
For same-network Compose services, set `IDMP_URL` to the private service URL and
`IDMP_PUBLIC_URL` to the host URL users open in a browser.

Authentication supports either `IDMP_USER` + `IDMP_PASSWORD` or `IDMP_API_KEY`.

## Customer folder layout

```
customer-job/
  display-name/
    screenshot.png      # PI Vision reference (optional but recommended)
    tags.csv            # required
    display.json        # optional: name, element_id, theme, dashboard_id
```

See `scenarios/examples/ops-overview/` and `harness/FOLDER_SPEC.md`.

## PI Vision → IDMP chart types

| PI Vision | tags.csv type | IDMP panel |
|-----------|---------------|------------|
| Trend | trend | line |
| Gauge | gauge | gauge |
| Value/KPI | kpi | stat |
| Bar | bar | bar |
| Pie | pie | pie |
| XY Plot | scatter | scatter |
| State | state | state-history |
| P&ID | process / pid / pnid | CANVAS dashboard (Meta2d) |

## Hard rules for agents

1. **Never** `docker exec` into IDMP — use REST API only
2. **Never** commit credentials — use env vars
3. **Prefer charts over tables** for customer-facing dashboards
4. **Default time window**: `now-15m` → `now`, 30s resolution, 15s refresh
5. **Layout**: 24-column grid, full-width header (w=24), rows must not leave empty half-width gaps
6. **Tag prerequisite**: PI tags must map to IDMP element attributes or panels will be empty

## Key files

| Path | Purpose |
|------|---------|
| `agentic_pi_migration/migrator.py` | Core migration engine |
| `agentic_pi_migration/canvas/` | P&ID Canvas scene and live-panel builder |
| `agentic_pi_migration/folder_intake.py` | Screenshot + tags folder → JSON |
| `agentic_pi_migration/client.py` | IDMP REST client |
| `agentic_pi_migration/web/server.py` | Web UI backend (FastAPI) |
| `web/` | Web UI frontend wizard |
| `run-ui.sh` | Start the web UI |
| `scenarios/summit-creek-oil.json` | Reference 3-dashboard oil scenario |
| `harness/AGENT_CONTEXT.md` | Extended agent reference |
| `.cursor/skills/agentic-pi-migration/SKILL.md` | Cursor skill entry point |

## IDMP API surface used

- `POST /api/v1/users/login`
- `GET /api/v1/elements/search`
- `POST /api/v1/ai/panels/create`
- `POST /api/v1/elements/{id}/panels`
- `PUT /api/v1/elements/{id}/panels/{panelId}`
- `PUT /api/v1/elements/{id}/dashboards/{dashboardId}`
- `POST /api/v1/elements/{id}/dashboards` with `type: CANVAS`
- `POST /api/v1/elements/{id}/panels/query`

## Limitations to communicate

- Chart displays: fully agentic
- P&ID process graphics: generated as editable IDMP Canvas dashboards; raw `pens`
  or an equipment/flow plan may be supplied for pixel-level fidelity
- No native PI Vision file import — customer provides folder or scenario JSON
