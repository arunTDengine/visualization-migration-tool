"""Load migration scenario files (JSON)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .migrator import DashboardSpec, LayoutCell, PanelSpec, SeriesBinding


def load_scenario(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def parse_dashboard(data: dict[str, Any]) -> DashboardSpec:
    panels = []
    for p in data["panels"]:
        series = [
            SeriesBinding(
                element_id=int(s["element_id"]),
                attr=str(s.get("attr") or s.get("attribute") or "val"),
                alias=str(s.get("alias") or s.get("pi_tag") or s.get("attr") or "val"),
            )
            for s in (p.get("series") or [])
        ]
        panels.append(
            PanelSpec(
                key=p["key"],
                title=p["title"],
                panel_type=p["type"],
                element_id=int(p["element_id"]),
                prompt=p.get("prompt") or p["title"],
                pi_tags=p.get("pi_tags", []),
                series=series,
            )
        )
    layout = [
        LayoutCell(
            panel_key=c["panel"],
            column=int(c["col"]),
            row=int(c["row"]),
            width=int(c["w"]),
            height=int(c["h"]),
        )
        for c in data.get("layout", [])
    ]
    dashboard_type = str(data.get("dashboard_type") or data.get("type") or "grid").lower()
    if dashboard_type == "grid" and any(
        p.panel_type.lower().strip() in ("process", "p&id", "pnid", "pid") for p in panels
    ):
        dashboard_type = "canvas"
    return DashboardSpec(
        name=data["name"],
        description=data.get("description", data["name"]),
        element_id=int(data["element_id"]),
        dashboard_id=int(data["dashboard_id"]) if data.get("dashboard_id") else None,
        theme=data.get("theme", "control-room"),
        header_html=data.get(
            "header_html",
            f"<div style='padding:18px;color:#fff;background:#0f172a'><b>{data['name']}</b></div>",
        ),
        panels=panels,
        layout=layout,
        refresh_seconds=int(data.get("refresh_seconds", 15)),
        time_from=data.get("time_from", "now-15m"),
        time_to=data.get("time_to", "now"),
        dashboard_type=dashboard_type,
        canvas=dict(data.get("canvas") or data.get("canvas_plan") or {}),
    )


def load_dashboards(path: Path) -> list[DashboardSpec]:
    raw = load_scenario(path)
    displays = raw.get("displays", [raw])
    return [parse_dashboard(d) for d in displays]
