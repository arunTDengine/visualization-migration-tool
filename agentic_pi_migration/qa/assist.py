"""External LLM co-pilot for IDMP's built-in panel AI + series panel polish.

Power mode (default): rich prompts, chart chrome polish, alias upgrades.
Attribute expressions from tags.csv are never invented or rewritten.
"""

from __future__ import annotations

import json
import os
from typing import Any

from agentic_pi_migration.qa.llm import LlmError, chat_judge, llm_config_from_env


ASSIST_SYSTEM = """You are a senior industrial visualization engineer and co-pilot for TDengine IDMP.
You write elite operator-console panel briefs for IDMP's built-in panel AI and polish chart chrome.
Hard rules:
- NEVER invent historian tag or attribute names. Use ONLY tags supplied in the request.
- Prefer live relative time windows (now-8h → now or now-15m → now).
- Modern dark ops aesthetic: clear titles, bottom legend, smooth lines, 2 decimals, readable series names.
- Output MUST be valid JSON only.
"""


def assist_enabled(explicit: bool | None = None) -> bool:
    if explicit is not None:
        return explicit
    flag = os.environ.get("QA_LLM_ASSIST_PANELS", "1").strip().lower()
    if flag in ("0", "false", "no", "off"):
        return False
    return bool(llm_config_from_env().get("api_key"))


def power_mode() -> bool:
    """Spend tokens freely for richer briefs (default on)."""
    flag = os.environ.get("QA_LLM_POWER", "1").strip().lower()
    return flag not in ("0", "false", "no", "off")


def enrich_idmp_panel_prompt(
    *,
    title: str,
    panel_type: str,
    idmp_type: str,
    prompt: str,
    pi_tags: list[str],
    prompt_context: str = "",
    time_from: str = "now-8h",
    time_to: str = "now",
) -> dict[str, Any]:
    """Ask external LLM to craft a strong prompt for IDMP's panel AI."""
    tags = ", ".join(pi_tags) if pi_tags else "(none listed — stay generic but professional)"
    depth = (
        "Write a DETAILED imperative brief (4–8 sentences) covering chart type, exact attributes, "
        "legend labels, axis units if implied, LIVE time window, density, and industrial styling."
        if power_mode()
        else "Write a tight 1–3 sentence imperative prompt."
    )
    user = f"""Design an IDMP panel-AI prompt for this migrated PI Vision panel.

Title: {title}
Requested PI/chart type: {panel_type}
Target IDMP panelType: {idmp_type}
Existing prompt notes: {prompt}
Historian / attribute tags (ONLY these): {tags}
Global design direction: {prompt_context or "(none)"}
Time window: {time_from} → {time_to}

{depth}

Return JSON:
{{
  "idmp_prompt": "full prompt string for IDMP AI — mention ONLY the tags listed above",
  "preferred_type": "{idmp_type}",
  "series_aliases": ["friendly legend labels aligned 1:1 with tags if tags exist"],
  "notes": "one short sentence on design intent",
  "style_hints": {{
    "legend": "bottom",
    "line_style": "smooth",
    "decimals": 2,
    "tooltip_mode": "all"
  }}
}}
"""
    judgment = chat_judge(
        system=ASSIST_SYSTEM,
        user=user,
        screenshot=None,
        temperature=0.35 if power_mode() else 0.1,
        max_tokens=2500 if power_mode() else 1200,
    )
    if not isinstance(judgment, dict) or not judgment.get("idmp_prompt"):
        raise LlmError("External assist returned no idmp_prompt")
    judgment["idmp_prompt"] = str(judgment["idmp_prompt"]).strip()
    judgment["preferred_type"] = str(judgment.get("preferred_type") or idmp_type).strip() or idmp_type
    return judgment


