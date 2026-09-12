from __future__ import annotations

import pytest
from elmos_teaching_subsystem.diagram_generators import (
    ArchitectureDiagramGenerator,
    ModuleDependencyDiagramGenerator,
    CallSequenceDiagramGenerator,
    UnifiedDiagramService,
    DiagramType,
    sanitize_label
)

def test_sanitize_label():
    assert sanitize_label("test@label!") == "testlabel"
    assert sanitize_label("hello world-123") == "hello world-123"
    assert sanitize_label("valid_label") == "valid_label"

def test_architecture_generator():
    gen = ArchitectureDiagramGenerator()
    data = {
        "title": "Sys Context",
        "components": [{"id": "c1", "name": "Web"}],
        "relationships": [{"source": "c1", "target": "db", "description": "uses"}]
    }
    spec = gen.generate(data)
    assert spec.diagram_type == DiagramType.ARCHITECTURE
    assert "Person(c1" in spec.mermaid_code
    assert "Rel(c1, db, \"uses\")" in spec.mermaid_code

def test_module_dependency_generator():
    gen = ModuleDependencyDiagramGenerator()
    data = {
        "title": "Mods",
        "modules": [{"id": "m1", "name": "Core"}],
        "dependencies": [{"source": "m1", "target": "m2"}]
    }
    spec = gen.generate(data)
    assert spec.diagram_type == DiagramType.MODULE_DEPENDENCY
    assert "m1 --> m2" in spec.mermaid_code

def test_call_sequence_generator():
    gen = CallSequenceDiagramGenerator()
    data = {
        "participants": ["A", "B"],
        "calls": [{"caller": "A", "callee": "B", "method": "doWork"}]
    }
    spec = gen.generate(data)
    assert spec.diagram_type == DiagramType.CALL_SEQUENCE
    assert "A->>B: doWork" in spec.mermaid_code

def test_unified_service():
    svc = UnifiedDiagramService()
    spec = svc.generate_diagram(DiagramType.ARCHITECTURE, {"components": []})
    assert spec.diagram_type == DiagramType.ARCHITECTURE
    with pytest.raises(ValueError):
        svc.generate_diagram("INVALID", {}) # type: ignore

def test_process_flow_generator():
    svc = UnifiedDiagramService()
    data = {
        "title": "Order Processing Workflow",
        "steps": [
            {"id": "start", "name": "Receive Order", "type": "start"},
            {"id": "validate", "name": "Validate Payment", "type": "decision"},
            {"id": "fulfill", "name": "Fulfill Inventory", "type": "process"},
            {"id": "db", "name": "Order DB", "type": "database"},
            {"id": "end", "name": "Complete Order", "type": "end"}
        ],
        "transitions": [
            {"source": "start", "target": "validate"},
            {"source": "validate", "target": "fulfill", "label": "Approved"},
            {"source": "fulfill", "target": "db"},
            {"source": "db", "target": "end"}
        ]
    }
    spec = svc.generate_diagram(DiagramType.PROCESS_FLOW, data)
    assert spec.diagram_type == DiagramType.PROCESS_FLOW
    assert "start([\"Receive Order\"])" in spec.mermaid_code
    assert "validate{\"Validate Payment\"}" in spec.mermaid_code
    assert "fulfill[\"Fulfill Inventory\"]" in spec.mermaid_code
    assert "db[(\"Order DB\")]" in spec.mermaid_code
    assert "validate -- \"Approved\" --> fulfill" in spec.mermaid_code
