from __future__ import annotations

from elmos_teaching_subsystem.export_service import (
    DiagramExporter, ReportExporter, ExportFormat, ExportOptions
)
from elmos_teaching_subsystem.diagram_generators import DiagramSpec, DiagramType

def test_diagram_exporter():
    exp = DiagramExporter()
    spec = DiagramSpec(DiagramType.ARCHITECTURE, "T", "code", 1, 1)
    
    assert exp.export_mermaid(spec) == "code"
    assert "<svg>" in exp.export_svg(spec)
    assert "<html>" in exp.export_html(spec)
    assert exp.export_pptx(spec) == b"PPTX_DATA"
    assert "ARCHITECTURE" in exp.export_json(spec)

def test_report_exporter():
    exp = ReportExporter()
    assert "1" in exp.export_project_report({}, [DiagramSpec(DiagramType.ARCHITECTURE, "T", "code", 1, 1)], ExportFormat.HTML)
    class DummyTour:
        title = "T"
    assert "T" in exp.export_tour_report(DummyTour(), ExportFormat.HTML)
