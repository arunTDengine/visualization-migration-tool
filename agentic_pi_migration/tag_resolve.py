"""Resolve PI-style tag paths onto IDMP child-element attribute bindings.

AF-style imports (e.g. GTU) often store measurements as:
  Host / 54FC061 / PV / t_54fc061_pv.attributes['val']

Customer tags.csv uses `54FC061.PV`; walkthrough placeholders like
`quality_index` do not exist on the host and must fall back to real leaves.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass
class SeriesBinding:
    """Maps one PI tag / series onto an IDMP element attribute."""

    element_id: int
    attr: str
    alias: str


_MEASUREMENT_ALIASES = {"pv", "mv", "sv", "sp", "out", "value", "val"}


class ElementClient(Protocol):
    def get_element(self, element_id: int) -> dict[str, Any]: ...

    def list_child_elements(self, parent_id: int) -> list[dict[str, Any]]: ...


class TagResolver:
    def __init__(self, client: ElementClient) -> None:
        self.client = client
        self._children: dict[int, list[dict[str, Any]]] = {}
        self._elements: dict[int, dict[str, Any]] = {}
        self._leaves_under: dict[int, list[SeriesBinding]] = {}

    def resolve_tags(
        self,
        root_element_id: int,
        tags: list[str],
        *,
        fallback_samples: bool = True,
    ) -> list[SeriesBinding]:
        bindings: list[SeriesBinding] = []
        used: set[tuple[int, str]] = set()
        unresolved = 0
        for tag in tags:
            binding = self.resolve_tag(root_element_id, tag)
            if binding is None:
                unresolved += 1
                continue
            key = (binding.element_id, binding.attr.lower())
            if key in used:
                continue
            used.add(key)
            bindings.append(binding)

        if bindings and not unresolved:
            return bindings

        if fallback_samples:
            needed = max(len(tags), 1) if not bindings else len(tags)
            for sample in self.sample_bindings(root_element_id, count=needed + len(used)):
                key = (sample.element_id, sample.attr.lower())
                if key in used:
                    continue
                used.add(key)
                alias = tags[len(bindings)] if len(bindings) < len(tags) else sample.alias
                bindings.append(
                    SeriesBinding(
                        element_id=sample.element_id,
                        attr=sample.attr,
                        alias=self._safe_alias(alias or sample.alias),
                    )
                )
                if len(bindings) >= needed:
                    break
        return bindings

    def resolve_tag(self, root_element_id: int, tag: str) -> SeriesBinding | None:
        raw = (tag or "").strip()
        if not raw:
            return None
        parts = [p for p in raw.replace("\\", "/").replace("/", ".").split(".") if p]
        if not parts:
            return None

        node = int(root_element_id)
        consumed = 0
        for i, part in enumerate(parts):
            child = self._find_child(node, part)
            if child is None:
                break
            node = int(child["id"])
            consumed = i + 1

        remainder = parts[consumed:]
        leaves = self._leaves_under_element(node)
        if not leaves:
            return None

        if remainder:
            want = remainder[-1].lower()
            for leaf in leaves:
                if leaf.attr.lower() == want:
                    return SeriesBinding(leaf.element_id, leaf.attr, alias=self._safe_alias(raw))
            if want in _MEASUREMENT_ALIASES:
                for leaf in leaves:
                    if leaf.attr.lower() == "val":
                        return SeriesBinding(leaf.element_id, leaf.attr, alias=self._safe_alias(raw))
            if consumed:
                leaf = leaves[0]
                return SeriesBinding(leaf.element_id, leaf.attr, alias=self._safe_alias(raw))
            return None

        leaf = leaves[0]
        return SeriesBinding(leaf.element_id, leaf.attr, alias=self._safe_alias(raw))

    def sample_bindings(self, root_element_id: int, *, count: int = 4) -> list[SeriesBinding]:
        leaves = self._leaves_under_element(int(root_element_id))
        out: list[SeriesBinding] = []
        seen: set[tuple[int, str]] = set()
        for leaf in leaves:
            key = (leaf.element_id, leaf.attr.lower())
            if key in seen:
                continue
            seen.add(key)
            out.append(leaf)
            if len(out) >= count:
                break
        return out

    def _find_child(self, parent_id: int, name: str) -> dict[str, Any] | None:
        want = name.strip().lower()
        for child in self._children_of(parent_id):
            if str(child.get("name") or "").strip().lower() == want:
                return child
        return None

    def _children_of(self, parent_id: int) -> list[dict[str, Any]]:
        if parent_id not in self._children:
            try:
                self._children[parent_id] = list(self.client.list_child_elements(parent_id) or [])
            except Exception:
                self._children[parent_id] = []
        return self._children[parent_id]

    def _element(self, element_id: int) -> dict[str, Any]:
        if element_id not in self._elements:
            try:
                self._elements[element_id] = dict(self.client.get_element(element_id) or {})
            except Exception:
                self._elements[element_id] = {}
        return self._elements[element_id]

    def _leaves_under_element(self, element_id: int) -> list[SeriesBinding]:
        if element_id in self._leaves_under:
            return self._leaves_under[element_id]

        found: list[SeriesBinding] = []
        seen: set[int] = set()
        queue = [element_id]
        while queue and len(seen) < 400:
            eid = queue.pop(0)
            if eid in seen:
                continue
            seen.add(eid)
            el = self._element(eid)
            for attr in el.get("attributes") or []:
                name = attr.get("name") or attr.get("attributeName")
                if not name:
                    continue
                alias = str(el.get("name") or name)
                found.append(
                    SeriesBinding(
                        element_id=eid,
                        attr=str(name),
                        alias=self._safe_alias(alias),
                    )
                )
            if el.get("hasChildren") or self._children_of(eid):
                for child in self._children_of(eid):
                    cid = child.get("id")
                    if cid is not None:
                        queue.append(int(cid))

        self._leaves_under[element_id] = found
        return found

    @staticmethod
    def _safe_alias(alias: str) -> str:
        import re

        cleaned = re.sub(r"[^A-Za-z0-9_]+", "_", alias).strip("_")
        if not cleaned:
            return "series"
        if cleaned[0].isdigit():
            return f"series_{cleaned}"
        return cleaned
