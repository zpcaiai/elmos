from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from enum import Enum
import re

MAX_NODES = 2000
MAX_EDGES = 6000

class DiagramType(Enum):
    ARCHITECTURE = "ARCHITECTURE"
    MODULE_DEPENDENCY = "MODULE_DEPENDENCY"
    CALL_SEQUENCE = "CALL_SEQUENCE"
    DATA_FLOW = "DATA_FLOW"
    PROCESS_FLOW = "PROCESS_FLOW"
    ER_DIAGRAM = "ER_DIAGRAM"
    THREAT_MODEL = "THREAT_MODEL"
    MINDMAP = "MINDMAP"
    DEPLOYMENT = "DEPLOYMENT"
    COMPONENT = "COMPONENT"

@dataclass
class DiagramSpec:
    diagram_type: DiagramType
    title: str
    mermaid_code: str
    nodes: int
    edges: int
    metadata: Dict[str, Any] = field(default_factory=dict)

def sanitize_label(label: str) -> str:
    return re.sub(r'[^a-zA-Z0-9_\- ]', '', label)

class ArchitectureDiagramGenerator:
    def generate(self, data: Dict[str, Any]) -> DiagramSpec:
        nodes = min(len(data.get('components', [])), MAX_NODES)
        edges = min(len(data.get('relationships', [])), MAX_EDGES)
        
        lines = ["C4Context", f"title {sanitize_label(data.get('title', 'System Context'))}"]
        for i, comp in enumerate(data.get('components', [])[:nodes]):
            lines.append(f"Person({sanitize_label(comp['id'])}, \"{sanitize_label(comp['name'])}\")")
        for i, rel in enumerate(data.get('relationships', [])[:edges]):
            lines.append(f"Rel({sanitize_label(rel['source'])}, {sanitize_label(rel['target'])}, \"{sanitize_label(rel['description'])}\")")
            
        return DiagramSpec(DiagramType.ARCHITECTURE, data.get('title', 'Architecture'), "\n".join(lines), nodes, edges)

class ModuleDependencyDiagramGenerator:
    def generate(self, data: Dict[str, Any]) -> DiagramSpec:
        nodes = min(len(data.get('modules', [])), MAX_NODES)
        edges = min(len(data.get('dependencies', [])), MAX_EDGES)
        
        lines = ["graph TD", f"%% Title: {sanitize_label(data.get('title', 'Module Dependencies'))}"]
        for mod in data.get('modules', [])[:nodes]:
            lines.append(f"{sanitize_label(mod['id'])}[\"{sanitize_label(mod['name'])}\"]")
        for dep in data.get('dependencies', [])[:edges]:
            lines.append(f"{sanitize_label(dep['source'])} --> {sanitize_label(dep['target'])}")
            
        return DiagramSpec(DiagramType.MODULE_DEPENDENCY, data.get('title', 'Module Dependency'), "\n".join(lines), nodes, edges)

class CallSequenceDiagramGenerator:
    def generate(self, data: Dict[str, Any]) -> DiagramSpec:
        nodes = min(len(data.get('participants', [])), MAX_NODES)
        edges = min(len(data.get('calls', [])), MAX_EDGES)
        
        lines = ["sequenceDiagram"]
        for p in data.get('participants', [])[:nodes]:
            lines.append(f"participant {sanitize_label(p)}")
        for call in data.get('calls', [])[:edges]:
            lines.append(f"{sanitize_label(call['caller'])}->>{sanitize_label(call['callee'])}: {sanitize_label(call['method'])}")
            
        return DiagramSpec(DiagramType.CALL_SEQUENCE, data.get('title', 'Call Sequence'), "\n".join(lines), nodes, edges)

class DataFlowDiagramGenerator:
    def generate(self, data: Dict[str, Any]) -> DiagramSpec:
        nodes = min(len(data.get('entities', [])), MAX_NODES)
        edges = min(len(data.get('flows', [])), MAX_EDGES)
        
        lines = ["graph TD"]
        for e in data.get('entities', [])[:nodes]:
            lines.append(f"{sanitize_label(e['id'])}[\"{sanitize_label(e['name'])}\"]")
        for flow in data.get('flows', [])[:edges]:
            lines.append(f"{sanitize_label(flow['source'])} --\"{sanitize_label(flow['data'])}\"--> {sanitize_label(flow['target'])}")
            
        return DiagramSpec(DiagramType.DATA_FLOW, data.get('title', 'Data Flow'), "\n".join(lines), nodes, edges)

class ProcessFlowDiagramGenerator:
    """
    Generates Mermaid process flowcharts (数据流程图 / 业务流程图)
    representing processing steps, decisions, inputs/outputs, and data transitions.
    """
    def generate(self, data: Dict[str, Any]) -> DiagramSpec:
        raw_nodes = data.get('steps', data.get('nodes', []))
        raw_edges = data.get('transitions', data.get('flows', []))
        nodes = min(len(raw_nodes), MAX_NODES)
        edges = min(len(raw_edges), MAX_EDGES)

        lines = ["graph TD", f"%% Title: {sanitize_label(data.get('title', 'Process Flow'))}"]

        for step in raw_nodes[:nodes]:
            sid = sanitize_label(step['id'])
            slabel = sanitize_label(step.get('name', step.get('label', sid)))
            stype = step.get('type', 'process').lower()
            if stype in ('start', 'end', 'terminal'):
                lines.append(f"{sid}([\"{slabel}\"])")
            elif stype in ('decision', 'condition'):
                lines.append(f"{sid}{{\"{slabel}\"}}")
            elif stype in ('database', 'storage', 'data'):
                lines.append(f"{sid}[(\"{slabel}\")]")
            elif stype in ('io', 'input', 'output'):
                lines.append(f"{sid}[/\"{slabel}\"/]")
            elif stype in ('subprocess', 'subroutine'):
                lines.append(f"{sid}[[\"{slabel}\"]]")
            else:
                lines.append(f"{sid}[\"{slabel}\"]")

        for trans in raw_edges[:edges]:
            src = sanitize_label(trans['source'])
            tgt = sanitize_label(trans['target'])
            lbl = sanitize_label(trans.get('label', trans.get('condition', '')))
            if lbl:
                lines.append(f"{src} -- \"{lbl}\" --> {tgt}")
            else:
                lines.append(f"{src} --> {tgt}")

        return DiagramSpec(
            DiagramType.PROCESS_FLOW,
            data.get('title', 'Process Flow'),
            "\n".join(lines),
            nodes,
            edges
        )

