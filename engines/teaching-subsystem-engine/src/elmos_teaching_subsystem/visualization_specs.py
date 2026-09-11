"""Visualization specification generators."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

@dataclass(frozen=True)
class VisualizationSpec:
    type: str
    title: str
    data: dict[str, Any]
    options: dict[str, Any]
    width: int
    height: int

class D3SpecGenerator:
    def generate_force_graph(self, nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> dict[str, Any]:
        return {"nodes": nodes, "links": edges}

    def generate_treemap(self, hierarchy: dict[str, Any]) -> dict[str, Any]:
        return {"name": hierarchy.get("name", "root"), "children": hierarchy.get("children", [])}

    def generate_sunburst(self, hierarchy: dict[str, Any]) -> dict[str, Any]:
        return {"name": hierarchy.get("name", "root"), "children": hierarchy.get("children", [])}

    def generate_timeline(self, events: list[dict[str, Any]]) -> dict[str, Any]:
        return {"events": events}

    def generate_heatmap(self, matrix: list[list[float]], x_labels: list[str], y_labels: list[str]) -> dict[str, Any]:
        return {"z": matrix, "x": x_labels, "y": y_labels}

    def generate_sankey(self, flows: list[dict[str, Any]]) -> dict[str, Any]:
        return {"flows": flows}
