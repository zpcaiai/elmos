"""Compatibility Test Matrix Engine (Batch 43 - Skill 1452).

Full-version matrix evaluation across language runtimes, frameworks,
databases, and cloud deployment targets. Enforces LTS readiness and breaking change gating.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from elmos_mature_platform.types import (
    CompatibilityCell,
    CompatibilityTestMatrixReport,
    MatrixCellStatus,
)


class CompatibilityTestMatrixEngine:
    """Industrial engine for full-version compatibility test matrix (B43)."""

    def __init__(self, target_profile: str = "enterprise-modernization-lts"):
        self.target_profile = target_profile
        # Cells: cell_id -> CompatibilityCell
        self._cells: Dict[str, CompatibilityCell] = {}
        # Incompatibility rules: (component_pattern_A, component_pattern_B, reason)
        self._known_incompatibilities: List[Tuple[str, str, str]] = [
            ("spring-boot@3.*", "java@8", "Spring Boot 3 requires Java 17 minimum"),
            ("spring-boot@3.*", "java@11", "Spring Boot 3 requires Java 17 minimum"),
            ("django@5.*", "python@3.8", "Django 5 requires Python 3.10 minimum"),
            ("django@5.*", "python@3.9", "Django 5 requires Python 3.10 minimum"),
            ("airgap-onprem", "aws-dynamodb", "Airgap on-prem cannot reach AWS DynamoDB"),
            ("airgap-onprem", "azure-cosmos", "Airgap on-prem cannot reach Azure Cosmos"),
        ]
        self._lts_critical_combinations: Set[str] = {
            "java@17|spring-boot@3.2|postgresql@16",
            "java@21|spring-boot@3.2|postgresql@16",
            "python@3.11|fastapi@0.109|postgresql@16",
        }
        self._audit_log: List[Dict[str, Any]] = []

    def register_cell(self, cell: CompatibilityCell) -> CompatibilityCell:
        """Register or update a compatibility matrix cell."""
        if not cell.evaluated_at:
            cell.evaluated_at = datetime.now(timezone.utc).isoformat()
        
        # Check static incompatibility rules
        for pat_a, pat_b, reason in self._known_incompatibilities:
            all_str = f"{cell.language_runtime}|{cell.framework}|{cell.database}|{cell.cloud_profile}"
            if self._matches_pattern(pat_a, all_str) and self._matches_pattern(pat_b, all_str):
                cell.status = MatrixCellStatus.INCOMPATIBLE
                if reason not in cell.broken_features:
                    cell.broken_features.append(reason)

        self._cells[cell.cell_id] = cell
        self._record_audit("cell_registered", cell.cell_id, {"status": cell.status.value})
        return cell

    def update_cell_test_result(
        self,
        cell_id: str,
        test_run_id: str,
        passed: bool,
        latency_p95_ms: float = 0.0,
        broken_features: Optional[List[str]] = None,
    ) -> bool:
        """Update a cell with dynamic test execution results."""
        cell = self._cells.get(cell_id)
        if not cell:
            return False

        cell.test_run_id = test_run_id
        cell.latency_p95_ms = latency_p95_ms
        cell.evaluated_at = datetime.now(timezone.utc).isoformat()

        if passed:
            if latency_p95_ms > 1000.0:
                cell.status = MatrixCellStatus.DEGRADED
                cell.broken_features = ["High latency overhead (>1000ms)"]
            else:
                cell.status = MatrixCellStatus.COMPATIBLE
                cell.broken_features = []
        else:
            cell.status = MatrixCellStatus.INCOMPATIBLE
            cell.broken_features = broken_features or ["Automated compatibility test suite failed"]

        self._record_audit("cell_test_updated", cell_id, {
            "passed": passed,
            "status": cell.status.value,
            "latency": latency_p95_ms,
        })
        return True

    def get_cell(self, cell_id: str) -> Optional[CompatibilityCell]:
        """Fetch cell by ID."""
        return self._cells.get(cell_id)

    def list_cells(self, status: Optional[MatrixCellStatus] = None) -> List[CompatibilityCell]:
        """List matrix cells, optionally filtered by status."""
        if status:
            return [c for c in self._cells.values() if c.status == status]
        return list(self._cells.values())

    def evaluate_matrix_report(self) -> CompatibilityTestMatrixReport:
        """Analyze current matrix, determine LTS readiness and produce report."""
        total = len(self._cells)
        comp_count = 0
        incomp_count = 0
        degraded_count = 0
        untested_count = 0
        breaking_pairs: List[str] = []

        lts_satisfied = True

        for cell in self._cells.values():
            if cell.status == MatrixCellStatus.COMPATIBLE:
                comp_count += 1
            elif cell.status == MatrixCellStatus.INCOMPATIBLE:
                incomp_count += 1
                breaking_pairs.append(f"{cell.language_runtime} + {cell.framework} + {cell.database}: {', '.join(cell.broken_features)}")
            elif cell.status == MatrixCellStatus.DEGRADED:
                degraded_count += 1
            elif cell.status == MatrixCellStatus.UNTESTED:
                untested_count += 1

            # Check if this cell is a critical LTS combination
            sig = f"{cell.language_runtime}|{cell.framework}|{cell.database}"
            if sig in self._lts_critical_combinations and cell.status != MatrixCellStatus.COMPATIBLE:
                lts_satisfied = False

        pct = (comp_count / total * 100.0) if total > 0 else 100.0

        report_id = f"matrix-rep-{int(datetime.now(timezone.utc).timestamp())}"
        report = CompatibilityTestMatrixReport(
            report_id=report_id,
            target_profile=self.target_profile,
            total_cells=total,
            compatible_cells_count=comp_count,
            incompatible_cells_count=incomp_count,
            degraded_cells_count=degraded_count,
            untested_cells_count=untested_count,
            compatibility_score_pct=round(pct, 2),
            breaking_pairwise_combinations=breaking_pairs,
            lts_ready=lts_satisfied and incomp_count == 0,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )

        self._record_audit("matrix_evaluated", report_id, {
            "total": total,
            "compatible": comp_count,
            "lts_ready": report.lts_ready,
        })
        return report

    @staticmethod
    def _matches_pattern(pattern: str, text: str) -> bool:
        """Simple wildcard matching (e.g. spring-boot@3.*)."""
        regex = "^" + re.escape(pattern).replace(r"\*", ".*") + "$"
        return any(bool(re.match(regex, part)) for part in text.split("|"))

    def _record_audit(self, action: str, entity_id: str, details: Dict[str, Any]) -> None:
        self._audit_log.append({
            "action": action,
            "entity_id": entity_id,
            "details": details,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    def get_audit_log(self) -> List[Dict[str, Any]]:
        return list(self._audit_log)
