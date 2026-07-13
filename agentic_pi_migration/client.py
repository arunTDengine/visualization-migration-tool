"""IDMP REST API client for agentic dashboard migration."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from .idmp_compat import (
    API_ROOTS,
    IdmpProfile,
    candidate_urls,
    extract_token,
    looks_like_tsdb,
    normalize_url,
)


class IdmpClient:
    def __init__(
        self,
        base_url: str,
        login_name: str = "",
        password: str = "",
        *,
        api_key: str | None = None,
        auto_discover: bool | None = None,
    ) -> None:
        self.requested_url = base_url
        self.base_url = ""
        self._api_root = ""
        self._headers: dict[str, str] = {"Content-Type": "application/json"}
        self.timeout = float(os.environ.get("IDMP_REQUEST_TIMEOUT", "30"))
        if auto_discover is None:
            auto_discover = os.environ.get("IDMP_AUTO_DISCOVER", "1").lower() in (
                "1",
                "true",
                "yes",
            )
        api_key = api_key or os.environ.get("IDMP_API_KEY")
        self.profile = self._connect(
            login_name,
            password,
            api_key=api_key,
            auto_discover=auto_discover,
        )
        self.api_base_url = self.profile.resolved_url
        self.base_url = os.environ.get("IDMP_PUBLIC_URL", "").rstrip("/") or (
            normalize_url(self.requested_url)
            if os.environ.get("RUNNING_IN_DOCKER", "").lower() in ("1", "true", "yes")
            and normalize_url(self.requested_url).split("://", 1)[-1].startswith(
                ("localhost", "127.0.0.1")
            )
            else self.profile.resolved_url
        )

    def _connect(
        self,
        login_name: str,
        password: str,
        *,
        api_key: str | None,
        auto_discover: bool,
    ) -> IdmpProfile:
        if looks_like_tsdb(self.requested_url):
            raise RuntimeError(
                "This URL appears to use a TDengine TSDB REST port (ending in 41). "
                "The migration tool needs the IDMP web/API port, normally ending in 42."
            )
        errors: list[str] = []
        candidates = candidate_urls(self.requested_url, auto_discover=auto_discover)
        for candidate_index, candidate in enumerate(candidates):
            for api_path in API_ROOTS:
                self.base_url = candidate
                self._api_root = f"{candidate}{api_path}"
                self._headers = {"Content-Type": "application/json"}
                try:
                    if api_key:
                        self._headers["Authorization"] = f"Bearer {api_key}"
                        result = self._request(
                            "GET",
                            "/api/v1/elements/search?keyword=&limit=1",
                        )
                        if not isinstance(result, dict):
                            raise RuntimeError("Element API returned an unexpected response.")
                        auth_mode = "api_key"
                    else:
                        if not login_name or not password:
                            raise RuntimeError("Enter an IDMP email and password, or set IDMP_API_KEY.")
                        data = self._request(
                            "POST",
                            "/api/v1/users/login",
                            {"login_name": login_name, "password": password},
                            auth=False,
                        )
                        token = extract_token(data)
                        if not token:
                            raise RuntimeError("Login response did not contain a supported token field.")
                        self._headers["Authorization"] = f"Bearer {token}"
                        auth_mode = "password"
                    warnings = []
                    if candidate != candidates[0]:
                        warnings.append(
                            f"Requested IDMP was unavailable; connected to discovered local instance {candidate}."
                        )
                    if api_path != "/api/v1":
                        warnings.append(f"Using legacy IDMP API root {api_path}.")
                    return IdmpProfile(
                        requested_url=candidates[0],
                        resolved_url=candidate,
                        api_root=self._api_root,
                        auth_mode=auth_mode,
                        health="connected",
                        warnings=warnings,
                    )
                except RuntimeError as exc:
                    message = str(exc)
                    errors.append(f"{candidate}{api_path}: {message}")
                    if candidate_index == 0 and (
                        "authentication failed" in message.lower()
                        or "enter an idmp email" in message.lower()
                    ):
                        raise
                    continue
        hint = (
            " No compatible IDMP REST API was found. Confirm IDMP—not bare TSDB—is "
            "running and expose its web port (usually xx42). When this tool runs in "
            "Docker, use host.docker.internal:<host-port> or the IDMP Compose service name."
        )
        raise RuntimeError((errors[0] if errors else "Unable to reach IDMP.") + hint)

    def login(self, login_name: str, password: str) -> None:
        """Re-authenticate against the resolved API root."""
        data = self._request(
            "POST",
            "/api/v1/users/login",
            {"login_name": login_name, "password": password},
            auth=False,
        )
        token = extract_token(data)
        if not token:
            raise RuntimeError("IDMP login succeeded but no supported token was returned.")
        self._headers["Authorization"] = f"Bearer {token}"

    def _request(
        self,
        method: str,
        path: str,
        body: Any = None,
        *,
        auth: bool = True,
    ) -> Any:
        relative = path
        if relative.startswith("/api/v1"):
            relative = relative[len("/api/v1") :]
        elif relative.startswith("/api"):
            relative = relative[len("/api") :]
        url = f"{self._api_root}{relative}"
        payload = json.dumps(body).encode() if body is not None else None
        headers = self._headers if auth else {"Content-Type": "application/json"}
        req = urllib.request.Request(url, data=payload, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read()
                if not raw:
                    return {}
                return json.loads(raw)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            if exc.code in (401, 403):
                raise RuntimeError(
                    f"IDMP authentication failed ({exc.code}). Check the account/API key "
                    f"and confirm it belongs to {self.base_url}. {detail}"
                ) from exc
            if exc.code == 404:
                raise RuntimeError(
                    f"IDMP API endpoint is unavailable ({method} {path}). This may be an "
                    f"older IDMP version or the wrong base URL. {detail}"
                ) from exc
            raise RuntimeError(f"IDMP {method} {path} failed ({exc.code}): {detail}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise RuntimeError(f"Cannot reach IDMP at {self.base_url}: {exc}") from exc

    def get_dashboard(self, element_id: int, dashboard_id: int) -> dict[str, Any]:
        return self._request("GET", f"/api/v1/elements/{element_id}/dashboards/{dashboard_id}")

    def update_dashboard(
        self,
        element_id: int,
        dashboard_id: int,
        body: dict[str, Any],
    ) -> None:
        self._request("PUT", f"/api/v1/elements/{element_id}/dashboards/{dashboard_id}", body)

    def delete_dashboard(self, element_id: int, dashboard_id: int) -> None:
        self._request("DELETE", f"/api/v1/elements/{element_id}/dashboards/{dashboard_id}")

    def create_dashboard(self, element_id: int, body: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", f"/api/v1/elements/{element_id}/dashboards", body)

    def create_canvas_dashboard(
        self,
        element_id: int,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        """Create a Canvas dashboard and return its inline-panel ID mapping."""
        payload = {**body, "type": "CANVAS"}
        return self.create_dashboard(element_id, payload)

    def update_canvas_dashboard(
        self,
        element_id: int,
        dashboard_id: int,
        body: dict[str, Any],
    ) -> None:
        """Replace a Canvas document. Callers must send the complete chart."""
        self.update_dashboard(element_id, dashboard_id, {**body, "type": "CANVAS"})

    def create_panel(self, element_id: int, panel: dict[str, Any]) -> int:
        result = self._request("POST", f"/api/v1/elements/{element_id}/panels", panel)
        return int(result["id"])

    def update_panel(self, element_id: int, panel_id: int, panel: dict[str, Any]) -> None:
        self._request("PUT", f"/api/v1/elements/{element_id}/panels/{panel_id}", panel)

    def delete_panel(self, element_id: int, panel_id: int) -> None:
        self._request("DELETE", f"/api/v1/elements/{element_id}/panels/{panel_id}")

    def get_panel(self, element_id: int, panel_id: int) -> dict[str, Any]:
        return self._request("GET", f"/api/v1/elements/{element_id}/panels/{panel_id}")

    def ai_create_panel(self, element_id: int, prompt: str) -> dict[str, Any]:
        return self._request(
            "POST",
            "/api/v1/ai/panels/create",
            {"elementId": element_id, "prompt": prompt, "record": True},
        )

    def query_panel(self, element_id: int, panel: dict[str, Any]) -> Any:
        return self._request("POST", f"/api/v1/elements/{element_id}/panels/query", panel)

    def get_attribute_data(self, element_id: int, attribute_ids: list[int]) -> Any:
        return self._request(
            "POST",
            f"/api/v1/elements/{element_id}/attributes/data",
            attribute_ids,
        )

    def evaluate_expression(self, element_id: int, expression: str) -> Any:
        return self._request(
            "POST",
            f"/api/v1/elements/{element_id}/attributes/evaluate-expression",
            {"expression": expression, "dataReferenceType": "Formula"},
        )

    def search_elements(self, keyword: str, limit: int = 50) -> list[dict[str, Any]]:
        query = urllib.parse.urlencode({"keyword": keyword, "limit": limit})
        result = self._request("GET", f"/api/v1/elements/search?{query}")
        return result.get("rows", [])
