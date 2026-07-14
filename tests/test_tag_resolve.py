from __future__ import annotations

import unittest
from typing import Any

from agentic_pi_migration.tag_resolve import TagResolver


class FakeTreeClient:
    def __init__(self, tree: dict[int, dict[str, Any]]) -> None:
        self.tree = tree

    def get_element(self, element_id: int) -> dict[str, Any]:
        return dict(self.tree[int(element_id)])

    def list_child_elements(self, parent_id: int) -> list[dict[str, Any]]:
        el = self.tree[int(parent_id)]
        return [
            {"id": cid, "name": self.tree[cid]["name"]}
            for cid in el.get("child_ids", [])
        ]


class TagResolveTests(unittest.TestCase):
    def setUp(self) -> None:
        # GTU / 54FC061 / PV / t_pv.val
        self.tree = {
            1: {"id": 1, "name": "GTU", "attributes": [], "hasChildren": True, "child_ids": [10]},
            10: {
                "id": 10,
                "name": "54FC061",
                "attributes": [],
                "hasChildren": True,
                "child_ids": [20],
            },
            20: {
                "id": 20,
                "name": "PV",
                "attributes": [],
                "hasChildren": True,
                "child_ids": [30],
            },
            30: {
                "id": 30,
                "name": "t_54fc061_pv",
                "attributes": [{"name": "val"}],
                "hasChildren": False,
                "child_ids": [],
            },
        }
        self.resolver = TagResolver(FakeTreeClient(self.tree))

    def test_resolve_af_style_pv_path(self) -> None:
        binding = self.resolver.resolve_tag(1, "54FC061.PV")
        assert binding is not None
        self.assertEqual(binding.element_id, 30)
        self.assertEqual(binding.attr, "val")
        self.assertTrue(binding.alias.startswith("series_") or "54FC061" in binding.alias)

    def test_placeholder_falls_back_to_live_leaves(self) -> None:
        bindings = self.resolver.resolve_tags(1, ["quality_index", "throughput_bpd"])
        self.assertEqual(len(bindings), 1)  # only one real leaf available
        self.assertEqual(bindings[0].element_id, 30)
        self.assertEqual(bindings[0].attr, "val")


if __name__ == "__main__":
    unittest.main()
