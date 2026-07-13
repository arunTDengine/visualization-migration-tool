# Customer Folder Specification

## Structure

One subfolder per PI Vision display:

```
acme-migration/
├── ops-overview/
│   ├── screenshot.png
│   ├── tags.csv
│   └── display.json
└── p101-pump/
    ├── screenshot.png
    ├── tags.csv
    └── display.json
```

Single-display flat folder is also supported (tags at root).

## tags.csv

Required columns (header row):

| Column | Required | Description |
|--------|----------|-------------|
| panel_key | yes | Unique key for layout |
| title | yes | Professional SCADA panel title |
| type | yes | trend, gauge, kpi, bar, pie, scatter, bar-gauge, state, process/pid/pnid |
| element_id | yes* | IDMP element ID (*or set in display.json) |
| pi_tags | yes | PI tags, pipe-separated: `tag1\|tag2` |
| prompt | no | AI panel prompt override |

Example:

```csv
panel_key,title,type,element_id,pi_tags,prompt
vibration,Vibration Severity Index,gauge,2023515242121480,vibration_mm_s,gauge with alarm at 6 mm/s
trend,Hydraulic Performance Trend,trend,2023515242121480,suction_pressure_psi|discharge_pressure_psi,line chart last 15 minutes
```

## display.json

```json
{
  "name": "P-101 Mechanical Performance Monitor",
  "element_id": 2023515242121480,
  "dashboard_id": null,
  "theme": "rotating",
  "refresh_seconds": 15,
  "description": "Optional description"
}
```

Themes: `control-room`, `rotating`, `process`

### P&ID through IDMP Canvas

Set `dashboard_type` to `canvas`, or include a `process`, `pid`, or `pnid`
row in `tags.csv` to select Canvas automatically. The migration creates an
editable Meta2d canvas through REST; it does not change historian data.

```json
{
  "name": "P-101 Process P&ID",
  "element_id": 2023515242121480,
  "dashboard_type": "canvas",
  "theme": "process",
  "canvas": {
    "width": 3200,
    "height": 1800,
    "equipment": [
      {"id": "feed", "label": "Feed Tank", "type": "tank", "x": 150, "y": 480},
      {
        "id": "p101",
        "label": "P-101",
        "type": "pump",
        "x": 850,
        "y": 480,
        "binding": {
          "element_id": 2023515242121480,
          "attr": "discharge_pressure_psi",
          "suffix": " psi"
        }
      },
      {"id": "outlet", "label": "Outlet", "type": "valve", "x": 1550, "y": 480}
    ],
    "flows": [
      {"from": "feed", "to": "p101", "kind": "process"},
      {"from": "p101", "to": "outlet", "kind": "process"}
    ],
    "panel_placements": [
      {"panel": "pressure", "x": 80, "y": 1120, "w": 1480, "h": 560},
      {"panel": "vibration", "x": 1640, "y": 1120, "w": 1480, "h": 560}
    ]
  }
}
```

Canvas options:

- `equipment`: process nodes; supported icon types include `pump`, `tank`,
  `boiler`, `valve`, `fan`, `transformer`, `inverter`, and `turbine`.
- `flows`: animated connections between equipment IDs.
- `binding`: optional live Formula text on a piece of equipment.
- `panel_placements`: exact locations for live chart cards.
- `pens`: optional raw Meta2d pens. When supplied, these replace the generated
  equipment/flow scene and enable screenshot-matched layouts.

## screenshot.png

- Formats: PNG, JPG, WEBP, GIF
- Used as `reference_screenshot` in generated scenario
- Agent should open and compare layout to PI Vision before migrate
