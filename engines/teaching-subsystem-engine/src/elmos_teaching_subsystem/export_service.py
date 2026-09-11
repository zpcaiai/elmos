from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from enum import Enum
from .diagram_generators import DiagramSpec

class ExportFormat(Enum):
    MERMAID = "MERMAID"
    SVG = "SVG"
    HTML = "HTML"
    PPTX = "PPTX"
    PDF = "PDF"
    PNG = "PNG"
    JSON = "JSON"

@dataclass
class ExportOptions:
    format: ExportFormat
    theme: str = "default"
    include_metadata: bool = True
    max_width: int = 1920
    max_height: int = 1080

class DiagramExporter:
    def export_mermaid(self, spec: DiagramSpec) -> str:
        return spec.mermaid_code

    def export_svg(self, spec: DiagramSpec) -> str:
        return f"<svg><desc>{spec.title}</desc></svg>"

    def export_html(self, spec: DiagramSpec) -> str:
        return f"<html><body><div class='mermaid'>{spec.mermaid_code}</div></body></html>"

    def export_pptx(self, spec: DiagramSpec, template: Optional[str] = None) -> bytes:
        return b"PPTX_DATA"

    def export_json(self, spec: DiagramSpec) -> str:
        import json
        return json.dumps({
            "type": spec.diagram_type.value,
            "title": spec.title,
            "nodes": spec.nodes,
            "edges": spec.edges
        })

class ReportExporter:
    def export_project_report(self, analysis: Any, diagrams: List[DiagramSpec], format: ExportFormat) -> str:
        return f"Report with {len(diagrams)} diagrams"

    def export_tour_report(self, tour: Any, format: ExportFormat) -> str:
        return f"Tour Report for {tour.title}"
