"""Compatibility helpers for locally deployed TDengine IDMP instances."""

from __future__ import annotations

import json
import os
import socket
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from urllib.parse import urlparse, urlunparse

COMMON_IDMP_PORTS = (6042, 6142, 6242, 6342, 6442, 6542, 6642, 6742, 6842, 6942, 7042, 7142)
API_ROOTS = ("/api/v1", "/api")
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "host.docker.internal"}


@dataclass
class IdmpProfile:
    requested_url: str
    resolved_url: str
    api_root: str
    auth_mode: str
    health: str = "unknown"
    capabilities: dict[str, bool | None] = field(
        default_factory=lambda: {
            "elements": True,
            "dashboards": True,
            "ai_panels": None,
            "canvas": None,
            "panel_query": None,
        }
    )
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def normalize_url(raw: str) -> str:
    value = (raw or "").strip()
    if not value:
        raise ValueError("Enter an IDMP URL.")
    if "://" not in value:
        value = f"http://{value}"
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError(f"Invalid IDMP URL: {raw}")
    path = parsed.path.rstrip("/")
    for suffix in ("/api/v1", "/api"):
        if path.endswith(suffix):
            path = path[: -len(suffix)]
            break
    return urlunparse((parsed.scheme, parsed.netloc, path, "", "", "")).rstrip("/")


def candidate_urls(raw: str, *, auto_discover: bool = True) -> list[str]:
    requested = normalize_url(raw)
    parsed = urlparse(requested)
    candidates = [requested]
    if not auto_discover or parsed.hostname not in LOCAL_HOSTS:
        return candidates
    scheme = parsed.scheme
    host = parsed.hostname or "localhost"
    if os.environ.get("RUNNING_IN_DOCKER", "").lower() in ("1", "true", "yes") and host in {
        "localhost",
        "127.0.0.1",
    }:
        host = "host.docker.internal"
    for port in COMMON_IDMP_PORTS:
        netloc = f"{host}:{port}"
        candidate = urlunparse((scheme, netloc, parsed.path, "", "", "")).rstrip("/")
        if candidate not in candidates:
            candidates.append(candidate)
    return candidates


def extract_token(data: object) -> str | None:
    if not isinstance(data, dict):
        return None
    nested = data.get("data")
    return (
        data.get("token")
        or data.get("accessToken")
        or data.get("access_token")
        or (nested.get("token") if isinstance(nested, dict) else None)
        or (nested.get("accessToken") if isinstance(nested, dict) else None)
    )


def looks_like_tsdb(url: str) -> bool:
    port = urlparse(normalize_url(url)).port
    return port is not None and str(port).endswith("41")


def probe_health(url: str, *, timeout: float = 1.25) -> tuple[bool, str]:
    origin = normalize_url(url)
    for path in ("/q/health", "/"):
        req = urllib.request.Request(f"{origin}{path}", method="GET")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read(1024)
                detail = raw.decode("utf-8", errors="replace").strip()
                if resp.status < 500:
                    return True, detail[:160] or f"HTTP {resp.status}"
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                return True, f"HTTP {exc.code} (authentication required)"
            if exc.code != 404:
                return False, f"HTTP {exc.code}"
        except (urllib.error.URLError, TimeoutError, socket.timeout):
            return False, "unreachable"
    return False, "unreachable"


def discover_local_idmp(*, timeout: float = 0.5) -> list[dict[str, object]]:
    """Find responsive local IDMP web ports without requiring credentials."""
    host = (
        "host.docker.internal"
        if os.environ.get("RUNNING_IN_DOCKER", "").lower() in ("1", "true", "yes")
        else "localhost"
    )
    found: list[dict[str, object]] = []
    for port in COMMON_IDMP_PORTS:
        url = f"http://{host}:{port}"
        ok, detail = probe_health(url, timeout=timeout)
        if ok:
            found.append({"url": url, "port": port, "detail": detail})
    return found


def decode_json(raw: bytes) -> object:
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"raw": raw.decode("utf-8", errors="replace")[:500]}
