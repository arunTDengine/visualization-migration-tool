"""Ingest a customer folder: screenshots + tag files → scenario JSON."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
TAG_FILES = ("tags.csv", "tags.json")


def _find_screenshot(folder: Path) -> Path | None:
    for path in sorted(folder.iterdir()):
        if path.is_file() and path.suffix.lower() in IMAGE_EXT:
            return path
    return None


def _load_tags_csv(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            cleaned = {k.strip(): (v.strip() if v else "") for k, v in row.items() if k}
            if cleaned:
                rows.append(cleaned)
    return rows


def _load_tags_json(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data
    return data.get("panels", data.get("tags", []))


def _split_tags(raw: str) -> list[str]:
    if not raw:
        return []
    for sep in ("|", ";", ","):
        if sep in raw:
            return [t.strip() for t in raw.split(sep) if t.strip()]
    return [raw.strip()]


def _parse_tag_row(row: dict[str, Any], default_element_id: int | None) -> dict[str, Any]:
    key = row.get("panel_key") or row.get("key") or row.get("panel") or "panel"
    title = row.get("title") or row.get("panel_title") or row.get("name") or key.replace("_", " ").title()
    chart_type = row.get("type") or row.get("chart_type") or row.get("pi_type") or "trend"

    element_id = row.get("element_id") or row.get("idmp_element_id")
    if not element_id and default_element_id is not None:
        element_id = default_element_id
    if not element_id:
        raise ValueError(f"Row '{title}' missing element_id (set in tags row or display.json)")

    pi_tags = _split_tags(row.get("pi_tags") or row.get("pi_tag") or row.get("tags") or "")
    prompt = row.get("prompt") or row.get("description") or f"{chart_type} chart for {', '.join(pi_tags) or title}"

    return {
        "key": key,
        "title": title,
        "type": chart_type,
        "element_id": int(element_id),
        "prompt": prompt,
        "pi_tags": pi_tags,
    }


def _auto_layout(panels: list[dict[str, Any]], *, has_header: bool = True) -> list[dict[str, Any]]:
    """Simple 24-column grid from panel count and types."""
    layout: list[dict[str, Any]] = []
    row = 0
    if has_header:
        layout.append({"panel": "header", "col": 0, "row": 0, "w": 24, "h": 2})
        row = 2

    keys = [p["key"] for p in panels]
    n = len(keys)
    if n <= 0:
        return layout

    if n <= 3:
        w = 24 // n
        for i, key in enumerate(keys):
            layout.append({"panel": key, "col": i * w, "row": row, "w": w, "h": 5})
        return layout

    if n == 4:
        for i, key in enumerate(keys):
            layout.append({"panel": key, "col": (i % 2) * 12, "row": row + (i // 2) * 6, "w": 12, "h": 6})
        return layout

    # default: 3-column top, rest full width pairs
    top = keys[:3]
    w = 8
    for i, key in enumerate(top):
        layout.append({"panel": key, "col": i * w, "row": row, "w": w, "h": 5})
    row += 5
    rest = keys[3:]
    for i, key in enumerate(rest):
        layout.append({"panel": key, "col": 0 if i % 2 == 0 else 12, "row": row, "w": 12, "h": 6})
        if i % 2 == 1:
            row += 6
    return layout


def _load_display_folder(folder: Path) -> dict[str, Any]:
    meta_path = folder / "display.json"
    meta: dict[str, Any] = {}
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))

    tags_path = None
    for name in TAG_FILES:
        candidate = folder / name
        if candidate.exists():
            tags_path = candidate
            break
    if tags_path is None:
        raise FileNotFoundError(f"No tags.csv or tags.json in {folder}")

    tag_rows = _load_tags_json(tags_path) if tags_path.suffix == ".json" else _load_tags_csv(tags_path)
    default_element = meta.get("element_id")
    panels = [_parse_tag_row(row, default_element) for row in tag_rows]
    requested_type = str(meta.get("dashboard_type") or meta.get("type") or "").lower()
    has_process_panel = any(
        str(panel["type"]).lower().strip() in ("process", "p&id", "pid", "pnid")
        for panel in panels
    )
    dashboard_type = requested_type or ("canvas" if has_process_panel else "grid")

    screenshot = _find_screenshot(folder)
    name = meta.get("name") or folder.name.replace("-", " ").replace("_", " ").title()
    theme = meta.get("theme", "control-room")
    header = meta.get(
        "header_html",
        f"<div style='padding:12px 16px;background:#0f172a;border-left:4px solid #f59e0b;"
        f"border-radius:8px;color:#e2e8f0'><div style='font-size:11px;letter-spacing:2px;"
        f"text-transform:uppercase;color:#94a3b8'>Agentic PI Migration</div>"
        f"<div style='font-size:22px;font-weight:600;margin-top:4px'>{name}</div></div>",
    )

    display: dict[str, Any] = {
        "name": name,
        "description": meta.get("description", f"Agentic migration of PI Vision display '{name}'"),
        "element_id": int(meta.get("element_id") or panels[0]["element_id"]),
        "dashboard_id": int(meta["dashboard_id"]) if meta.get("dashboard_id") else None,
        "dashboard_type": dashboard_type,
        "theme": theme,
        "refresh_seconds": int(meta.get("refresh_seconds", 15)),
        "time_from": meta.get("time_from", "now-15m" if dashboard_type == "canvas" else "now-90d"),
        "time_to": meta.get("time_to", "now"),
        "header_html": header,
        "panels": panels,
        "layout": meta.get("layout") or _auto_layout(panels),
    }
    if dashboard_type == "canvas":
        display["canvas"] = dict(meta.get("canvas") or meta.get("canvas_plan") or {})
    if screenshot:
        display["reference_screenshot"] = str(screenshot.resolve())
    return display


def ingest_folder(folder: Path) -> dict[str, Any]:
    """
    Read a customer submission folder.

    Expected layout (one subfolder per PI Vision display):

        customer-job/
          ops-overview/
            screenshot.png      ← PI Vision screenshot (optional but recommended)
            tags.csv              ← required: panel definitions + PI tags
            display.json          ← optional: name, element_id, theme, layout
          p101-pump/
            screenshot.png
            tags.csv
            display.json

    Or flat (single display):

        single-display/
          screenshot.png
          tags.csv
          display.json
    """
    folder = folder.resolve()
    if not folder.is_dir():
        raise NotADirectoryError(folder)

    displays: list[dict[str, Any]] = []
    subdirs = sorted(p for p in folder.iterdir() if p.is_dir() and not p.name.startswith("."))

    if subdirs:
        for sub in subdirs:
            if any((sub / n).exists() for n in TAG_FILES):
                displays.append(_load_display_folder(sub))
    elif any((folder / n).exists() for n in TAG_FILES):
        displays.append(_load_display_folder(folder))
    else:
        raise FileNotFoundError(
            f"No display subfolders with tags.csv/tags.json found under {folder}"
        )

    return {
        "name": folder.name,
        "description": f"Agentic PI Migration Upgrade intake from {folder.name}",
        "source_folder": str(folder),
        "displays": displays,
    }


def write_scenario(folder: Path, output: Path) -> dict[str, Any]:
    scenario = ingest_folder(folder)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(scenario, indent=2), encoding="utf-8")
    return scenario
