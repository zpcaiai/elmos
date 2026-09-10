"""Industrial Architecture Drift & Layer Dependency Conformance Detector.

Analyzes repository structure and imports against architectural rules:
- Clean Architecture / Hexagonal / 3-Tier Layer conformance
- Detection of prohibited cross-layer dependencies (e.g. Domain depending on Infrastructure)
- Package-level cycle detection (circular imports)
- Layer bypass detection (skipping intermediary architectural layers)
- Instability and coupling metrics (Afferent Ca, Efferent Ce, Instability I = Ce / (Ca + Ce))
- Cryptographic drift audit fingerprinting and remediation suggestions
"""

from __future__ import annotations

import ast
from collections import defaultdict
from dataclasses import dataclass
import hashlib
import json
from pathlib import PurePosixPath
import re
from typing import Dict, List, Mapping, Optional, Sequence, Set, Tuple


@dataclass(frozen=True, slots=True)
class ArchitecturalLayer:
    name: str
    order: int
    allowed_dependencies: Tuple[str, ...]
    path_patterns: Tuple[str, ...]


DEFAULT_CLEAN_LAYERS: Tuple[ArchitecturalLayer, ...] = (
    ArchitecturalLayer(
        name="domain",
        order=1,
        allowed_dependencies=(),
        path_patterns=("domain", "entities", "models", "core"),
    ),
    ArchitecturalLayer(
        name="application",
        order=2,
        allowed_dependencies=("domain",),
        path_patterns=("application", "services", "use_cases", "usecases"),
    ),
    ArchitecturalLayer(
        name="infrastructure",
        order=3,
        allowed_dependencies=("domain", "application"),
        path_patterns=("infrastructure", "adapters", "persistence", "db", "repositories"),
    ),
    ArchitecturalLayer(
        name="presentation",
        order=4,
        allowed_dependencies=("application", "domain"),
        path_patterns=("presentation", "api", "controllers", "views", "web", "cli"),
    ),
)


@dataclass(frozen=True, slots=True)
class ArchitectureViolation:
    violation_type: str
    severity: str
    source_file: str
    target_file_or_module: str
    source_layer: str
    target_layer: str
    line_number: int
    remediation: str


@dataclass(frozen=True, slots=True)
class ArchitectureDriftReport:
    total_files_analyzed: int
    total_dependencies: int
    total_violations: int
    conformance_score: float
    violations: Tuple[ArchitectureViolation, ...]
    circular_packages: Tuple[Tuple[str, ...], ...]
    instability_metrics: Mapping[str, float]
    audit_digest: str


