from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from agentic_pi_migration.canvas import CanvasBuilder
from agentic_pi_migration.folder_intake import ingest_folder
from agentic_pi_migration.loader import load_dashboards
from agentic_pi_migration.migrator import AgenticPiMigrator


class FakeClient:
    base_url = "http://idmp.test"

    def __init__(self) -> None:
        self.created: dict[int, dict[str, Any]] = {}
        self.updated_dashboard: dict[str, Any] | None = None

    def create_canvas_dashboard(self, element_id: int, body: dict[str, Any]) -> dict[str, Any]:
        self.create_body = body
        mapping = {}
        for index, item in enumerate(body["newInlinePanels"], start=1):
            panel_id = 1000 + index
            mapping[str(item["tempId"])] = panel_id
            self.created[panel_id] = item["panel"]
        return {"id": 9001, "panelIdMap": mapping}

    def update_canvas_dashboard(
        self,
        element_id: int,
        dashboard_id: int,
        body: dict[str, Any],
    ) -> None:
        self.updated_dashboard = {**body, "type": "CANVAS"}

    def get_panel(self, element_id: int, panel_id: int) -> dict[str, Any]:
        return self.created[panel_id]

    def query_panel(self, element_id: int, panel: dict[str, Any]) -> list[dict[str, Any]]:
        return [{"data": [{"ts": 1, "value": 2}]}]


class CanvasMigrationTests(unittest.TestCase):
    def test_process_scenario_routes_to_canvas(self) -> None:
        scenario = {
            "name": "Pump Train P&ID",
            "element_id": 42,
            "header_html": "<div>Pump Train</div>",
            "panels": [
                {
                    "key": "pressure",
                    "title": "Pressure Trend",
                    "type": "process",
                    "element_id": 42,
                    "pi_tags": ["pressure_bar"],
                }
            ],
            "layout": [{"panel": "pressure", "col": 0, "row": 0, "w": 24, "h": 6}],
            "canvas": {
                "width": 1600,
                "height": 900,
                "panel_top": 600,
                "equipment": [
                    {"id": "feed", "label": "Feed Tank", "type": "tank", "x": 100, "y": 300},
                    {"id": "p101", "label": "P-101", "type": "pump", "x": 650, "y": 300},
                ],
                "flows": [{"from": "feed", "to": "p101", "kind": "water"}],
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "scenario.json"
            path.write_text(json.dumps(scenario), encoding="utf-8")
            spec = load_dashboards(path)[0]

        self.assertEqual(spec.dashboard_type, "canvas")
        client = FakeClient()
        result = AgenticPiMigrator(client).migrate_dashboard(spec)

        self.assertEqual(result["dashboard_type"], "canvas")
        self.assertEqual(result["dashboard_id"], 9001)
        self.assertIn("edit_url", result)
        self.assertEqual(client.create_body["type"], "CANVAS")
        self.assertEqual(client.updated_dashboard["type"], "CANVAS")
        cards = [
            pen
            for pen in client.updated_dashboard["chart"]["pens"]
            if pen.get("name") == "lePanelCard"
        ]
        self.assertEqual(len(cards), 2)

    def test_canvas_rejects_out_of_bounds_pens(self) -> None:
        builder = CanvasBuilder({"width": 800, "height": 600})
        with self.assertRaises(ValueError):
            builder.chart(
                [
                    {
                        "id": "bad",
                        "name": "rectangle",
                        "x": 790,
                        "y": 10,
                        "width": 100,
                        "height": 20,
                    }
                ]
            )

    def test_folder_process_row_selects_canvas(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "tags.csv").write_text(
                "panel_key,title,type,element_id,pi_tags\n"
                "pid,Process P&ID,process,42,pressure_bar|flow_tph\n",
                encoding="utf-8",
            )
            scenario = ingest_folder(folder)
        display = scenario["displays"][0]
        self.assertEqual(display["dashboard_type"], "canvas")
        self.assertEqual(display["time_from"], "now-15m")
        self.assertIn("canvas", display)


if __name__ == "__main__":
    unittest.main()
