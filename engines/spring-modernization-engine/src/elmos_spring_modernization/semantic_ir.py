from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Dict

@dataclass
class BeanDefinition:
    name: str
    class_name: str
    scope: str
    qualifiers: List[str]
    dependencies: List[str]
    init_method: str = ""
    destroy_method: str = ""

@dataclass
class SpringBeanGraph:
    beans: List[BeanDefinition]
    dependencies: Dict[str, List[str]]
    scopes: Dict[str, str]

@dataclass
class SecurityFilterChain:
    filters: List[str]
    matchers: List[str]
    authorization_rules: List[str]

@dataclass
class TransactionBoundary:
    method: str
    propagation: str
    isolation: str
    read_only: bool
    timeout: int

@dataclass
class SpringSemanticIR:
    bean_graph: SpringBeanGraph
    security_chains: List[SecurityFilterChain]
    transaction_boundaries: List[TransactionBoundary]
    endpoints: List[str]
    scheduled_tasks: List[str]

class SpringSemanticExtractor:
    def extract_bean_graph(self, project_root: str) -> SpringBeanGraph:
        return SpringBeanGraph([], {}, {})

    def extract_security_config(self, project_root: str) -> List[SecurityFilterChain]:
        return []

    def extract_transaction_boundaries(self, project_root: str) -> List[TransactionBoundary]:
        return []

    def extract_endpoints(self, project_root: str) -> List[str]:
        return []

    def extract_full_ir(self, project_root: str) -> SpringSemanticIR:
        return SpringSemanticIR(
            self.extract_bean_graph(project_root),
            self.extract_security_config(project_root),
            self.extract_transaction_boundaries(project_root),
            self.extract_endpoints(project_root),
            []
        )
