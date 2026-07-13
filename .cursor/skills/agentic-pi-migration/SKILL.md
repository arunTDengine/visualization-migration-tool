---
name: agentic-pi-migration
description: >-
  Run Agentic PI Migration Upgrade — recreate PI Vision displays on TDengine IDMP
  from scenario JSON or customer folders (screenshots + tags.csv). Use when the
  user mentions PI Vision migration, agentic migration, historian upgrade, IDMP
  dashboard automation, folder intake, or agentic-pi-migration tool.
---

# Agentic PI Migration Upgrade

Read [AGENTS.md](../../AGENTS.md) first. Extended reference: [harness/AGENT_CONTEXT.md](../../harness/AGENT_CONTEXT.md).

## Quick workflow

1. `validate` — test IDMP connection and find element IDs
2. `ingest-folder` — if customer submitted screenshots + tags (no login needed)
3. Review `reference_screenshot` paths in generated JSON; refine titles/types
4. `migrate` — build dashboards via REST
5. Share dashboard URLs from report output

## Commands

```bash
cd agentic-pi-migration
export IDMP_URL=http://localhost:7142 IDMP_USER=... IDMP_PASSWORD=...

./run.sh validate --keyword SCE
./run.sh ingest-folder /path/to/customer-folder -o scenarios/generated.json
./run.sh migrate scenarios/generated.json --report reports/latest.json
```

## Customer folder

```
display-name/
  screenshot.png
  tags.csv
  display.json   # optional
```

tags.csv: `panel_key,title,type,element_id,pi_tags,prompt` — pi_tags separated by `|`

## Rules

- REST API only — never docker exec into IDMP
- Charts over tables for visual dashboards
- 15-minute live window, 24-column aligned layout
- P&ID/process/pid/pnid → editable IDMP Canvas via REST; use equipment/flow
  plans or raw Meta2d pens for screenshot-level fidelity
- Prefer Migration Studio (`run-ui.sh`, `run-ui.ps1`, or `docker compose up
  --build`) for human users; it auto-discovers local IDMP xx42 ports and supports
  password or API-key authentication
- IDMP REST is required; never point migration at bare TDengine TSDB xx41
