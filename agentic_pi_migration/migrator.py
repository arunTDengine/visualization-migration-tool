"""Agentic PI Migration Upgrade — core migration engine."""

from __future__ import annotations

import concurrent.futures
import secrets
import string
from dataclasses import dataclass, field
from typing import Any

from .canvas import CanvasBuilder, panel_card
from .client import IdmpClient
from .qa.assist import (
    assist_enabled,
    enrich_or_passthrough,
    expand_design_direction,
    polish_series_panel,
)
from .qa.llm import LlmError
from .tag_resolve import SeriesBinding, TagResolver

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
    "pid": "advanced",
    "pnid": "advanced",
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
    # Optional explicit series bindings (needed when each PI tag lives on a
    # different child element, e.g. GTU/54FC007/PV/val).
    series: list[SeriesBinding] = field(default_factory=list)


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
    dashboard_type: str = "grid"
    canvas: dict[str, Any] = field(default_factory=dict)


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

    def __init__(
        self,
        client: IdmpClient,
        *,
        workers: int = 3,
        prompt_context: str = "",
        external_assist: bool | None = None,
    ) -> None:
        self.client = client
        self.workers = workers
        self.prompt_context = prompt_context.strip()
        self.external_assist = assist_enabled(external_assist)
        self.assist_log: list[dict[str, Any]] = []
        self._tag_resolver = TagResolver(client)

    @staticmethod
    def map_pi_type(pi_symbol: str) -> str:
        return PI_TO_IDMP_PANEL.get(pi_symbol.lower().strip(), "line")

    def _bindings_for_panel(
        self,
        spec: PanelSpec,
        dashboard_element_id: int,
    ) -> list[SeriesBinding]:
        """Map pi_tags onto real IDMP child-element attributes when needed."""
        root = int(dashboard_element_id or spec.element_id)
        return self._tag_resolver.resolve_tags(
            root,
            list(spec.pi_tags or []),
            fallback_samples=True,
        )

    @staticmethod
    def _random_name_suffix(length: int = 4) -> str:
        alphabet = string.ascii_lowercase + string.digits
        return "".join(secrets.choice(alphabet) for _ in range(length))

    def _unique_dashboard_name(self, element_id: int, base_name: str) -> str:
        """Always keep a unique dashboard title — append ·xxxx if the name exists."""
        base = (base_name or "Migration").strip() or "Migration"
        try:
            existing = {
                str(d.get("name") or "").strip().lower()
                for d in self.client.list_dashboards(int(element_id))
            }
        except Exception:
            existing = set()
        if base.lower() not in existing:
            return base
        for _ in range(12):
            candidate = f"{base} · {self._random_name_suffix()}"
            if candidate.lower() not in existing:
                return candidate
        return f"{base} · {self._random_name_suffix(6)}"

    def _build_ai_prompt(
        self,
        spec: PanelSpec,
        *,
        time_from: str = "now-15m",
        time_to: str = "now",
    ) -> str:
        idmp_type = self.map_pi_type(spec.panel_type)
        tag_hint = ""
        if spec.pi_tags:
            tag_hint = f" PI tags: {', '.join(spec.pi_tags)}."
        base = (
            f"Create ONLY a {idmp_type} chart — no table unless type is table. "
            f"Industrial SCADA / PI Vision migration quality. "
            f"Professional title: '{spec.title}'. {spec.prompt}.{tag_hint}"
            + (f" Additional context: {self.prompt_context}." if self.prompt_context else "")
            + f" Use live window {time_from} → {time_to}."
        )
        enriched, meta = enrich_or_passthrough(
            base_prompt=base,
            title=spec.title,
            panel_type=spec.panel_type,
            idmp_type=idmp_type,
            prompt=spec.prompt,
            pi_tags=list(spec.pi_tags or []),
            prompt_context=self.prompt_context,
            time_from=time_from,
            time_to=time_to,
            enabled=self.external_assist,
        )
        if meta is not None:
            self.assist_log.append(
                {
                    "panel": spec.key,
                    "title": spec.title,
                    "assisted": "error" not in meta,
                    "meta": meta,
                }
            )
        return enriched

    def _try_idmp_ai_panel(
        self,
        spec: PanelSpec,
        *,
        time_from: str,
        time_to: str,
    ) -> dict[str, Any] | None:
        """External LLM enriches prompt → IDMP internal AI creates panel. None on failure."""
        prompt = self._build_ai_prompt(spec, time_from=time_from, time_to=time_to)
        try:
            panel = self.client.ai_create_panel(spec.element_id, prompt)
        except RuntimeError:
            return None
        idmp_type = panel.get("panelType", self.map_pi_type(spec.panel_type))
        panel["name"] = spec.title
        chart = panel.get("chart") or {}
        graph = chart.get("graph") or {}
        graph["title"] = spec.title
        chart["graph"] = graph
        panel["chart"] = chart
        self._apply_live_window(panel, idmp_type, time_from=time_from, time_to=time_to)
        return panel

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

    @staticmethod
    def _safe_alias(alias: str) -> str:
        """TDengine rejects dotted aliases in INTERVAL queries (e.g. 54FC007.PV)."""
        import re
        cleaned = re.sub(r"[^A-Za-z0-9_]+", "_", alias).strip("_")
        if not cleaned:
            return "series"
        if cleaned[0].isdigit():
            return f"series_{cleaned}"
        return cleaned

    @staticmethod
    def _series_ya(binding: SeriesBinding, *, dashboard_element_id: int) -> dict[str, Any]:
        """Build a yaAttributes entry, qualifying child element paths when needed."""
        import uuid

        if binding.element_id == dashboard_element_id:
            q = f"attributes['{binding.attr}']"
        else:
            q = f"{binding.element_id}|attributes['{binding.attr}']"
        return {
            "uuid": str(uuid.uuid4()),
            "attributeExpression": q,
            "expression": f"${{{q}}}",
            "function": None,
            "parameters": None,
            "tsColumnType": "none",
            "groupBy": False,
            "limits": None,
            "forecast": None,
            "timeShift": None,
            "window": None,
            "alias": AgenticPiMigrator._safe_alias(binding.alias),
            "checked": True,
            "formula": False,
            "orderBy": None,
            "filter": None,
            "displayUom": None,
            "defaultUomClassId": None,
            "qualityColumn": None,
        }

    def _create_panel_from_series(
        self,
        spec: PanelSpec,
        *,
        dashboard_element_id: int,
        time_from: str,
        time_to: str,
    ) -> dict[str, Any]:
        """Create a chart panel from explicit series bindings (no AI inventing tags)."""
        idmp_type = self.map_pi_type(spec.panel_type)
        panel = self._panel_body_from_series(
            spec,
            dashboard_element_id=dashboard_element_id,
            time_from=time_from,
            time_to=time_to,
        )
        if self.external_assist:
            try:
                polished = polish_series_panel(
                    panel=panel,
                    title=spec.title,
                    pi_tags=list(spec.pi_tags or []),
                    prompt=spec.prompt,
                    prompt_context=self.prompt_context,
                    time_from=time_from,
                    time_to=time_to,
                )
                panel = polished
                self.assist_log.append(
                    {
                        "panel": spec.key,
                        "title": spec.title,
                        "assisted": True,
                        "mode": "series_polish",
                    }
                )
            except (LlmError, TypeError, ValueError, KeyError) as exc:
                self.assist_log.append(
                    {
                        "panel": spec.key,
                        "title": spec.title,
                        "assisted": False,
                        "mode": "series_polish",
                        "error": str(exc),
                    }
                )
        host_id = dashboard_element_id
        panel_id = self.client.create_panel(host_id, panel)
        saved = self.client.get_panel(host_id, panel_id)
        self._apply_live_window(saved, idmp_type, time_from=time_from, time_to=time_to)
        self.client.update_panel(host_id, panel_id, saved)
        return {
            "panelId": panel_id,
            "elementId": host_id,
            "type": idmp_type,
            "key": spec.key,
            "title": panel.get("name") or spec.title,
            "assisted": self.external_assist,
        }

    def _panel_body_from_series(
        self,
        spec: PanelSpec,
        *,
        dashboard_element_id: int,
        time_from: str,
        time_to: str,
        panel_type: str | None = None,
    ) -> dict[str, Any]:
        """Build a deterministic panel body without writing it to IDMP."""
        idmp_type = panel_type or self.map_pi_type(spec.panel_type)
        ya = [
            self._series_ya(s, dashboard_element_id=dashboard_element_id)
            for s in spec.series
        ]
        panel: dict[str, Any] = {
            "name": spec.title,
            "panelType": idmp_type,
            "categories": [5],
            "chart": {
                "graph": {"title": spec.title},
                "legend": {"placement": "bottom", "showType": "list", "stats": ["last"], "show": True},
                "series": {
                    "lineOpacity": 1,
                    "lineType": "solid",
                    "lineWidth": 1.5,
                    "style": "smooth",
                    "graphMode": "line",
                },
                "standardOptions": {"colorSchema": "classic-palette-by-series", "decimals": 2},
                "tooltip": {"hideZeros": True, "mode": "all", "sortOrder": "descending"},
            },
            "yaAttributes": ya,
            "xaAttributes": [],
            "params": {"fromText": time_from, "toText": time_to},
        }
        self._apply_live_window(panel, idmp_type, time_from=time_from, time_to=time_to)
        return panel

    def _create_chart_panel(
        self,
        spec: PanelSpec,
        *,
        dashboard_element_id: int,
        time_from: str,
        time_to: str,
    ) -> dict[str, Any]:
        # Prefer explicit series / pi_tags for accuracy (attributes are the contract).
        # External LLM + IDMP AI only when there is no tag map to bind.
        if not spec.series and spec.pi_tags:
            spec.series = self._bindings_for_panel(spec, dashboard_element_id)
        if spec.series:
            return self._create_panel_from_series(
                spec,
                dashboard_element_id=dashboard_element_id,
                time_from=time_from,
                time_to=time_to,
            )

        ai_panel = self._try_idmp_ai_panel(spec, time_from=time_from, time_to=time_to)
        if ai_panel is not None:
            panel_id = self.client.create_panel(spec.element_id, ai_panel)
            saved = self.client.get_panel(spec.element_id, panel_id)
            idmp_type = saved.get("panelType", self.map_pi_type(spec.panel_type))
            self._apply_live_window(saved, idmp_type, time_from=time_from, time_to=time_to)
            self.client.update_panel(spec.element_id, panel_id, saved)
            return {
                "panelId": panel_id,
                "elementId": spec.element_id,
                "type": idmp_type,
                "key": spec.key,
                "title": spec.title,
                "assisted": self.external_assist,
            }

        raise RuntimeError(
            f"Panel '{spec.key}' has no pi_tags/series and IDMP AI did not create a panel"
        )

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

        # Absolute historical windows (ISO timestamps) work better without INTERVAL
        # aggregation — PI Vision exports are already dense samples.
        use_interval = not (
            (time_from[:1].isdigit() if time_from else False)
            or (time_to[:1].isdigit() if time_to else False)
        )
        if use_interval and panel_type in ("line", "bar", "scatter", "state-history", "stat", "bar-gauge"):
            for key in ("yaAttributes", "xaAttributes"):
                for attr in panel.get(key) or []:
                    # Raw attributes cannot be selected directly in a TDengine
                    # INTERVAL query. Apply the window only when the series has
                    # an aggregate function (AVG, MAX, and so on).
                    if attr.get("function"):
                        attr["window"] = {
                            **(attr.get("window") or {}),
                            **DEFAULT_WINDOW,
                        }

    def _canvas_inline_panel(self, spec: PanelSpec, dashboard: DashboardSpec) -> dict[str, Any]:
        """Build an inline canvas panel without changing source data."""
        process_type = spec.panel_type.lower().strip() in ("process", "p&id", "pid", "pnid")
        # Accuracy-first: tag series win over AI for Canvas embedded charts.
        if not spec.series and spec.pi_tags:
            spec.series = self._bindings_for_panel(spec, dashboard.element_id)
        if spec.series:
            panel = self._panel_body_from_series(
                spec,
                dashboard_element_id=dashboard.element_id,
                time_from=dashboard.time_from,
                time_to=dashboard.time_to,
                panel_type="line" if process_type else None,
            )
            if self.external_assist and not process_type:
                try:
                    panel = polish_series_panel(
                        panel=panel,
                        title=spec.title,
                        pi_tags=list(spec.pi_tags or []),
                        prompt=spec.prompt,
                        prompt_context=self.prompt_context,
                        time_from=dashboard.time_from,
                        time_to=dashboard.time_to,
                    )
                    self.assist_log.append(
                        {
                            "panel": spec.key,
                            "title": spec.title,
                            "assisted": True,
                            "mode": "canvas_series_polish",
                        }
                    )
                except (LlmError, TypeError, ValueError, KeyError) as exc:
                    self.assist_log.append(
                        {
                            "panel": spec.key,
                            "assisted": False,
                            "mode": "canvas_series_polish",
                            "error": str(exc),
                        }
                    )
            return panel

        if self.external_assist and not process_type:
            ai_panel = self._try_idmp_ai_panel(
                spec,
                time_from=dashboard.time_from,
                time_to=dashboard.time_to,
            )
            if ai_panel is not None:
                return ai_panel

        return {
            "name": spec.title,
            "panelType": "text",
            "categories": [5],
            "textContent": (
                "<div style='height:100%;box-sizing:border-box;padding:16px;"
                "background:#0f172a;color:#e2e8f0;border:1px solid #334155;"
                f"border-radius:12px'><b>{spec.title}</b><div style='margin-top:8px;"
                f"color:#94a3b8'>{spec.prompt}</div></div>"
            ),
        }

    def migrate_canvas_dashboard(
        self,
        spec: DashboardSpec,
        *,
        update_existing: bool = False,
    ) -> dict[str, Any]:
        """Create an editable IDMP Canvas P&ID with live embedded panels."""
        creating = not (spec.dashboard_id and update_existing)
        if creating:
            spec.name = self._unique_dashboard_name(spec.element_id, spec.name)

        if self.external_assist and self.prompt_context:
            self.prompt_context = expand_design_direction(
                self.prompt_context, display_name=spec.name
            )
        builder = CanvasBuilder(spec.canvas)
        scene = builder.build_scene(spec.name)
        inline_specs: list[tuple[str, int, str, dict[str, Any]]] = [
            (
                "header",
                -2,
                f"{spec.name} Banner",
                {
                    "name": f"{spec.name} Banner",
                    "panelType": "text",
                    "categories": [5],
                    "textContent": spec.header_html,
                },
            )
        ]
        for index, panel_spec in enumerate(spec.panels):
            inline_specs.append(
                (
                    panel_spec.key,
                    -10 - index,
                    panel_spec.title,
                    self._canvas_inline_panel(panel_spec, spec),
                )
            )

        placements = builder.panel_placements(
            [key for key, _, _, _ in inline_specs if key != "header"],
            spec.layout,
        )
        header_place = dict(
            (spec.canvas.get("header_placement") or {})
            or {"x": 50, "y": 30, "w": builder.width - 100, "h": 150}
        )
        placements["header"] = header_place
        params = {
            "refreshInterval": spec.refresh_seconds * 1000,
            "fromText": spec.time_from,
            "toText": spec.time_to,
        }

        if spec.dashboard_id and update_existing:
            # GET first: PUT replaces the complete Canvas document.
            self.client.get_dashboard(spec.element_id, spec.dashboard_id)
            panel_map: dict[int, int] = {}
            for _, temp_id, _, panel_body in inline_specs:
                panel_map[temp_id] = self.client.create_panel(spec.element_id, panel_body)
            dashboard_id = spec.dashboard_id
            action = "updated"
        else:
            create_body = {
                "name": spec.name,
                "description": spec.description,
                "type": "CANVAS",
                "params": params,
                "chart": builder.chart(scene),
                "newInlinePanels": [
                    {"tempId": temp_id, "panel": panel_body}
                    for _, temp_id, _, panel_body in inline_specs
                ],
                "panels": [],
            }
            result = self.client.create_canvas_dashboard(spec.element_id, create_body)
            dashboard_id = int(result["id"])
            panel_map = {
                int(temp_id): int(panel_id)
                for temp_id, panel_id in (result.get("panelIdMap") or {}).items()
            }
            missing = [temp_id for _, temp_id, _, _ in inline_specs if temp_id not in panel_map]
            if missing:
                raise RuntimeError(f"IDMP Canvas creation omitted inline panel IDs: {missing}")
            action = "created"

        cards: list[dict[str, Any]] = []
        panel_ids: list[int] = []
        for key, temp_id, panel_name, _ in inline_specs:
            placement = placements.get(key)
            if not placement:
                raise KeyError(f"Canvas has no placement for panel key: {key}")
            real_id = panel_map[temp_id]
            panel_ids.append(real_id)
            cards.append(
                panel_card(
                    key,
                    placement,
                    real_id,
                    spec.element_id,
                    panel_name,
                )
            )

        all_pens = scene + cards
        self.client.update_canvas_dashboard(
            spec.element_id,
            dashboard_id,
            {
                "name": spec.name,
                "description": spec.description,
                "params": params,
                "chart": builder.chart(all_pens),
                "panels": [],
            },
        )

        live: list[str] = []
        failed: list[str] = []
        for (_, _, name, panel_body), panel_id in zip(inline_specs, panel_ids):
            if panel_body.get("panelType") == "text":
                continue
            try:
                saved = self.client.get_panel(spec.element_id, panel_id)
                result = self.client.query_panel(spec.element_id, saved)
                if result:
                    live.append(name)
                else:
                    failed.append(name)
            except RuntimeError as exc:
                failed.append(f"{name}: {exc}")

        return {
            "action": action,
            "dashboard_id": dashboard_id,
            "dashboard_type": "canvas",
            "element_id": spec.element_id,
            "name": spec.name,
            "panel_count": len(cards),
            "pens": len(all_pens),
            "panels_live": live,
            "panels_failed": failed,
            "external_assist": self.external_assist,
            "assist_log": list(self.assist_log),
            "url": f"{self.client.base_url}/explorer/dashboard?id={dashboard_id}",
            "edit_url": (
                f"{self.client.base_url}/explorer/canvas-dashboard-create/{dashboard_id}"
            ),
        }

    def migrate_dashboard(
        self,
        spec: DashboardSpec,
        *,
        update_existing: bool = False,
    ) -> dict[str, Any]:
        """Run agentic migration for one PI Vision display → IDMP dashboard."""
        if spec.dashboard_type.lower() in ("canvas", "pid", "p&id", "pnid", "process"):
            return self.migrate_canvas_dashboard(spec, update_existing=update_existing)

        creating = not (spec.dashboard_id and update_existing)
        if creating:
            spec.name = self._unique_dashboard_name(spec.element_id, spec.name)

        if self.external_assist and self.prompt_context:
            self.prompt_context = expand_design_direction(
                self.prompt_context, display_name=spec.name
            )

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
            "params": {
                "refreshInterval": spec.refresh_seconds,
                "fromText": spec.time_from,
                "toText": spec.time_to,
            },
            "chart": theme,
        }

        if spec.dashboard_id and update_existing:
            self.client.update_dashboard(spec.element_id, spec.dashboard_id, body)
            dashboard_id = spec.dashboard_id
            action = "updated"
        else:
            result = self.client.create_dashboard(spec.element_id, body)
            dashboard_id = int(result["id"])
            action = "created"

        return {
            "action": action,
            "dashboard_id": dashboard_id,
            "element_id": spec.element_id,
            "name": spec.name,
            "panel_count": len(layout),
            "external_assist": self.external_assist,
            "assist_log": list(self.assist_log),
            "url": f"{self.client.base_url}/explorer/dashboard?id={dashboard_id}",
        }
