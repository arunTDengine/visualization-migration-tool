from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from agentic_pi_migration.client import IdmpClient
from agentic_pi_migration.idmp_compat import (
    candidate_urls,
    extract_token,
    looks_like_tsdb,
    normalize_url,
)


class FakeResponse:
    def __init__(self, body: object, status: int = 200) -> None:
        self.body = json.dumps(body).encode()
        self.status = status

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self, *_: object) -> bytes:
        return self.body


class IdmpCompatibilityTests(unittest.TestCase):
    def test_normalizes_api_urls(self) -> None:
        self.assertEqual(
            normalize_url("localhost:6842/api/v1/"),
            "http://localhost:6842",
        )
        self.assertEqual(
            normalize_url("https://idmp.example.test/prefix/api"),
            "https://idmp.example.test/prefix",
        )

    def test_detects_tsdb_port(self) -> None:
        self.assertTrue(looks_like_tsdb("http://localhost:6041"))
        self.assertFalse(looks_like_tsdb("http://localhost:6042"))

    def test_extracts_common_token_shapes(self) -> None:
        self.assertEqual(extract_token({"token": "a"}), "a")
        self.assertEqual(extract_token({"access_token": "b"}), "b")
        self.assertEqual(extract_token({"data": {"accessToken": "c"}}), "c")

    def test_candidate_urls_preserve_requested_first(self) -> None:
        rows = candidate_urls("http://localhost:6842", auto_discover=True)
        self.assertEqual(rows[0], "http://localhost:6842")
        self.assertIn("http://localhost:6042", rows)

    @patch("urllib.request.urlopen")
    def test_client_connects_and_encodes_search(self, urlopen: object) -> None:
        calls: list[str] = []

        def respond(request: object, timeout: float) -> FakeResponse:
            calls.append(request.full_url)
            if request.full_url.endswith("/users/login"):
                return FakeResponse({"accessToken": "token-value"})
            return FakeResponse({"rows": [{"id": 1, "name": "A"}]})

        urlopen.side_effect = respond
        client = IdmpClient(
            "http://localhost:9999/api/v1",
            "user@example.com",
            "secret",
            auto_discover=False,
        )
        rows = client.search_elements("Wind Farm", limit=2)
        self.assertEqual(rows[0]["name"], "A")
        self.assertTrue(any("keyword=Wind+Farm" in call for call in calls))
        self.assertEqual(client.profile.api_root, "http://localhost:9999/api/v1")


if __name__ == "__main__":
    unittest.main()
