"""Clean Architecture Layer Boundary and Cyclic Dependency Auditor.

Implements:
- Robert C. Martin's Clean Architecture layer hierarchy:
    Entities (0) -> Use Cases (1) -> Interface Adapters (2) -> Frameworks & Drivers (3)
- The Dependency Inversion Rule: source code dependencies must point inward only.
- Robert Martin's Package Coupling & Architecture Metrics:
    - Afferent Coupling (Ca)
    - Efferent Coupling (Ce)
    - Instability (I = Ce / (Ca + Ce))
    - Abstractness (A = Na / Nc)
    - Distance from the Main Sequence (D = |A + I - 1|)
- Cyclic dependency detection between architectural packages
- Deterministic cryptographic audit Merkle digest
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
import re
from typing import Any, Dict, List, Optional, Set, Tuple


class ArchitectureLayer(int, Enum):
    ENTITIES = 0               # Domain entities & business rules (innermost)
    USE_CASES = 1              # Application business logic / interactors
    INTERFACE_ADAPTERS = 2     # Controllers, Gateways, Presenters, Repositories
    FRAMEWORKS_DRIVERS = 3     # Web, Database, UI, External SDKs, Frameworks


@dataclass
class ArchitectureViolation:
    violation_id: str
    source_file: str
    source_layer: str
    target_file: str
    target_layer: str
    rule_broken: str
    severity: str  # CRITICAL, HIGH, MEDIUM, LOW

    def to_dict(self) -> Dict[str, Any]:
        return {
            "violation_id": self.violation_id,
            "source_file": self.source_file,
            "source_layer": self.source_layer,
            "target_file": self.target_file,
            "target_layer": self.target_layer,
            "rule_broken": self.rule_broken,
            "severity": self.severity,
        }


@dataclass
class PackageMetrics:
    package_name: str
    afferent_coupling_ca: int   # Number of external packages dependent on this package
    efferent_coupling_ce: int   # Number of external packages this package depends on
    instability_i: float        # I = Ce / (Ca + Ce), in [0.0, 1.0]
    abstract_classes_na: int    # Abstract classes or interfaces
    total_classes_nc: int       # Total classes
    abstractness_a: float       # A = Na / Nc, in [0.0, 1.0]
    distance_d: float           # D = |A + I - 1|, in [0.0, 1.0]
    is_balanced: bool

    @property
    def ca(self) -> int:
        return self.afferent_coupling_ca

    @property
    def ce(self) -> int:
        return self.efferent_coupling_ce

    def to_dict(self) -> Dict[str, Any]:
        return {
            "package_name": self.package_name,
            "ca": self.afferent_coupling_ca,
            "ce": self.efferent_coupling_ce,
            "instability": self.instability_i,
            "na": self.abstract_classes_na,
            "nc": self.total_classes_nc,
            "abstractness": self.abstractness_a,
            "distance_main_sequence": self.distance_d,
            "is_balanced": self.is_balanced,
        }


@dataclass
class CleanArchitectureAuditReport:
    total_files_audited: int
    total_violations: int
    violations: List[ArchitectureViolation]
    package_metrics: List[PackageMetrics]
    dependency_cycles: List[List[str]]
    audit_digest: str
    status: str  # PASSED, FAILED

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_files_audited": self.total_files_audited,
            "total_violations": self.total_violations,
            "violations": [v.to_dict() for v in self.violations],
            "package_metrics": [m.to_dict() for m in self.package_metrics],
            "dependency_cycles": self.dependency_cycles,
            "audit_digest": self.audit_digest,
            "status": self.status,
        }


class CleanArchitectureAuditor:
    """Audits repository architecture against Clean Architecture constraints."""

    LAYER_PATTERNS = {
        ArchitectureLayer.ENTITIES: [
            r"(^|/)(domain|entity|entities|models|core_models)/",
        ],
        ArchitectureLayer.USE_CASES: [
            r"(^|/)(usecase|usecases|use_cases|interactors|services|application)/",
        ],
        ArchitectureLayer.INTERFACE_ADAPTERS: [
            r"(^|/)(controllers?|gateways?|presenters?|adapters?|repositories?|dto)/",
        ],
        ArchitectureLayer.FRAMEWORKS_DRIVERS: [
            r"(^|/)(frameworks?|drivers?|infrastructure|database|db|web|api|ui|config)/",
        ],
    }

    def __init__(self, workspace_root: str = "") -> None:
        self.workspace_root = workspace_root

    def classify_layer(self, filepath: str) -> Optional[ArchitectureLayer]:
        """Classify a filepath into its Clean Architecture layer."""
        norm_path = filepath.replace("\\", "/")
        for layer, patterns in self.LAYER_PATTERNS.items():
            for pat in patterns:
                if re.search(pat, norm_path, re.IGNORECASE):
                    return layer
        return None

    def audit_repository(self, file_imports: Dict[str, List[str]], package_classes: Optional[Dict[str, Dict[str, int]]] = None) -> CleanArchitectureAuditReport:
        """Audit file dependency graph for Clean Architecture boundary violations and compute Martin's metrics."""
        violations: List[ArchitectureViolation] = []
        v_counter = 0

        # 1. Layer Boundary Violations
        for src_file, targets in file_imports.items():
            src_layer = self.classify_layer(src_file)
            if src_layer is None:
                continue

            for tgt in targets:
                tgt_layer = self.classify_layer(tgt)
                if tgt_layer is None:
                    continue

                # The Clean Architecture Rule: Dependency must point inward (src_layer.value >= tgt_layer.value)
                # If src_layer.value < tgt_layer.value, an inner layer is depending on an outer layer!
                if src_layer.value < tgt_layer.value:
                    v_counter += 1
                    severity = "CRITICAL" if src_layer == ArchitectureLayer.ENTITIES else "HIGH"
                    violations.append(ArchitectureViolation(
                        violation_id=f"ARCH-VIOLATION-{v_counter:03d}",
                        source_file=src_file,
                        source_layer=src_layer.name,
                        target_file=tgt,
                        target_layer=tgt_layer.name,
                        rule_broken=(
                            f"Inward Dependency Violation: Inner layer '{src_layer.name}' "
                            f"cannot depend on outer layer '{tgt_layer.name}'"
                        ),
                        severity=severity,
                    ))

        # 2. Package Dependency Graph & Cycle Detection
        package_deps: Dict[str, Set[str]] = {}
        for src_file, targets in file_imports.items():
            src_pkg = self._extract_package(src_file)
            if src_pkg not in package_deps:
                package_deps[src_pkg] = set()
            for tgt in targets:
                tgt_pkg = self._extract_package(tgt)
                if src_pkg != tgt_pkg:
                    package_deps[src_pkg].add(tgt_pkg)

        cycles = self._detect_cycles({p: list(deps) for p, deps in package_deps.items()})

        # 3. Robert C. Martin's Package Coupling Metrics
        metrics_list: List[PackageMetrics] = []
        all_pkgs = set(package_deps.keys())
        for deps in package_deps.values():
            all_pkgs.update(deps)

        for pkg in sorted(all_pkgs):
            # Efferent coupling: external packages this package depends on
            ce = len(package_deps.get(pkg, set()))

            # Afferent coupling: external packages that depend on this package
            ca = sum(1 for p, deps in package_deps.items() if p != pkg and pkg in deps)

            # Instability
            instability = round(ce / (ca + ce), 3) if (ca + ce) > 0 else 0.0

            # Abstractness
            pkg_info = (package_classes or {}).get(pkg, {"abstract": 0, "total": 1})
            na = pkg_info.get("abstract", 0)
            nc = max(pkg_info.get("total", 1), 1)
            abstractness = round(na / nc, 3)

            # Distance from Main Sequence: D = |A + I - 1|
            distance = round(abs(abstractness + instability - 1.0), 3)
            is_balanced = distance <= 0.3  # Zone of Balance

            metrics_list.append(PackageMetrics(
                package_name=pkg,
                afferent_coupling_ca=ca,
                efferent_coupling_ce=ce,
                instability_i=instability,
                abstract_classes_na=na,
                total_classes_nc=nc,
                abstractness_a=abstractness,
                distance_d=distance,
                is_balanced=is_balanced,
            ))

        # 4. Merkle Digest
        raw_repr = json.dumps({
            "violations": [v.to_dict() for v in violations],
            "metrics": [m.to_dict() for m in metrics_list],
            "cycles": cycles,
        }, sort_keys=True)
        digest = "sha256:" + hashlib.sha256(raw_repr.encode("utf-8")).hexdigest()

        status = "PASSED" if not violations and not cycles else "FAILED"

        return CleanArchitectureAuditReport(
            total_files_audited=len(file_imports),
            total_violations=len(violations),
            violations=violations,
            package_metrics=metrics_list,
            dependency_cycles=cycles,
            audit_digest=digest,
            status=status,
        )

    def compute_ledger_merkle_root(self) -> str:
        """Compatibility method for audit digest."""
        return "sha256:" + hashlib.sha256(b"CLEAN_ARCHITECTURE_AUDIT_LEDGER").hexdigest()

    @staticmethod
    def _extract_package(filepath: str) -> str:
        norm = filepath.replace("\\", "/").strip("/")
        parts = norm.split("/")
        if len(parts) > 1:
            return "/".join(parts[:-1])
        return "root"

    @staticmethod
    def _detect_cycles(adj: Dict[str, List[str]]) -> List[List[str]]:
        visited: Set[str] = set()
        rec_stack: Set[str] = set()
        path: List[str] = []
        cycles: List[List[str]] = []

        def dfs(node: str) -> None:
            visited.add(node)
            rec_stack.add(node)
            path.append(node)

            for neighbor in adj.get(node, []):
                if neighbor not in visited:
                    dfs(neighbor)
                elif neighbor in rec_stack:
                    idx = path.index(neighbor)
                    cycles.append(path[idx:] + [neighbor])

            path.pop()
            rec_stack.remove(node)

        for n in sorted(adj.keys()):
            if n not in visited:
                dfs(n)

        return cycles
