from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum, auto

MAX_BEANS = 1000

class DependencyType(Enum):
    CONSTRUCTOR = auto()
    FIELD = auto()
    SETTER = auto()
    FACTORY = auto()

@dataclass(frozen=True)
class BeanNode:
    name: str
    type_name: str
    scope: str

@dataclass(frozen=True)
class BeanEdge:
    source: str
    target: str
    dependency_type: DependencyType

@dataclass(frozen=True)
class BeanGraph:
    nodes: list[BeanNode]
    edges: list[BeanEdge]
    cycles: list[list[str]]
    mermaid_diagram: str

class BeanDependencyGraphExtractor:
    def extract(self, definitions: list[dict]) -> BeanGraph:
        if len(definitions) > MAX_BEANS:
            raise ValueError(f"Too many beans. Max allowed is {MAX_BEANS}")
            
        nodes = []
        edges = []
        
        for idx, d in enumerate(definitions):
            name = d.get("name", f"bean_{idx}")
            nodes.append(BeanNode(
                name=name,
                type_name=d.get("type", "java.lang.Object"),
                scope=d.get("scope", "singleton")
            ))
            for dep in d.get("dependencies", []):
                edges.append(BeanEdge(
                    source=name,
                    target=dep.get("target"),
                    dependency_type=DependencyType.FIELD
                ))
                
        # Basic cycle detection mockup
        cycles = []
        
        mermaid = "graph TD;\n"
        for edge in edges:
            mermaid += f"  {edge.source} --> {edge.target};\n"
            
        return BeanGraph(nodes=nodes, edges=edges, cycles=cycles, mermaid_diagram=mermaid)
