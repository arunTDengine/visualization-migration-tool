"""Materialize an agent-authored P&ID plan as an IDMP Meta2d document."""

from __future__ import annotations

import re
from typing import Any


DEFAULT_WIDTH = 3200
DEFAULT_HEIGHT = 1800
DEFAULT_BACKGROUND = "#101820"
DEFAULT_TEXT = "#d7e1ee"
FLOW_COLORS = {
    "process": "#31a7f5",
    "water": "#31a7f5",
    "steam": "#e6d950",
    "gas": "#f59e0b",
    "power": "#30ee6f",
    "alert": "#ff5959",
}
EQUIPMENT_IMAGES = {
    "pump": "/static/png/IoT-Pumps(泵)/Centrifugal pump（离心泵）.svg",
    "tank": "/static/png/IoT-water tank（水槽）/Drum（滚筒）.svg",
    "boiler": "/static/png/IoT-Boilers(锅炉)/Boiler 3(锅炉3).svg",
    "valve": "/static/png/IoT-valve symbols（阀门符号）/3-D Gate valve（三维闸阀）.svg",
    "fan": "/static/png/IoT-Blowers(鼓风机)/Cool-fan(冷风机).gif",
    "transformer": "/static/png/IoT-power(电源)/Transformer（变压器）.svg",
    "inverter": "/static/png/IoT-power(电源)/AC drive交流传动).svg",
    "turbine": "/static/png/IoT-power(电源)/Industrial wind generators 2（工业风力发电机2）.svg",
}


def _slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "-", value).strip("-").lower() or "item"


def panel_card(
    key: str,
    placement: dict[str, Any],
    panel_id: int,
    element_id: int,
    panel_name: str,
) -> dict[str, Any]:
    return {
        "id": f"panel-{_slug(key)}",
        "name": "lePanelCard",
        "x": float(placement["x"]),
        "y": float(placement["y"]),
        "width": float(placement["w"]),
        "height": float(placement["h"]),
        "panelId": panel_id,
        "elementId": element_id,
        "panelName": panel_name,
    }