def polish_series_panel(
    *,
    panel: dict[str, Any],
    title: str,
    pi_tags: list[str],
    prompt: str = "",
    prompt_context: str = "",
    time_from: str = "now-8h",
    time_to: str = "now",
) -> dict[str, Any]:
    """Upgrade chart chrome / aliases while locking attribute expressions."""
    ya = panel.get("yaAttributes") or []
    locked = [
        {
            "alias": a.get("alias"),
            "attributeExpression": a.get("attributeExpression"),
            "expression": a.get("expression"),
        }
        for a in ya
    ]
    user = f"""Polish this IDMP series chart for a modern operator console.
You may improve title, legend labels (aliases), and chart style.
You MUST keep every attributeExpression / expression EXACTLY as given — character for character.

Title: {title}
Prompt notes: {prompt}
Global design: {prompt_context or "(none)"}
Time window: {time_from} → {time_to}
Tags (reference only): {', '.join(pi_tags) or '(from expressions)'}
Locked series:
{json.dumps(locked, indent=2)}

Return JSON:
{{
  "title": "improved professional title",
  "aliases": ["one alias per locked series, same length and order"],
  "chart": {{
    "legend": {{"placement": "bottom", "showType": "list", "stats": ["last"], "show": true}},
    "series": {{"lineOpacity": 1, "lineType": "solid", "lineWidth": 1.8, "style": "smooth", "graphMode": "line"}},
    "standardOptions": {{"colorSchema": "classic-palette-by-series", "decimals": 2}},
    "tooltip": {{"hideZeros": true, "mode": "all", "sortOrder": "descending"}}
  }},
  "notes": "short note"
}}
"""
    judgment = chat_judge(
        system=ASSIST_SYSTEM,
        user=user,
        screenshot=None,
        temperature=0.25 if power_mode() else 0.1,
        max_tokens=2000 if power_mode() else 1000,
    )
    if not isinstance(judgment, dict):
        raise LlmError("polish_series_panel returned non-object")

    out = dict(panel)
    new_title = str(judgment.get("title") or title).strip() or title
    out["name"] = new_title
    chart = dict(out.get("chart") or {})
    graph = dict(chart.get("graph") or {})
    graph["title"] = new_title
    chart["graph"] = graph
    style = judgment.get("chart") if isinstance(judgment.get("chart"), dict) else {}
    for key in ("legend", "series", "standardOptions", "tooltip"):
        if isinstance(style.get(key), dict):
            chart[key] = {**(chart.get(key) or {}), **style[key]}
    out["chart"] = chart

    aliases = judgment.get("aliases") or []
    if isinstance(aliases, list) and len(aliases) == len(ya):
        for attr, alias in zip(ya, aliases):
            if alias:
                attr["alias"] = str(alias).strip()[:64]
        out["yaAttributes"] = ya
    return out


def expand_design_direction(prompt_context: str, *, display_name: str = "") -> str:
    """Expand a short human design note into a richer operator-console brief."""
    if not prompt_context.strip() or not assist_enabled():
        return prompt_context
    if not power_mode():
        return prompt_context
    user = f"""Expand this migration design direction into a crisp industrial UX brief
(8–12 bullet-like sentences in one paragraph). Keep intent; add concrete visual rules
(dark slate, LIVE feel, no old SCADA chrome, precise spacing). Display: {display_name or 'n/a'}

Input:
{prompt_context}

Return JSON: {{"expanded": "..."}}
"""
    try:
        result = chat_judge(
            system=ASSIST_SYSTEM,
            user=user,
            temperature=0.4,
            max_tokens=1200,
        )
        expanded = str((result or {}).get("expanded") or "").strip()
        return expanded or prompt_context
    except (LlmError, TypeError, ValueError):
        return prompt_context


def enrich_or_passthrough(
    *,
    base_prompt: str,
    title: str,
    panel_type: str,
    idmp_type: str,
    prompt: str,
    pi_tags: list[str],
    prompt_context: str = "",
    time_from: str = "now-8h",
    time_to: str = "now",
    enabled: bool | None = None,
) -> tuple[str, dict[str, Any] | None]:
    """Return (prompt_for_idmp, assist_meta). Falls back to base_prompt on error/disabled."""
    if not assist_enabled(enabled):
        return base_prompt, None
    try:
        meta = enrich_idmp_panel_prompt(
            title=title,
            panel_type=panel_type,
            idmp_type=idmp_type,
            prompt=prompt,
            pi_tags=pi_tags,
            prompt_context=prompt_context,
            time_from=time_from,
            time_to=time_to,
        )
        return meta["idmp_prompt"], meta
    except (LlmError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        return base_prompt, {"error": str(exc), "fallback": "base_prompt"}