class ERDiagramGenerator:
    def generate(self, data: Dict[str, Any]) -> DiagramSpec:
        nodes = min(len(data.get('tables', [])), MAX_NODES)
        edges = min(len(data.get('relations', [])), MAX_EDGES)
        
        lines = ["erDiagram"]
        for t in data.get('tables', [])[:nodes]:
            lines.append(f"{sanitize_label(t['name'])} {{")
            for col in t.get('columns', []):
                lines.append(f"  {sanitize_label(col['type'])} {sanitize_label(col['name'])}")
            lines.append("}")
        for r in data.get('relations', [])[:edges]:
            lines.append(f"{sanitize_label(r['source'])} ||--o{{ {sanitize_label(r['target'])} : \"{sanitize_label(r['name'])}\"")
            
        return DiagramSpec(DiagramType.ER_DIAGRAM, data.get('title', 'ER Diagram'), "\n".join(lines), nodes, edges)

class ThreatModelDiagramGenerator:
    def generate(self, data: Dict[str, Any]) -> DiagramSpec:
        nodes = min(len(data.get('elements', [])), MAX_NODES)
        edges = min(len(data.get('threats', [])), MAX_EDGES)
        lines = ["graph TD"]
        for e in data.get('elements', [])[:nodes]:
            lines.append(f"{sanitize_label(e['id'])}[\"{sanitize_label(e['name'])}\"]")
        return DiagramSpec(DiagramType.THREAT_MODEL, data.get('title', 'Threat Model'), "\n".join(lines), nodes, edges)

class MindmapDiagramGenerator:
    def generate(self, data: Dict[str, Any]) -> DiagramSpec:
        nodes = min(len(data.get('nodes', [])), MAX_NODES)
        lines = ["mindmap"]
        for n in data.get('nodes', [])[:nodes]:
            indent = "  " * n.get('level', 1)
            lines.append(f"{indent}{sanitize_label(n['id'])}[\"{sanitize_label(n['name'])}\"]")
        return DiagramSpec(DiagramType.MINDMAP, data.get('title', 'Mindmap'), "\n".join(lines), nodes, 0)

class DeploymentDiagramGenerator:
    def generate(self, data: Dict[str, Any]) -> DiagramSpec:
        nodes = min(len(data.get('nodes', [])), MAX_NODES)
        lines = ["graph TD"]
        for n in data.get('nodes', [])[:nodes]:
            lines.append(f"{sanitize_label(n['id'])}[\"{sanitize_label(n['name'])}\"]")
        return DiagramSpec(DiagramType.DEPLOYMENT, data.get('title', 'Deployment'), "\n".join(lines), nodes, 0)

class ComponentDiagramGenerator:
    def generate(self, data: Dict[str, Any]) -> DiagramSpec:
        nodes = min(len(data.get('components', [])), MAX_NODES)
        edges = min(len(data.get('interactions', [])), MAX_EDGES)
        lines = ["graph TD"]
        for c in data.get('components', [])[:nodes]:
            lines.append(f"{sanitize_label(c['id'])}[\"{sanitize_label(c['name'])}\"]")
        for i in data.get('interactions', [])[:edges]:
            lines.append(f"{sanitize_label(i['source'])} --> {sanitize_label(i['target'])}")
        return DiagramSpec(DiagramType.COMPONENT, data.get('title', 'Component Diagram'), "\n".join(lines), nodes, edges)

class UnifiedDiagramService:
    def __init__(self):
        self.generators = {
            DiagramType.ARCHITECTURE: ArchitectureDiagramGenerator(),
            DiagramType.MODULE_DEPENDENCY: ModuleDependencyDiagramGenerator(),
            DiagramType.CALL_SEQUENCE: CallSequenceDiagramGenerator(),
            DiagramType.DATA_FLOW: DataFlowDiagramGenerator(),
            DiagramType.PROCESS_FLOW: ProcessFlowDiagramGenerator(),
            DiagramType.ER_DIAGRAM: ERDiagramGenerator(),
            DiagramType.THREAT_MODEL: ThreatModelDiagramGenerator(),
            DiagramType.MINDMAP: MindmapDiagramGenerator(),
            DiagramType.DEPLOYMENT: DeploymentDiagramGenerator(),
            DiagramType.COMPONENT: ComponentDiagramGenerator(),
        }

    def generate_diagram(self, type_enum: DiagramType, data: Dict[str, Any]) -> DiagramSpec:
        if type_enum not in self.generators:
            raise ValueError(f"Unsupported diagram type: {type_enum}")
        return self.generators[type_enum].generate(data)
