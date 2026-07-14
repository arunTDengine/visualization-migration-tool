"""External LLM client — OpenAI-compatible + Anthropic Messages."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any


class LlmError(RuntimeError):
    pass


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def llm_config_from_env() -> dict[str, Any]:
    provider = (_env("QA_LLM_PROVIDER") or "openai").lower()
    return {
        "provider": provider,
        "api_key": _env("QA_LLM_API_KEY") or _env("OPENAI_API_KEY") or _env("ANTHROPIC_API_KEY"),
        "base_url": _env("QA_LLM_BASE_URL")
        or ("https://api.anthropic.com" if provider == "anthropic" else "https://api.openai.com/v1"),
        "model": _env("QA_LLM_MODEL")
        or ("claude-sonnet-4-5" if provider == "anthropic" else "gpt-4.1"),
        "timeout": int(_env("QA_LLM_TIMEOUT", "180") or "180"),
    }


def _post_json(url: str, headers: dict[str, str], body: dict[str, Any], timeout: int) -> dict[str, Any]:
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={**headers, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:800]
        raise LlmError(f"LLM HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise LlmError(f"LLM request failed: {exc}") from exc


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:].strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start : end + 1])
        raise LlmError(f"LLM did not return JSON: {text[:400]}")


def chat_judge(
    *,
    system: str,
    user: str,
    screenshot: dict[str, str] | None = None,
    config: dict[str, Any] | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> dict[str, Any]:
    cfg = config or llm_config_from_env()
    if not cfg.get("api_key"):
        raise LlmError(
            "Set QA_LLM_API_KEY (or OPENAI_API_KEY / ANTHROPIC_API_KEY) to enable the external LLM judge."
        )
    provider = cfg["provider"]
    if provider == "anthropic":
        return _anthropic_judge(
            system=system,
            user=user,
            screenshot=screenshot,
            cfg=cfg,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    return _openai_judge(
        system=system,
        user=user,
        screenshot=screenshot,
        cfg=cfg,
        temperature=temperature,
        max_tokens=max_tokens,
    )


def _openai_judge(
    *,
    system: str,
    user: str,
    screenshot: dict[str, str] | None,
    cfg: dict[str, Any],
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> dict[str, Any]:
    content: list[dict[str, Any]] = [{"type": "text", "text": user}]
    if screenshot and screenshot.get("base64") and screenshot.get("mime"):
        content.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:{screenshot['mime']};base64,{screenshot['base64']}",
                },
            }
        )
    body: dict[str, Any] = {
        "model": cfg["model"],
        "temperature": 0.35 if temperature is None else temperature,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": content},
        ],
    }
    if max_tokens:
        body["max_tokens"] = max_tokens
    base = cfg["base_url"].rstrip("/")
    url = base if base.endswith("/chat/completions") else f"{base}/chat/completions"
    raw = _post_json(
        url,
        {"Authorization": f"Bearer {cfg['api_key']}"},
        body,
        int(cfg["timeout"]),
    )
    text = raw["choices"][0]["message"]["content"]
    return _extract_json(text)


def _anthropic_judge(
    *,
    system: str,
    user: str,
    screenshot: dict[str, str] | None,
    cfg: dict[str, Any],
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> dict[str, Any]:
    content: list[dict[str, Any]] = [{"type": "text", "text": user}]
    if screenshot and screenshot.get("base64") and screenshot.get("mime"):
        media = screenshot["mime"].split("/")[-1]
        if media == "jpg":
            media = "jpeg"
        content.append(
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": screenshot["mime"] if "/" in screenshot["mime"] else f"image/{media}",
                    "data": screenshot["base64"],
                },
            }
        )
    body = {
        "model": cfg["model"],
        "max_tokens": max_tokens or 4000,
        "temperature": 0.35 if temperature is None else temperature,
        "system": system,
        "messages": [{"role": "user", "content": content}],
    }
    base = cfg["base_url"].rstrip("/")
    url = f"{base}/v1/messages" if not base.endswith("/messages") else base
    raw = _post_json(
        url,
        {
            "x-api-key": cfg["api_key"],
            "anthropic-version": "2023-06-01",
        },
        body,
        int(cfg["timeout"]),
    )
    parts = [b.get("text", "") for b in raw.get("content") or [] if b.get("type") == "text"]
    return _extract_json("\n".join(parts))