class CanvasBuilder:
    """Builds safe, bounded Meta2d pens from a portable Canvas plan."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = config or {}
        self.width = int(self.config.get("width", DEFAULT_WIDTH))
        self.height = int(self.config.get("height", DEFAULT_HEIGHT))
        self.background = str(self.config.get("background", DEFAULT_BACKGROUND))
        self.text_color = str(self.config.get("text_color", DEFAULT_TEXT))

    def chart(self, pens: list[dict[str, Any]]) -> dict[str, Any]:
        self.validate_bounds(pens)
        return {
            "x": 0,
            "y": 0,
            "scale": 1,
            "pens": pens,
            "width": self.width,
            "height": self.height,
            "background": self.background,
            "color": self.text_color,
            "theme": self.config.get("theme", "dark"),
            "grid": bool(self.config.get("grid", False)),
            "lineWidth": int(self.config.get("line_width", 6)),
            "lineCross": True,
            "networkInterval": int(self.config.get("network_interval", 5)),
            "locked": int(self.config.get("locked", 0)),
            "version": "1.1.19",
        }

    def build_scene(self, title: str) -> list[dict[str, Any]]:
        raw = self.config.get("pens")
        if raw:
            return [dict(p) for p in raw]

        panel_top = float(self.config.get("panel_top", 1080))
        process_height = max(300, min(820, panel_top - 260))
        pens = [
            self._rect("canvas-bg", 0, 0, self.width, self.height, self.background, self.background, 0),
            self._rect(
                "process-frame",
                50,
                220,
                self.width - 100,
                process_height,
                "#0f1824",
                "#24415f",
                2,
            ),
            self._label("process-title", 90, 245, self.width - 180, 48, title, 28, "#ffffff", "left", "bold"),
        ]
        equipment = list(self.config.get("equipment") or [])
        if not equipment:
            equipment = self._default_equipment()
        positions: dict[str, dict[str, float]] = {}
        for index, item in enumerate(equipment):
            pen_group, position = self._equipment(item, index, len(equipment))
            pens.extend(pen_group)
            positions[str(item.get("id") or f"equipment-{index + 1}")] = position

        flows = list(self.config.get("flows") or [])
        if not flows and len(equipment) > 1:
            flows = [
                {
                    "from": equipment[i].get("id") or f"equipment-{i + 1}",
                    "to": equipment[i + 1].get("id") or f"equipment-{i + 2}",
                    "kind": "process",
                }
                for i in range(len(equipment) - 1)
            ]
        for index, flow in enumerate(flows):
            source = positions.get(str(flow.get("from")))
            target = positions.get(str(flow.get("to")))
            if source and target:
                pens.append(self._flow(flow, source, target, index))

        pens.extend(dict(p) for p in (self.config.get("annotations") or []))
        return pens

    def panel_placements(
        self,
        panel_keys: list[str],
        grid_layout: list[Any],
    ) -> dict[str, dict[str, float]]:
        explicit = {
            str(p["panel"]): {
                "x": float(p["x"]),
                "y": float(p["y"]),
                "w": float(p["w"]),
                "h": float(p["h"]),
            }
            for p in (self.config.get("panel_placements") or [])
        }
        if explicit:
            return explicit

        placements: dict[str, dict[str, float]] = {}
        panel_top = float(self.config.get("panel_top", 1080))
        panel_height = max(180.0, self.height - panel_top - 60)
        for cell in grid_layout:
            if cell.panel_key not in panel_keys:
                continue
            placements[cell.panel_key] = {
                "x": 50 + (cell.column / 24) * (self.width - 100),
                "y": panel_top + (cell.row / max(1, self._max_grid_row(grid_layout))) * panel_height,
                "w": max(240, (cell.width / 24) * (self.width - 120)),
                "h": max(160, (cell.height / max(6, self._max_grid_row(grid_layout))) * panel_height),
            }
        if placements:
            return placements

        count = max(1, len(panel_keys))
        gap = 24
        width = (self.width - 100 - gap * (count - 1)) / count
        return {
            key: {"x": 50 + i * (width + gap), "y": panel_top, "w": width, "h": panel_height}
            for i, key in enumerate(panel_keys)
        }

    def validate_bounds(self, pens: list[dict[str, Any]]) -> None:
        for pen in pens:
            x = float(pen.get("x") or 0)
            y = float(pen.get("y") or 0)
            w = abs(float(pen.get("width") or 0))
            h = abs(float(pen.get("height") or 0))
            if x < 0 or y < 0 or x + w > self.width + 1 or y + h > self.height + 1:
                raise ValueError(
                    f"Canvas pen '{pen.get('id', pen.get('name'))}' is outside "
                    f"{self.width}x{self.height}: x={x}, y={y}, w={w}, h={h}"
                )

    def _default_equipment(self) -> list[dict[str, Any]]:
        return [
            {"id": "source", "label": "Process Inlet", "type": "tank"},
            {"id": "unit", "label": "Process Unit", "type": "pump"},
            {"id": "control", "label": "Control Valve", "type": "valve"},
            {"id": "outlet", "label": "Process Outlet", "type": "tank"},
        ]

    def _equipment(
        self,
        item: dict[str, Any],
        index: int,
        count: int,
    ) -> tuple[list[dict[str, Any]], dict[str, float]]:
        item_id = str(item.get("id") or f"equipment-{index + 1}")
        w = float(item.get("w", 260))
        h = float(item.get("h", 210))
        auto_gap = (self.width - 220) / max(1, count)
        x = float(item.get("x", 110 + index * auto_gap + (auto_gap - w) / 2))
        y = float(item.get("y", 475))
        label = str(item.get("label") or item_id)
        kind = str(item.get("type") or "equipment").lower()
        image = item.get("image") or EQUIPMENT_IMAGES.get(kind)
        pens = [self._rect(f"{_slug(item_id)}-frame", x, y, w, h, "#132235", "#31506f", 2)]
        if image:
            pens.append(
                {
                    "id": f"{_slug(item_id)}-image",
                    "name": "image",
                    "x": x + w * 0.2,
                    "y": y + 18,
                    "width": w * 0.6,
                    "height": h * 0.58,
                    "image": image,
                    "crossOrigin": "anonymous",
                }
            )
        pens.append(self._label(f"{_slug(item_id)}-label", x + 8, y + h - 55, w - 16, 34, label, 17, "#ffffff", "center", "bold"))
        binding = item.get("binding") or {}
        if binding.get("element_id") and binding.get("attr"):
            pens.append(self._live_value(item_id, x + 20, y + h + 8, w - 40, binding))
        return pens, {"x": x, "y": y, "w": w, "h": h}

    def _flow(
        self,
        flow: dict[str, Any],
        source: dict[str, float],
        target: dict[str, float],
        index: int,
    ) -> dict[str, Any]:
        x1 = source["x"] + source["w"]
        y1 = source["y"] + source["h"] / 2
        x2 = target["x"]
        y2 = target["y"] + target["h"] / 2
        color = str(flow.get("color") or FLOW_COLORS.get(str(flow.get("kind", "process")).lower(), FLOW_COLORS["process"]))
        return {
            "id": str(flow.get("id") or f"flow-{index + 1}"),
            "name": "line",
            "type": 1,
            "lineName": "line",
            "x": x1,
            "y": min(y1, y2),
            "width": x2 - x1,
            "height": abs(y2 - y1),
            "lineWidth": float(flow.get("width", 7)),
            "color": color,
            "anchors": [{"id": "0", "x": 0, "y": 0.5, "start": True}, {"id": "1", "x": 1, "y": 0.5}],
            "lineAnimateType": 1,
            "animateColor": "#ffffff",
            "animateSpan": int(flow.get("span", 2)),
            "keepAnimateState": True,
            "autoPlay": bool(flow.get("animated", True)),
            "animateReverse": bool(flow.get("reverse", False)),
        }

    def _live_value(
        self,
        item_id: str,
        x: float,
        y: float,
        w: float,
        binding: dict[str, Any],
    ) -> dict[str, Any]:
        attr = str(binding["attr"])
        suffix = str(binding.get("suffix") or "")
        return {
            "id": f"{_slug(item_id)}-value",
            "name": "text",
            "x": x,
            "y": y,
            "width": w,
            "height": 44,
            "text": f"--{suffix}",
            "color": str(binding.get("color") or "#38bdf8"),
            "fontSize": float(binding.get("font_size", 24)),
            "fontWeight": "bold",
            "textAlign": "center",
            "disableAnchor": True,
            "form": [
                {
                    "key": "text",
                    "name": "value",
                    "type": "text",
                    "expression": f"${{attributes['{attr}']}}",
                    "dataReferenceType": "Formula",
                    "expressionElementId": int(binding["element_id"]),
                }
            ],
        }

    @staticmethod
    def _max_grid_row(layout: list[Any]) -> int:
        return max((cell.row + cell.height for cell in layout), default=6)

    @staticmethod
    def _rect(
        pen_id: str,
        x: float,
        y: float,
        w: float,
        h: float,
        background: str,
        color: str,
        line_width: float,
    ) -> dict[str, Any]:
        return {
            "id": pen_id,
            "name": "rectangle",
            "x": x,
            "y": y,
            "width": w,
            "height": h,
            "background": background,
            "color": color,
            "lineWidth": line_width,
            "text": "",
            "disableAnchor": True,
        }

    @staticmethod
    def _label(
        pen_id: str,
        x: float,
        y: float,
        w: float,
        h: float,
        text: str,
        size: float,
        color: str,
        align: str,
        weight: str,
    ) -> dict[str, Any]:
        return {
            "id": pen_id,
            "name": "text",
            "x": x,
            "y": y,
            "width": w,
            "height": h,
            "text": text,
            "color": color,
            "fontSize": size,
            "fontWeight": weight,
            "textAlign": align,
            "disableAnchor": True,
        }