class ArchitectureDriftDetector:
    """Enforces architectural boundaries and detects structural entropy."""

    def __init__(self, layers: Optional[Sequence[ArchitecturalLayer]] = None) -> None:
        self.layers = tuple(layers or DEFAULT_CLEAN_LAYERS)
        self.layer_by_name = {layer.name: layer for layer in self.layers}

    def determine_layer(self, file_path: str) -> Optional[str]:
        p = PurePosixPath(file_path)
        parts = [part.lower() for part in p.parts]
        for layer in sorted(self.layers, key=lambda layer: layer.order):
            for pat in layer.path_patterns:
                if pat in parts:
                    return layer.name
        return None

    def extract_imports_python(self, file_path: str, source_code: str) -> List[Tuple[int, str]]:
        imports: List[Tuple[int, str]] = []
        try:
            tree = ast.parse(source_code, filename=file_path)
        except SyntaxError:
            return imports

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append((node.lineno, alias.name))
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.append((node.lineno, node.module))
        return imports

    def extract_imports_js_ts(self, file_path: str, source_code: str) -> List[Tuple[int, str]]:
        imports: List[Tuple[int, str]] = []
        pat = re.compile(r"""(?:import\s+.*?from\s+['"]([^'"]+)['"]|require\s*\(\s*['"]([^'"]+)['"]\s*\))""")
        for idx, line in enumerate(source_code.splitlines(), 1):
            m = pat.search(line)
            if m:
                target = m.group(1) or m.group(2)
                imports.append((idx, target))
        return imports

    def analyze_repository(self, files: Mapping[str, str]) -> ArchitectureDriftReport:
        file_layers: Dict[str, str] = {}
        for path in files:
            layer = self.determine_layer(path)
            if layer:
                file_layers[path] = layer

        dep_graph: Dict[str, Set[str]] = defaultdict(set)
        rev_dep_graph: Dict[str, Set[str]] = defaultdict(set)
        violations: List[ArchitectureViolation] = []
        total_dependencies = 0

        for path, code in files.items():
            src_layer = file_layers.get(path)
            raw_imports: List[Tuple[int, str]] = []
            if path.endswith(".py"):
                raw_imports = self.extract_imports_python(path, code)
            elif path.endswith((".ts", ".tsx", ".js", ".jsx")):
                raw_imports = self.extract_imports_js_ts(path, code)

            for line_no, target_mod in raw_imports:
                total_dependencies += 1
                # Resolve target file or layer if internal
                target_layer = None
                for target_path, t_layer in file_layers.items():
                    mod_path_variant = target_mod.replace(".", "/")
                    if mod_path_variant in target_path or target_mod in target_path:
                        target_layer = t_layer
                        dep_graph[path].add(target_path)
                        rev_dep_graph[target_path].add(path)
                        break

                if target_layer is None:
                    # Check if target module string contains layer patterns directly
                    target_layer = self.determine_layer(target_mod.replace(".", "/"))

                if src_layer and target_layer and src_layer != target_layer:
                    layer_def = self.layer_by_name.get(src_layer)
                    if layer_def and target_layer not in layer_def.allowed_dependencies:
                        v_type = "LAYER_INVERSION" if self.layer_by_name[target_layer].order > layer_def.order else "LAYER_BYPASS"
                        sev = "CRITICAL" if v_type == "LAYER_INVERSION" else "HIGH"
                        remediation = (
                            f"Invert dependency: {src_layer} cannot depend on {target_layer}. "
                            f"Introduce an interface in {src_layer} or move shared logic to domain."
                        )
                        violations.append(
                            ArchitectureViolation(
                                violation_type=v_type,
                                severity=sev,
                                source_file=path,
                                target_file_or_module=target_mod,
                                source_layer=src_layer,
                                target_layer=target_layer,
                                line_number=line_no,
                                remediation=remediation,
                            )
                        )

        # Detect package cycles
        circular_packages: List[Tuple[str, ...]] = []

        def find_cycle(node: str, path: List[str]) -> None:
            if node in path:
                cycle_idx = path.index(node)
                cycle = tuple(path[cycle_idx:])
                if len(cycle) > 1 and cycle not in circular_packages:
                    circular_packages.append(cycle)
                return
            for neighbor in dep_graph.get(node, ()):
                find_cycle(neighbor, path + [node])

        for n in list(dep_graph.keys()):
            find_cycle(n, [])

        # Calculate Instability metrics I = Ce / (Ca + Ce)
        instability: Dict[str, float] = {}
        all_nodes = set(dep_graph.keys()).union(rev_dep_graph.keys())
        for n in all_nodes:
            ce = len(dep_graph.get(n, set()))
            ca = len(rev_dep_graph.get(n, set()))
            instability[n] = round(ce / (ca + ce), 4) if (ca + ce) > 0 else 0.0

        conformance = 1.0 - (len(violations) / max(1, total_dependencies))
        conformance = max(0.0, min(1.0, round(conformance, 4)))

        raw_audit = {
            "violations": [
                f"{v.violation_type}:{v.source_file}:{v.target_file_or_module}:{v.line_number}"
                for v in violations
            ],
            "circular_packages": [list(c) for c in circular_packages],
            "conformance_score": conformance,
        }
        audit_digest = "sha256:" + hashlib.sha256(json.dumps(raw_audit, sort_keys=True).encode("utf-8")).hexdigest()

        return ArchitectureDriftReport(
            total_files_analyzed=len(files),
            total_dependencies=total_dependencies,
            total_violations=len(violations),
            conformance_score=conformance,
            violations=tuple(violations),
            circular_packages=tuple(circular_packages),
            instability_metrics=instability,
            audit_digest=audit_digest,
        )


__all__ = [
    "ArchitecturalLayer",
    "ArchitectureDriftDetector",
    "ArchitectureDriftReport",
    "ArchitectureViolation",
    "DEFAULT_CLEAN_LAYERS",
]
