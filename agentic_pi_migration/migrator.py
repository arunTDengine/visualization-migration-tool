"""Agentic PI Migration Upgrade — core migration engine."""

from __future__ import annotations

import concurrent.futures
from dataclasses import dataclass, field
from typing import Any

from .client import IdmpClient

# PI Vision symbol / display type → IDMP panel type
PI_TO_IDMP_PANEL: dict[str, str] = {
    "trend": "line",
    "line": "line",
    "gauge": "gauge",
    "value": "stat",
    "kpi": "stat",
    "bar": "bar",
    "pie": "pie",
    "scatter": "scatter",
    "bar-gauge": "bar-gauge",
    "state": "state-history",
    "timeline": "state-history",
    "text": "text",
    "table": "table",  # supported but discouraged for visual-first migrations
    "p&id": "advanced",
    "process": "advanced",
}

DEFAULT_TIME = {"fromText": "now-15m", "toText": "now"}
DEFAULT_WINDOW = {
    "windowType": "Interval",
    "timeColumn": "_wstart",
    "timeOffset": None,
    "eventTemplateId": None,
    "eventTemplateAttrExprs": None,
    "interval": "30s",
    "sliding": "30s",
    "fillType": "NONE",
    "fillValues": None,
}


@dataclass
class PanelSpec:
    key: str
    title: str
    panel_type: str
    element_id: int
    prompt: str
    pi_tags: list[str] = field(default_factory=list)


@dataclass
class LayoutCell:
    panel_key: str
    column: int
    row: int
    width: int
    height: int


@dataclass
class DashboardSpec:
    name: str
    description: str
    element_id: int
    dashboard_id: int | None
    theme: str
    header_html: str
    panels: list[PanelSpec]
    layout: list[LayoutCell]
    refresh_seconds: int = 15
    time_from: str = "now-15m"
    time_to: str = "now"


THEMES: dict[str, dict[str, Any]] = {
    "control-room": {
        "backgroundColor": "rgba(8, 20, 38, 0.98)",
        "showGridLines": False,
        "backgroundEffect": "none",
        "panelBorderStyle": "solid",
        "panelBorderRadius": 14,
        "panelRowMap": {},
    },
    "rotating": {
        "backgroundColor": "rgba(22, 16, 12, 0.98)",
        "showGridLines": False,
        "backgroundEffect": "none",
        "panelBorderStyle": "solid",
        "panelBorderRadius": 14,
        "panelRowMap": {},
    },
    "process": {
        "backgroundColor": "rgba(10, 28, 26, 0.98)",
        "showGridLines": False,
        "backgroundEffect": "none",
        "panelBorderStyle": "solid",
        "panelBorderRadius": 14,
        "panelRowMap": {},
    },
}


