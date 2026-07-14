"""Hardcoded walkthrough examples — one grid dashboard, one Canvas P&ID.

Both require a live target_element_id from the user's IDMP (Step 1 search).
Attribute names are illustrative; retargeting swaps the element_id everywhere.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


HARDCODED_EXAMPLES: dict[str, dict[str, Any]] = {
    "demo-grid-dashboard": {
        "id": "demo-grid-dashboard",
        "label": "Example · Grid dashboard",
        "blurb": "KPI + trend layout — shows how tags.csv becomes live IDMP panels.",
        "kind": "grid",
        "requires_element": True,
        "scenario": {
            "name": "demo-grid-dashboard",
            "description": "Hardcoded grid walkthrough (Agentic PI Migration)",
            "displays": [
                {
                    "name": "Plant Ops Overview (Example)",
                    "description": "Hardcoded example grid dashboard",
                    "element_id": 0,
                    "dashboard_type": "grid",
                    "theme": "control-room",
                    "refresh_seconds": 15,
                    "time_from": "now-15m",
                    "time_to": "now",
                    "header_html": (
                        "<div style='padding:12px 16px;background:#0f172a;border-left:4px solid #38bdf8;"
                        "border-radius:8px;color:#e2e8f0'><div style='font-size:11px;letter-spacing:2px;"
                        "text-transform:uppercase;color:#94a3b8'>Example</div>"
                        "<div style='font-size:18px;font-weight:700'>Plant Ops Overview</div>"
                        "<div style='font-size:12px;color:#94a3b8'>Hardcoded grid walkthrough</div></div>"
                    ),
                    "panels": [
                        {
                            "key": "kpi_throughput",
                            "title": "Throughput",
                            "type": "kpi",
                            "element_id": 0,
                            "pi_tags": ["throughput_bpd"],
                            "prompt": "stat card for throughput in bpd",
                        },
                        {
                            "key": "kpi_health",
                            "title": "Asset Health",
                            "type": "gauge",
                            "element_id": 0,
                            "pi_tags": ["asset_health_pct"],
                            "prompt": "gauge 0-100 for asset health",
                        },
                        {
                            "key": "trend_production",
                            "title": "15-Minute Production",
                            "type": "trend",
                            "element_id": 0,
                            "pi_tags": ["throughput_bpd", "quality_index"],
                            "prompt": "multi-series line last 15 minutes",
                        },
                        {
                            "key": "alarms",
                            "title": "Active Alarms",
                            "type": "bar-gauge",
                            "element_id": 0,
                            "pi_tags": ["active_alarm_count"],
                            "prompt": "bar-gauge for alarm count",
                        },
                    ],
                    "layout": [
                        {"panel": "header", "col": 0, "row": 0, "w": 24, "h": 2},
                        {"panel": "kpi_throughput", "col": 0, "row": 2, "w": 8, "h": 5},
                        {"panel": "kpi_health", "col": 8, "row": 2, "w": 8, "h": 5},
                        {"panel": "alarms", "col": 16, "row": 2, "w": 8, "h": 5},
                        {"panel": "trend_production", "col": 0, "row": 7, "w": 24, "h": 8},
                    ],
                }
            ],
        },
    },
    "demo-canvas-pnid": {
        "id": "demo-canvas-pnid",
        "label": "Example · Canvas P&ID",
        "blurb": "Animated feed → pump → valve — shows editable Meta2d Canvas migration.",
        "kind": "canvas",
        "requires_element": True,
        "scenario": {
            "name": "demo-canvas-pnid",
            "description": "Hardcoded Canvas P&ID walkthrough (Agentic PI Migration)",
            "displays": [
                {
                    "name": "Pump Train P&ID (Example)",
                    "description": "Hardcoded example Canvas process display",
                    "element_id": 0,
                    "dashboard_type": "canvas",
                    "theme": "process",
                    "refresh_seconds": 5,
                    "time_from": "now-15m",
                    "time_to": "now",
                    "header_html": (
                        "<div style='padding:10px 16px;background:#0b1524;border-bottom:1px solid #243447;"
                        "color:#eef3f8;font-family:ui-sans-serif,system-ui,sans-serif'>"
                        "<strong>Example Canvas P&amp;ID</strong>"
                        "<span style='margin-left:12px;color:#8b9eb0;font-size:12px'>"
                        "Hardcoded walkthrough · editable Meta2d</span></div>"
                    ),
                    "panels": [
                        {
                            "key": "flow_trend",
                            "title": "Process Flow",
                            "type": "trend",
                            "element_id": 0,
                            "pi_tags": ["flow_rate", "discharge_pressure"],
                            "prompt": "live process flow and discharge pressure",
                        }
                    ],
                    "canvas": {
                        "width": 1800,
                        "height": 900,
                        "background": "#0a0e14",
                        "text_color": "#eef3f8",
                        "equipment": [
                            {"id": "feed", "label": "Feed Tank", "type": "tank", "x": 160, "y": 280},
                            {"id": "p101", "label": "P-101", "type": "pump", "x": 700, "y": 280},
                            {"id": "cv101", "label": "CV-101", "type": "valve", "x": 1240, "y": 280},
                        ],
                        "flows": [
                            {"from": "feed", "to": "p101", "kind": "water", "animated": True},
                            {"from": "p101", "to": "cv101", "kind": "water", "animated": True},
                        ],
                        "header_placement": {"x": 40, "y": 20, "w": 1720, "h": 48},
                        "panel_placements": [
                            {"panel": "flow_trend", "x": 80, "y": 620, "w": 1640, "h": 220},
                        ],
                    },
                }
            ],
        },
    },
}


def list_hardcoded_examples() -> list[dict[str, Any]]:
    return [
        {
            "id": ex["id"],
            "label": ex["label"],
            "blurb": ex["blurb"],
            "kind": ex["kind"],
            "requires_element": ex["requires_element"],
            "available": True,
            "hardcoded": True,
        }
        for ex in HARDCODED_EXAMPLES.values()
    ]


def build_hardcoded_scenario(example_id: str, *, target_element_id: int) -> dict[str, Any]:
    if example_id not in HARDCODED_EXAMPLES:
        raise KeyError(f"Unknown hardcoded example: {example_id}")
    if not target_element_id or int(target_element_id) <= 0:
        raise ValueError("Pick a target element ID from Step 1 search results")
    scenario = deepcopy(HARDCODED_EXAMPLES[example_id]["scenario"])
    eid = int(target_element_id)
    for display in scenario.get("displays") or []:
        display["element_id"] = eid
        display["dashboard_id"] = None
        for panel in display.get("panels") or []:
            panel["element_id"] = eid
        for equipment in (display.get("canvas") or {}).get("equipment") or []:
            binding = equipment.get("binding")
            if binding:
                binding["element_id"] = eid
    scenario["source_folder"] = f"hardcoded:{example_id}"
    scenario["intake_warnings"] = [
        "Hardcoded example — placeholder tags are remapped to live child attributes under your target element at publish time.",
    ]
    return scenario
