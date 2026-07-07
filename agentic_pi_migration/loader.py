"""Load migration scenario files (JSON)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .migrator import DashboardSpec, LayoutCell, PanelSpec


def load_scenario(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def parse_dashboard(data: dict[str, Any]) -> DashboardSpec:
    panels = [
        PanelSpec(
            key=p["key"],
            title=p["title"],
            panel_type=p["type"],
            element_id=int(p["element_id"]),
            prompt=p["prompt"],
            pi_tags=p.get("pi_tags", []),
        )
        for p in data["panels"]
    ]
    layout = [
        LayoutCell(
            panel_key=c["panel"],
            column=int(c["col"]),
            row=int(c["row"]),
            width=int(c["w"]),
            height=int(c["h"]),
        )
        for c in data["layout"]
    ]
    return DashboardSpec(
        name=data["name"],
        description=data.get("description", data["name"]),
        element_id=int(data["element_id"]),
        dashboard_id=int(data["dashboard_id"]) if data.get("dashboard_id") else None,
        theme=data.get("theme", "control-room"),
        header_html=data["header_html"],
        panels=panels,
        layout=layout,
        refresh_seconds=int(data.get("refresh_seconds", 15)),
        time_from=data.get("time_from", "now-15m"),
        time_to=data.get("time_to", "now"),
    )


def load_dashboards(path: Path) -> list[DashboardSpec]:
    raw = load_scenario(path)
    displays = raw.get("displays", [raw])
    return [parse_dashboard(d) for d in displays]