class AgenticPiMigrator:
    """Recreates PI Vision-style displays on IDMP via REST + AI panel generation."""

    def __init__(self, client: IdmpClient, *, workers: int = 3, prompt_context: str = "") -> None:
        self.client = client
        self.workers = workers
        self.prompt_context = prompt_context.strip()

    @staticmethod
    def map_pi_type(pi_symbol: str) -> str:
        return PI_TO_IDMP_PANEL.get(pi_symbol.lower().strip(), "line")

    def _build_ai_prompt(self, spec: PanelSpec) -> str:
        idmp_type = self.map_pi_type(spec.panel_type)
        tag_hint = ""
        if spec.pi_tags:
            tag_hint = f" PI tags: {', '.join(spec.pi_tags)}."
        return (
            f"Create ONLY a {idmp_type} chart — no table unless type is table. "
            f"Industrial SCADA / PI Vision migration quality. "
            f"Professional title: '{spec.title}'. {spec.prompt}.{tag_hint}"
            + (f" Additional context: {self.prompt_context}." if self.prompt_context else "")
        )

    def _create_text_panel(self, element_id: int, html: str, *, name: str = "Display Banner") -> dict[str, Any]:
        return {
            "panelId": self.client.create_panel(
                element_id,
                {
                    "name": name,
                    "panelType": "text",
                    "textContent": html,
                },
            ),
            "elementId": element_id,
            "type": "text",
            "key": "header",
        }

    def _create_chart_panel(
        self,
        spec: PanelSpec,
        *,
        dashboard_element_id: int,
        time_from: str,
        time_to: str,
    ) -> dict[str, Any]:
        prompt = self._build_ai_prompt(spec)
        panel = self.client.ai_create_panel(spec.element_id, prompt)
        idmp_type = panel.get("panelType", self.map_pi_type(spec.panel_type))

        panel["name"] = spec.title
        chart = panel.get("chart") or {}
        graph = chart.get("graph") or {}
        graph["title"] = spec.title
        chart["graph"] = graph
        panel["chart"] = chart

        panel_id = self.client.create_panel(spec.element_id, panel)
        saved = self.client.get_panel(spec.element_id, panel_id)
        self._apply_live_window(saved, idmp_type, time_from=time_from, time_to=time_to)
        self._qualify_child_attributes(saved, spec.element_id, dashboard_element_id)
        self.client.update_panel(spec.element_id, panel_id, saved)

        return {
            "panelId": panel_id,
            "elementId": spec.element_id,
            "type": idmp_type,
            "key": spec.key,
            "title": spec.title,
        }

    @staticmethod
    def _qualify_child_attributes(
        panel: dict[str, Any],
        panel_element_id: int,
        dashboard_element_id: int,
    ) -> None:
        """Prefix attribute paths when panels live on child elements.

        Dashboard queries run against the dashboard root element. Child-element
        panels must use ``{elementId}|attributes['...']`` so expressions resolve.
        """
        if panel_element_id == dashboard_element_id:
            return
        prefix = f"{panel_element_id}|"
        for key in ("yaAttributes", "xaAttributes"):
            for attr in panel.get(key) or []:
                expr = attr.get("attributeExpression") or ""
                if not expr or "|" in expr:
                    continue
                qualified = f"{prefix}{expr}"
                attr["attributeExpression"] = qualified
                if attr.get("expression"):
                    attr["expression"] = attr["expression"].replace(expr, qualified)

    def _apply_live_window(
        self,
        panel: dict[str, Any],
        panel_type: str,
        *,
        time_from: str = "now-15m",
        time_to: str = "now",
    ) -> None:
        if panel_type == "text":
            return
        params = panel.setdefault("params", {})
        params.update({"fromText": time_from, "toText": time_to})

        chart = panel.get("chart") or {}
        legend = chart.get("legend") or {}
        legend["show"] = True
        legend["placement"] = "bottom"
        chart["legend"] = legend

        series = chart.get("series") or {}
        if panel_type == "stat":
            series["graphMode"] = "area"
            series["textMode"] = "value_and_name"
        elif panel_type == "line":
            series["graphMode"] = "area"
        chart["series"] = series
        panel["chart"] = chart

        if panel_type in ("line", "bar", "scatter", "state-history", "stat", "bar-gauge"):
            for key in ("yaAttributes", "xaAttributes"):
                for attr in panel.get(key) or []:
                    attr["window"] = {**(attr.get("window") or {}), **DEFAULT_WINDOW}

    def migrate_dashboard(
        self,
        spec: DashboardSpec,
        *,
        update_existing: bool = True,
    ) -> dict[str, Any]:
        """Run agentic migration for one PI Vision display → IDMP dashboard."""
        created: dict[str, dict[str, Any]] = {}

        created["header"] = {
            **self._create_text_panel(spec.element_id, spec.header_html, name=f"{spec.name} Banner"),
            "key": "header",
        }

        chart_specs = [p for p in spec.panels if p.panel_type != "text"]
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.workers) as pool:
            futures = {
                pool.submit(
                    self._create_chart_panel,
                    p,
                    dashboard_element_id=spec.element_id,
                    time_from=spec.time_from,
                    time_to=spec.time_to,
                ): p.key
                for p in chart_specs
            }
            for future in concurrent.futures.as_completed(futures):
                panel = future.result()
                created[panel["key"]] = panel

        layout = []
        for cell in spec.layout:
            panel = created.get(cell.panel_key)
            if not panel:
                raise KeyError(f"Layout references unknown panel key: {cell.panel_key}")
            layout.append(
                {
                    "panelId": panel["panelId"],
                    "elementId": panel["elementId"],
                    "column": cell.column,
                    "row": cell.row,
                    "width": cell.width,
                    "height": cell.height,
                }
            )

        theme = THEMES.get(spec.theme, THEMES["control-room"])
        body = {
            "name": spec.name,
            "description": spec.description,
            "panels": layout,
            "params": {"refreshInterval": spec.refresh_seconds},
            "chart": theme,
        }

        if spec.dashboard_id and update_existing:
            self.client.update_dashboard(spec.element_id, spec.dashboard_id, body)
            dashboard_id = spec.dashboard_id
            action = "updated"
        else:
            result = self.client._request(
                "POST",
                f"/api/v1/elements/{spec.element_id}/dashboards",
                body,
            )
            dashboard_id = int(result["id"])
            action = "created"

        return {
            "action": action,
            "dashboard_id": dashboard_id,
            "element_id": spec.element_id,
            "name": spec.name,
            "panel_count": len(layout),
            "url": f"{self.client.base_url}/explorer/dashboard?id={dashboard_id}",
        }
